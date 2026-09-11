"""
Capa de Detección en Tiempo Real (Productor Asíncrono Desacoplado)
Arquitectura de Doble Hilo:
1. Hilo de Captura: Adquiere frames a 30 FPS continuos y renderiza cajas para visualización ultra-fluida.
2. Hilo de Inferencia: Ejecuta YOLO en segundo plano sin congelar la tasa de cuadros de la cámara.
"""

import cv2
import base64
import time
import threading
import queue
import numpy as np
from typing import Dict, Any, List, Optional, Union, Tuple, Callable


# =====================================================================
# CONSTANTES DE MAPEO ESPACIAL Y ACTUACIÓN MECATRÓNICA (ESP32)
# =====================================================================
ANCHO_BANDA_PX: int = 640
ALTO_FRAME_PX: int = 640
NUM_CANALES_VIRTUALES: int = 4
ANCHO_CANAL_PX: int = 160        # 640 / 4 = 160 px para las 5 líneas divisorias de canales
NUM_CARRILES_ACTUACION: int = 4  # 4 carriles virtuales para la neumática
ANCHO_CARRIL_PX: int = 160       # canal = int(x_center // 160)
LINEA_DISPARO_Y: int = 500       # Y = 500 coordenada de activación para válvulas ESP32


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


class YOLODetector:
    """
    Productor multihilo de detección de granos de café.
    Separa la captura de video (30 FPS) de la inferencia de red neuronal para fluidez total.
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
    ):
        """
        :param ruta_modelo: Ruta al archivo de pesos .pt entrenado.
        :param fuente_video: Índice de cámara (0, 1), ruta de video o 'demo'.
        :param cola_salida: Cola thread-safe donde se depositan los payloads para la UI.
        :param confianza_minima: Umbral mínimo de confianza para registrar una detección.
        :param resolucion_captura: Tupla (ancho, alto) para la captura de video (default 640x640).
        :param linea_disparo_y: Coordenada Y de la línea horizontal de disparo ESP32 (default 500).
        :param callback_actuacion: Función callback opcional invocada al disparar una válvula neumática.
        :param esp32_bridge: Instancia de ESP32Bridge para control de electroválvulas mecatrónicas.
        """
        self.ruta_modelo = ruta_modelo
        self.fuente_video = fuente_video
        self.cola_salida = cola_salida if cola_salida is not None else queue.Queue(maxsize=3)
        self.confianza_minima = confianza_minima
        self.resolucion_captura = resolucion_captura
        self.linea_disparo_y = linea_disparo_y
        self.callback_actuacion = callback_actuacion
        self.esp32_bridge = esp32_bridge

        # Estado del detector
        self._ejecutando = False
        self._pausado = False
        self.clasificacion_activa = False
        self._solicitud_cambio_fuente: Optional[Union[int, str]] = None
        self._lock = threading.RLock()

        # Modelo YOLO
        self.modelo = None
        self.modo_simulado = False
        self._inicializar_modelo()

        # Telemetría y estado compartido entre hilos
        self._frame_reciente: Optional[np.ndarray] = None
        self._ultimas_detecciones: List[Dict[str, Any]] = []
        self._latencia_inferencia_ms: float = 0.0
        self._fps_captura: float = 30.0
        self._hilo_captura: Optional[threading.Thread] = None
        self._hilo_inferencia: Optional[threading.Thread] = None

        # Objeto de captura OpenCV
        self._cap = None

    def _inicializar_modelo(self) -> None:
        """Carga el modelo Ultralytics YOLO buscando en rutas comunes o activa modo simulado."""
        import os
        ruta_encontrada = None
        if self.ruta_modelo and os.path.exists(self.ruta_modelo):
            ruta_encontrada = self.ruta_modelo
        elif self.ruta_modelo in ("best.pt", "models/best.pt", "weights/best.pt", None, ""):
            for cand in ["models/best.pt", "best.pt", "weights/best.pt"]:
                if os.path.exists(cand):
                    ruta_encontrada = cand
                    break

        try:
            from ultralytics import YOLO
            if ruta_encontrada:
                print(f"[YOLODetector] Modelo detectado exitosamente: {ruta_encontrada}")
                self.modelo = YOLO(ruta_encontrada)
                self.ruta_modelo = ruta_encontrada
                self.modo_simulado = False
            else:
                print(f"[YOLODetector] Modelo '{self.ruta_modelo}' no encontrado. Operando en modo demostrativo/simulado.")
                self.modo_simulado = True
        except ImportError:
            print("[YOLODetector] Ultralytics no disponible. Activando modo simulador sintético.")
            self.modo_simulado = True
        except Exception as e:
            print(f"[YOLODetector] Advertencia al cargar YOLO ({e}). Usando modo simulador.")
            self.modo_simulado = True

    def iniciar(self) -> bool:
        """
        Inicia los hilos de captura de video para visualización en vivo (modo preview).
        La inferencia del modelo YOLO permanece en espera hasta llamar a iniciar_clasificacion().
        """
        with self._lock:
            if self._ejecutando:
                return True

            self._ejecutando = True
            self._pausado = False
            self.clasificacion_activa = False

            # Iniciar hilo 1: Captura de Video continua a 30 FPS
            self._hilo_captura = threading.Thread(
                target=self._bucle_captura_video,
                daemon=True,
                name="HiloCapturaVideo"
            )
            self._hilo_captura.start()

            # Iniciar hilo 2: Inferencia YOLO en paralelo (en espera de activación)
            self._hilo_inferencia = threading.Thread(
                target=self._bucle_inferencia_yolo,
                daemon=True,
                name="HiloInferenciaYOLO"
            )
            self._hilo_inferencia.start()
            return True

    def iniciar_clasificacion(self) -> None:
        """Activa la inferencia del modelo YOLO y la clasificación continua."""
        with self._lock:
            self.clasificacion_activa = True
            self._pausado = False

    def pausar(self) -> None:
        """Pausa la clasificación y detiene la inferencia de YOLO (mantiene preview de cámara)."""
        with self._lock:
            self.clasificacion_activa = False
            self._ultimas_detecciones = []
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
            self._latencia_inferencia_ms = 0.0

    def detener(self) -> None:
        """Detiene completamente la captura y libera el hardware de la cámara."""
        with self._lock:
            self._ejecutando = False
            self._pausado = False
            self.clasificacion_activa = False

        if self._hilo_captura and self._hilo_captura.is_alive():
            self._hilo_captura.join(timeout=1.0)
        if self._hilo_inferencia and self._hilo_inferencia.is_alive():
            self._hilo_inferencia.join(timeout=1.0)

        self._liberar_camara()

    def cambiar_fuente(self, nueva_fuente: Union[int, str]) -> None:
        """
        Solicita el cambio de fuente de video de forma segura y thread-safe
        para evitar colisiones con el hilo de captura OpenCV.
        """
        with self._lock:
            self._solicitud_cambio_fuente = nueva_fuente

    def _abrir_camara(self) -> bool:
        """Abre la cámara web o archivo con backend DirectShow en Windows para latencia cero."""
        if str(self.fuente_video).lower() in ("demo", "simulado", "synthetic"):
            print("[YOLODetector] Modo Simulación (Demo) seleccionado.")
            return True

        try:
            fuente = int(self.fuente_video) if str(self.fuente_video).isdigit() else self.fuente_video
            if isinstance(fuente, int):
                self._cap = cv2.VideoCapture(fuente, cv2.CAP_DSHOW)
                if not self._cap or not self._cap.isOpened():
                    self._cap = cv2.VideoCapture(fuente)
            else:
                self._cap = cv2.VideoCapture(fuente)

            if not self._cap or not self._cap.isOpened():
                print(f"[YOLODetector] Cámara {self.fuente_video} no disponible. Activando generador demostrativo.")
                self.fuente_video = "demo"
                return True

            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolucion_captura[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolucion_captura[1])
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            print(f"[YOLODetector] Cámara {fuente} abierta exitosamente.")
            return True
        except Exception as e:
            print(f"[YOLODetector] Error al abrir cámara ({e}). Usando modo demo.")
            self.fuente_video = "demo"
            return True

    def _liberar_camara(self) -> None:
        """Libera los recursos de la cámara con seguridad."""
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _bucle_captura_video(self) -> None:
        """
        Hilo 1: Adquiere frames a alta frecuencia (~30-60 FPS), aplica anotaciones si está
        activa la clasificación y despacha a la cola de la UI.
        """
        self._abrir_camara()
        ultimo_tiempo = time.perf_counter()

        while self._ejecutando:
            # 0. Atender solicitudes de cambio de cámara en caliente de forma segura
            if self._solicitud_cambio_fuente is not None:
                with self._lock:
                    nueva = self._solicitud_cambio_fuente
                    self._solicitud_cambio_fuente = None
                    self._liberar_camara()
                    self.fuente_video = nueva
                    self._abrir_camara()
                    self._ultimas_detecciones = []
                    self._latencia_inferencia_ms = 0.0

            t_inicio = time.perf_counter()

            # 1. Leer frame
            frame = self._leer_frame()
            if frame is None:
                if isinstance(self.fuente_video, str) and self.fuente_video != "demo" and self._cap:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                time.sleep(0.02)
                continue

            # Guardar frame para el hilo de inferencia
            with self._lock:
                self._frame_reciente = frame.copy()
                if self.clasificacion_activa:
                    detecciones_actuales = list(self._ultimas_detecciones)
                    latencia_ms = self._latencia_inferencia_ms
                else:
                    detecciones_actuales = []
                    latencia_ms = 0.0

            # 2. Calcular FPS de la cámara
            t_ahora = time.perf_counter()
            delta = t_ahora - ultimo_tiempo
            ultimo_tiempo = t_ahora
            fps = 1.0 / max(delta, 1e-4)
            self._fps_captura = fps

            # 3. Dibujar cajas de detección, guías espaciales y evaluar disparo a ESP32
            if self.clasificacion_activa and detecciones_actuales:
                self._evaluar_disparo_esp32(detecciones_actuales)
                frame_anotado = self._dibujar_detecciones(frame, detecciones_actuales)
            else:
                frame_anotado = frame.copy()
                self._dibujar_guias_canales_y_disparo(frame_anotado)

            # 4. Telemetría y estado de válvula neumática
            valvula_activa = any(
                d.get("es_defecto", False) and d.get("y_center", 0) >= self.linea_disparo_y
                for d in detecciones_actuales
            ) if self.clasificacion_activa else False

            self._dibujar_hud(frame_anotado, fps, latencia_ms, valvula_activa, len(detecciones_actuales))

            # 5. Codificar imagen a Base64 Data URI y Bytes
            frame_bytes = self._frame_a_bytes(frame_anotado)
            frame_b64 = self._frame_a_base64(frame_anotado)

            payload = {
                "frame_bgr": frame_anotado,
                "frame_bytes": frame_bytes,
                "frame_base64": frame_b64,
                "frame_src": f"data:image/jpeg;base64,{frame_b64}",
                "detecciones": detecciones_actuales,
                "fps": round(fps, 1),
                "latencia_ms": round(latencia_ms, 1),
                "valvula_activa": valvula_activa,
                "total_detectados": len(detecciones_actuales),
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
        Hilo 2: Ejecuta inferencia YOLO en paralelo únicamente cuando la clasificación está activa.
        En modo vista previa (preview), se suspende para no consumir CPU/GPU y permitir streaming limpio.
        """
        while self._ejecutando:
            if not self.clasificacion_activa:
                with self._lock:
                    self._ultimas_detecciones = []
                    self._latencia_inferencia_ms = 0.0
                time.sleep(0.05)
                continue

            frame_para_inferir = None
            with self._lock:
                if self._frame_reciente is not None:
                    frame_para_inferir = self._frame_reciente.copy()

            if frame_para_inferir is None:
                time.sleep(0.03)
                continue

            t0 = time.perf_counter()
            detecciones = self._ejecutar_inferencia(frame_para_inferir)
            t1 = time.perf_counter()
            latencia_ms = (t1 - t0) * 1000.0

            with self._lock:
                self._ultimas_detecciones = detecciones
                self._latencia_inferencia_ms = latencia_ms

            # Pequeña pausa para no saturar 100% el CPU
            time.sleep(0.02)

    def _leer_frame(self) -> Optional[np.ndarray]:
        """Captura un frame de OpenCV o genera el frame sintético de prueba."""
        if str(self.fuente_video).lower() in ("demo", "simulado", "synthetic") or self._cap is None:
            return self._generar_frame_sintetico()

        ret, frame = self._cap.read()
        if not ret or frame is None:
            return None
        return frame

    def _ejecutar_inferencia(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """Ejecuta YOLOv8/v11 optimizado con resolución adaptativa y mapeo espacial."""
        if self.modo_simulado or self.modelo is None or str(self.fuente_video).lower() in ("demo", "simulado", "synthetic"):
            return self._simular_detecciones(frame.shape)

        detecciones = []
        try:
            # Inferencia con Ultralytics con imgsz=320 para alta velocidad en CPU
            resultados = self.modelo(frame, imgsz=320, conf=self.confianza_minima, verbose=False)
            for r in resultados:
                for box in r.boxes:
                    clase_id = int(box.cls[0].item())
                    confianza = float(box.conf[0].item())
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]

                    nombre_clase = self.NOMBRES_CLASES_DEFECTO.get(clase_id, f"Clase_{clase_id}")
                    es_sano = clase_id in (2, 9) or "Bueno" in nombre_clase
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
            print(f"[YOLODetector] Error en inferencia: {e}")
            detecciones = []
        return detecciones

    def _evaluar_disparo_esp32(self, detecciones: List[Dict[str, Any]]) -> List[int]:
        """
        Lógica de Disparo (Preparación para ESP32):
        Si el y_center del defecto cruza la línea horizontal (y_center >= 500),
        el sistema imprime en consola un mensaje estructurado:
        [ACTUACION] Defecto en Canal {canal} - Enviando señal a ESP32...
        Si es grano bueno (Arabica_Bueno o Robusta_Bueno), se deja pasar sin activar.
        """
        canales_disparados = []
        for det in detecciones:
            if det.get("es_defecto", False):
                y_center = det.get("y_center", 0)
                canal = det.get("canal", 0)
                if y_center >= self.linea_disparo_y:
                    canales_disparados.append(canal)
                    print(f"[ACTUACION] Defecto en Canal {canal} - Enviando señal a ESP32...")
                    if self.esp32_bridge:
                        try:
                            self.esp32_bridge.disparar_canal(canal)
                        except Exception as e:
                            print(f"[YOLODetector] Error al disparar canal en ESP32: {e}")
                    if self.callback_actuacion:
                        try:
                            self.callback_actuacion(canal, det)
                        except Exception as e:
                            print(f"[YOLODetector] Error en callback de actuación: {e}")
        return canales_disparados

    def _dibujar_guias_canales_y_disparo(self, frame: np.ndarray) -> None:
        """
        Dibuja sobre el frame:
        1. 5 líneas verticales divisorias para separar visualmente los 4 canales virtuales (cada 160 px en 640 px).
        2. Línea horizontal roja en Y = 500 ('Línea de Disparo' / Trigger Line).
        Optimizado con primitivas vectorizadas de OpenCV para cero impacto en FPS.
        """
        h, w = frame.shape[:2]

        # 1. 5 Líneas verticales divisorias para 4 canales (x = 0, 160, 320, 480, 639)
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

    def _dibujar_detecciones(self, frame: np.ndarray, detecciones: List[Dict[str, Any]]) -> np.ndarray:
        """
        Dibuja las guías espaciales, línea de disparo, cajas delimitadoras y centroides.
        - Grano Defecto: Centroide rojo con aro blanco y etiqueta de canal C{canal}.
        - Grano Sano: Centroide verde con aro blanco.
        """
        frame_anotado = frame.copy()
        self._dibujar_guias_canales_y_disparo(frame_anotado)

        for det in detecciones:
            x1, y1, x2, y2 = det["caja"]
            nombre = det.get("nombre_clase", "Grano")
            conf = det.get("confianza", 0.0)
            es_defecto = det.get("es_defecto", False)

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
            etiqueta = f"{nombre} {int(conf * 100)}% [C{canal}]"

            # Caja delimitadora (Bounding Box)
            cv2.rectangle(frame_anotado, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(etiqueta, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
            cv2.rectangle(frame_anotado, (x1, max(0, y1 - th - 6)), (x1 + tw + 6, max(th + 6, y1)), color, -1)
            cv2.putText(
                frame_anotado,
                etiqueta,
                (x1 + 3, max(th, y1 - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

            # Dibujo del Centroide del grano
            if es_defecto:
                # Centroide rojo con aro blanco
                cv2.circle(frame_anotado, (cx, cy), 5, (0, 0, 255), -1, cv2.LINE_AA)
                cv2.circle(frame_anotado, (cx, cy), 8, (255, 255, 255), 1, cv2.LINE_AA)
                if cy >= self.linea_disparo_y:
                    # Halo amarillo de advertencia cuando cruza la línea de disparo
                    cv2.circle(frame_anotado, (cx, cy), 13, (0, 255, 255), 2, cv2.LINE_AA)
            else:
                # Grano sano: centroide verde con aro blanco
                cv2.circle(frame_anotado, (cx, cy), 4, self.COLOR_SANO_BGR, -1, cv2.LINE_AA)
                cv2.circle(frame_anotado, (cx, cy), 6, (255, 255, 255), 1, cv2.LINE_AA)

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
            texto = f"FPS: {fps:.1f} | MODO: VISTA PREVIA (Inferencia en Espera)"
            color_valvula = (120, 120, 120)
            estado_valvula = "ESP32: STANDBY"

        cv2.putText(frame, texto, (12, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.circle(frame, (w - 170, 18), 6, color_valvula, -1)
        cv2.putText(frame, estado_valvula, (w - 155, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1, cv2.LINE_AA)

    def _generar_frame_sintetico(self) -> np.ndarray:
        """Genera un fondo sintético animado para pruebas sin cámara."""
        w, h = self.resolucion_captura
        frame = np.full((h, w, 3), (240, 238, 235), dtype=np.uint8)

        cv2.rectangle(frame, (40, 45), (w - 40, h - 45), (210, 205, 200), -1)
        cv2.rectangle(frame, (40, 45), (w - 40, h - 45), (160, 150, 140), 2)

        offset = int(time.time() * 60) % 40
        for y in range(45 + offset, h - 45, 40):
            cv2.line(frame, (45, y), (w - 45, y), (195, 190, 185), 1)

        return frame

    def _simular_detecciones(self, shape: tuple) -> List[Dict[str, Any]]:
        """Genera detecciones de prueba con coordenadas espaciales completas para el modo demo."""
        h, w = shape[:2]
        import random
        num_granos = random.randint(1, 3)
        detecciones = []
        ids = [0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9, 9, 10, 11, 12]
        for _ in range(num_granos):
            gx = random.randint(50, max(70, w - 140))
            gy = random.randint(60, max(100, h - 90))
            gw = random.randint(45, 75)
            gh = random.randint(35, 60)
            c_id = random.choice(ids)
            nombre = self.NOMBRES_CLASES_DEFECTO.get(c_id, "Arabica_Bueno")
            es_sano = c_id in (2, 9) or "Bueno" in nombre

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
        dets = self._ejecutar_inferencia(frame)
        self._evaluar_disparo_esp32(dets)
        dibujado = self._dibujar_detecciones(frame, dets)
        return dets, dibujado
