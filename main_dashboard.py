"""
Punto de Entrada Principal del Dashboard de Inferencia y Telemetría MOPPI
Ejecuta la interfaz nativa en CustomTkinter para streaming ultra-fluido (30-60 FPS)
sin congelamientos, y permite usar Flet mediante el argumento --flet si se desea.
"""

import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno si existen
load_dotenv()

from core.detector import YOLODetector
from core.metricas import GestorMetricas
from storage.database import DatabaseManager, GestorLotes, MongoManager


def main():
    """Función de arranque principal."""
    ruta_default = "models/best.pt" if os.path.exists("models/best.pt") else "best.pt"
    ruta_modelo = os.getenv("MODEL_PATH", ruta_default)
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

    # 1. Inicialización de componentes desacoplados
    metricas = GestorMetricas(potencia_nominal_kw=potencia_kw)
    detector = YOLODetector(
        ruta_modelo=ruta_modelo,
        fuente_video=fuente_video,
        confianza_minima=confianza_min,
    )
    db_manager = DatabaseManager(uri_mongo=mongo_uri)
    gestor_lotes = GestorLotes(db_manager=db_manager)

    # 2. Lanzar interfaz gráfica
    if "--flet" in sys.argv:
        print("[MOPPI] Iniciando interfaz Flet...")
        import flet as ft
        from ui.dashboard import InterfazClasificadora

        def flet_entry(page: ft.Page):
            InterfazClasificadora(
                page=page,
                detector=detector,
                metricas=metricas,
                db_manager=db_manager,
            )

        if hasattr(ft, "run"):
            ft.run(flet_entry)
        else:
            ft.app(target=flet_entry)
    else:
        print("[MOPPI] Iniciando interfaz nativa CustomTkinter (30-60 FPS)...")
        from ui.dashboard_ctk import DashboardCustomTkinter
        app = DashboardCustomTkinter(
            detector=detector,
            metricas=metricas,
            db_manager=db_manager,
            gestor_lotes=gestor_lotes,
        )
        app.mainloop()


if __name__ == "__main__":
    main()
