/**
 * @file main.cpp
 * @brief Firmware ESP32 Esclavo para Actuación Mecatrónica Neumática (MOPPI v1.5.0)
 * 
 * Gestiona:
 * 1. Control de 4 canales de electroválvulas mediante pulsos no bloqueantes con millis().
 * 2. Monitoreo continuo de presión en la galería del manifold mediante presostato digital.
 * 3. Protocolo de comunicación serial bidireccional delimitado por '\n' a 115200 baudios.
 *    - Comandos recibidos: "ACT:<canal>", "STOP", "PING"
 *    - Respuestas emitidas: "OK:<canal>", "OK:STOP", "PONG", "ERR:PRESSURE_FAULT_CH_<canal>"
 */

#include <Arduino.h>

// =====================================================================
// 1. CONFIGURACIÓN DE PINES Y CONSTANTES
// =====================================================================

static const uint8_t NUM_CANALES = 4;
static const unsigned long TIEMPO_PULSO_DEFAULT_MS = 20;

// Mapeo de pines GPIO a 3.3V para las 4 electroválvulas neumáticas
static const uint8_t PINES_VALVULAS[NUM_CANALES] = {
    25,  // Canal 0
    26,  // Canal 1
    27,  // Canal 2
    14   // Canal 3
};

// Pin del presostato digital en la galería del manifold
// Configurado con INPUT_PULLUP: LOW = Presión adecuada en galería, HIGH = Falla o descompresión
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
void leerSerialNoBloqueante();
void actualizarTemporizadores();

// =====================================================================
// 4. SETUP Y LOOP
// =====================================================================

void setup() {
    // Inicializar puerto serial con velocidad estándar 115200
    Serial.begin(115200);
    while (!Serial && millis() < 1000) {
        // Breve espera para estabilización en arranque
    }

    // Configurar pines de electroválvulas como salidas en estado inactivo (LOW)
    for (uint8_t i = 0; i < NUM_CANALES; i++) {
        canales[i].pin = PINES_VALVULAS[i];
        canales[i].activo = false;
        canales[i].tiempoActivacion = 0;
        canales[i].pendienteVerificacionPresion = false;

        pinMode(canales[i].pin, OUTPUT);
        digitalWrite(canales[i].pin, LOW);
    }

    // Configurar presostato con pull-up interna
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

/**
 * Lee bytes del puerto serie sin detener la ejecución de loop().
 * Detecta saltos de línea ('\n' o '\r') para despachar el comando completo.
 */
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
                // Desbordamiento de buffer: resetear por seguridad
                indiceBuffer = 0;
            }
        }
    }
}

/**
 * Procesa comandos delimitados según el protocolo de MOPPI.
 */
void procesarComando(const char* comando) {
    // Comando PING -> PONG (Validación de latencia y enlace activo)
    if (strcmp(comando, "PING") == 0) {
        Serial.println("PONG");
        return;
    }

    // Comando STOP -> Desactiva todas las válvulas inmediatamente
    if (strcmp(comando, "STOP") == 0) {
        desactivarTodosLosCanales();
        Serial.println("OK:STOP");
        return;
    }

    // Comando ACT:<canal> -> Activa el canal especificado
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

/**
 * Activa la electroválvula del canal correspondiente de forma no bloqueante
 * y programa la verificación de la galería con el presostato.
 */
void dispararCanal(uint8_t canal) {
    canales[canal].activo = true;
    canales[canal].tiempoActivacion = millis();
    canales[canal].pendienteVerificacionPresion = true;

    // Encender electroválvula
    digitalWrite(canales[canal].pin, HIGH);
}

/**
 * Desactiva inmediatamente todos los canales de electroválvulas.
 */
void desactivarTodosLosCanales() {
    for (uint8_t i = 0; i < NUM_CANALES; i++) {
        digitalWrite(canales[i].pin, LOW);
        canales[i].activo = false;
        canales[i].pendienteVerificacionPresion = false;
    }
}

/**
 * Supervisa el tiempo de activación de cada electroválvula y apaga
 * el pin automáticamente tras TIEMPO_PULSO_DEFAULT_MS.
 * Verifica además la respuesta de presión del presostato digital.
 */
void actualizarTemporizadores() {
    unsigned long ahora = millis();

    for (uint8_t i = 0; i < NUM_CANALES; i++) {
        if (canales[i].activo) {
            // Verificar si transcurrió la duración del pulso
            if (ahora - canales[i].tiempoActivacion >= TIEMPO_PULSO_DEFAULT_MS) {
                // Apagar electroválvula
                digitalWrite(canales[i].pin, LOW);
                canales[i].activo = false;

                // Comprobación de presostato al concluir el pulso de eyección
                if (canales[i].pendienteVerificacionPresion) {
                    canales[i].pendienteVerificacionPresion = false;

                    // Lectura del presostato:
                    // Si el pin está en HIGH (circuito abierto por falta de presión de línea
                    // o falla de presurización en la galería del manifold):
                    int estadoPresostato = digitalRead(PIN_PRESOSTATO);

                    // Nota: En condiciones normales de operación con aire presurizado,
                    // el presostato cerrado a masa da LOW. Si está en HIGH o no hay presión:
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