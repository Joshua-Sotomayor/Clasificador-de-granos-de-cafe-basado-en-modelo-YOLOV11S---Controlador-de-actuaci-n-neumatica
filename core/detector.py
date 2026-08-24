"""
Capa de Detección en Tiempo Real (Productor)
Contiene la clase YOLODetector que adquiere frames de video, ejecuta inferencia con YOLO (best.pt),
dibuja las cajas delimitadoras y coloca los resultados en una cola de mensajes (Queue).
"""

import cv2
import base64
import time
import threading
import queue
import numpy as np
from typing import Dict, Any, List, Optional, Union


class YOLODetector:
    """
    Productor multihilo de detección de granos de café.
    Captura video, ejecuta inferencia YOLO y despacha frames renderizados y métricas a una cola.
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
        ruta_modelo: str = "best.pt",
        fuente_video: Union[int, str] = 0,
        cola_salida: Optional[queue.Queue] = None,
        confianza_minima: float = 0.35,
        resolucion_captura: tuple = (640, 480),
    ):
        """
        :param ruta_modelo: Ruta al archivo de pesos .pt entrenado.
        :param fuente_video: Índice de cámara (0, 1), ruta de video .mp4 o 'demo'/'simulado'.
        :param cola_salida: Cola thread-safe donde se depositan los payloads para la UI.
        :param confianza_minima: Umbral mínimo de confianza para registrar una detección.
        :param resolucion_captura: Tupla (ancho, alto) para la captura de video.
        """
        self.ruta_modelo = ruta_modelo
        self.fuente_video = fuente_video
        self.cola_salida = cola_salida if cola_salida is not None else queue.Queue(maxsize=5)
        self.confianza_minima = confianza_minima
        self.resolucion_captura = resolucion_captura

        # Estado del detector
        self._ejecutando = False
        self._pausado = False
        self._hilo: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        # Modelo YOLO
        self.modelo = None
        self.modo_simulado = False
        self._inicializar_modelo()

        # Objeto de captura
        self._cap = None

    def _inicializar_modelo(self) -> None:
        """Carga el modelo Ultralytics YOLO buscando en la ruta especificada o rutas estándar."""
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
        """Inicia el hilo de captura e inferencia en segundo plano."""
        with self._lock:
            if self._ejecutando:
                return True

            self._ejecutando = True
            self._pausado = False
            self._hilo = threading.Thread(target=self._bucle_captura, daemon=True, name="HiloYOLODetector")
            self._hilo.start()
            return True

    def pausar(self) -> None:
        """Pausa temporalmente la adquisición sin destruir el hilo."""
        with self._lock:
            self._pausado = True

    def reanudar(self) -> None:
        """Reanuda la adquisición si estaba pausada."""
        with self._lock:
            self._pausado = False

    def detener(self) -> None:
        """Detiene el hilo y libera los recursos de hardware."""
        with self._lock:
            self._ejecutando = False
            self._pausado = False

        if self._hilo and self._hilo.is_alive():
            self._hilo.join(timeout=1.5)

        self._liberar_camara()

    def cambiar_fuente(self, nueva_fuente: Union[int, str]) -> None:
        """Permite alternar la fuente de video (ej. cambiar entre webcam y video)."""
        estaba_ejecutando = self._ejecutando
        if estaba_ejecutando:
            self.detener()

        self.fuente_video = nueva_fuente
        if estaba_ejecutando:
            self.iniciar()

    def _abrir_camara(self) -> bool:
        """Abre la cámara o archivo de video con DirectShow en Windows para arranque instantáneo."""
        if str(self.fuente_video).lower() in ("demo", "simulado", "synthetic"):
            return True

        try:
            fuente = int(self.fuente_video) if str(self.fuente_video).isdigit() else self.fuente_video
            if isinstance(fuente, int):
                # En Windows, DirectShow previene bloqueos de cámara
                self._cap = cv2.VideoCapture(fuente, cv2.CAP_DSHOW)
                if not self._cap.isOpened():
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
            print(f"[YOLODetector] Cámara {fuente} inicializada correctamente ({self.resolucion_captura[0]}x{self.resolucion_captura[1]}).")
            return True
        except Exception as e:
            print(f"[YOLODetector] Error abriendo cámara ({e}). Pasando a demo.")
            self.fuente_video = "demo"
            return True

    def _liberar_camara(self) -> None:
        """Libera el objeto VideoCapture de OpenCV."""
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _bucle_captura(self) -> None:
        """Ciclo principal de captura ejecutado en segundo plano."""
        self._abrir_camara()
        ultimo_tiempo_frame = time.perf_counter()

        while self._ejecutando:
            if self._pausado:
                time.sleep(0.05)
                continue

            tiempo_inicio_frame = time.perf_counter()

            # 1. Obtener frame
            frame = self._leer_frame()
            if frame is None:
                # Si es un video terminado, reiniciar el video
                if isinstance(self.fuente_video, str) and self.fuente_video != "demo":
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                time.sleep(0.03)
                continue

            # 2. Inferencia y medición de latencia
            t0_inferencia = time.perf_counter()
            detecciones, frame_dibujado = self._procesar_frame(frame)
            t1_inferencia = time.perf_counter()
            latencia_ms = (t1_inferencia - t0_inferencia) * 1000.0

            # 3. Cálculo de FPS instantáneos
            tiempo_actual = time.perf_counter()
            delta_frame = tiempo_actual - ultimo_tiempo_frame
            ultimo_tiempo_frame = tiempo_actual
            fps = 1.0 / max(delta_frame, 1e-4)

            # 4. Señal de control electromecánico (Válvula neumática rápida < 30ms)
            hay_defectos = any(d.get("es_defecto", False) for d in detecciones)
            valvula_activa = hay_defectos and (latencia_ms < 35.0)

            # 5. Dibujar HUD en el frame con datos de telemetría
            self._dibujar_hud(frame_dibujado, fps, latencia_ms, valvula_activa, len(detecciones))

            # 6. Codificar a Bytes y Base64 para Flet
            frame_bytes = self._frame_a_bytes(frame_dibujado)
            frame_b64 = self._frame_a_base64(frame_dibujado)

            # 7. Despachar a la cola (si la cola está llena, descartar frame antiguo para mantener tiempo real)
            payload = {
                "frame_bytes": frame_bytes,
                "frame_base64": frame_b64,
                "detecciones": detecciones,
                "fps": round(fps, 1),
                "latencia_ms": round(latencia_ms, 2),
                "valvula_activa": valvula_activa,
                "total_detectados": len(detecciones),
            }

            if self.cola_salida.full():
                try:
                    self.cola_salida.get_nowait()
                except queue.Empty:
                    pass

            try:
                self.cola_salida.put_nowait(payload)
            except queue.Full:
                pass

            # Control de tasa de muestreo (~30 FPS máximo)
            tiempo_procesamiento = time.perf_counter() - tiempo_inicio_frame
            tiempo_espera = max(0.001, (1.0 / 30.0) - tiempo_procesamiento)
            time.sleep(tiempo_espera)

        self._liberar_camara()

    def _leer_frame(self) -> Optional[np.ndarray]:
        """Adquiere el frame de la cámara o genera un frame sintético."""
        if str(self.fuente_video).lower() in ("demo", "simulado", "synthetic") or self._cap is None:
            return self._generar_frame_sintetico()

        ret, frame = self._cap.read()
        if not ret:
            return None
        return frame

    def _procesar_frame(self, frame: np.ndarray) -> tuple:
        """Ejecuta inferencia y dibuja cajas en el frame."""
        frame_anotado = frame.copy()
        detecciones = []

        if self.modo_simulado or self.modelo is None or str(self.fuente_video).lower() in ("demo", "simulado", "synthetic"):
            detecciones = self._simular_detecciones(frame.shape)
        else:
            try:
                # Inferencia con Ultralytics YOLO
                resultados = self.modelo(frame, conf=self.confianza_minima, verbose=False)
                for r in resultados:
                    for box in r.boxes:
                        clase_id = int(box.cls[0].item())
                        confianza = float(box.conf[0].item())
                        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]

                        nombre_clase = self.NOMBRES_CLASES_DEFECTO.get(clase_id, f"Clase_{clase_id}")
                        es_sano = clase_id in (2, 9) or "Bueno" in nombre_clase

                        detecciones.append({
                            "clase_id": clase_id,
                            "nombre_clase": nombre_clase,
                            "confianza": round(confianza, 2),
                            "caja": (x1, y1, x2, y2),
                            "es_defecto": not es_sano,
                        })
            except Exception as e:
                print(f"[YOLODetector] Error en inferencia: {e}")
                detecciones = self._simular_detecciones(frame.shape)

        # Dibujar cajas en el frame
        for det in detecciones:
            x1, y1, x2, y2 = det["caja"]
            nombre = det["nombre_clase"]
            conf = det["confianza"]
            es_defecto = det.get("es_defecto", False)

            color = self.COLOR_DEFECTO_BGR if es_defecto else self.COLOR_SANO_BGR
            etiqueta = f"{nombre} {int(conf * 100)}%"

            # Rectángulo del grano
            cv2.rectangle(frame_anotado, (x1, y1), (x2, y2), color, 2)

            # Fondo del texto
            (tw, th), _ = cv2.getTextSize(etiqueta, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(frame_anotado, (x1, max(0, y1 - th - 6)), (x1 + tw + 6, max(th + 6, y1)), color, -1)
            cv2.putText(
                frame_anotado,
                etiqueta,
                (x1 + 3, max(th, y1 - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        return detecciones, frame_anotado

    def _dibujar_hud(
        self,
        frame: np.ndarray,
        fps: float,
        latencia_ms: float,
        valvula_activa: bool,
        total_granos: int
    ) -> None:
        """Dibuja barra superior con estado electromecánico."""
        h, w, _ = frame.shape
        # Overlay semi-transparente superior
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 38), (40, 30, 25), -1)
        cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)

        # Texto FPS y Latencia
        texto_telemetria = f"FPS: {fps:.1f} | Latencia: {latencia_ms:.1f}ms | Granos: {total_granos}"
        cv2.putText(frame, texto_telemetria, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)

        # Indicador de Válvula Neumática
        color_valvula = (0, 220, 0) if valvula_activa else (120, 120, 120)
        estado_valvula = "VALVULA: DISPARO ACTIVO" if valvula_activa else "VALVULA: STANDBY"
        cv2.circle(frame, (w - 180, 19), 6, color_valvula, -1)
        cv2.putText(frame, estado_valvula, (w - 165, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1, cv2.LINE_AA)

    def _generar_frame_sintetico(self) -> np.ndarray:
        """Genera un fondo simulado con banda transportadora de granos."""
        w, h = self.resolucion_captura
        frame = np.full((h, w, 3), (240, 238, 235), dtype=np.uint8)

        # Dibujar banda transportadora central
        cv2.rectangle(frame, (80, 50), (w - 80, h - 50), (210, 205, 200), -1)
        cv2.rectangle(frame, (80, 50), (w - 80, h - 50), (160, 150, 140), 2)

        # Líneas guía de la banda
        for y in range(80, h - 50, 40):
            cv2.line(frame, (85, y), (w - 85, y), (195, 190, 185), 1)

        return frame

    def _simular_detecciones(self, shape: tuple) -> List[Dict[str, Any]]:
        """Genera detecciones sintéticas para demostración fluida cuando no hay cámara conectada."""
        h, w = shape[:2]
        import random
        # Generar entre 1 y 4 granos aleatorios dentro de la banda transportadora
        num_granos = random.randint(1, 3)
        detecciones = []

        ids_posibles = [0, 1, 2, 2, 2, 3, 4, 5, 6, 7, 8, 9, 9, 10, 11, 12]
        for _ in range(num_granos):
            gx = random.randint(110, w - 180)
            gy = random.randint(80, h - 140)
            gw = random.randint(45, 75)
            gh = random.randint(35, 60)

            c_id = random.choice(ids_posibles)
            nombre = self.NOMBRES_CLASES_DEFECTO.get(c_id, "Arabica_Bueno")
            es_sano = c_id in (2, 9)

            detecciones.append({
                "clase_id": c_id,
                "nombre_clase": nombre,
                "confianza": round(random.uniform(0.75, 0.96), 2),
                "caja": (gx, gy, gx + gw, gy + gh),
                "es_defecto": not es_sano,
            })
        return detecciones

    def _frame_a_bytes(self, frame: np.ndarray) -> bytes:
        """Convierte frame BGR a bytes JPEG para renderizado directo en Flet."""
        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ret:
            return b""
        return buffer.tobytes()

    def _frame_a_base64(self, frame: np.ndarray) -> str:
        """Convierte frame BGR a cadena base64 JPEG optimizada para Flet."""
        ret, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not ret:
            return ""
        return base64.b64encode(buffer).decode("utf-8")
