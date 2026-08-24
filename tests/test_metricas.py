"""
Pruebas Unitarias para GestorMetricas
Valida el cronometraje, cálculo de kWh, conteos acumulativos, porcentajes de defectos y generación de resumen.
"""

import os
import sys
import unittest
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.metricas import GestorMetricas


class TestGestorMetricas(unittest.TestCase):
    def setUp(self):
        self.metricas = GestorMetricas(potencia_nominal_kw=1.0)

    def test_inicializacion(self):
        self.assertEqual(self.metricas.total_granos, 0)
        self.assertEqual(self.metricas.total_sanos, 0)
        self.assertEqual(self.metricas.total_defectuosos, 0)
        self.assertEqual(self.metricas.obtener_porcentaje_calidad(), 100.0)
        self.assertEqual(self.metricas.calcular_consumo_kwh(), 0.0)

    def test_registro_detecciones(self):
        detecciones = [
            {"clase_id": 2, "nombre_clase": "Arabica_Bueno", "confianza": 0.95},
            {"clase_id": 9, "nombre_clase": "Robusta_Bueno", "confianza": 0.91},
            {"clase_id": 1, "nombre_clase": "Arabica_Brocado", "confianza": 0.88},
            {"clase_id": 0, "nombre_clase": "Arabica_Agrio", "confianza": 0.84},
        ]

        self.metricas.registrar_detecciones(detecciones, fps=28.5, latencia_ms=22.4)

        self.assertEqual(self.metricas.total_granos, 4)
        self.assertEqual(self.metricas.total_sanos, 2)
        self.assertEqual(self.metricas.total_defectuosos, 2)
        self.assertEqual(self.metricas.obtener_porcentaje_calidad(), 50.0)

        # Defectos específicos
        porcentajes = self.metricas.obtener_porcentajes_defectos()
        self.assertEqual(porcentajes["Brocado"], 50.0)
        self.assertEqual(porcentajes["Agrio"], 50.0)
        self.assertEqual(self.metricas.fps_actual, 28.5)
        self.assertEqual(self.metricas.latencia_actual_ms, 22.4)

    def test_cronometro_y_calculo_kwh(self):
        self.metricas.iniciar_sesion()
        self.assertTrue(self.metricas.esta_activo)

        time.sleep(0.1)  # Simular breve tiempo de operación
        segundos = self.metricas.obtener_segundos_activos()
        self.assertGreater(segundos, 0.05)

        kwh = self.metricas.calcular_consumo_kwh()
        self.assertGreaterEqual(kwh, 0.0)

        # Pausar sesión
        self.metricas.pausar_sesion()
        self.assertFalse(self.metricas.esta_activo)

    def test_generacion_resumen_lote(self):
        self.metricas.iniciar_sesion()
        self.metricas.registrar_detecciones(
            [{"clase_id": 2, "nombre_clase": "Arabica_Bueno", "confianza": 0.90}],
            fps=30.0,
            latencia_ms=18.5,
        )

        resumen = self.metricas.generar_resumen_lote("LOTE-TEST-001")
        self.assertEqual(resumen["id_lote"], "LOTE-TEST-001")
        self.assertEqual(resumen["total_granos"], 1)
        self.assertEqual(resumen["total_sanos"], 1)
        self.assertEqual(resumen["total_defectuosos"], 0)
        self.assertEqual(resumen["porcentaje_calidad"], 100.0)
        self.assertIn("timestamp", resumen)
        self.assertIn("duracion_formato", resumen)


if __name__ == "__main__":
    unittest.main()
