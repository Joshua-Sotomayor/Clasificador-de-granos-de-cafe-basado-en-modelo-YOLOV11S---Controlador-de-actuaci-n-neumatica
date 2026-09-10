"""
Pruebas Unitarias para Mapeo Espacial OpenCV, Centroides y Actuacion ESP32 (v1.3.0)
Valida:
1. Calculo de centroides (x_center, y_center).
2. Asignacion de 4 canales/carriles virtuales (x_center // 160) en rango [0..3].
3. 5 lineas divisorias de canales y linea horizontal roja en Y=500.
4. Logica de disparo mecatronico a ESP32 para defectos.
5. Inclusion de identificadores multi-tenant (tenant_id, maquina_id) en el backend.
"""

import io
import os
import sys
import unittest
import tempfile
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vision.detector import (
    YOLODetector,
    calcular_centroide,
    asignar_canal,
    ANCHO_BANDA_PX,
    ALTO_FRAME_PX,
    NUM_CANALES_VIRTUALES,
    NUM_CARRILES_ACTUACION,
    ANCHO_CARRIL_PX,
    LINEA_DISPARO_Y,
)
from storage.database import DatabaseManager, GestorLotes


class TestVisionSpatial(unittest.TestCase):
    def setUp(self):
        self.detector = YOLODetector(fuente_video="demo", resolucion_captura=(640, 640))

    def tearDown(self):
        self.detector.detener()

    def test_constantes_espaciales(self):
        """Verifica que las constantes geometricas respeten los 4 carriles y linea Y=500."""
        self.assertEqual(ANCHO_BANDA_PX, 640)
        self.assertEqual(ALTO_FRAME_PX, 640)
        self.assertEqual(NUM_CANALES_VIRTUALES, 4)
        self.assertEqual(NUM_CARRILES_ACTUACION, 4)
        self.assertEqual(ANCHO_CARRIL_PX, 160)
        self.assertEqual(LINEA_DISPARO_Y, 500)

    def test_calculo_centroide(self):
        """Verifica el calculo matematico del centroide exacto a partir del bounding box."""
        caja_1 = (100, 200, 200, 300)
        cx, cy = calcular_centroide(caja_1)
        self.assertEqual(cx, 150)
        self.assertEqual(cy, 250)

        caja_2 = (0, 0, 80, 80)
        cx2, cy2 = calcular_centroide(caja_2)
        self.assertEqual(cx2, 40)
        self.assertEqual(cy2, 40)

    def test_asignacion_4_canales_carriles(self):
        """Verifica que canal = int(x_center // 160) mapee correctamente a los 4 carriles [0..3]."""
        # Canal 0: [0 a 159 px]
        self.assertEqual(asignar_canal(0), 0)
        self.assertEqual(asignar_canal(80), 0)
        self.assertEqual(asignar_canal(159), 0)

        # Canal 1: [160 a 319 px]
        self.assertEqual(asignar_canal(160), 1)
        self.assertEqual(asignar_canal(240), 1)
        self.assertEqual(asignar_canal(319), 1)

        # Canal 2: [320 a 479 px]
        self.assertEqual(asignar_canal(320), 2)
        self.assertEqual(asignar_canal(400), 2)
        self.assertEqual(asignar_canal(479), 2)

        # Canal 3: [480 a 639 px]
        self.assertEqual(asignar_canal(480), 3)
        self.assertEqual(asignar_canal(560), 3)
        self.assertEqual(asignar_canal(639), 3)

        # Clamping de seguridad fuera de limites
        self.assertEqual(asignar_canal(-10), 0)
        self.assertEqual(asignar_canal(700), 3)

    def test_actuacion_esp32_disparo_defecto(self):
        """Verifica que defectos que cruzan Y>=500 emitan el mensaje estructurado de actuacion."""
        # Defecto en Canal 2 (x=360 // 160 = 2) que cruza la linea Y=500 (y_center=510)
        det_defecto_cruza = {
            "clase_id": 0,
            "nombre_clase": "Arabica_Agrio",
            "es_defecto": True,
            "caja": (340, 490, 380, 530),
            "x_center": 360,
            "y_center": 510,
            "canal": 2,
        }
        # Defecto en Canal 0 (x=100 // 160 = 0) que NO cruza (y_center=450 < 500)
        det_defecto_espera = {
            "clase_id": 1,
            "nombre_clase": "Arabica_Brocado",
            "es_defecto": True,
            "caja": (80, 430, 120, 470),
            "x_center": 100,
            "y_center": 450,
            "canal": 0,
        }
        # Grano sano que cruza Y>=500 (NO debe disparar)
        det_sano_cruza = {
            "clase_id": 2,
            "nombre_clase": "Arabica_Bueno",
            "es_defecto": False,
            "caja": (200, 500, 240, 540),
            "x_center": 220,
            "y_center": 520,
            "canal": 1,
        }

        buffer = io.StringIO()
        stdout_orig = sys.stdout
        sys.stdout = buffer
        try:
            canales = self.detector._evaluar_disparo_esp32([
                det_defecto_cruza,
                det_defecto_espera,
                det_sano_cruza,
            ])
        finally:
            sys.stdout = stdout_orig

        salida = buffer.getvalue()
        self.assertIn("[ACTUACION] Defecto en Canal 2 - Enviando señal a ESP32...", salida)
        self.assertNotIn("Canal 0", salida)
        self.assertNotIn("Canal 1", salida)
        self.assertEqual(canales, [2])

    def test_dibujo_guias_canales_y_disparo(self):
        """Verifica que el renderizado de guias y anotaciones sobre OpenCV funcione correctamente."""
        frame = np.full((640, 640, 3), 220, dtype=np.uint8)
        frame_anotado = self.detector._dibujar_detecciones(frame, [
            {
                "clase_id": 0,
                "nombre_clase": "Arabica_Agrio",
                "confianza": 0.92,
                "caja": (100, 480, 140, 520),
                "es_defecto": True,
            },
            {
                "clase_id": 2,
                "nombre_clase": "Arabica_Bueno",
                "confianza": 0.95,
                "caja": (300, 200, 340, 240),
                "es_defecto": False,
            },
        ])
        self.assertEqual(frame_anotado.shape, (640, 640, 3))
        self.assertFalse(np.array_equal(frame, frame_anotado))

    def test_multi_tenant_database_payload(self):
        """Verifica que el backend registre tenant_id y maquina_id en SQLite y JSON."""
        ruta_temp = os.path.join(tempfile.gettempdir(), "test_spatial_tenant_4ch.db")
        db = DatabaseManager(
            ruta_sqlite=ruta_temp,
            tenant_id="finca_alvizua",
            maquina_id="moppi_01",
        )
        gestor = GestorLotes(
            db_manager=db,
            tenant_id="finca_alvizua",
            maquina_id="moppi_01",
        )

        gestor.registrar_detecciones([
            {"clase_id": 0, "nombre_clase": "Arabica_Agrio", "es_defecto": True, "x_center": 120, "y_center": 520, "canal": 0}
        ], fps=30.0, latencia_ms=10.0)

        resumen = gestor.finalizar_lote()
        self.assertIsNotNone(resumen)
        self.assertEqual(resumen.get("tenant_id"), "finca_alvizua")
        self.assertEqual(resumen.get("maquina_id"), "moppi_01")

        ultimos = db.obtener_ultimos_lotes(limite=1)
        self.assertGreaterEqual(len(ultimos), 1)
        self.assertEqual(ultimos[0].get("tenant_id"), "finca_alvizua")
        self.assertEqual(ultimos[0].get("maquina_id"), "moppi_01")


if __name__ == "__main__":
    unittest.main()
