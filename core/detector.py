"""
Capa de Detección en Tiempo Real (Productor Asíncrono Desacoplado)
Arquitectura de Doble Cámara Maestro-Esclavo y Doble Hilo:
1. Hilo de Captura: Adquiere frames sincronizados (Cámara Superior / Dorsal y Cámara Inferior / Ventral)
   a 30 FPS continuos con visualización dual y renderizado espacial sin congelamiento.
2. Hilo de Inferencia: Ejecuta YOLOv8/v11 en paralelo y realiza la fusión lógica booleana
   OR inclusivo entre caras dorsal y ventral.
3. Seguidor de Granos Anti-Duplicidad: Asegura que cada defecto dispare su electroválvula
   exactamente una sola vez al cruzar la línea de disparo (Y >= 500).
"""

import os
import cv2
import base64
import time
import threading
import queue
import numpy as np
from typing import Dict, Any, List, Optional, Union, Tuple, Callable


# =====================================================================
# CONSTANTES DE MAPEO ESPACIAL, DOBLE CÁMARA Y ACTUACIÓN MECATRÓNICA
# =====================================================================
ANCHO_BANDA_PX: int = 640
ALTO_FRAME_PX: int = 640
NUM_CANALES_VIRTUALES: int = 4
ANCHO_CANAL_PX: int = 160        # 640 / 4 = 160 px para las 5 líneas divisorias de canales
NUM_CARRILES_ACTUACION: int = 4  # 4 carriles virtuales para la neumática
ANCHO_CARRIL_PX: int = 160       # canal = int(x_center // 160)
LINEA_DISPARO_Y: int = 500       # Y = 500 coordenada de activación para válvulas ESP32

CAMERA_MATCHING_X_TOLERANCE_PX_DEFAULT: int = int(os.getenv("CAMERA_MATCHING_X_TOLERANCE_PX", "25"))
CAMERA_SOURCE_TOP_DEFAULT: Union[int, str] = os.getenv("CAMERA_SOURCE_TOP", "0")
CAMERA_SOURCE_BOTTOM_DEFAULT: Union[int, str] = os.getenv("CAMERA_SOURCE_BOTTOM", "1")


def calcular_centroide(caja: Union[tuple, list]) -> Tuple[int, int]:
    """
    Extrae las coordenadas de la caja delimitadora (Bounding Box: x1, y1, x2, y2)
    y calcula el centroide espacial (x_center, y_center).
    """
    x1, y1, x2, y2 = caja
    x_center = int(round((x1 + x2) / 2.0))
    y_center = int(round((y1 + y2) / 2.0))
    return x_center, y_center


