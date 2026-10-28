"""
Punto de Entrada Principal del Dashboard de Inferencia y Telemetria MOPPI
Ejecuta la interfaz nativa en CustomTkinter para streaming ultra-fluido (30-60 FPS)
sin congelamientos, con soporte estereo de doble camara y control industrial.
"""

import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno si existen
load_dotenv()

from core.detector import YOLODetector
from core.metricas import GestorMetricas
from storage.database import DatabaseManager, GestorLotes
from hardware.serial_bridge import ESP32Bridge
from ui import DashboardCustomTkinter


def main():
    """Funcion de arranque principal de la HMI Industrial."""
    ruta_default = "models/best.pt" if os.path.exists("models/best.pt") else "best.pt"
    ruta_modelo = os.getenv("MODEL_PATH", ruta_default)
    ruta_modelo_13clases = os.getenv("MODEL_13CLASES_PATH", "models/best_13clases.pt")
    fuente_video_raw = os.getenv("CAMERA_SOURCE", "0")
    fuente_video = int(fuente_video_raw) if fuente_video_raw.isdigit() else fuente_video_raw
    fuente_top_raw = os.getenv("CAMERA_SOURCE_TOP", fuente_video_raw)
    fuente_bot_raw = os.getenv("CAMERA_SOURCE_BOTTOM", "1")
    fuente_top = int(fuente_top_raw) if str(fuente_top_raw).isdigit() else fuente_top_raw
    fuente_bot = int(fuente_bot_raw) if str(fuente_bot_raw).isdigit() else fuente_bot_raw
    potencia_kw = float(os.getenv("HARDWARE_POWER_KW", "0.5"))
    confianza_min = float(os.getenv("CONFIDENCE_THRESHOLD", "0.35"))
    mongo_uri = os.getenv("MONGO_URI", "")

    print("=" * 60)
    print("Iniciando MOPPI - Sistema de Clasificacion Optica de Cafe")
    print(f"Modelo Tri-Clase: {ruta_modelo}")
    print(f"Modelo 13 Clases: {ruta_modelo_13clases}")
    print(f"Camara Superior: {fuente_top} | Camara Inferior: {fuente_bot}")
    print(f"Potencia Nominal: {potencia_kw} kW")
    print("=" * 60)

    # 1. Inicializacion de componentes desacoplados
    db_manager = DatabaseManager(uri_mongo=mongo_uri)
    gestor_lotes = GestorLotes(db_manager=db_manager)
    esp32_bridge = ESP32Bridge(db_manager=db_manager)
    metricas = GestorMetricas(potencia_nominal_kw=potencia_kw)
    detector = YOLODetector(
        ruta_modelo=ruta_modelo,
        ruta_modelo_13clases=ruta_modelo_13clases,
        fuente_video=fuente_video,
        fuente_video_top=fuente_top,
        fuente_video_bottom=fuente_bot,
        confianza_minima=confianza_min,
        esp32_bridge=esp32_bridge,
    )
    # Iniciar streaming continuo del detector
    detector.iniciar()

    # 2. Lanzar interfaz grafica nativa CustomTkinter (30-60 FPS)
    print("[MOPPI] Iniciando interfaz nativa CustomTkinter (30-60 FPS)...")
    app = DashboardCustomTkinter(
        detector=detector,
        metricas=metricas,
        db_manager=db_manager,
        gestor_lotes=gestor_lotes,
        esp32_bridge=esp32_bridge,
    )
    app.mainloop()


if __name__ == "__main__":
    main()
