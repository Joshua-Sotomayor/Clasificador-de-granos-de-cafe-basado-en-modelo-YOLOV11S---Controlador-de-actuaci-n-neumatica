"""
Pruebas Unitarias para Compensación Cinemática y Configuración de Actuador
Valida el cálculo físico v_banda * t_latencia * PPM, posicionamiento Y_trigger,
previsualización y persistencia atómica en storage/config_maquina.json.
"""

import os
import sys
import json
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.detector import YOLODetector, calcular_desplazamiento_cinematico


class TestCinematicaActuador(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ruta_config = os.path.join(self.temp_dir, "config_maquina_test.json")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_calculo_cinematico_formula_fisica(self):
        """
        Verifica que ΔY = v_banda * (t_valvula / 1000) * PPM_Y
        y que Y_trigger = Y_nozzle - ΔY.
        Con v=1.5 m/s, PPM_Y=6400 px/m, Y_nozzle=530 px:
        - Latencia 3.0 ms -> ΔY = 1.5 * 0.003 * 6400 = 28.8 px -> Y_trigger = 530 - 28.8 = 501.2 -> 501 px.
        - Latencia 10.0 ms -> ΔY = 1.5 * 0.010 * 6400 = 96.0 px -> Y_trigger = 530 - 96 = 434 px.
        - Latencia 1.0 ms -> ΔY = 1.5 * 0.001 * 6400 = 9.6 px -> Y_trigger = 530 - 9.6 = 520.4 -> 520 px.
        - Latencia 25.0 ms -> ΔY = 1.5 * 0.025 * 6400 = 240.0 px -> Y_trigger = 530 - 240 = 290 px.
        """
        # Latencia estándar 3.0 ms
        offset_3, y_trig_3 = calcular_desplazamiento_cinematico(3.0, belt_speed_m_s=1.5, pixels_per_meter_y=6400.0, y_nozzle_px=530)
        self.assertAlmostEqual(offset_3, 28.8, places=1)
        self.assertEqual(y_trig_3, 501)

        # Latencia 10.0 ms
        offset_10, y_trig_10 = calcular_desplazamiento_cinematico(10.0, belt_speed_m_s=1.5, pixels_per_meter_y=6400.0, y_nozzle_px=530)
        self.assertAlmostEqual(offset_10, 96.0, places=1)
        self.assertEqual(y_trig_10, 434)

        # Latencia 1.0 ms
        offset_1, y_trig_1 = calcular_desplazamiento_cinematico(1.0, belt_speed_m_s=1.5, pixels_per_meter_y=6400.0, y_nozzle_px=530)
        self.assertAlmostEqual(offset_1, 9.6, places=1)
        self.assertEqual(y_trig_1, 520)

        # Latencia 25.0 ms
        offset_25, y_trig_25 = calcular_desplazamiento_cinematico(25.0, belt_speed_m_s=1.5, pixels_per_meter_y=6400.0, y_nozzle_px=530)
        self.assertAlmostEqual(offset_25, 240.0, places=1)
        self.assertEqual(y_trig_25, 290)

    def test_persistencia_atomica_config_maquina(self):
        """
        Verifica que al guardar la configuración se genere un JSON válido
        con las claves requeridas y tipos correspondientes.
        """
        detector = YOLODetector(
            ruta_modelo="models/inexistente.pt",
            fuente_video="demo",
        )
        detector.ruta_config_maquina = self.ruta_config

        # Actualizar latencia a 5.5 ms
        y_nuevo = detector.actualizar_latencia_actuador(5.5)

        # Verificar que el archivo existe y es legible
        self.assertTrue(os.path.exists(self.ruta_config))
        with open(self.ruta_config, "r", encoding="utf-8") as f:
            datos = json.load(f)

        self.assertIn("valvula_latencia_ms", datos)
        self.assertIn("y_trigger_px", datos)
        self.assertIn("posicion_camara_invertida", datos)
        self.assertIn("ultima_actualizacion", datos)

        self.assertEqual(datos["valvula_latencia_ms"], 5.5)
        self.assertEqual(datos["y_trigger_px"], y_nuevo)
        self.assertIsInstance(datos["posicion_camara_invertida"], bool)

    def test_previsualizacion_y_cancelacion(self):
        """
        Verifica que la previsualización altere temporalmente y_trigger_preview
        sin alterar y_trigger persistido, y que la cancelación restablezca el estado.
        """
        detector = YOLODetector(
            ruta_modelo="models/inexistente.pt",
            fuente_video="demo",
        )
        detector.ruta_config_maquina = self.ruta_config
        detector.actualizar_latencia_actuador(3.0)
        y_original = detector.y_trigger

        self.assertIsNone(detector.y_trigger_preview)

        # Iniciar previsualización con 12.0 ms
        y_prev = detector.previsualizar_latencia_actuador(12.0)
        self.assertEqual(detector.y_trigger_preview, y_prev)
        self.assertEqual(detector.y_trigger, y_original)
        self.assertNotEqual(detector.y_trigger, detector.y_trigger_preview)

        # Cancelar previsualización
        detector.cancelar_previsualizacion_latencia()
        self.assertIsNone(detector.y_trigger_preview)
        self.assertEqual(detector.y_trigger, y_original)

    def test_alternar_posicion_camaras(self):
        """Verifica la alternancia del flag posicion_camara_invertida."""
        detector = YOLODetector(
            ruta_modelo="models/inexistente.pt",
            fuente_video="demo",
        )
        detector.ruta_config_maquina = self.ruta_config
        inicial = detector.posicion_camara_invertida

        nuevo_top, nuevo_bot = detector.alternar_posicion_camaras()
        self.assertEqual(detector.posicion_camara_invertida, not inicial)

        # Debe haberse guardado en disco
        with open(self.ruta_config, "r", encoding="utf-8") as f:
            datos = json.load(f)
        self.assertEqual(datos["posicion_camara_invertida"], not inicial)


if __name__ == "__main__":
    unittest.main()
