"""
Pruebas Unitarias para YOLODetector
Valida la inicialización del detector, generación sintética de frames y despacho en cola.
"""

import os
import sys
import unittest
import queue
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.detector import YOLODetector


class TestYOLODetector(unittest.TestCase):
    def setUp(self):
        self.cola = queue.Queue(maxsize=5)
        self.detector = YOLODetector(
            ruta_modelo="modelo_inexistente_para_prueba.pt",
            fuente_video="demo",
            cola_salida=self.cola,
        )

    def tearDown(self):
        self.detector.detener()

    def test_modo_simulado_fallback(self):
        """Verifica que active modo simulado si el modelo no existe."""
        self.assertTrue(self.detector.modo_simulado)

    def test_generacion_frame_sintetico(self):
        """Verifica la generación correcta de frame y anotación de detecciones."""
        frame = self.detector._generar_frame_sintetico()
        self.assertIsNotNone(frame)
        self.assertEqual(len(frame.shape), 3)

        detecciones, frame_anotado = self.detector._procesar_frame(frame)
        self.assertIsInstance(detecciones, list)
        self.assertGreater(len(detecciones), 0)

        # Validar estructura de las detecciones
        det = detecciones[0]
        self.assertIn("clase_id", det)
        self.assertIn("nombre_clase", det)
        self.assertIn("confianza", det)
        self.assertIn("caja", det)
        self.assertIn("es_defecto", det)

    def test_flujo_multihilo_cola(self):
        """Verifica que el productor despache payloads válidos a la cola."""
        self.detector.iniciar()
        time.sleep(0.3)

        payload = self.cola.get(timeout=2.0)
        self.assertIsNotNone(payload)
        self.assertIn("frame_base64", payload)
        self.assertIn("detecciones", payload)
        self.assertIn("fps", payload)
        self.assertIn("latencia_ms", payload)
        self.assertIn("valvula_activa", payload)

        self.detector.detener()
        self.assertFalse(self.detector._ejecutando)


if __name__ == "__main__":
    unittest.main()
