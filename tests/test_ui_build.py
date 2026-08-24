"""
Prueba de Construcción del Árbol de Widgets de UI
"""
import os
import sys
import unittest
import flet as ft

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.detector import YOLODetector
from core.metricas import GestorMetricas
from storage.database import MongoManager
from ui.dashboard import InterfazClasificadora


class MockPage:
    def __init__(self):
        self.title = ""
        self.theme_mode = None
        self.bgcolor = ""
        self.padding = 0
        self.width = 0
        self.height = 0
        self.controls = []
        self.overlay = []

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        pass


class TestUIBuild(unittest.TestCase):
    def test_construccion_interfaz(self):
        page = MockPage()
        detector = YOLODetector(fuente_video="demo")
        metricas = GestorMetricas()
        db_manager = MongoManager(uri_mongo="")

        app = InterfazClasificadora(page, detector, metricas, db_manager)
        self.assertIsNotNone(app)
        self.assertEqual(len(page.controls), 1)

        # Detener hilos al finalizar la prueba
        app._hilo_consumidor_activo = False
        detector.detener()


if __name__ == "__main__":
    unittest.main()
