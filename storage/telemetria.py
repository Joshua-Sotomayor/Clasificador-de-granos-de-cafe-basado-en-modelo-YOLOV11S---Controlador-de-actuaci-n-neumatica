"""
Módulo de Telemetría de Hardware y Persistencia Anti-Apagones para MOPPI.
Administra el tiempo acumulado de operación de la máquina con almacenamiento
atómico en JSON (storage/estado_maquina.json) para soportar cortes eléctricos abruptos.
"""

import os
import json
import time
import threading
from datetime import datetime
from typing import Optional, Dict, Any


RUTA_ESTADO_DEFAULT = os.path.join(os.path.dirname(__file__), "estado_maquina.json")


class GestorTiempoUso:
    """
    Controla el cómputo y la persistencia del tiempo de uso diario de la clasificadora.
    Garantiza consistencia anti-apagones mediante escrituras atómicas (archivo temporal + os.replace).
    """

    def __init__(
        self,
        ruta_archivo: Optional[str] = None,
        intervalo_guardado_seg: int = 60,
    ) -> None:
        self.ruta_archivo = ruta_archivo or RUTA_ESTADO_DEFAULT
        self.intervalo_guardado_seg = intervalo_guardado_seg
        self._lock = threading.RLock()

        self.fecha_actual: str = datetime.now().strftime("%Y-%m-%d")
        self.segundos_acumulados: int = 0
        self.estado_operativo: str = "STANDBY"
        self.requiere_reset_por_corte: bool = False
        self._ultimo_guardado_ts: float = time.time()
        self._ultimo_tick_ts: Optional[float] = None

        # Cargar estado previo o inicializar
        self.cargar_estado()

    def cargar_estado(self) -> int:
        """
        Lee el archivo storage/estado_maquina.json.
        Si la fecha coincide con hoy, recupera los segundos acumulados.
        Detecta cortes abruptos si el estado previo era 'EN_MARCHA'.
        """
        with self._lock:
            hoy = datetime.now().strftime("%Y-%m-%d")
            self.fecha_actual = hoy

            if os.path.exists(self.ruta_archivo):
                try:
                    with open(self.ruta_archivo, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    fecha_guardada = data.get("fecha", "")
                    if fecha_guardada == hoy:
                        self.segundos_acumulados = int(data.get("segundos_uso", 0))
                    else:
                        # Día nuevo: reiniciar contador a 0
                        self.segundos_acumulados = 0

                    estado_guardado = data.get("estado_operativo", "STANDBY")
                    # Detección de parada abrupta (Seta de paro / corte eléctrico)
                    if estado_guardado == "EN_MARCHA":
                        self.requiere_reset_por_corte = True
                        self.estado_operativo = "PARO"
                    else:
                        self.requiere_reset_por_corte = data.get("requiere_reset_por_corte", False)
                        self.estado_operativo = estado_guardado

                    self.guardar_estado()
                except Exception:
                    self.segundos_acumulados = 0
                    self.estado_operativo = "STANDBY"
                    self.requiere_reset_por_corte = False
                    self.guardar_estado()
            else:
                self.segundos_acumulados = 0
                self.estado_operativo = "STANDBY"
                self.requiere_reset_por_corte = False
                self.guardar_estado()

            return self.segundos_acumulados

    def guardar_estado(self) -> None:
        """
        Persistencia Atómica Anti-Apagones:
        Escribe en un archivo temporal (.tmp) y luego realiza un os.replace() atómico.
        Esto garantiza que un corte de energía nunca deje el archivo JSON corrupto a medio escribir.
        """
        with self._lock:
            directorio = os.path.dirname(self.ruta_archivo)
            if directorio and not os.path.exists(directorio):
                os.makedirs(directorio, exist_ok=True)

            payload = {
                "fecha": self.fecha_actual,
                "segundos_uso": self.segundos_acumulados,
                "estado_operativo": self.estado_operativo,
                "requiere_reset_por_corte": self.requiere_reset_por_corte,
                "ultima_actualizacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            ruta_tmp = f"{self.ruta_archivo}.tmp"
            try:
                with open(ruta_tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())

                # Reemplazo atómico compatible con POSIX y Windows NTFS
                os.replace(ruta_tmp, self.ruta_archivo)
                self._ultimo_guardado_ts = time.time()
            except Exception:
                if os.path.exists(ruta_tmp):
                    try:
                        os.remove(ruta_tmp)
                    except Exception:
                        pass

    def actualizar_estado_operativo(self, nuevo_estado: str) -> None:
        """
        Actualiza y persiste atómicamente el estado operacional
        (STANDBY, EN_MARCHA, PARO).
        """
        with self._lock:
            self.estado_operativo = nuevo_estado
            self.guardar_estado()

    def reset_corte_abrupto(self) -> None:
        """
        Limpia la bandera de corte abrupto tras confirmación de purga por botón Reset.
        """
        with self._lock:
            self.requiere_reset_por_corte = False
            self.estado_operativo = "STANDBY"
            self.guardar_estado()

    def tick(self, clasificacion_activa: bool) -> int:
        """
        Llamado periódicamente (ej. cada segundo o en cada ciclo de la UI).
        Si la máquina está en clasificación activa, incrementa el tiempo de uso.
        Verifica cambio de día y realiza guardado atómico cada intervalo_guardado_seg.
        """
        with self._lock:
            ahora_ts = time.time()
            hoy = datetime.now().strftime("%Y-%m-%d")

            # Verificación de cambio de medianoche
            if hoy != self.fecha_actual:
                self.fecha_actual = hoy
                self.segundos_acumulados = 0
                self.guardar_estado()

            if clasificacion_activa:
                if self._ultimo_tick_ts is not None:
                    delta = ahora_ts - self._ultimo_tick_ts
                    if 0 < delta < 5.0:
                        self.segundos_acumulados += int(round(delta))
                    else:
                        self.segundos_acumulados += 1
                else:
                    self.segundos_acumulados += 1

                self._ultimo_tick_ts = ahora_ts

                # Guardado automático cada 60 segundos
                if ahora_ts - self._ultimo_guardado_ts >= self.intervalo_guardado_seg:
                    self.guardar_estado()
            else:
                self._ultimo_tick_ts = None

            return self.segundos_acumulados

    def agregar_segundos(self, segundos: int) -> int:
        """Suma segundos directamente y persiste el cambio."""
        with self._lock:
            self.segundos_acumulados += max(0, segundos)
            self.guardar_estado()
            return self.segundos_acumulados

    def obtener_tiempo_formateado(self) -> str:
        """Retorna el tiempo de uso del día en formato HH:MM:SS."""
        with self._lock:
            s = self.segundos_acumulados
            hh = s // 3600
            mm = (s % 3600) // 60
            ss = s % 60
            return f"{hh:02d}:{mm:02d}:{ss:02d}"

    @property
    def segundos_uso(self) -> int:
        return self.segundos_acumulados

    @segundos_uso.setter
    def segundos_uso(self, valor: int) -> None:
        with self._lock:
            self.segundos_acumulados = max(0, int(valor))
