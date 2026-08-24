"""
Punto de Entrada Principal del Dashboard de Inferencia y Telemetría
Lanza la aplicación Flet integrando el Productor (YOLODetector),
el Consumidor (InterfazClasificadora) y la capa de almacenamiento (MongoManager).
"""

import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno si existen
load_dotenv()

import flet as ft
from core.detector import YOLODetector
from core.metricas import GestorMetricas
from storage.database import MongoManager
from ui.dashboard import InterfazClasificadora


def main(page: ft.Page):
    """Función de arranque principal de la interfaz Flet."""
    # 1. Lectura de variables de entorno o valores por defecto
    ruta_modelo = os.getenv("MODEL_PATH", "best.pt")
    fuente_video_raw = os.getenv("CAMERA_SOURCE", "0")
    fuente_video = int(fuente_video_raw) if fuente_video_raw.isdigit() else fuente_video_raw
    potencia_kw = float(os.getenv("HARDWARE_POWER_KW", "0.5"))
    confianza_min = float(os.getenv("CONFIDENCE_THRESHOLD", "0.35"))
    mongo_uri = os.getenv("MONGO_URI", "")

    print("=" * 60)
    print("Iniciando MOPPI - Sistema de Clasificación Óptica de Café")
    print(f"Modelo: {ruta_modelo}")
    print(f"Fuente Video: {fuente_video}")
    print(f"Potencia Nominal: {potencia_kw} kW")
    print("=" * 60)

    # 2. Inicialización de componentes desacoplados
    metricas = GestorMetricas(potencia_nominal_kw=potencia_kw)
    detector = YOLODetector(
        ruta_modelo=ruta_modelo,
        fuente_video=fuente_video,
        confianza_minima=confianza_min,
    )
    db_manager = MongoManager(uri_mongo=mongo_uri)

    # 3. Lanzar interfaz gráfica
    app_interfaz = InterfazClasificadora(
        page=page,
        detector=detector,
        metricas=metricas,
        db_manager=db_manager,
    )


if __name__ == "__main__":
    ft.app(target=main)
