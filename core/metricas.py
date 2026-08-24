"""
Capa de Métricas y Cálculos de Operación
Responsable de llevar el cronometraje de sesión, cálculo de consumo eléctrico (kWh),
conteo de granos (sanos vs. defectuosos), distribución de defectos, latencia y FPS.
"""

import time
import threading
from typing import Dict, Any, List, Optional


class GestorMetricas:
    """
    Gestiona y calcula en tiempo real las métricas analíticas del clasificador de granos.
    Implementa thread-safety para permitir lecturas desde la UI y escrituras desde el detector.
    """

    # Definición de clases según el esquema de 13 etiquetas del dataset (data.yaml)
    NOMBRES_CLASES = {
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

    CLASES_SANAS = {2, 9, "Arabica_Bueno", "Robusta_Bueno"}

    CATEGORIAS_DEFECTOS = [
        "Brocado",
        "Agrio",
        "Negro",
        "Quebrado",
        "Cereza",
        "Concha",
        "Inmaduro"
    ]

    def __init__(self, potencia_nominal_kw: float = 0.5):
        """
        :param potencia_nominal_kw: Potencia nominal del hardware (computadora + compresor/válvulas) en kW.
        """
        self.potencia_nominal_kw: float = potencia_nominal_kw
        self._lock = threading.RLock()

        # Tiempos de operación
        self.tiempo_inicio: Optional[float] = None
        self.tiempo_pausa_acumulado: float = 0.0
        self.momento_pausa: Optional[float] = None
        self.esta_activo: bool = False

        # Contadores de granos
        self.total_granos: int = 0
        self.total_sanos: int = 0
        self.total_defectuosos: int = 0
        self.conteo_por_clase: Dict[str, int] = {nombre: 0 for nombre in self.NOMBRES_CLASES.values()}
        self.conteo_por_defecto: Dict[str, int] = {cat: 0 for cat in self.CATEGORIAS_DEFECTOS}

        # Rendimiento de inferencia
        self.fps_actual: float = 0.0
        self.latencia_actual_ms: float = 0.0
        self.historial_latencias: List[float] = []
        self.historial_fps: List[float] = []

    def iniciar_sesion(self) -> None:
        """Inicia o reanuda el cronómetro de la sesión activa."""
        with self._lock:
            ahora = time.time()
            if self.tiempo_inicio is None:
                self.tiempo_inicio = ahora
            elif self.momento_pausa is not None:
                self.tiempo_pausa_acumulado += (ahora - self.momento_pausa)
                self.momento_pausa = None
            self.esta_activo = True

    def pausar_sesion(self) -> None:
        """Pausa el cronómetro de operación."""
        with self._lock:
            if self.esta_activo and self.momento_pausa is None:
                self.momento_pausa = time.time()
                self.esta_activo = False

    def reiniciar(self) -> None:
        """Restablece todos los contadores y cronómetros a cero."""
        with self._lock:
            self.tiempo_inicio = None
            self.tiempo_pausa_acumulado = 0.0
            self.momento_pausa = None
            self.esta_activo = False

            self.total_granos = 0
            self.total_sanos = 0
            self.total_defectuosos = 0
            self.conteo_por_clase = {nombre: 0 for nombre in self.NOMBRES_CLASES.values()}
            self.conteo_por_defecto = {cat: 0 for cat in self.CATEGORIAS_DEFECTOS}

            self.fps_actual = 0.0
            self.latencia_actual_ms = 0.0
            self.historial_latencias.clear()
            self.historial_fps.clear()

    def registrar_detecciones(
        self,
        detecciones: List[Dict[str, Any]],
        fps: float,
        latencia_ms: float
    ) -> None:
        """
        Registra un lote de detecciones del frame actual.
        
        :param detecciones: Lista de diccionarios con 'clase_id', 'nombre_clase', 'confianza', etc.
        :param fps: FPS instantáneo del detector.
        :param latencia_ms: Latencia de inferencia en milisegundos.
        """
        with self._lock:
            self.fps_actual = fps
            self.latencia_actual_ms = latencia_ms

            if len(self.historial_fps) > 100:
                self.historial_fps.pop(0)
            self.historial_fps.append(fps)

            if len(self.historial_latencias) > 100:
                self.historial_latencias.pop(0)
            self.historial_latencias.append(latencia_ms)

            for det in detecciones:
                clase_id = det.get("clase_id")
                nombre_clase = det.get("nombre_clase")

                if nombre_clase is None and clase_id in self.NOMBRES_CLASES:
                    nombre_clase = self.NOMBRES_CLASES[clase_id]

                if not nombre_clase:
                    continue

                self.total_granos += 1
                self.conteo_por_clase[nombre_clase] = self.conteo_por_clase.get(nombre_clase, 0) + 1

                # Clasificar en Sano o Defectuoso
                if clase_id in self.CLASES_SANAS or nombre_clase in self.CLASES_SANAS:
                    self.total_sanos += 1
                else:
                    self.total_defectuosos += 1
                    # Extraer categoría de defecto (e.g. "Arabica_Brocado" -> "Brocado")
                    categoria = self._extraer_categoria_defecto(nombre_clase)
                    if categoria in self.conteo_por_defecto:
                        self.conteo_por_defecto[categoria] += 1
                    else:
                        self.conteo_por_defecto[categoria] = 1

    def _extraer_categoria_defecto(self, nombre_clase: str) -> str:
        """Normaliza el nombre de la clase al tipo genérico de defecto."""
        partes = nombre_clase.split("_")
        if len(partes) > 1:
            return partes[1]
        return nombre_clase

    def obtener_segundos_activos(self) -> float:
        """Calcula el tiempo neto transcurrido de operación activa en segundos."""
        if self.tiempo_inicio is None:
            return 0.0
        
        ahora = time.time()
        if self.esta_activo:
            tiempo_bruto = ahora - self.tiempo_inicio
            return max(0.0, tiempo_bruto - self.tiempo_pausa_acumulado)
        else:
            if self.momento_pausa is not None:
                tiempo_bruto = self.momento_pausa - self.tiempo_inicio
                return max(0.0, tiempo_bruto - self.tiempo_pausa_acumulado)
            return 0.0

    def obtener_tiempo_formateado(self) -> str:
        """Devuelve el tiempo transcurrido en formato HH:MM:SS."""
        segundos = int(self.obtener_segundos_activos())
        horas = segundos // 3600
        minutos = (segundos % 3600) // 60
        segs = segundos % 60
        return f"{horas:02d}:{minutos:02d}:{segs:02d} Hrs"

    def calcular_consumo_kwh(self) -> float:
        """
        Calcula el consumo de energía eléctrica acumulada en kWh:
        kWh = Potencia (kW) * Horas de Operación
        """
        segundos = self.obtener_segundos_activos()
        horas = segundos / 3600.0
        return round(self.potencia_nominal_kw * horas, 4)

    def obtener_latencia_promedio(self) -> float:
        """Devuelve la latencia promedio en ms."""
        with self._lock:
            if not self.historial_latencias:
                return 0.0
            return round(sum(self.historial_latencias) / len(self.historial_latencias), 2)

    def obtener_fps_promedio(self) -> float:
        """Devuelve el promedio móvil de FPS."""
        with self._lock:
            if not self.historial_fps:
                return 0.0
            return round(sum(self.historial_fps) / len(self.historial_fps), 1)

    def obtener_porcentaje_calidad(self) -> float:
        """Devuelve el porcentaje de granos sanos sobre el total procesado."""
        with self._lock:
            if self.total_granos == 0:
                return 100.0
            return round((self.total_sanos / self.total_granos) * 100.0, 2)

    def obtener_porcentajes_defectos(self) -> Dict[str, float]:
        """Devuelve la distribución porcentual de cada tipo de defecto."""
        with self._lock:
            if self.total_defectuosos == 0:
                return {k: 0.0 for k in self.CATEGORIAS_DEFECTOS}
            return {
                cat: round((conteo / self.total_defectuosos) * 100.0, 1)
                for cat, conteo in self.conteo_por_defecto.items()
            }

    def generar_resumen_lote(self, id_lote: str = "") -> Dict[str, Any]:
        """
        Genera un diccionario con el reporte completo del lote listo para almacenar en MongoDB Atlas.
        """
        with self._lock:
            ahora_str = time.strftime("%Y-%m-%d %H:%M:%S")
            segundos_op = self.obtener_segundos_activos()
            kwh = self.calcular_consumo_kwh()
            porcentaje_calidad = self.obtener_porcentaje_calidad()

            return {
                "id_lote": id_lote or f"LOTE-{time.strftime('%Y%m%d-%H%M%S')}",
                "timestamp": ahora_str,
                "duracion_segundos": round(segundos_op, 1),
                "duracion_formato": self.obtener_tiempo_formateado(),
                "potencia_nominal_kw": self.potencia_nominal_kw,
                "consumo_kwh": kwh,
                "total_granos": self.total_granos,
                "total_sanos": self.total_sanos,
                "total_defectuosos": self.total_defectuosos,
                "porcentaje_calidad": porcentaje_calidad,
                "conteo_por_defecto": dict(self.conteo_por_defecto),
                "conteo_por_clase": dict(self.conteo_por_clase),
                "latencia_promedio_ms": self.obtener_latencia_promedio(),
                "fps_promedio": self.obtener_fps_promedio(),
            }
