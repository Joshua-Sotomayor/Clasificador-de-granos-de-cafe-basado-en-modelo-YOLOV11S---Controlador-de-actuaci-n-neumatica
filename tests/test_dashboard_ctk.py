"""
Pruebas Unitarias para DashboardCustomTkinter.
Verifica que la UI se instancie con los switches de modelo y SAHI,
que el gráfico reactivo de Matplotlib se inicialice correctamente y que los cambios de modelo
actualicen las categorías de la gráfica sin errores.
"""

import os
import sys
import unittest
import queue

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.detector import YOLODetector
from core.metricas import GestorMetricas
from storage.database import DatabaseManager, GestorLotes
from ui.dashboard_ctk import DashboardCustomTkinter


class TestDashboardCustomTkinter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ruta_db = "storage/test_ui_db.db"

    def setUp(self):
        self.metricas = GestorMetricas(potencia_nominal_kw=0.5)
        self.db_manager = DatabaseManager(
            uri_mongo="",
            ruta_sqlite=self.ruta_db,
            dias_retencion=30,
        )
        self.detector = YOLODetector(
            ruta_modelo="models/inexistente.pt",
            fuente_video="demo",
            cola_salida=queue.Queue(maxsize=3),
        )

    def tearDown(self):
        self.db_manager.cerrar()
        if os.path.exists(self.ruta_db):
            try:
                os.remove(self.ruta_db)
            except Exception:
                pass

    def test_instanciacion_ui_y_switches(self):
        """Verifica que la ventana CustomTkinter cree los switches requeridos y la gráfica."""
        app = DashboardCustomTkinter(
            detector=self.detector,
            metricas=self.metricas,
            db_manager=self.db_manager,
        )

        try:
            # 1. Verificar switches
            self.assertTrue(hasattr(app, "switch_modelo"))
            self.assertTrue(hasattr(app, "switch_sahi"))
            self.assertEqual(app.switch_modelo.get(), 0)  # Tri-clase por defecto

            # 2. Verificar StatCards
            self.assertTrue(hasattr(app, "card_kpi_tiempo"))
            self.assertTrue(hasattr(app, "card_kpi_lotes"))
            self.assertTrue(hasattr(app, "card_kpi_granos"))
            self.assertTrue(hasattr(app, "card_kpi_consumo"))
            self.assertTrue(hasattr(app, "card_kpi_latencia"))
            self.assertTrue(hasattr(app, "gestor_tiempo"))
            self.assertTrue(hasattr(app, "tab_logs"))
            self.assertTrue(hasattr(app, "txt_logs"))

            # Probar apertura de ventana toplevel de logs
            app._abrir_ventana_logs_toplevel()
            self.assertIsNotNone(app._ventana_logs)
            self.assertTrue(app._ventana_logs.winfo_exists())

            # 3. Verificar Canvas y Figura Reactiva
            self.assertIsNotNone(app.fig_reactiva)
            self.assertIsNotNone(app.ax_reactivo)
            self.assertIsNotNone(app.canvas_reactivo)

            # 4. Probar cambio a 13 Clases
            app.switch_modelo.select()  # 1
            app._al_cambiar_switch_modelo()
            self.assertTrue(app.gestor_lotes.modelo_13_clases)
            self.assertEqual(app.switch_modelo.cget("text"), "13 Clases")

            # 5. Probar cambio de SAHI
            app.switch_sahi.select()
            app._al_cambiar_switch_sahi()
            self.assertTrue(app.gestor_lotes.modo_sahi)
            self.assertEqual(app.switch_sahi.cget("text"), "SAHI: ON")

            # 6. Probar retorno a Tri-clase
            app.switch_modelo.deselect()  # 0
            app._al_cambiar_switch_modelo()
            self.assertFalse(app.gestor_lotes.modelo_13_clases)
            self.assertEqual(app.switch_modelo.cget("text"), "Tri-clase")

        finally:
            app._al_cerrar()


if __name__ == "__main__":
    unittest.main()
