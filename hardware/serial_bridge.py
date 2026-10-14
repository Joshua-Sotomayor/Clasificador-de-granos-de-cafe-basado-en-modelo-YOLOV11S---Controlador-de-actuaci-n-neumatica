"""
Puente de Comunicación Serial Asíncrono con ESP32 (MOPPI v1.5.0).
Permite la transmisión no bloqueante de comandos de activación neumática
hacia el ESP32 esclavo mediante colas concurrentes (queue.Queue) e hilos
trabajadores independientes, garantizando que el pipeline de inferencia YOLO
y el streaming de video nunca experimenten retrasos de latencia.
"""

import os
import time
import queue
import logging
import threading
from typing import Optional, Callable, Dict, Any

try:
    import serial
    from serial import SerialException
    PYSERIAL_DISPONIBLE = True
except ImportError:
    serial = None
    SerialException = Exception
    PYSERIAL_DISPONIBLE = False

logger = logging.getLogger("MOPPI.Hardware")
if not logger.handlers:
    _h = logging.StreamHandler()
    _f = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")
    _h.setFormatter(_f)
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# Variables de entorno por defecto
PUERTO_DEFAULT = os.getenv("SERIAL_PORT", "COM3" if os.name == "nt" else "/dev/ttyUSB0")
BAUDRATE_DEFAULT = int(os.getenv("SERIAL_BAUDRATE", "115200"))
PULSO_MS_DEFAULT = int(os.getenv("PNEUMATIC_PULSE_MS", "20"))
SIMULACION_DEFAULT = os.getenv("SERIAL_SIMULATION_MODE", "False").lower() in ("true", "1", "yes")


