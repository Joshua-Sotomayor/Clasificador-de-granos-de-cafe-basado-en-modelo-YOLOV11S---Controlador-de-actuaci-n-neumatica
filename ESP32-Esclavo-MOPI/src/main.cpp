/**
 * @file main.cpp
 * @brief Firmware ESP32 Esclavo para Actuación Mecatrónica Neumática (MOPPI v1.7.0)
 * 
 * Gestiona:
 * 1. Control de 4 canales de electroválvulas con extensión y rearmado de pulso continuo (millis()).
 * 2. Control de tracción de banda transportadora (BANDA:ON, BANDA:OFF en GPIO 22).
 * 3. Señalización óptica con luces piloto industriales (24V): ROJA (18), VERDE (17), BLANCA (16), AMARILLA (4).
 * 4. Lectura analógica de transductores de presión en manifold (GPIOs 34, 35, 32, 33) y presostato digital (GPIO 19).
 * 5. Protocolo serial bidireccional delimitado por '\n' a 115200 baudios.
 */

#include <Arduino.h>

// =====================================================================
// 1. CONFIGURACIÓN DE PINES Y CONSTANTES (MAPEO CONSOLIDADO)
// =====================================================================

static const uint8_t NUM_CANALES = 4;
static const unsigned long TIEMPO_PULSO_DEFAULT_MS = 20;

// Mapeo de pines GPIO para las 4 electroválvulas neumáticas
static const uint8_t PINES_VALVULAS[NUM_CANALES] = {
    25,  // Canal 0
    26,  // Canal 1
    27,  // Canal 2
    14   // Canal 3
};

// Habilitación de tracción de banda transportadora
static const uint8_t PIN_CONTROL_BANDA = 22;

// Luces piloto de estado industrial (24V vía transistores / drivers)
static const uint8_t PIN_LUZ_ROJA     = 18;
static const uint8_t PIN_LUZ_VERDE    = 17;
static const uint8_t PIN_LUZ_BLANCA   = 16;
static const uint8_t PIN_LUZ_AMARILLA = 4;

// Entradas analógicas de presión en galería/manifold (0..4095)
static const uint8_t PINES_PRESION[NUM_CANALES] = {
    34,  // Canal 0
    35,  // Canal 1
    32,  // Canal 2
    33   // Canal 3
};

// Pin del presostato digital en la galería del manifold
// INPUT_PULLUP: LOW = Presión adecuada en galería, HIGH = Falla o descompresión
static const uint8_t PIN_PRESOSTATO = 19;

// =====================================================================
// 2. ESTRUCTURA DE ESTADO DE CANALES
// =====================================================================

struct CanalValvula {
    uint8_t pin;
    bool activo;
    unsigned long tiempoActivacion;
    bool pendienteVerificacionPresion;
};

static CanalValvula canales[NUM_CANALES];

// Buffer para recepción serial no bloqueante
static const size_t BUFFER_SERIAL_LEN = 64;
static char bufferSerial[BUFFER_SERIAL_LEN];
static size_t indiceBuffer = 0;

// =====================================================================
// 3. DECLARACIÓN DE FUNCIONES AUXILIARES
// =====================================================================

void procesarComando(const char* comando);
void desactivarTodosLosCanales();
void dispararCanal(uint8_t canal);
void conmutarPiloto(const char* color);
void leerSerialNoBloqueante();
void actualizarTemporizadores();

// =====================================================================
// 4. SETUP Y LOOP
// =====================================================================

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 1000) {
        // Breve espera para estabilización en arranque
    }

    // Configurar pines de electroválvulas como salidas en LOW
    for (uint8_t i = 0; i < NUM_CANALES; i++) {
        canales[i].pin = PINES_VALVULAS[i];
        canales[i].activo = false;
        canales[i].tiempoActivacion = 0;
        canales[i].pendienteVerificacionPresion = false;

        pinMode(canales[i].pin, OUTPUT);
        digitalWrite(canales[i].pin, LOW);
    }

    // Configurar tracción de banda transportadora
    pinMode(PIN_CONTROL_BANDA, OUTPUT);
    digitalWrite(PIN_CONTROL_BANDA, LOW);

    // Configurar luces piloto de señalización (por defecto standby: BLANCO encendido)
    pinMode(PIN_LUZ_ROJA, OUTPUT);
    digitalWrite(PIN_LUZ_ROJA, LOW);

    pinMode(PIN_LUZ_VERDE, OUTPUT);
    digitalWrite(PIN_LUZ_VERDE, LOW);

    pinMode(PIN_LUZ_BLANCA, OUTPUT);
    digitalWrite(PIN_LUZ_BLANCA, HIGH);

    pinMode(PIN_LUZ_AMARILLA, OUTPUT);
    digitalWrite(PIN_LUZ_AMARILLA, LOW);

    // Configurar entradas de presión analógica
    for (uint8_t i = 0; i < NUM_CANALES; i++) {
        pinMode(PINES_PRESION[i], INPUT);
    }

    // Configurar presostato digital con pull-up interna
    pinMode(PIN_PRESOSTATO, INPUT_PULLUP);

    Serial.println("MOPPI:ESP32_READY");
}

void loop() {
    // 1. Lectura y ensamblado no bloqueante de tramas seriales
    leerSerialNoBloqueante();

    // 2. Control de apagado automático de pulsos de 20ms y chequeo de presostato
    actualizarTemporizadores();
}

// =====================================================================
// 5. IMPLEMENTACIÓN DE FUNCIONES
// =====================================================================

