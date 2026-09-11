"""
Pruebas Unitarias para el Puente de Comunicación Serial con ESP32 (MOPPI v1.5.0).
Verifica:
1. Formato y serialización estricta de tramas (ACT:0 a ACT:3, STOP, PING).
2. Comportamiento asíncrono y no bloqueante de la cola concurrente.
3. Conmutación a modo simulación / virtual ante ausencia de puerto físico.
4. Captura de fallas del presostato (ERR:PRESSURE_FAULT) y persistencia en SQLite (ALARM).
5. Acoplamiento e invocación directa desde el detector espacial de defectos (YOLODetector).
"""

import os
import sys
import time
import queue
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from hardware.serial_bridge import ESP32Bridge
from storage.database import DatabaseManager
from core.detector import YOLODetector


class TestSerialBridge(unittest.TestCase):
    def setUp(self):
        self.test_dir = "storage/test_hardware"
        os.makedirs(self.test_dir, exist_ok=True)
        self.ruta_db = os.path.join(self.test_dir, "test_hardware_logs.db")

        if os.path.exists(self.ruta_db):
            try:
                os.remove(self.ruta_db)
            except Exception:
                pass

        self.db_manager = DatabaseManager(
            uri_mongo="",
            ruta_sqlite=self.ruta_db,
            dias_retencion=30,
        )

        # Instanciar bridge forzando modo simulación para entornos de test CI/CD
        self.bridge = ESP32Bridge(
            puerto="COM99",
            baudrate=115200,
            pulso_ms=20,
            modo_simulacion=True,
            db_manager=self.db_manager,
        )

    def tearDown(self):
        self.bridge.cerrar()
        self.db_manager.cerrar()
        if os.path.exists(self.ruta_db):
            try:
                os.remove(self.ruta_db)
            except Exception:
                pass
        if os.path.exists(self.test_dir):
            try:
                os.rmdir(self.test_dir)
            except Exception:
                pass

    # =========================================================================
    # 1. SERIALIZACIÓN Y VALIDACIÓN DE TRAMAS
    # =========================================================================

    def test_formato_tramas_canales_validos(self):
        """Verifica que los 4 canales virtuales (0..3) se validen y encolen."""
        for canal in range(4):
            exito = self.bridge.disparar_canal(canal)
            self.assertTrue(exito, f"El canal {canal} debe encolarse exitosamente.")

        stats = self.bridge.obtener_estadisticas()
        self.assertEqual(stats["total_disparos"], 4)
        for c in range(4):
            self.assertEqual(stats["disparos_por_canal"][c], 1)

    def test_rechazo_canales_invalidos(self):
        """Verifica que canales fuera del rango 0..3 sean rechazados sin encolar."""
        self.assertFalse(self.bridge.disparar_canal(-1))
        self.assertFalse(self.bridge.disparar_canal(4))
        self.assertFalse(self.bridge.disparar_canal(99))

        stats = self.bridge.obtener_estadisticas()
        self.assertEqual(stats["total_disparos"], 0)

    def test_comandos_stop_y_ping(self):
        """Verifica la serialización de STOP y PING."""
        self.assertTrue(self.bridge.detener_todo())
        self.assertTrue(self.bridge.hacer_ping())
        self.assertTrue(self.bridge.esta_conectado())

    # =========================================================================
    # 2. CONCURRENCIA Y COLA ASÍNCRONA NO BLOQUEANTE
    # =========================================================================

    def test_encolamiento_asincrono_masivo(self):
        """Verifica que ráfagas de eyecciones no bloqueen el hilo de llamada."""
        t_inicio = time.time()
        num_disparos = 50
        for i in range(num_disparos):
            canal = i % 4
            self.bridge.disparar_canal(canal)
        duracion_ms = (time.time() - t_inicio) * 1000.0

        # Debe encolar 50 comandos en menos de 50 ms (operación puramente en memoria)
        self.assertLess(duracion_ms, 50.0, "El encolamiento concurrentemente debe ser instantáneo.")
        stats = self.bridge.obtener_estadisticas()
        self.assertEqual(stats["total_disparos"], num_disparos)

    # =========================================================================
    # 3. MODO SIMULACIÓN Y RESPUESTAS VIRTUALES
    # =========================================================================

    def test_modo_simulacion_activo(self):
        """Verifica que el bridge reconozca el modo virtual."""
        self.assertTrue(self.bridge.esta_en_simulacion())
        self.assertTrue(self.bridge.esta_conectado())

    def test_despacho_respuestas_simuladas(self):
        """Verifica que en simulación se procesen callbacks de confirmación."""
        respuestas_recibidas = []

        def mi_callback_resp(trama):
            respuestas_recibidas.append(trama)

        self.bridge.callback_respuesta = mi_callback_resp

        # Simular envío y esperar brevemente al worker
        self.bridge.hacer_ping()
        self.bridge.disparar_canal(2)
        self.bridge.detener_todo()

        time.sleep(0.3)

        self.assertIn("PONG", respuestas_recibidas)
        self.assertIn("OK:2", respuestas_recibidas)
        self.assertIn("OK:STOP", respuestas_recibidas)

    # =========================================================================
    # 4. CAPTURA DE FALLAS DEL PRESOSTATO Y ALARMAS EN SQLITE
    # =========================================================================

    def test_captura_falla_presostato_y_registro_alarma_sqlite(self):
        """Al recibir ERR:PRESSURE_FAULT, debe registrar automáticamente un log ALARM en SQLite."""
        alarma_callback_recibida = []

        def mi_cb_alarma(linea):
            alarma_callback_recibida.append(linea)

        self.bridge.callback_alarma = mi_cb_alarma

        # Simular recepción de trama de falla de presostato desde el ESP32
        trama_falla = "ERR:PRESSURE_FAULT_CH_1"
        self.bridge._procesar_linea_recibida(trama_falla)

        # 1. Verificar callback
        self.assertEqual(len(alarma_callback_recibida), 1)
        self.assertEqual(alarma_callback_recibida[0], trama_falla)

        # 2. Verificar estadísticas
        stats = self.bridge.obtener_estadisticas()
        self.assertEqual(stats["fallas_presion"], 1)

        # 3. Verificar persistencia inmediata en SQLite (logs_locales)
        logs = self.db_manager.obtener_logs_locales(tipo="ALARM", filtro_fecha="Hoy")
        self.assertGreaterEqual(len(logs), 1)
        ultimo_log = logs[0]
        self.assertEqual(ultimo_log["tipo"], "ALARM")
        self.assertIn("presostato", ultimo_log["mensaje"].lower())
        self.assertIn("CH_1", ultimo_log["mensaje"])

    # =========================================================================
    # 5. INTEGRACIÓN VISIÓN - ESP32 BRIDGE
    # =========================================================================

    def test_integracion_vision_disparo_defecto(self):
        """Verifica que YOLODetector dispare el bridge cuando un defecto cruza Y>=500."""
        detector = YOLODetector(
            fuente_video="demo",
            esp32_bridge=self.bridge,
            linea_disparo_y=500,
        )

        det_defecto = {
            "clase_id": 0,
            "nombre_clase": "Arabica_Agrio",
            "es_defecto": True,
            "y_center": 515,
            "canal": 3,
        }

        det_sano = {
            "clase_id": 1,
            "nombre_clase": "Arabica_Bueno",
            "es_defecto": False,
            "y_center": 530,
            "canal": 1,
        }

        canales = detector._evaluar_disparo_esp32([det_defecto, det_sano])
        self.assertEqual(canales, [3])

        # Comprobar que el bridge registró el disparo en el canal 3
        stats = self.bridge.obtener_estadisticas()
        self.assertEqual(stats["disparos_por_canal"][3], 1)
        self.assertEqual(stats["disparos_por_canal"][1], 0)


if __name__ == "__main__":
    unittest.main()
