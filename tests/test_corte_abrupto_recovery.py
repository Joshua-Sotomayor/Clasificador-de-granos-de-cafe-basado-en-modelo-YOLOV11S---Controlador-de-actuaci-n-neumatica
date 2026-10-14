"""
Pruebas Unitarias para Recuperación ante Cortes Abruptos de Energía
Valida la detección de parada inesperada (apagado abrupto en EN_MARCHA),
bloqueo de seguridad con piloto rojo (GPIO 18), e inmunidad hasta purga con Reset.
"""

import os
import sys
import json
import queue
import unittest
import tempfile
import shutil
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.detector import YOLODetector
from core.metricas import GestorMetricas
from storage.database import DatabaseManager
from storage.telemetria import GestorTiempoUso
from hardware.serial_bridge import ESP32Bridge
from ui.dashboard_ctk import DashboardCustomTkinter


class TestCorteAbruptoRecovery(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ruta_db = os.path.join(self.temp_dir, "test_recovery.db")
        self.ruta_estado = os.path.join(self.temp_dir, "estado_maquina.json")
        self.ruta_config = os.path.join(self.temp_dir, "config_maquina.json")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _simular_apagado_abrupto(self):
        """Crea un estado persistente simulando que la máquina quedó EN_MARCHA tras apagón."""
        payload = {
            "fecha": datetime.now().strftime("%Y-%m-%d"),
            "segundos_hoy": 3600,
            "horas_acumuladas": 1.0,
            "estado_operativo": "EN_MARCHA",  # Quedó encendida sin paro ordenado
            "requiere_reset_por_corte": False,
        }
        with open(self.ruta_estado, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def test_deteccion_en_gestor_tiempo_uso(self):
        """
        Verifica que GestorTiempoUso marque requiere_reset_por_corte = True
        al arrancar si el último estado guardado era 'EN_MARCHA'.
        """
        self._simular_apagado_abrupto()

        gestor = GestorTiempoUso(ruta_archivo=self.ruta_estado)
        self.assertTrue(gestor.requiere_reset_por_corte)
        self.assertEqual(gestor.estado_operativo, "PARO")

        # Al invocar reset_corte_abrupto, la bandera se despeja
        gestor.reset_corte_abrupto()
        self.assertFalse(gestor.requiere_reset_por_corte)
        self.assertEqual(gestor.estado_operativo, "STANDBY")

        # Verificar persistencia en archivo
        with open(self.ruta_estado, "r", encoding="utf-8") as f:
            datos = json.load(f)
        self.assertFalse(datos["requiere_reset_por_corte"])
        self.assertEqual(datos["estado_operativo"], "STANDBY")

    def test_bloqueo_hmi_y_recuperacion_con_reset(self):
        """
        Verifica que la UI inicie bloqueada ante corte abrupto:
        - btn_marcha disabled
        - btn_reset habilitado con texto 'Reset (Purgar)'
        - Piloto rojo (RED)
        - Al pulsar Marcha, sigue bloqueado
        - Al pulsar Reset, se normaliza a STANDBY y se habilita Marcha
        """
        self._simular_apagado_abrupto()

        db_manager = DatabaseManager(ruta_sqlite=self.ruta_db, dias_retencion=30)
        metricas = GestorMetricas()
        detector = YOLODetector(
            ruta_modelo="models/inexistente.pt",
            fuente_video="demo",
            cola_salida=queue.Queue(maxsize=3),
        )
        detector.ruta_config_maquina = self.ruta_config
        esp32_bridge = ESP32Bridge(puerto="TEST_PORT", baudrate=115200)

        # Crear app inyectando el gestor con corte abrupto
        app = DashboardCustomTkinter(
            detector=detector,
            metricas=metricas,
            db_manager=db_manager,
            esp32_bridge=esp32_bridge,
        )
        # Re-enlazar con el archivo de corte abrupto simulado
        app.gestor_tiempo = GestorTiempoUso(ruta_archivo=self.ruta_estado)
        app._verificar_estado_previo_maquina()

        try:
            # 1. Comprobar bloqueo de seguridad inicial
            self.assertTrue(app.gestor_tiempo.requiere_reset_por_corte)
            self.assertEqual(app.btn_marcha.cget("state"), "disabled")
            self.assertEqual(app.btn_reset.cget("state"), "normal")
            self.assertIn(app.btn_reset.cget("text"), ("Reset (Purgar)", "R"))
            self.assertEqual(esp32_bridge._piloto_actual, "RED")

            # 2. Intentar pulsar Marcha no debe transicionar a EN_MARCHA
            app._al_pulsar_marcha()
            self.assertNotEqual(app.estado_operativo, "EN_MARCHA")
            self.assertEqual(app.btn_marcha.cget("state"), "disabled")

            # 3. Pulsar Reset para purgar
            app._al_pulsar_reset()

            # 4. Estado normalizado
            self.assertFalse(app.gestor_tiempo.requiere_reset_por_corte)
            self.assertEqual(app.estado_operativo, "STANDBY")
            self.assertEqual(app.btn_marcha.cget("state"), "normal")
            self.assertIn(app.btn_marcha.cget("text"), ("Marcha", "M"))
            self.assertEqual(app.btn_reset.cget("state"), "disabled")
            self.assertEqual(esp32_bridge._piloto_actual, "WHITE")

        finally:
            app._al_cerrar()
            db_manager.cerrar()
            esp32_bridge.desconectar()


if __name__ == "__main__":
    unittest.main()
