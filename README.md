# Sistema Clasificador Optico de Cafe Oro MOPPI

## Descripcion del Sistema
El proyecto MOPPI (Finca Alvizua) consiste en una solucion mecatronica de clasificacion en tiempo real para cafe verde basada en vision artificial en el borde (Edge AI). El sistema integra un pipeline de inferencia optimizado bajo YOLO11s (acelerador neural Hailo-8L sobre Raspberry Pi 5) acoplado a una etapa esclava basada en microcontrolador ESP32 para el gobierno determinista de un bloque manifold electroneumatico con electrovalvulas de respuesta rapida.

## Arquitectura de Software y Hardware

### 1. Vision e Inferencia
- Modelo Campeon: YOLO11s bajo paradigma Tri-Clase (Arabica_Bueno, Robusta_Bueno, Grano_Defecto).
- Resolucion de entrada: 640x640 pixeles a 204 FPS proyectados (latencia de inferencia de 4.9 ms).
- Segmentacion espacial: Mapeo de 4 canales virtuales (160 px por carril) con determinacion analitica de centroides.

### 2. Persistencia y Ciclo de Vida (Offline-First)
- Buffer local transaccional: SQLite en modo WAL (Write-Ahead Logging) con recuperacion ACID y auto-purga a los 30 dias.
- Capa remota: MongoDB Atlas (coleccion multi-tenant indexada por tenant_id y maquina_id).
- Sincronizacion asincrona: Demonio en segundo plano con reintentos automaticos e inmunidad a fallos de red.
- Telemetria de hardware: Registro persistente anti-apagones del tiempo de operacion diaria en storage/estado_maquina.json.

### 3. Enlace Mecatronico (Raspberry Pi 5 -> ESP32)
- Enlace serial: UART-over-USB a 115200 baudios gestionado por una cola concurrente (Queue) de hilo emisor/receptor independiente.
- Firmware: PlatformIO / C++ sobre ESP32-WROOM con temporizacion no bloqueante basada en millis() (pulsos fijos de 20 ms).
- Lazo cerrado de seguridad: Verificacion de conmutacion de presostato digital en la galeria del manifold para deteccion de caidas de presion de linea.

## Requisitos de Instalacion
1. Python 3.10 o superior.
2. Dependencias del sistema:
   pip install -r requirements.txt
3. Configuracion de variables de entorno en archivo .env local.

## Ejecucion
Para iniciar la interfaz de control y telemetria:
python main_dashboard.py