void leerSerialNoBloqueante() {
    while (Serial.available() > 0) {
        char c = (char)Serial.read();

        if (c == '\n' || c == '\r') {
            if (indiceBuffer > 0) {
                bufferSerial[indiceBuffer] = '\0';
                procesarComando(bufferSerial);
                indiceBuffer = 0;
            }
        } else {
            if (indiceBuffer < BUFFER_SERIAL_LEN - 1) {
                bufferSerial[indiceBuffer++] = c;
            } else {
                indiceBuffer = 0;
            }
        }
    }
}

void procesarComando(const char* comando) {
    // Comando PING -> PONG
    if (strcmp(comando, "PING") == 0) {
        Serial.println("PONG");
        return;
    }

    // Comando STOP -> Desactiva todas las válvulas inmediatamente
    if (strcmp(comando, "STOP") == 0) {
        desactivarTodosLosCanales();
        digitalWrite(PIN_CONTROL_BANDA, LOW);
        Serial.println("OK:STOP");
        return;
    }

    // Tracción de banda transportadora
    if (strcmp(comando, "BANDA:ON") == 0) {
        digitalWrite(PIN_CONTROL_BANDA, HIGH);
        Serial.println("OK:BANDA_ON");
        return;
    }
    if (strcmp(comando, "BANDA:OFF") == 0) {
        digitalWrite(PIN_CONTROL_BANDA, LOW);
        Serial.println("OK:BANDA_OFF");
        return;
    }

    // Señalización de luces piloto: PILOT:<COLOR>
    if (strncmp(comando, "PILOT:", 6) == 0) {
        conmutarPiloto(comando + 6);
        return;
    }

    // Comando ACT:<canal> -> Activa o reengancha el pulso del canal especificado
    if (strncmp(comando, "ACT:", 4) == 0) {
        int canal = atoi(comando + 4);
        if (canal >= 0 && canal < NUM_CANALES) {
            dispararCanal((uint8_t)canal);
        } else {
            Serial.print("ERR:INVALID_CHANNEL_");
            Serial.println(canal);
        }
        return;
    }

    // Comando desconocido
    Serial.print("ERR:UNKNOWN_CMD_");
    Serial.println(comando);
}

void conmutarPiloto(const char* color) {
    if (strcmp(color, "RED") == 0) {
        digitalWrite(PIN_LUZ_ROJA, HIGH);
        digitalWrite(PIN_LUZ_VERDE, LOW);
        digitalWrite(PIN_LUZ_BLANCA, LOW);
        digitalWrite(PIN_LUZ_AMARILLA, LOW);
        Serial.println("OK:PILOT:RED");
    } else if (strcmp(color, "GREEN") == 0) {
        digitalWrite(PIN_LUZ_ROJA, LOW);
        digitalWrite(PIN_LUZ_VERDE, HIGH);
        digitalWrite(PIN_LUZ_BLANCA, LOW);
        digitalWrite(PIN_LUZ_AMARILLA, LOW);
        Serial.println("OK:PILOT:GREEN");
    } else if (strcmp(color, "WHITE") == 0) {
        digitalWrite(PIN_LUZ_ROJA, LOW);
        digitalWrite(PIN_LUZ_VERDE, LOW);
        digitalWrite(PIN_LUZ_BLANCA, HIGH);
        digitalWrite(PIN_LUZ_AMARILLA, LOW);
        Serial.println("OK:PILOT:WHITE");
    } else if (strcmp(color, "YELLOW") == 0) {
        digitalWrite(PIN_LUZ_ROJA, LOW);
        digitalWrite(PIN_LUZ_VERDE, LOW);
        digitalWrite(PIN_LUZ_BLANCA, LOW);
        digitalWrite(PIN_LUZ_AMARILLA, HIGH);
        Serial.println("OK:PILOT:YELLOW");
    } else {
        Serial.print("ERR:UNKNOWN_PILOT_COLOR_");
        Serial.println(color);
    }
}

/**
 * Extensión y Rearmado de Pulso Continuo:
 * Si el canal ya se encuentra activo (canales[canal].activo == true), refresca
 * tiempoActivacion = millis() sin apagar el pin físico, logrando una descarga
 * de aire ininterrumpida ante defectos sucesivos cercanos.
 */
void dispararCanal(uint8_t canal) {
    if (canales[canal].activo) {
        canales[canal].tiempoActivacion = millis();
        return;
    }

    canales[canal].activo = true;
    canales[canal].tiempoActivacion = millis();
    canales[canal].pendienteVerificacionPresion = true;

    // Encender electroválvula física
    digitalWrite(canales[canal].pin, HIGH);
}

void desactivarTodosLosCanales() {
    for (uint8_t i = 0; i < NUM_CANALES; i++) {
        digitalWrite(canales[i].pin, LOW);
        canales[i].activo = false;
        canales[i].pendienteVerificacionPresion = false;
    }
}

void actualizarTemporizadores() {
    unsigned long ahora = millis();

    for (uint8_t i = 0; i < NUM_CANALES; i++) {
        if (canales[i].activo) {
            if (ahora - canales[i].tiempoActivacion >= TIEMPO_PULSO_DEFAULT_MS) {
                // Apagar electroválvula tras expirar tiempo acumulado del pulso
                digitalWrite(canales[i].pin, LOW);
                canales[i].activo = false;

                if (canales[i].pendienteVerificacionPresion) {
                    canales[i].pendienteVerificacionPresion = false;
                    int estadoPresostato = digitalRead(PIN_PRESOSTATO);

                    if (estadoPresostato == HIGH) {
                        Serial.print("ERR:PRESSURE_FAULT_CH_");
                        Serial.println(i);
                    } else {
                        Serial.print("OK:");
                        Serial.println(i);
                    }
                }
            }
        }
    }
}