class ESP32Bridge:
    """
    Puente de enlace serial concurrente para control de electroválvulas neumáticas.
    
    Características clave:
    1. Envío no bloqueante mediante cola thread-safe (O(1)).
    2. Hilo emisor y receptor desacoplados para cero latencia en FPS.
    3. Modo de simulación virtual automático ante ausencia de hardware.
    4. Redirección de fallas del presostato hacia logs locales de SQLite (ALARM).
    """

    def __init__(
        self,
        puerto: Optional[str] = None,
        baudrate: Optional[int] = None,
        pulso_ms: Optional[int] = None,
        modo_simulacion: Optional[bool] = None,
        db_manager: Optional[Any] = None,
        callback_alarma: Optional[Callable[[str], None]] = None,
        callback_respuesta: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.puerto: str = puerto or PUERTO_DEFAULT
        self.baudrate: int = baudrate or BAUDRATE_DEFAULT
        self.pulso_ms: int = pulso_ms or PULSO_MS_DEFAULT
        self.solicitar_simulacion: bool = modo_simulacion if modo_simulacion is not None else SIMULACION_DEFAULT

        self.db_manager = db_manager
        self.callback_alarma = callback_alarma
        self.callback_respuesta = callback_respuesta

        # Colas concurrentes y sincronización
        self._cola_envio: queue.Queue = queue.Queue(maxsize=300)
        self._activo = threading.Event()
        self._serial_conn = None
        self._en_simulacion = False

        # Métricas y telemetría de hardware
        self._stats_disparos: Dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}
        self._total_fallas_presion: int = 0
        self._ultimo_ping_ts: float = 0.0
        self._latencia_ping_ms: float = 0.0
        self._banda_activa: bool = False
        self._piloto_actual: str = "WHITE"
        self._lock_stats = threading.Lock()

        # Iniciar conexión
        self._inicializar_puerto()

    def _inicializar_puerto(self) -> None:
        """Intenta abrir el puerto serial físico o conmuta a modo simulación."""
        if not self.solicitar_simulacion and PYSERIAL_DISPONIBLE:
            try:
                self._serial_conn = serial.Serial(
                    port=self.puerto,
                    baudrate=self.baudrate,
                    timeout=0.1,
                    write_timeout=0.1,
                )
                self._en_simulacion = False
                logger.info(f"[ESP32Bridge] Puerto físico abierto exitosamente en '{self.puerto}' @ {self.baudrate} baud.")
            except Exception as e:
                logger.warning(
                    f"[ESP32Bridge] No se pudo abrir puerto físico '{self.puerto}': {e}. "
                    f"Activando modo de simulación automática."
                )
                self._serial_conn = None
                self._en_simulacion = True
        else:
            self._serial_conn = None
            self._en_simulacion = True
            logger.info("[ESP32Bridge] Operando en Modo Simulación / Virtual (Microcontrolador emulado).")

        # Iniciar hilos trabajadores
        self._activo.set()
        self._hilo_emisor = threading.Thread(
            target=self._worker_emisor, name="ESP32Bridge-Emisor", daemon=True
        )
        self._hilo_receptor = threading.Thread(
            target=self._worker_receptor, name="ESP32Bridge-Receptor", daemon=True
        )
        self._hilo_emisor.start()
        self._hilo_receptor.start()

    # =========================================================================
    # MÉTODOS PÚBLICOS NO BLOQUEANTES
    # =========================================================================

    def disparar_canal(self, canal: int) -> bool:
        """
        Encola un comando de eyección para un canal virtual (0..3).
        Operación O(1) no bloqueante garantizada para el hilo de video.
        
        :param canal: Identificador del canal neumático (0, 1, 2 o 3).
        :return: True si se encoló correctamente, False si la cola está saturada.
        """
        if canal not in (0, 1, 2, 3):
            logger.warning(f"[ESP32Bridge] Canal fuera de rango: {canal}")
            return False

        with self._lock_stats:
            self._stats_disparos[canal] += 1

        trama = f"ACT:{canal}"
        try:
            self._cola_envio.put_nowait(trama)
            return True
        except queue.Full:
            logger.error("[ESP32Bridge] Cola de comandos saturada. Descartando eyección.")
            return False

    def detener_todo(self) -> bool:
        """Encola el comando STOP para apagar inmediatamente todas las electroválvulas."""
        try:
            self._cola_envio.put_nowait("STOP")
            return True
        except queue.Full:
            return False

    def control_banda(self, activa: bool) -> bool:
        """Encola el comando para encender (BANDA:ON) o apagar (BANDA:OFF) la tracción."""
        self._banda_activa = bool(activa)
        trama = "BANDA:ON" if activa else "BANDA:OFF"
        try:
            self._cola_envio.put_nowait(trama)
            return True
        except queue.Full:
            logger.error(f"[ESP32Bridge] Cola llena al enviar {trama}")
            return False

    def cambiar_piloto(self, color: str) -> bool:
        """
        Encola el comando PILOT:<COLOR> (RED, GREEN, WHITE, YELLOW)
        para conmutar las luces piloto de estado industrial (24V).
        """
        color_norm = str(color).upper().strip()
        mapa_colores = {
            "ROJO": "RED", "RED": "RED",
            "VERDE": "GREEN", "GREEN": "GREEN",
            "BLANCO": "WHITE", "WHITE": "WHITE",
            "AMARILLO": "YELLOW", "YELLOW": "YELLOW",
        }
        color_final = mapa_colores.get(color_norm, color_norm)
        self._piloto_actual = color_final
        trama = f"PILOT:{color_final}"
        try:
            self._cola_envio.put_nowait(trama)
            return True
        except queue.Full:
            logger.error(f"[ESP32Bridge] Cola llena al enviar {trama}")
            return False

    def hacer_ping(self) -> bool:
        """Encola un comando PING para verificar la presencia y latencia del ESP32."""
        self._ultimo_ping_ts = time.time()
        try:
            self._cola_envio.put_nowait("PING")
            return True
        except queue.Full:
            return False

    def esta_conectado(self) -> bool:
        """Retorna True si el enlace físico está abierto o si opera en simulación activa."""
        if self._en_simulacion:
            return self._activo.is_set()
        return bool(self._serial_conn and self._serial_conn.is_open)

    def esta_en_simulacion(self) -> bool:
        """Retorna True si el puente está operando en modo virtual/simulado."""
        return self._en_simulacion

    def obtener_estadisticas(self) -> Dict[str, Any]:
        """Devuelve telemetría consolidada del puente de comunicación."""
        with self._lock_stats:
            return {
                "disparos_por_canal": dict(self._stats_disparos),
                "total_disparos": sum(self._stats_disparos.values()),
                "fallas_presion": self._total_fallas_presion,
                "latencia_ping_ms": round(self._latencia_ping_ms, 2),
                "en_simulacion": self._en_simulacion,
                "cola_pendientes": self._cola_envio.qsize(),
            }

    def cerrar(self) -> None:
        """Cierra el puente serial y termina ordenadamente los hilos trabajadores."""
        if not self._activo.is_set():
            return

        self._activo.clear()
        try:
            self._cola_envio.put_nowait(None)
        except Exception:
            pass

        if self._serial_conn:
            try:
                self._serial_conn.close()
            except Exception:
                pass
            self._serial_conn = None

        logger.info("[ESP32Bridge] Puente serial cerrado correctamente.")

    def desconectar(self) -> None:
        """Alias para cerrar()."""
        self.cerrar()

    # =========================================================================
    # HILOS TRABAJADORES (EMISOR Y RECEPTOR)
    # =========================================================================

    def _worker_emisor(self) -> None:
        """Hilo de fondo que extrae comandos de la cola y los transmite al ESP32."""
        while self._activo.is_set():
            try:
                comando = self._cola_envio.get(timeout=0.1)
            except queue.Empty:
                continue

            if comando is None:
                break

            if self._en_simulacion:
                # Simular respuesta inmediata del firmware
                self._simular_respuesta(comando)
            else:
                if self._serial_conn and self._serial_conn.is_open:
                    try:
                        linea = (comando + "\n").encode("utf-8")
                        self._serial_conn.write(linea)
                        self._serial_conn.flush()
                    except Exception as e:
                        logger.error(f"[ESP32Bridge] Error transmitiendo trama '{comando}': {e}")
                        # Ante error en transmisión física, registrar alarma
                        if self.db_manager and hasattr(self.db_manager, "registrar_log_local"):
                            self.db_manager.registrar_log_local(
                                "WARNING", f"Fallo al transmitir por puerto serial: {e}"
                            )

    def _worker_receptor(self) -> None:
        """Hilo de fondo que lee respuestas y eventos generados por el ESP32."""
        while self._activo.is_set():
            if self._en_simulacion:
                # En modo simulación no se lee del hardware físico
                time.sleep(0.05)
                continue

            if self._serial_conn and self._serial_conn.is_open:
                try:
                    linea_raw = self._serial_conn.readline()
                    if linea_raw:
                        linea = linea_raw.decode("utf-8", errors="ignore").strip()
                        if linea:
                            self._procesar_linea_recibida(linea)
                except Exception as e:
                    if self._activo.is_set():
                        logger.error(f"[ESP32Bridge] Error leyendo puerto serial: {e}")
                    time.sleep(0.05)
            else:
                time.sleep(0.05)

    def _simular_respuesta(self, comando: str) -> None:
        """Simula la respuesta del firmware de acuerdo con el protocolo."""
        if comando == "PING":
            self._procesar_linea_recibida("PONG")
        elif comando == "STOP":
            self._procesar_linea_recibida("OK:STOP")
        elif comando == "BANDA:ON":
            self._procesar_linea_recibida("OK:BANDA_ON")
        elif comando == "BANDA:OFF":
            self._procesar_linea_recibida("OK:BANDA_OFF")
        elif comando.startswith("PILOT:"):
            self._procesar_linea_recibida(f"OK:{comando}")
        elif comando.startswith("ACT:"):
            canal = comando[4:]
            self._procesar_linea_recibida(f"OK:{canal}")

    def _procesar_linea_recibida(self, linea: str) -> None:
        """
        Analiza las tramas provenientes del ESP32 y despacha eventos/alarmas.
        """
        # 1. Alarma crítica de presostato: ERR:PRESSURE_FAULT_CH_<canal>
        if linea.startswith("ERR:PRESSURE_FAULT"):
            with self._lock_stats:
                self._total_fallas_presion += 1

            logger.error(f"[ESP32Bridge] ¡ALARMA DE HARDWARE! {linea}")

            # Persistencia estricta en SQLite local
            if self.db_manager and hasattr(self.db_manager, "registrar_log_local"):
                self.db_manager.registrar_log_local(
                    "ALARM",
                    f"Falla de presión neumática detectada por presostato en manifold ({linea})",
                )

            if self.callback_alarma:
                try:
                    self.callback_alarma(linea)
                except Exception as e:
                    logger.error(f"[ESP32Bridge] Error en callback de alarma: {e}")

        # 2. Confirmación de PONG
        elif linea == "PONG":
            if self._ultimo_ping_ts > 0:
                self._latencia_ping_ms = (time.time() - self._ultimo_ping_ts) * 1000.0

        # 3. Callback general de respuesta
        if self.callback_respuesta:
            try:
                self.callback_respuesta(linea)
            except Exception as e:
                logger.error(f"[ESP32Bridge] Error en callback de respuesta: {e}")
