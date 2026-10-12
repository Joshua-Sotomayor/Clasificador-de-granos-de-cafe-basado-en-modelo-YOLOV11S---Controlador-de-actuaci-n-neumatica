"""
Pruebas Unitarias para la Máquina de Estados (FSM) de Botonera y HMI Touch
Valida el ciclo Marcha -> Paro -> Reanudar -> Reset, el bloqueo de slider
cinemático durante EN_MARCHA, y la respuesta visual de los 4 canales de electroválvulas.
"""

import os
import sys
import time
import queue
import unittest
import tempfile
import shutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.detector import YOLODetector
from core.metricas import GestorMetricas
from storage.database import DatabaseManager
from hardware.serial_bridge import ESP32Bridge
from ui.dashboard_ctk import DashboardCustomTkinter, VentanaConfirmacionTrigger


class TestHMIFSMBotonera(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ruta_db = os.path.join(self.temp_dir, "test_fsm.db")
        self.ruta_config = os.path.join(self.temp_dir, "test_config_maquina.json")
        self.ruta_estado = os.path.join(self.temp_dir, "test_estado_maquina.json")

        self.db_manager = DatabaseManager(ruta_sqlite=self.ruta_db, dias_retencion=30)
        self.metricas = GestorMetricas()
        self.detector = YOLODetector(
            ruta_modelo="models/inexistente.pt",
            fuente_video="demo",
            cola_salida=queue.Queue(maxsize=3),
        )
        self.detector.ruta_config_maquina = self.ruta_config

        self.esp32_bridge = ESP32Bridge(puerto="TEST_PORT", baudrate=115200)

        self.app = DashboardCustomTkinter(
            detector=self.detector,
            metricas=self.metricas,
            db_manager=self.db_manager,
            esp32_bridge=self.esp32_bridge,
        )
        # Apuntar gestor_tiempo al archivo temporal
        self.app.gestor_tiempo.ruta_archivo = self.ruta_estado

    def tearDown(self):
        try:
            self.app._al_cerrar()
        except Exception:
            pass
        self.db_manager.cerrar()
        if self.esp32_bridge:
            self.esp32_bridge.desconectar()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_estado_inicial_standby(self):
        """Verifica que el sistema arranque en STANDBY con los botones correctos."""
        self.assertEqual(self.app.estado_operativo, "STANDBY")
        self.assertEqual(self.app.btn_marcha.cget("text"), "Marcha")
        self.assertEqual(self.app.btn_marcha.cget("state"), "normal")
        self.assertEqual(self.app.btn_paro.cget("state"), "disabled")
        self.assertEqual(self.app.btn_reset.cget("state"), "disabled")

        # El slider de latencia y sus botones deben estar habilitados en reposo
        self.assertEqual(self.app.slider_latencia.cget("state"), "normal")
        self.assertEqual(self.app.btn_aplicar_latencia.cget("state"), "normal")
        self.assertEqual(self.app.btn_cancelar_latencia.cget("state"), "normal")

    def test_transicion_marcha_y_bloqueo_trigger(self):
        """
        Al pulsar Marcha:
        - estado -> EN_MARCHA
        - btn_marcha -> 'En Marcha' (disabled)
        - btn_paro -> enabled
        - slider y botones de trigger -> disabled
        - banda -> activa, piloto -> GREEN
        """
        self.app._al_pulsar_marcha()
        self.assertEqual(self.app.estado_operativo, "EN_MARCHA")
        self.assertEqual(self.app.btn_marcha.cget("text"), "En Marcha")
        self.assertEqual(self.app.btn_marcha.cget("state"), "disabled")
        self.assertEqual(self.app.btn_paro.cget("state"), "normal")
        self.assertEqual(self.app.btn_reset.cget("state"), "disabled")

        # Bloqueo ergonómico: slider y botones deshabilitados para evitar descalibración al vuelo
        self.assertEqual(self.app.slider_latencia.cget("state"), "disabled")
        self.assertEqual(self.app.btn_aplicar_latencia.cget("state"), "disabled")
        self.assertEqual(self.app.btn_cancelar_latencia.cget("state"), "disabled")

        # Comprobar hardware
        self.assertTrue(self.esp32_bridge._banda_activa)

    def test_transicion_paro_y_desbloqueo_trigger(self):
        """
        Al pulsar Paro desde EN_MARCHA:
        - estado -> PARO
        - btn_marcha -> 'Reanudar' (normal)
        - btn_paro -> disabled
        - btn_reset -> normal
        - slider y botones de trigger -> habilitados nuevamente
        - banda -> inactiva, piloto -> WHITE
        """
        self.app._al_pulsar_marcha()
        self.app._al_pulsar_paro()

        self.assertEqual(self.app.estado_operativo, "PARO")
        self.assertEqual(self.app.btn_marcha.cget("text"), "Reanudar")
        self.assertEqual(self.app.btn_marcha.cget("state"), "normal")
        self.assertEqual(self.app.btn_paro.cget("state"), "disabled")
        self.assertEqual(self.app.btn_reset.cget("state"), "normal")

        # Slider reactivado
        self.assertEqual(self.app.slider_latencia.cget("state"), "normal")
        self.assertEqual(self.app.btn_aplicar_latencia.cget("state"), "normal")
        self.assertEqual(self.app.btn_cancelar_latencia.cget("state"), "normal")

        # Banda detenida
        self.assertFalse(self.esp32_bridge._banda_activa)

    def test_transicion_reset_a_standby(self):
        """
        Al pulsar Reset desde PARO:
        - estado -> STANDBY
        - btn_marcha -> 'Marcha' (normal)
        - btn_paro -> disabled
        - btn_reset -> disabled
        """
        self.app._al_pulsar_marcha()
        self.app._al_pulsar_paro()
        self.app._al_pulsar_reset()

        self.assertEqual(self.app.estado_operativo, "STANDBY")
        self.assertEqual(self.app.btn_marcha.cget("text"), "Marcha")
        self.assertEqual(self.app.btn_marcha.cget("state"), "normal")
        self.assertEqual(self.app.btn_paro.cget("state"), "disabled")
        self.assertEqual(self.app.btn_reset.cget("state"), "disabled")

    def test_indicadores_canales_activacion_y_apagado(self):
        """
        Verifica que al recibir OK:<canal> el canal correspondiente
        cambie a verde (#197B30) y regrese a inactivo (#E0E0E0) tras el pulso.
        """
        # Inicialmente todos apagados
        for i in range(4):
            self.assertEqual(self.app.indicadores_canales[i].cget("fg_color"), "#E0E0E0")

        # Simular disparo confirmado en canal 2
        self.app._al_recibir_respuesta_serial("OK:2")

        # Canal 2 activo
        self.assertEqual(self.app.indicadores_canales[2].cget("fg_color"), "#197B30")
        # Canal 0 sigue inactivo
        self.assertEqual(self.app.indicadores_canales[0].cget("fg_color"), "#E0E0E0")

        # Tras expirar el tiempo de destello (120 ms), se apaga
        self.app._apagar_indicador_canal(2)
        self.assertEqual(self.app.indicadores_canales[2].cget("fg_color"), "#E0E0E0")

    def test_modal_confirmacion_trigger(self):
        """
        Verifica que el modal de confirmación muestre la latencia y coordenada
        y al confirmar invoque el callback para guardar.
        """
        confirmado = []

        def on_confirmar():
            confirmado.append(True)

        modal = VentanaConfirmacionTrigger(
            parent=self.app,
            latencia_ms=7.5,
            y_calculado_px=458,
            on_confirmar=on_confirmar,
        )

        self.assertTrue(modal.winfo_exists())
        self.assertIn("7.5 ms", modal.lbl_mensaje.cget("text"))
        self.assertIn("458 px", modal.lbl_mensaje.cget("text"))

        # Simular clic en Confirmar
        modal._al_confirmar()
        self.assertEqual(confirmado, [True])


if __name__ == "__main__":
    unittest.main()
