"""
Pruebas Unitarias para MongoManager
Valida el modo offline, almacenamiento en búfer local JSON y recuperación de lotes.
"""

import os
import sys
import unittest
import json
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storage.database import MongoManager


class TestMongoManager(unittest.TestCase):
    def setUp(self):
        self.ruta_test_offline = f"storage/test_offline_logs_{uuid.uuid4().hex[:8]}.json"
        self.ruta_test_db = f"storage/test_respaldo_{uuid.uuid4().hex[:8]}.db"
        if os.path.exists(self.ruta_test_offline):
            os.remove(self.ruta_test_offline)

        self.db_manager = MongoManager(
            uri_mongo="",
            ruta_sqlite=self.ruta_test_db,
            ruta_archivo_offline=self.ruta_test_offline,
        )

    def tearDown(self):
        self.db_manager.cerrar()
        if os.path.exists(self.ruta_test_offline):
            try:
                os.remove(self.ruta_test_offline)
            except Exception:
                pass
        if os.path.exists(self.ruta_test_db):
            try:
                os.remove(self.ruta_test_db)
            except Exception:
                pass

    def test_modo_offline_inicial(self):
        """Verifica que sin URI opere en modo offline sin arrojar excepciones."""
        self.assertFalse(self.db_manager.esta_conectado)

    def test_guardado_y_recuperacion_offline(self):
        """Verifica que los resúmenes se almacenen correctamente en el archivo local de respaldo."""
        resumen_ejemplo = {
            "id_lote": "LOTE-UNIT-TEST-99",
            "timestamp": "2026-08-23 19:00:00",
            "total_granos": 50,
            "total_sanos": 45,
            "total_defectuosos": 5,
            "porcentaje_calidad": 90.0,
            "consumo_kwh": 0.0125,
        }

        exito, mensaje = self.db_manager.guardar_resumen_lote(resumen_ejemplo)
        self.assertTrue(exito)
        self.assertIn("Offline", mensaje)
        self.assertTrue(os.path.exists(self.ruta_test_offline))

        # Recuperar últimos lotes
        lotes = self.db_manager.obtener_ultimos_lotes(limite=5)
        self.assertEqual(len(lotes), 1)
        self.assertEqual(lotes[0]["id_lote"], "LOTE-UNIT-TEST-99")


if __name__ == "__main__":
    unittest.main()