def asignar_canal(
    x_center: Union[int, float],
    ancho_carril: int = ANCHO_CARRIL_PX,
    total_canales: int = NUM_CARRILES_ACTUACION,
) -> int:
    """
    Determina a qué canal o carril virtual [0 a 3] pertenece el grano mediante una división entera:
    canal = int(x_center // 160)
    Canal 0: [0 a 160 px]
    Canal 1: [160 a 320 px]
    Canal 2: [320 a 480 px]
    Canal 3: [480 a 640 px]
    Acota el valor en el rango seguro [0, total_canales - 1].
    """
    canal = int(x_center // ancho_carril)
    return max(0, min(canal, total_canales - 1))


def fusionar_detecciones_doble_camara(
    detecciones_top: List[Dict[str, Any]],
    detecciones_bottom: List[Dict[str, Any]],
    tolerancia_x_px: int = CAMERA_MATCHING_X_TOLERANCE_PX_DEFAULT,
) -> List[Dict[str, Any]]:
    """
    Fusión Lógica Booleana OR Inclusivo para Doble Cámara Maestro-Esclavo.

    Regla de Decisión:
    Eyección(grano_i) = (Clase_Top == Grano_Defecto) OR (Clase_Bottom == Grano_Defecto)

    - Cámara Superior (Maestro): Dicta canal cinemático y posición de referencia X/Y.
    - Cámara Inferior (Esclavo): Inspecciona cara ventral (reverso/hendidura).
      Si coincide en el mismo canal y |X_top - X_bottom| <= tolerancia_x_px,
      transfiere su diagnóstico de anomalía al grano maestro correspondiente.
    - La cámara inferior NUNCA calcula línea de disparo ni emite órdenes a ESP32.

    :param detecciones_top: Detecciones de cara dorsal (Maestro).
    :param detecciones_bottom: Detecciones de cara ventral (Esclavo).
    :param tolerancia_x_px: Ventana de tolerancia horizontal en píxeles.
    :return: Lista de detecciones maestras consolidadas con diagnóstico fusionado.
    """
    bottom_disponibles = list(detecciones_bottom)

    for grano_top in detecciones_top:
        canal_top = grano_top.get("canal", asignar_canal(grano_top.get("x_center", 0)))
        x_top = grano_top.get("x_center", 0)

        mejor_idx_bottom = None
        menor_delta_x = float("inf")

        for idx, grano_bot in enumerate(bottom_disponibles):
            canal_bot = grano_bot.get("canal", asignar_canal(grano_bot.get("x_center", 0)))
            if canal_bot != canal_top:
                continue

            delta_x = abs(grano_bot.get("x_center", 0) - x_top)
            if delta_x <= tolerancia_x_px and delta_x < menor_delta_x:
                menor_delta_x = delta_x
                mejor_idx_bottom = idx

        def_top = bool(grano_top.get("es_defecto", False))

        if mejor_idx_bottom is not None:
            grano_match = bottom_disponibles.pop(mejor_idx_bottom)
            def_bot = bool(grano_match.get("es_defecto", False))

            # Fusión booleana OR inclusivo
            es_defecto_fused = def_top or def_bot

            grano_top["es_defecto"] = es_defecto_fused
            grano_top["defecto_confirmado"] = es_defecto_fused
            grano_top["match_bottom"] = True
            grano_top["deteccion_bottom"] = grano_match
            if def_top and def_bot:
                grano_top["origen_defecto"] = "AMBOS"
            elif def_top:
                grano_top["origen_defecto"] = "TOP"
            elif def_bot:
                grano_top["origen_defecto"] = "BOTTOM"
            else:
                grano_top["origen_defecto"] = "NINGUNO"

            grano_match["pareado_con_top"] = True
            grano_match["defecto_confirmado"] = es_defecto_fused
        else:
            grano_top["es_defecto"] = def_top
            grano_top["defecto_confirmado"] = def_top
            grano_top["match_bottom"] = False
            grano_top["origen_defecto"] = "TOP" if def_top else "NINGUNO"

    for rem in bottom_disponibles:
        rem["pareado_con_top"] = False

    return detecciones_top


class GranoRastreado:
    """Representa el estado cinemático y de actuación de un grano individual en la banda."""

    def __init__(self, id_grano: int, x: int, y: int, canal: int, es_defecto: bool):
        self.id: int = id_grano
        self.x: int = x
        self.y: int = y
        self.canal: int = canal
        self.es_defecto: bool = es_defecto
        self.procesado: bool = False
        self.primer_visto: float = time.time()
        self.ultimo_visto: float = time.time()
        self.frames_visto: int = 1


class SeguidorGranos:
    """
    Seguidor espacial anti-duplicidad para actuación mecatrónica (ESP32).
    Rastrea el tránsito cinemático de los granos a lo largo de cuadros sucesivos
    y garantiza que cada grano defectuoso active su electroválvula EXACTAMENTE UNA VEZ
    al cruzar la línea de disparo (Y >= 500).
    """

    def __init__(
        self,
        distancia_max_px: float = 65.0,
        tiempo_vida_s: float = 1.0,
    ):
        self.distancia_max_px = distancia_max_px
        self.tiempo_vida_s = tiempo_vida_s
        self._siguiente_id: int = 1
        self.granos_activos: Dict[int, GranoRastreado] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        """Reinicia el historial de rastreo y contadores de identificación."""
        with self._lock:
            self.granos_activos.clear()
            self._siguiente_id = 1

    def actualizar_y_filtrar_disparos(
        self,
        detecciones: List[Dict[str, Any]],
        linea_disparo_y: int = LINEA_DISPARO_Y,
    ) -> List[int]:
        """
        Asocia detecciones del frame actual con granos rastreados mediante mínima
        distancia euclidiana y filtra disparos redundantes.

        :param detecciones: Lista de diccionarios de detecciones con centroides y canal.
        :param linea_disparo_y: Umbral horizontal Y donde se activa la eyección mecatrónica.
        :return: Lista de canales [0..3] que deben disparar pulso en este ciclo.
        """
        with self._lock:
            ahora = time.time()
            canales_a_disparar: List[int] = []
            granos_asociados = set()

            for det in detecciones:
                cx = det.get("x_center", 0)
                cy = det.get("y_center", 0)
                canal = det.get("canal", asignar_canal(cx))
                es_def = det.get("es_defecto", False)

                mejor_id = None
                mejor_dist = self.distancia_max_px

                # Asociación voraz por menor distancia espacial
                for gid, grano in self.granos_activos.items():
                    if gid in granos_asociados:
                        continue
                    dist = ((cx - grano.x) ** 2 + (cy - grano.y) ** 2) ** 0.5
                    if dist < mejor_dist:
                        mejor_dist = dist
                        mejor_id = gid

                if mejor_id is not None:
                    # Actualizar grano previamente rastreado
                    grano = self.granos_activos[mejor_id]
                    grano.x = cx
                    grano.y = cy
                    grano.canal = canal
                    if es_def:
                        grano.es_defecto = True
                    grano.ultimo_visto = ahora
                    grano.frames_visto += 1
                    granos_asociados.add(mejor_id)

                    det["id_seguimiento"] = grano.id
                    det["procesado"] = grano.procesado

                    # Disparo único al cruzar línea cinemática
                    if grano.es_defecto and grano.y >= linea_disparo_y and not grano.procesado:
                        grano.procesado = True
                        det["procesado"] = True
                        canales_a_disparar.append(grano.canal)
                else:
                    # Nuevo grano ingresado al campo de visión
                    nuevo_id = self._siguiente_id
                    self._siguiente_id += 1

                    nuevo_grano = GranoRastreado(
                        id_grano=nuevo_id,
                        x=cx,
                        y=cy,
                        canal=canal,
                        es_defecto=es_def,
                    )
                    det["id_seguimiento"] = nuevo_id

                    # Si el grano nace ya sobre o después de la línea de disparo
                    if es_def and cy >= linea_disparo_y:
                        nuevo_grano.procesado = True
                        det["procesado"] = True
                        canales_a_disparar.append(canal)
                    else:
                        det["procesado"] = False

                    self.granos_activos[nuevo_id] = nuevo_grano
                    granos_asociados.add(nuevo_id)

            # Purgar de memoria granos que salieron de la banda
            ids_expirados = [
                gid for gid, g in self.granos_activos.items()
                if (ahora - g.ultimo_visto) > self.tiempo_vida_s
            ]
            for gid in ids_expirados:
                del self.granos_activos[gid]

            return canales_a_disparar


class YOLODetector:
    """
    Productor multihilo de detección de granos de café con soporte de doble cámara maestro-esclavo.
    Separa la captura sincronizada de video de la inferencia de red neuronal para fluidez total (30-60 FPS).
    """

    # Colores BGR institucionales para visualización OpenCV
    COLOR_SANO_BGR = (48, 123, 25)       # Verde ULSA (#197B30)
    COLOR_DEFECTO_BGR = (34, 50, 200)    # Rojo/Cálido para defectos
    COLOR_TEXTO_FONDO = (50, 59, 74)     # Café oscuro

    NOMBRES_CLASES_DEFECTO = {
        0: "Arabica_Agrio",
        1: "Arabica_Brocado",
        2: "Arabica_Bueno",
        3: "Arabica_Cereza",
        4: "Arabica_Concha",
        5: "Arabica_Inmaduro",
        6: "Arabica_Negro",
        7: "Arabica_Quebrado",
        8: "Robusta_Brocado",
        9: "Robusta_Bueno",
        10: "Robusta_Cereza",
        11: "Robusta_Negro",
        12: "Robusta_Quebrado",
    }

    # Taxonomía del modelo campeón Tri-Clase (V10)
    NOMBRES_CLASES_TRICLASE = {
        0: "Arabica_Bueno",
        1: "Robusta_Bueno",
        2: "Grano_Defecto",
    }

    def __init__(
        self,
        ruta_modelo: str = "models/best.pt",
        fuente_video: Union[int, str] = 0,
        cola_salida: Optional[queue.Queue] = None,
        confianza_minima: float = 0.30,
        resolucion_captura: tuple = (640, 640),
        linea_disparo_y: int = LINEA_DISPARO_Y,
        callback_actuacion: Optional[Callable[[int, Dict[str, Any]], None]] = None,
        esp32_bridge: Optional[Any] = None,
        fuente_video_top: Optional[Union[int, str]] = None,
        fuente_video_bottom: Optional[Union[int, str]] = None,
        tolerancia_x_match: Optional[int] = None,
        ruta_modelo_13clases: Optional[str] = None,
    ):
        """
        :param ruta_modelo: Ruta al archivo de pesos Tri-clase (.pt). Por defecto models/best.pt.
        :param fuente_video: Índice de cámara primaria o 'demo'.
        :param cola_salida: Cola thread-safe donde se depositan los payloads para la UI.
        :param confianza_minima: Umbral mínimo de confianza para registrar una detección.
        :param resolucion_captura: Tupla (ancho, alto) para la captura de video (default 640x640).
        :param linea_disparo_y: Coordenada Y de la línea horizontal de disparo ESP32 (default 500).
        :param callback_actuacion: Función callback opcional invocada al disparar una válvula neumática.
        :param esp32_bridge: Instancia de ESP32Bridge para control de electroválvulas mecatrónicas.
        :param fuente_video_top: Fuente para la cámara superior (Master / Dorsal).
        :param fuente_video_bottom: Fuente para la cámara inferior (Slave / Ventral).
        :param tolerancia_x_match: Tolerancia en píxeles para el acoplamiento espacial X.
        :param ruta_modelo_13clases: Ruta al archivo de pesos de 13 clases (.pt). Por defecto models/best_13clases.pt.
        """
        self.ruta_modelo_triclase = ruta_modelo or os.getenv("MODEL_PATH", "models/best.pt")
        self.ruta_modelo_13clases = ruta_modelo_13clases or os.getenv("MODEL_13CLASES_PATH", "models/best_13clases.pt")
        self.ruta_modelo = self.ruta_modelo_triclase
        self.es_modo_13clases: bool = False

        self.fuente_video = fuente_video
        self.cola_salida = cola_salida if cola_salida is not None else queue.Queue(maxsize=3)
        self.confianza_minima = confianza_minima
        self.resolucion_captura = resolucion_captura
        self.linea_disparo_y = linea_disparo_y
        self.callback_actuacion = callback_actuacion
        self.esp32_bridge = esp32_bridge

        # Configuración de Doble Cámara
        if fuente_video_top is not None:
            self.fuente_video_top = fuente_video_top
        elif str(fuente_video).lower() in ("demo", "simulado", "synthetic"):
            self.fuente_video_top = "demo"
        elif fuente_video != 0 and fuente_video is not None:
            self.fuente_video_top = fuente_video
        else:
            self.fuente_video_top = CAMERA_SOURCE_TOP_DEFAULT

        if fuente_video_bottom is not None:
            self.fuente_video_bottom = fuente_video_bottom
        elif str(fuente_video).lower() in ("demo", "simulado", "synthetic"):
            self.fuente_video_bottom = "demo"
        else:
            self.fuente_video_bottom = CAMERA_SOURCE_BOTTOM_DEFAULT

        self.tolerancia_x_match = (
            tolerancia_x_match if tolerancia_x_match is not None else CAMERA_MATCHING_X_TOLERANCE_PX_DEFAULT
        )

        # Seguidor espacial anti-duplicidad
        self.seguidor_granos = SeguidorGranos()

        # Estado del detector
        self._ejecutando = False
        self._pausado = False
        self.clasificacion_activa = False
        self._solicitud_cambio_fuente: Optional[Union[int, str]] = None
        self._solicitud_cambio_fuentes: Optional[Tuple[Union[int, str], Union[int, str]]] = None
        self._lock = threading.RLock()

        # Modelo YOLO compartido globalmente (mismo modelo para ambas cámaras)
        self.modelo = None
        self.modo_simulado = False
        self._inicializar_modelo()

        # Telemetría y estado compartido entre hilos
        self.es_dual_sincronizado = True
        self._frame_reciente: Optional[np.ndarray] = None
        self._frame_top_reciente: Optional[np.ndarray] = None
        self._frame_bottom_reciente: Optional[np.ndarray] = None

        self._ultimas_detecciones: List[Dict[str, Any]] = []
        self._ultimas_detecciones_top: List[Dict[str, Any]] = []
        self._ultimas_detecciones_bottom: List[Dict[str, Any]] = []

        self._latencia_inferencia_ms: float = 0.0
        self._fps_captura: float = 30.0
        self._hilo_captura: Optional[threading.Thread] = None
        self._hilo_inferencia: Optional[threading.Thread] = None

        # Objetos de captura OpenCV
        self._cap_top = None
        self._cap_bottom = None
        self._cap = None  # Alias para retrocompatibilidad

    @property
    def ejecutando(self) -> bool:
        """Indica si el bucle de procesamiento del detector se encuentra activo."""
        return self._ejecutando

    def _inicializar_modelo(self) -> None:
        """
        Carga el modelo global compartido Ultralytics YOLO (Tri-clase por defecto o 13 Clases)
        o activa modo simulado si el archivo no está presente.
        El modelo seleccionado procesa tanto la cara dorsal (superior) como la cara ventral (inferior).
        """
        ruta_actual = self.ruta_modelo_13clases if self.es_modo_13clases else self.ruta_modelo_triclase
        ruta_encontrada = None
        if ruta_actual and os.path.exists(ruta_actual):
            ruta_encontrada = ruta_actual
        elif not self.es_modo_13clases and (ruta_actual in ("best.pt", "models/best.pt", "weights/best.pt", None, "")):
            for cand in ["models/best.pt", "best.pt", "weights/best.pt"]:
                if os.path.exists(cand):
                    ruta_encontrada = cand
                    break

        try:
            from ultralytics import YOLO
            if ruta_encontrada:
                modo_txt = "13 Clases" if self.es_modo_13clases else "Tri-clase"
                print(f"[YOLODetector] Modelo global ({modo_txt}) cargado exitosamente: {ruta_encontrada}")
                self.modelo = YOLO(ruta_encontrada)
                self.ruta_modelo = ruta_encontrada
                self.modo_simulado = False
            else:
                print(f"[YOLODetector] Modelo global '{ruta_actual}' no encontrado. Operando en modo demostrativo/simulado.")
                self.modelo = None
                self.modo_simulado = True
        except ImportError:
            print("[YOLODetector] Ultralytics no disponible. Activando modo simulador sintético.")
            self.modelo = None
            self.modo_simulado = True
        except Exception as e:
            print(f"[YOLODetector] Advertencia al cargar YOLO ({e}). Usando modo simulador.")
            self.modelo = None
            self.modo_simulado = True

    def cambiar_modelo(self, usar_13_clases: bool) -> bool:
        """
        Conmuta el modelo de red neuronal global compartido entre 'Tri-clase' y '13 Clases'.
        Ambas cámaras (superior e inferior) utilizarán inmediatamente los mismos pesos actualizados.
        :param usar_13_clases: True para activar 13 Clases, False para modelo Tri-clase (Campeón V10).
        """
        with self._lock:
            self.es_modo_13clases = usar_13_clases
            self._inicializar_modelo()
            modo_txt = "13 Clases" if usar_13_clases else "Tri-clase (Campeón V10)"
            print(f"[YOLODetector] Modelo global actualizado para ambas cámaras: {modo_txt}")
            return not self.modo_simulado

    def iniciar(self) -> bool:
        """
        Inicia los hilos de captura de video para visualización en vivo (modo preview dual).
        La inferencia del modelo YOLO permanece en espera hasta llamar a iniciar_clasificacion().
        """
        with self._lock:
            if self._ejecutando:
                return True

            self._ejecutando = True
            self._pausado = False
            self.clasificacion_activa = False

            # Iniciar hilo 1: Captura de Video continua sincronizada a 30 FPS
            self._hilo_captura = threading.Thread(
                target=self._bucle_captura_video,
                daemon=True,
                name="HiloCapturaVideoDual"
            )
            self._hilo_captura.start()

            # Iniciar hilo 2: Inferencia YOLO y Fusión Booleana en paralelo
            self._hilo_inferencia = threading.Thread(
                target=self._bucle_inferencia_yolo,
                daemon=True,
                name="HiloInferenciaYOLODual"
            )
            self._hilo_inferencia.start()
            return True

    def iniciar_clasificacion(self) -> None:
        """Activa la inferencia del modelo YOLO y la clasificación continua."""
        with self._lock:
            self.clasificacion_activa = True
            self._pausado = False

    def pausar(self) -> None:
        """Pausa la clasificación y detiene la inferencia de YOLO (mantiene preview de cámaras)."""
        with self._lock:
            self.clasificacion_activa = False
            self._ultimas_detecciones = []
            self._ultimas_detecciones_top = []
            self._ultimas_detecciones_bottom = []
            self._latencia_inferencia_ms = 0.0

    def reanudar(self) -> None:
        """Reanuda la clasificación activa con YOLO."""
        with self._lock:
            self.clasificacion_activa = True

    def detener_clasificacion(self) -> None:
        """Detiene la clasificación activa volviendo al modo preview."""
        with self._lock:
            self.clasificacion_activa = False
            self._ultimas_detecciones = []
            self._ultimas_detecciones_top = []
            self._ultimas_detecciones_bottom = []
            self._latencia_inferencia_ms = 0.0

    def detener(self) -> None:
        """Detiene completamente la captura y libera el hardware de ambas cámaras."""
        with self._lock:
            self._ejecutando = False
            self._pausado = False
            self.clasificacion_activa = False

        if self._hilo_captura and self._hilo_captura.is_alive():
            self._hilo_captura.join(timeout=1.0)
        if self._hilo_inferencia and self._hilo_inferencia.is_alive():
            self._hilo_inferencia.join(timeout=1.0)

        self._liberar_camara()

    def cambiar_fuentes_video(
        self, fuente_top: Union[int, str], fuente_bottom: Union[int, str]
    ) -> None:
        """
        Reconfigura dinámicamente ambas fuentes ópticas (Cámara Superior e Inferior)
        de forma segura y desacoplada del hilo de captura OpenCV.
        """
        with self._lock:
            self.fuente_video_top = fuente_top
            self.fuente_video_bottom = fuente_bottom
            self.fuente_video = fuente_top
            if self._ejecutando:
                self._solicitud_cambio_fuentes = (fuente_top, fuente_bottom)
            else:
                self._liberar_camara()
                self._abrir_camaras()

    def cambiar_fuente(self, nueva_fuente: Union[int, str]) -> None:
        """Alias para retrocompatibilidad, reconfigura la fuente superior."""
        self.cambiar_fuentes_video(nueva_fuente, self.fuente_video_bottom)

    def _abrir_camaras(self) -> bool:
        """Abre ambas cámaras web con backend DirectShow en Windows para latencia mínima."""
        # 1. Cámara Superior (Maestro)
        if str(self.fuente_video_top).lower() in ("demo", "simulado", "synthetic"):
            print("[YOLODetector] Cámara Superior (Maestro) en modo simulación (demo).")
            self._cap_top = None
        else:
            try:
                src_top = int(self.fuente_video_top) if str(self.fuente_video_top).isdigit() else self.fuente_video_top
                if isinstance(src_top, int):
                    self._cap_top = cv2.VideoCapture(src_top, cv2.CAP_DSHOW)
                    if not self._cap_top or not self._cap_top.isOpened():
                        self._cap_top = cv2.VideoCapture(src_top)
                else:
                    self._cap_top = cv2.VideoCapture(src_top)

                if not self._cap_top or not self._cap_top.isOpened():
                    print(f"[YOLODetector] Cámara superior {self.fuente_video_top} no disponible. Usando generador demo.")
                    self.fuente_video_top = "demo"
                    self._cap_top = None
                else:
                    self._cap_top.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolucion_captura[0])
                    self._cap_top.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolucion_captura[1])
                    self._cap_top.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    print(f"[YOLODetector] Cámara superior (Maestro) {src_top} abierta exitosamente.")
            except Exception as e:
                print(f"[YOLODetector] Error al abrir cámara superior ({e}). Usando modo demo.")
                self.fuente_video_top = "demo"
                self._cap_top = None

        # 2. Cámara Inferior (Esclavo)
        if str(self.fuente_video_bottom).lower() in ("demo", "simulado", "synthetic"):
            print("[YOLODetector] Cámara Inferior (Esclavo) en modo simulación (demo).")
            self._cap_bottom = None
        else:
            try:
                src_bot = int(self.fuente_video_bottom) if str(self.fuente_video_bottom).isdigit() else self.fuente_video_bottom
                if isinstance(src_bot, int):
                    self._cap_bottom = cv2.VideoCapture(src_bot, cv2.CAP_DSHOW)
                    if not self._cap_bottom or not self._cap_bottom.isOpened():
                        self._cap_bottom = cv2.VideoCapture(src_bot)
                else:
                    self._cap_bottom = cv2.VideoCapture(src_bot)

                if not self._cap_bottom or not self._cap_bottom.isOpened():
                    print(f"[YOLODetector] Cámara inferior {self.fuente_video_bottom} no disponible. Usando generador demo.")
                    self.fuente_video_bottom = "demo"
                    self._cap_bottom = None
                else:
                    self._cap_bottom.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolucion_captura[0])
                    self._cap_bottom.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolucion_captura[1])
                    self._cap_bottom.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    print(f"[YOLODetector] Cámara inferior (Esclavo) {src_bot} abierta exitosamente.")
            except Exception as e:
                print(f"[YOLODetector] Error al abrir cámara inferior ({e}). Usando modo demo.")
                self.fuente_video_bottom = "demo"
                self._cap_bottom = None

        self._cap = self._cap_top
        self.es_dual_sincronizado = True
        return True

    def _abrir_camara(self) -> bool:
        """Alias de compatibilidad."""
        return self._abrir_camaras()

    def _liberar_camara(self) -> None:
        """Libera los recursos de hardware de ambas cámaras con seguridad."""
        if self._cap_top is not None:
            try:
                self._cap_top.release()
            except Exception:
                pass
            self._cap_top = None

        if self._cap_bottom is not None:
            try:
                self._cap_bottom.release()
            except Exception:
                pass
            self._cap_bottom = None

        self._cap = None

    def _leer_frames_dual(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Adquiere simultáneamente los fotogramas de la cámara superior e inferior."""
        frame_top = None
        frame_bottom = None

        # 1. Lectura Superior (Maestro)
        if str(self.fuente_video_top).lower() in ("demo", "simulado", "synthetic") or self._cap_top is None:
            frame_top = self._generar_frame_sintetico()
        else:
            try:
                ret, f_top = self._cap_top.read()
                if ret and f_top is not None:
                    frame_top = f_top
                else:
                    frame_top = self._generar_frame_sintetico()
            except Exception:
                frame_top = self._generar_frame_sintetico()

        # 2. Lectura Inferior (Esclavo)
        if str(self.fuente_video_bottom).lower() in ("demo", "simulado", "synthetic") or self._cap_bottom is None:
            frame_bottom = self._generar_frame_sintetico_inferior()
        else:
            try:
                ret, f_bot = self._cap_bottom.read()
                if ret and f_bot is not None:
                    frame_bottom = f_bot
                else:
                    frame_bottom = self._generar_frame_sintetico_inferior()
            except Exception:
                frame_bottom = self._generar_frame_sintetico_inferior()

        return frame_top, frame_bottom

    def _leer_frame(self) -> Optional[np.ndarray]:
        """Captura un frame de la cámara superior (para compatibilidad con tests y flujos simples)."""
        f_top, _ = self._leer_frames_dual()
        return f_top

    def _bucle_captura_video(self) -> None:
        """
        Hilo 1: Adquiere frames duales sincronizados (~30-60 FPS), anota ambas vistas
        y despacha a la cola de la UI.
        """
        self._abrir_camaras()
        ultimo_tiempo = time.perf_counter()

        while self._ejecutando:
            # 0. Atender solicitudes de cambio de fuentes ópticas en caliente de forma segura
            if self._solicitud_cambio_fuentes is not None or self._solicitud_cambio_fuente is not None:
                with self._lock:
                    if self._solicitud_cambio_fuentes is not None:
                        nueva_top, nueva_bot = self._solicitud_cambio_fuentes
                        self._solicitud_cambio_fuentes = None
                        self._solicitud_cambio_fuente = None
                    else:
                        nueva_top = self._solicitud_cambio_fuente
                        nueva_bot = self.fuente_video_bottom
                        self._solicitud_cambio_fuente = None

                    self._liberar_camara()
                    self.fuente_video = nueva_top
                    self.fuente_video_top = nueva_top
                    self.fuente_video_bottom = nueva_bot
                    self._abrir_camaras()
                    self._ultimas_detecciones = []
                    self._ultimas_detecciones_top = []
                    self._ultimas_detecciones_bottom = []
                    self._latencia_inferencia_ms = 0.0

            t_inicio = time.perf_counter()

            # 1. Leer frames sincronizados
            frame_top, frame_bottom = self._leer_frames_dual()
            if frame_top is None:
                time.sleep(0.02)
                continue
            if frame_bottom is None:
                frame_bottom = self._generar_frame_sintetico_inferior()

            # Guardar frames para el hilo de inferencia
            with self._lock:
                self._frame_top_reciente = frame_top.copy()
                self._frame_bottom_reciente = frame_bottom.copy()
                self._frame_reciente = frame_top.copy()

                if self.clasificacion_activa:
                    detecciones_actuales = list(self._ultimas_detecciones)
                    detecciones_top_act = list(self._ultimas_detecciones_top)
                    detecciones_bot_act = list(self._ultimas_detecciones_bottom)
                    latencia_ms = self._latencia_inferencia_ms
                else:
                    detecciones_actuales = []
                    detecciones_top_act = []
                    detecciones_bot_act = []
                    latencia_ms = 0.0

            # 2. Calcular FPS de la cámara
            t_ahora = time.perf_counter()
            delta = t_ahora - ultimo_tiempo
            ultimo_tiempo = t_ahora
            fps = 1.0 / max(delta, 1e-4)
            self._fps_captura = fps

            # 3. Evaluar disparo mecatrónico a ESP32 (SÓLO la cámara superior tiene autoridad)
            if self.clasificacion_activa and detecciones_actuales:
                self._evaluar_disparo_esp32(detecciones_actuales)
                frame_top_anotado = self._dibujar_detecciones(frame_top, detecciones_actuales)
                frame_bottom_anotado = self._dibujar_detecciones_inferior(frame_bottom, detecciones_bot_act)
            else:
                frame_top_anotado = frame_top.copy()
                self._dibujar_guias_canales_y_disparo(frame_top_anotado)
                frame_bottom_anotado = frame_bottom.copy()
                self._dibujar_guias_canales_inferior(frame_bottom_anotado)

            # 4. Telemetría y estado de válvula neumática
            valvula_activa = any(
                d.get("es_defecto", False) and d.get("y_center", 0) >= self.linea_disparo_y
                for d in detecciones_actuales
            ) if self.clasificacion_activa else False

            self._dibujar_hud(frame_top_anotado, fps, latencia_ms, valvula_activa, len(detecciones_actuales))

            # 5. Codificar imágenes a Base64 Data URI y Bytes
            frame_bytes = self._frame_a_bytes(frame_top_anotado)
            frame_b64 = self._frame_a_base64(frame_top_anotado)

            payload = {
                "frame_bgr": frame_top_anotado,          # Compatibilidad retroactiva
                "frame_top": frame_top_anotado,          # Vista Cámara Superior (Master)
                "frame_bottom": frame_bottom_anotado,    # Vista Cámara Inferior (Slave)
                "frame_bytes": frame_bytes,
                "frame_base64": frame_b64,
                "frame_src": f"data:image/jpeg;base64,{frame_b64}",
                "detecciones": detecciones_actuales,     # Detecciones consolidadas con OR lógico
                "detecciones_top": detecciones_top_act,
                "detecciones_bottom": detecciones_bot_act,
                "fps": round(fps, 1),
                "latencia_ms": round(latencia_ms, 1),
                "valvula_activa": valvula_activa,
                "total_detectados": len(detecciones_actuales),
                "dual_sync": self.es_dual_sincronizado,
            }

            # Enviar a cola descartando cuadros viejos
            if self.cola_salida.full():
                try:
                    self.cola_salida.get_nowait()
                except queue.Empty:
                    pass
            try:
                self.cola_salida.put_nowait(payload)
            except queue.Full:
                pass

            # Controlar tasa de captura a ~30 FPS
            tiempo_trabajo = time.perf_counter() - t_inicio
            tiempo_dormir = max(0.001, (1.0 / 30.0) - tiempo_trabajo)
            time.sleep(tiempo_dormir)

        self._liberar_camara()

    def _bucle_inferencia_yolo(self) -> None:
        """
        Hilo 2: Ejecuta inferencia YOLO en paralelo para ambas cámaras cuando la clasificación está activa.
        Aplica la fusión lógica booleana OR inclusivo entre caras dorsal y ventral.
        """
        while self._ejecutando:
            if not self.clasificacion_activa:
                with self._lock:
                    self._ultimas_detecciones = []
                    self._ultimas_detecciones_top = []
                    self._ultimas_detecciones_bottom = []
                    self._latencia_inferencia_ms = 0.0
                time.sleep(0.05)
                continue

            frame_top_para_inferir = None
            frame_bottom_para_inferir = None
            with self._lock:
                if self._frame_top_reciente is not None:
                    frame_top_para_inferir = self._frame_top_reciente.copy()
                if self._frame_bottom_reciente is not None:
                    frame_bottom_para_inferir = self._frame_bottom_reciente.copy()

            if frame_top_para_inferir is None:
                time.sleep(0.03)
                continue

            t0 = time.perf_counter()
            # 1. Inferencia en Cámara Superior (Maestro / Cara Dorsal)
            detecciones_top = self._ejecutar_inferencia(frame_top_para_inferir)

            # 2. Inferencia en Cámara Inferior (Esclavo / Cara Ventral)
            if frame_bottom_para_inferir is not None:
                detecciones_bottom = self._ejecutar_inferencia_bottom(frame_bottom_para_inferir, detecciones_top)
            else:
                detecciones_bottom = []

            # 3. Fusión Booleana OR Inclusivo
            detecciones_fusionadas = fusionar_detecciones_doble_camara(
                detecciones_top,
                detecciones_bottom,
                tolerancia_x_px=self.tolerancia_x_match,
            )

            t1 = time.perf_counter()
            latencia_ms = (t1 - t0) * 1000.0

            with self._lock:
                self._ultimas_detecciones = detecciones_fusionadas
                self._ultimas_detecciones_top = detecciones_top
                self._ultimas_detecciones_bottom = detecciones_bottom
                self._latencia_inferencia_ms = latencia_ms

            # Pequeña pausa para no saturar 100% el CPU
            time.sleep(0.02)

    def _ejecutar_inferencia(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """Ejecuta YOLO optimizado con resolución adaptativa y mapeo espacial sobre la cámara superior."""
        if self.modo_simulado or self.modelo is None or str(self.fuente_video_top).lower() in ("demo", "simulado", "synthetic"):
            return self._simular_detecciones(frame.shape)

        detecciones = []
        try:
            resultados = self.modelo(frame, imgsz=320, conf=self.confianza_minima, verbose=False)
            for r in resultados:
                for box in r.boxes:
                    clase_id = int(box.cls[0].item())
                    confianza = float(box.conf[0].item())
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]

                    if self.es_modo_13clases:
                        nombre_clase = self.NOMBRES_CLASES_DEFECTO.get(clase_id, f"Clase_{clase_id}")
                        es_sano = clase_id in (2, 9) or "Bueno" in nombre_clase
                    else:
                        nombre_clase = self.NOMBRES_CLASES_TRICLASE.get(clase_id, f"Clase_{clase_id}")
                        es_sano = clase_id in (0, 1) or "Bueno" in nombre_clase
                    x_center, y_center = calcular_centroide((x1, y1, x2, y2))
                    canal = asignar_canal(x_center)

                    detecciones.append({
                        "clase_id": clase_id,
                        "nombre_clase": nombre_clase,
                        "confianza": round(confianza, 2),
                        "caja": (x1, y1, x2, y2),
                        "centroide": (x_center, y_center),
                        "x_center": x_center,
                        "y_center": y_center,
                        "canal": canal,
                        "es_defecto": not es_sano,
                    })
        except Exception as e:
            print(f"[YOLODetector] Error en inferencia cámara superior: {e}")
            detecciones = []
        return detecciones

    def _ejecutar_inferencia_bottom(
        self, frame: np.ndarray, detecciones_top: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """Inferencia para la cámara inferior (reverso / ventral)."""
        if self.modo_simulado or self.modelo is None or str(self.fuente_video_bottom).lower() in ("demo", "simulado", "synthetic"):
            return self._simular_detecciones_bottom(detecciones_top or [], frame.shape)

        detecciones = []
        try:
            resultados = self.modelo(frame, imgsz=320, conf=self.confianza_minima, verbose=False)
            for r in resultados:
                for box in r.boxes:
                    clase_id = int(box.cls[0].item())
                    confianza = float(box.conf[0].item())
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]

                    if self.es_modo_13clases:
                        nombre_clase = self.NOMBRES_CLASES_DEFECTO.get(clase_id, f"Clase_{clase_id}")
                        es_sano = clase_id in (2, 9) or "Bueno" in nombre_clase
                    else:
                        nombre_clase = self.NOMBRES_CLASES_TRICLASE.get(clase_id, f"Clase_{clase_id}")
                        es_sano = clase_id in (0, 1) or "Bueno" in nombre_clase
                    x_center, y_center = calcular_centroide((x1, y1, x2, y2))
                    canal = asignar_canal(x_center)

                    detecciones.append({
                        "clase_id": clase_id,
                        "nombre_clase": nombre_clase,
                        "confianza": round(confianza, 2),
                        "caja": (x1, y1, x2, y2),
                        "centroide": (x_center, y_center),
                        "x_center": x_center,
                        "y_center": y_center,
                        "canal": canal,
                        "es_defecto": not es_sano,
                        "es_camara_inferior": True,
                    })
        except Exception as e:
            print(f"[YOLODetector] Error en inferencia cámara inferior: {e}")
            detecciones = []
        return detecciones

    def _evaluar_disparo_esp32(self, detecciones: List[Dict[str, Any]]) -> List[int]:
        """
        Lógica de Disparo y Garantía Anti-Duplicidad (ESP32):
        Utiliza el SeguidorGranos para despachar la señal de eyección exactamente
        una única vez cuando el grano defectuoso cruza la línea Y >= 500.
        """
        canales_a_disparar = self.seguidor_granos.actualizar_y_filtrar_disparos(
            detecciones, linea_disparo_y=self.linea_disparo_y
        )

        for canal in canales_a_disparar:
            print(f"[ACTUACION] Defecto en Canal {canal} - Enviando señal a ESP32...")
            if self.esp32_bridge:
                try:
                    self.esp32_bridge.disparar_canal(canal)
                except Exception as e:
                    print(f"[YOLODetector] Error al disparar canal en ESP32: {e}")
            if self.callback_actuacion:
                try:
                    det_asociada = next(
                        (d for d in detecciones if d.get("canal") == canal and d.get("es_defecto")),
                        {}
                    )
                    self.callback_actuacion(canal, det_asociada)
                except Exception as e:
                    print(f"[YOLODetector] Error en callback de actuación: {e}")

        return canales_a_disparar

    def _dibujar_guias_canales_y_disparo(self, frame: np.ndarray) -> None:
        """
        Dibuja sobre el frame de la cámara superior (Master):
        1. 5 líneas divisorias verticales para los 4 canales virtuales (cada 160 px en 640 px).
        2. Línea horizontal roja en Y = 500 ('Línea de Disparo' / Trigger Line).
        """
        h, w = frame.shape[:2]

        # 1. 5 Líneas divisorias verticales para 4 canales (x = 0, 160, 320, 480, 639)
        paso_canal = w / float(NUM_CANALES_VIRTUALES)
        for i in range(NUM_CANALES_VIRTUALES + 1):
            x = min(int(round(i * paso_canal)), w - 1)
            cv2.line(frame, (x, 0), (x, h), (180, 180, 180), 1, cv2.LINE_AA)
            if i < NUM_CANALES_VIRTUALES:
                x_centro = int((i + 0.5) * paso_canal)
                cv2.putText(
                    frame,
                    f"CANAL {i}",
                    (x_centro - 28, 48),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.36,
                    (130, 145, 160),
                    1,
                    cv2.LINE_AA,
                )

        # 2. Línea de disparo horizontal roja en Y = 500
        y_disparo = min(self.linea_disparo_y, h - 5)
        cv2.line(frame, (0, y_disparo), (w, y_disparo), (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(
            frame,
            f"LINEA DE DISPARO (Y={y_disparo})",
            (10, max(18, y_disparo - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (0, 0, 255),
            1,
            cv2.LINE_AA,
        )

    def _dibujar_guias_canales_inferior(self, frame: np.ndarray) -> None:
        """
        Dibuja las líneas divisorias de canales para la cámara inferior (Slave).
        IMPORTANTE: La cámara inferior NO calcula línea de disparo ni dibuja línea roja en Y=500.
        """
        h, w = frame.shape[:2]
        paso_canal = w / float(NUM_CANALES_VIRTUALES)
        for i in range(NUM_CANALES_VIRTUALES + 1):
            x = min(int(round(i * paso_canal)), w - 1)
            cv2.line(frame, (x, 0), (x, h), (170, 175, 180), 1, cv2.LINE_AA)
            if i < NUM_CANALES_VIRTUALES:
                x_centro = int((i + 0.5) * paso_canal)
                cv2.putText(
                    frame,
                    f"CANAL {i}",
                    (x_centro - 28, 48),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.36,
                    (110, 125, 140),
                    1,
                    cv2.LINE_AA,
                )

    def _dibujar_detecciones(self, frame: np.ndarray, detecciones: List[Dict[str, Any]]) -> np.ndarray:
        """
        Dibuja las guías espaciales, línea de disparo, cajas delimitadoras y centroides en la cámara superior.
        - Grano Defecto: Centroide rojo con aro blanco y etiqueta de canal C{canal}.
        - Grano Sano: Centroide verde con aro blanco.
        - Fusión OR: Etiqueta [OR:REV] si el defecto fue descubierto en la cara ventral.
        """
        frame_anotado = frame.copy()
        self._dibujar_guias_canales_y_disparo(frame_anotado)

        for det in detecciones:
            x1, y1, x2, y2 = det["caja"]
            nombre = det.get("nombre_clase", "Grano")
            conf = det.get("confianza", 0.0)
            es_defecto = det.get("es_defecto", False)
            origen = det.get("origen_defecto", "")
            id_seg = det.get("id_seguimiento")

            cx = det.get("x_center")
            cy = det.get("y_center")
            if cx is None or cy is None:
                cx, cy = calcular_centroide((x1, y1, x2, y2))
                det["x_center"] = cx
                det["y_center"] = cy
                det["centroide"] = (cx, cy)

            canal = det.get("canal", asignar_canal(cx))
            det["canal"] = canal

            color = self.COLOR_DEFECTO_BGR if es_defecto else self.COLOR_SANO_BGR

            id_str = f"#{id_seg} " if id_seg is not None else ""
            tag_or = " [OR:REV]" if origen == "BOTTOM" else ""
            etiqueta = f"{id_str}{nombre} {int(conf * 100)}% [C{canal}]{tag_or}"

            # Caja delimitadora (Bounding Box)
            cv2.rectangle(frame_anotado, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(etiqueta, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)
            cv2.rectangle(frame_anotado, (x1, max(0, y1 - th - 6)), (x1 + tw + 6, max(th + 6, y1)), color, -1)
            cv2.putText(
                frame_anotado,
                etiqueta,
                (x1 + 3, max(th, y1 - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.40,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

            # Dibujo del Centroide del grano
            if es_defecto:
                cv2.circle(frame_anotado, (cx, cy), 5, (0, 0, 255), -1, cv2.LINE_AA)
                cv2.circle(frame_anotado, (cx, cy), 8, (255, 255, 255), 1, cv2.LINE_AA)
                if cy >= self.linea_disparo_y:
                    cv2.circle(frame_anotado, (cx, cy), 13, (0, 255, 255), 2, cv2.LINE_AA)
            else:
                cv2.circle(frame_anotado, (cx, cy), 4, self.COLOR_SANO_BGR, -1, cv2.LINE_AA)
                cv2.circle(frame_anotado, (cx, cy), 6, (255, 255, 255), 1, cv2.LINE_AA)

        return frame_anotado

    def _dibujar_detecciones_inferior(
        self, frame: np.ndarray, detecciones_bottom: List[Dict[str, Any]]
    ) -> np.ndarray:
        """
        Dibuja sobre el frame de la cámara inferior únicamente las cajas delimitadoras
        y etiquetas diagnósticas de la cara ventral. Sin línea de disparo.
        """
        frame_anotado = frame.copy()
        self._dibujar_guias_canales_inferior(frame_anotado)

        for det in detecciones_bottom:
            x1, y1, x2, y2 = det["caja"]
            nombre = det.get("nombre_clase", "Ventral")
            conf = det.get("confianza", 0.0)
            es_defecto = det.get("es_defecto", False)
            cx = det.get("x_center", 0)
            cy = det.get("y_center", 0)
            canal = det.get("canal", asignar_canal(cx))

            color = self.COLOR_DEFECTO_BGR if es_defecto else self.COLOR_SANO_BGR
            etiqueta = f"[Ventral] {nombre} {int(conf * 100)}% [C{canal}]"

            cv2.rectangle(frame_anotado, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(etiqueta, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)
            cv2.rectangle(frame_anotado, (x1, max(0, y1 - th - 6)), (x1 + tw + 6, max(th + 6, y1)), color, -1)
            cv2.putText(
                frame_anotado,
                etiqueta,
                (x1 + 3, max(th, y1 - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.40,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

            # Centroide ventral
            if es_defecto:
                cv2.circle(frame_anotado, (cx, cy), 5, (0, 0, 255), -1, cv2.LINE_AA)
                cv2.circle(frame_anotado, (cx, cy), 8, (255, 255, 255), 1, cv2.LINE_AA)
            else:
                cv2.circle(frame_anotado, (cx, cy), 4, self.COLOR_SANO_BGR, -1, cv2.LINE_AA)

        # Barra de estado superior para cámara esclava
        h, w = frame_anotado.shape[:2]
        header_h = min(36, h)
        sub = frame_anotado[0:header_h, 0:w]
        overlay = np.full_like(sub, (40, 45, 55))
        cv2.addWeighted(overlay, 0.85, sub, 0.15, 0, sub)
        cv2.putText(
            frame_anotado,
            "CÁMARA INFERIOR (VENTRAL - ESCLAVA) | SIN DISPARO DIRECTO",
            (12, 23),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.40,
            (220, 220, 220),
            1,
            cv2.LINE_AA,
        )
        return frame_anotado

    def _dibujar_hud(
        self,
        frame: np.ndarray,
        fps: float,
        latencia_ms: float,
        valvula_activa: bool,
        total_granos: int,
    ) -> None:
        """Dibuja la barra de telemetría superior optimizada para máxima velocidad."""
        h, w = frame.shape[:2]
        header_h = min(36, h)
        sub = frame[0:header_h, 0:w]
        overlay = np.full_like(sub, (30, 25, 20))
        cv2.addWeighted(overlay, 0.85, sub, 0.15, 0, sub)

        if self.clasificacion_activa:
            texto = f"FPS: {fps:.1f} | Latencia: {latencia_ms:.1f}ms | Granos: {total_granos}"
            color_valvula = (0, 220, 0) if valvula_activa else (120, 120, 120)
            estado_valvula = "ESP32: DISPARO" if valvula_activa else "ESP32: STANDBY"
        else:
            texto = f"FPS: {fps:.1f} | MODO: VISTA PREVIA DUAL (Inferencia en Espera)"
            color_valvula = (120, 120, 120)
            estado_valvula = "ESP32: STANDBY"

        cv2.putText(frame, texto, (12, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.circle(frame, (w - 170, 18), 6, color_valvula, -1)
        cv2.putText(frame, estado_valvula, (w - 155, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (220, 220, 220), 1, cv2.LINE_AA)

    def _generar_frame_sintetico(self) -> np.ndarray:
        """Genera un fondo sintético animado para la cámara superior (Master)."""
        w, h = self.resolucion_captura
        frame = np.full((h, w, 3), (240, 238, 235), dtype=np.uint8)

        cv2.rectangle(frame, (40, 45), (w - 40, h - 45), (210, 205, 200), -1)
        cv2.rectangle(frame, (40, 45), (w - 40, h - 45), (160, 150, 140), 2)

        offset = int(time.time() * 60) % 40
        for y in range(45 + offset, h - 45, 40):
            cv2.line(frame, (45, y), (w - 45, y), (195, 190, 185), 1)

        return frame

    def _generar_frame_sintetico_inferior(self) -> np.ndarray:
        """Genera un fondo sintético animado para la cámara inferior (Slave / Ventral)."""
        w, h = self.resolucion_captura
        frame = np.full((h, w, 3), (225, 230, 235), dtype=np.uint8)

        cv2.rectangle(frame, (40, 45), (w - 40, h - 45), (190, 195, 200), -1)
        cv2.rectangle(frame, (40, 45), (w - 40, h - 45), (140, 145, 150), 2)

        offset = int(time.time() * 60) % 40
        for y in range(45 + offset, h - 45, 40):
            cv2.line(frame, (45, y), (w - 45, y), (180, 185, 190), 1)

        return frame

    def _simular_detecciones(self, shape: tuple) -> List[Dict[str, Any]]:
        """Genera detecciones de prueba con coordenadas espaciales completas para el modo demo."""
        h, w = shape[:2]
        import random
        num_granos = random.randint(1, 3)
        detecciones = []
        if self.es_modo_13clases:
            ids = [0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9, 9, 10, 11, 12]
            nombre_map = self.NOMBRES_CLASES_DEFECTO
            es_sano_fn = lambda cid, nom: cid in (2, 9) or "Bueno" in nom
        else:
            ids = [0, 0, 1, 1, 2]
            nombre_map = self.NOMBRES_CLASES_TRICLASE
            es_sano_fn = lambda cid, nom: cid in (0, 1) or "Bueno" in nom

        for _ in range(num_granos):
            gx = random.randint(50, max(70, w - 140))
            gy = random.randint(60, max(100, h - 90))
            gw = random.randint(45, 75)
            gh = random.randint(35, 60)
            c_id = random.choice(ids)
            nombre = nombre_map.get(c_id, "Arabica_Bueno")
            es_sano = es_sano_fn(c_id, nombre)

            caja = (gx, gy, gx + gw, gy + gh)
            cx, cy = calcular_centroide(caja)
            canal = asignar_canal(cx)

            detecciones.append({
                "clase_id": c_id,
                "nombre_clase": nombre,
                "confianza": round(random.uniform(0.78, 0.96), 2),
                "caja": caja,
                "centroide": (cx, cy),
                "x_center": cx,
                "y_center": cy,
                "canal": canal,
                "es_defecto": not es_sano,
            })
        return detecciones

    def _simular_detecciones_bottom(
        self, detecciones_top: List[Dict[str, Any]], shape: tuple
    ) -> List[Dict[str, Any]]:
        """
        Simula detecciones en la cara ventral sincronizadas espacialmente con las detecciones
        de la cámara superior para validar la fusión OR en modo demo/offline.
        """
        import random
        detecciones_bot = []
        for det_top in detecciones_top:
            if random.random() < 0.85:
                cx_top = det_top.get("x_center", 320)
                cy_top = det_top.get("y_center", 320)
                # Pequeña variación espacial delta_x <= 15 px (dentro de tolerancia_x 25 px)
                delta_x = random.randint(-12, 12)
                cx_bot = max(20, min(620, cx_top + delta_x))
                cy_bot = max(20, min(620, cy_top + random.randint(-15, 15)))
                canal = asignar_canal(cx_bot)

                top_es_def = det_top.get("es_defecto", False)
                if self.es_modo_13clases:
                    if not top_es_def and random.random() < 0.35:
                        c_id = 1  # Brocado ventral en grano aparentemente sano arriba
                        nombre = "Arabica_Brocado"
                        es_def = True
                    elif top_es_def:
                        c_id = det_top.get("clase_id", 1)
                        nombre = det_top.get("nombre_clase", "Arabica_Brocado")
                        es_def = True
                    else:
                        c_id = 2
                        nombre = "Arabica_Bueno"
                        es_def = False
                else:
                    if not top_es_def and random.random() < 0.35:
                        c_id = 2  # Grano_Defecto ventral
                        nombre = "Grano_Defecto"
                        es_def = True
                    elif top_es_def:
                        c_id = 2
                        nombre = "Grano_Defecto"
                        es_def = True
                    else:
                        c_id = det_top.get("clase_id", 0)
                        nombre = self.NOMBRES_CLASES_TRICLASE.get(c_id, "Arabica_Bueno")
                        es_def = False

                gw = random.randint(45, 75)
                gh = random.randint(35, 60)
                caja = (cx_bot - gw // 2, cy_bot - gh // 2, cx_bot + gw // 2, cy_bot + gh // 2)

                detecciones_bot.append({
                    "clase_id": c_id,
                    "nombre_clase": nombre,
                    "confianza": round(random.uniform(0.75, 0.95), 2),
                    "caja": caja,
                    "centroide": (cx_bot, cy_bot),
                    "x_center": cx_bot,
                    "y_center": cy_bot,
                    "canal": canal,
                    "es_defecto": es_def,
                    "es_camara_inferior": True,
                })
        return detecciones_bot

    def _frame_a_bytes(self, frame: np.ndarray) -> bytes:
        """Convierte frame BGR a bytes JPEG."""
        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ret:
            return b""
        return buffer.tobytes()

    def _frame_a_base64(self, frame: np.ndarray) -> str:
        """Convierte frame BGR a cadena base64 JPEG."""
        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ret:
            return ""
        return base64.b64encode(buffer).decode("utf-8")

    def _procesar_frame(self, frame: np.ndarray) -> tuple:
        """Compatibilidad para tests unitarios."""
        dets_top = self._ejecutar_inferencia(frame)
        dets_bot = self._ejecutar_inferencia_bottom(frame, dets_top)
        dets_fused = fusionar_detecciones_doble_camara(dets_top, dets_bot, self.tolerancia_x_match)
        self._evaluar_disparo_esp32(dets_fused)
        dibujado = self._dibujar_detecciones(frame, dets_fused)
        return dets_fused, dibujado

    def _procesar_frame_dual(self, frame_top: np.ndarray, frame_bottom: np.ndarray) -> tuple:
        """Procesamiento síncrono para inspección dual y tests unitarios."""
        dets_top = self._ejecutar_inferencia(frame_top)
        dets_bot = self._ejecutar_inferencia_bottom(frame_bottom, dets_top)
        dets_fused = fusionar_detecciones_doble_camara(dets_top, dets_bot, self.tolerancia_x_match)
        self._evaluar_disparo_esp32(dets_fused)
        dibujado_top = self._dibujar_detecciones(frame_top, dets_fused)
        dibujado_bot = self._dibujar_detecciones_inferior(frame_bottom, dets_bot)
        return dets_fused, dibujado_top, dibujado_bot
