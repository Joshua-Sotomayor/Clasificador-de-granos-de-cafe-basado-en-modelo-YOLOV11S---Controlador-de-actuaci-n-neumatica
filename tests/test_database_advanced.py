"""
Pruebas Unitarias Avanzadas para DatabaseManager y GestorLotes.
Valida:
1. SQLite ACID & almacenamiento offline con sync=0.
2. Purga automática basada en DATA_RETENTION_DAYS.
3. Gestor de Lotes: switch de modelo (13 Clases vs Tri-clase), conteo crudo, cálculo de energía kWh y latencia.
4. Alerta de hardware cuando latencia > 35.0 ms.
"""

import os
import sys
import time
import uuid
import sqlite3
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storage.database import DatabaseManager, GestorLotes, verificar_alarma_valvula


class TestDatabaseAdvanced(unittest.TestCase):
    def setUp(self):
        self.ruta_db_test = f"storage/test_respaldo_{uuid.uuid4().hex[:8]}.db"
        self.db_manager = DatabaseManager(
            uri_mongo="",
            ruta_sqlite=self.ruta_db_test,
            dias_retencion=30,
        )

    def tearDown(self):
        self.db_manager.cerrar()
        time.sleep(0.05)
        if os.path.exists(self.ruta_db_test):
            try:
                os.remove(self.ruta_db_test)
            except Exception:
                pass

    def test_transaccion_sqlite_offline_acid(self):
        """Verifica que el lote se inserte en SQLite con sync=0 y consistencia atómica."""
        resumen = {
            "id_lote": "LOTE-ACID-001",
            "timestamp": "2026-09-09 10:00:00",
            "modelo_activo": "tri_clase",
            "modo_sahi": True,
            "duracion_segundos": 120.0,
            "duracion_formato": "00:02:00",
            "consumo_kwh": 0.01667,
            "potencia_nominal_kw": 0.5,
            "total_granos": 100,
            "total_sanos": 90,
            "total_defectuosos": 10,
            "porcentaje_calidad": 90.0,
            "latencia_promedio_ms": 12.5,
            "fps_promedio": 30.0,
            "conteo_crudo": {"Arabica_Bueno": 70, "Robusta_Bueno": 20, "Grano_Defecto": 10},
        }

        exito, msg = self.db_manager.guardar_lote_transaccional(resumen)
        self.assertTrue(exito)
        self.assertIn("Modo Offline", msg)

        # Verificar en SQLite directamente
        with sqlite3.connect(self.ruta_db_test) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sync, total_granos, modelo_activo, modo_sahi FROM lotes WHERE id_lote=?;", ("LOTE-ACID-001",))
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 0)  # sync = 0
            self.assertEqual(row[1], 100) # total_granos = 100
            self.assertEqual(row[2], "tri_clase")
            self.assertEqual(row[3], 1)  # modo_sahi = 1 (True)

    def test_purga_datos_antiguos(self):
        """Verifica que los registros anteriores a DATA_RETENTION_DAYS sean eliminados."""
        fecha_antigua = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S")
        fecha_reciente = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with sqlite3.connect(self.ruta_db_test) as conn:
            conn.execute(
                """
                INSERT INTO lotes (
                    id_lote, timestamp, fecha_creacion, modelo_activo, modo_sahi,
                    duracion_segundos, duracion_formato, consumo_kwh, potencia_nominal_kw,
                    total_granos, total_sanos, total_defectuosos, porcentaje_calidad,
                    latencia_promedio_ms, fps_promedio, conteo_crudo_json, resumen_completo_json, sync
                ) VALUES (?, ?, ?, 'tri_clase', 0, 10, '00:00:10', 0.001, 0.5, 10, 10, 0, 100.0, 10.0, 30.0, '{}', '{}', 1);
                """,
                ("LOTE-VIEJO-01", fecha_antigua, fecha_antigua),
            )
            conn.execute(
                """
                INSERT INTO lotes (
                    id_lote, timestamp, fecha_creacion, modelo_activo, modo_sahi,
                    duracion_segundos, duracion_formato, consumo_kwh, potencia_nominal_kw,
                    total_granos, total_sanos, total_defectuosos, porcentaje_calidad,
                    latencia_promedio_ms, fps_promedio, conteo_crudo_json, resumen_completo_json, sync
                ) VALUES (?, ?, ?, 'tri_clase', 0, 10, '00:00:10', 0.001, 0.5, 10, 10, 0, 100.0, 10.0, 30.0, '{}', '{}', 1);
                """,
                ("LOTE-NUEVO-01", fecha_reciente, fecha_reciente),
            )

        # Ejecutar purga de 30 días
        res = self.db_manager.purgar_datos_antiguos(dias=30)
        self.assertGreaterEqual(res["sqlite_eliminados"], 1)

        with sqlite3.connect(self.ruta_db_test) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id_lote FROM lotes;")
            filas = [r[0] for r in cursor.fetchall()]
            self.assertNotIn("LOTE-VIEJO-01", filas)
            self.assertIn("LOTE-NUEVO-01", filas)

    def test_gestor_lotes_conteo_tri_clase(self):
        """Valida que GestorLotes clasifique en 3 llaves cuando está en modo tri-clase."""
        gestor = GestorLotes(
            db_manager=self.db_manager,
            timeout_inactividad_seg=60,
            potencia_hardware_kw=0.5,
        )
        try:
            gestor.configurar_modelo(modelo_13_clases=False, modo_sahi=False)

            detecciones = [
                {"nombre_clase": "Arabica_Bueno", "clase_id": 2},
                {"nombre_clase": "Robusta_Bueno", "clase_id": 9},
                {"nombre_clase": "Arabica_Brocado", "clase_id": 1},  # Defecto -> Grano_Defecto
                {"nombre_clase": "Robusta_Cereza", "clase_id": 10},  # Defecto -> Grano_Defecto
            ]

            gestor.registrar_detecciones(detecciones, fps=60.0, latencia_ms=12.0)
            resumen = gestor.finalizar_lote(motivo="manual")

            self.assertIsNotNone(resumen)
            self.assertEqual(resumen["total_granos"], 4)
            self.assertEqual(resumen["total_sanos"], 2)
            self.assertEqual(resumen["total_defectuosos"], 2)
            self.assertEqual(resumen["porcentaje_calidad"], 50.0)
            self.assertEqual(resumen["conteo_crudo"]["Arabica_Bueno"], 1)
            self.assertEqual(resumen["conteo_crudo"]["Robusta_Bueno"], 1)
            self.assertEqual(resumen["conteo_crudo"]["Grano_Defecto"], 2)
            self.assertIn("consumo_kwh", resumen)
        finally:
            gestor.detener()

    def test_gestor_lotes_conteo_13_clases(self):
        """Valida que GestorLotes registre clases individuales cuando está en 13 Clases."""
        gestor = GestorLotes(
            db_manager=self.db_manager,
            timeout_inactividad_seg=60,
            potencia_hardware_kw=0.5,
        )
        try:
            gestor.configurar_modelo(modelo_13_clases=True, modo_sahi=True)

            detecciones = [
                {"nombre_clase": "Arabica_Agrio", "clase_id": 0},
                {"nombre_clase": "Arabica_Bueno", "clase_id": 2},
                {"nombre_clase": "Robusta_Brocado", "clase_id": 8},
            ]

            gestor.registrar_detecciones(detecciones, fps=55.0, latencia_ms=14.0)
            resumen = gestor.finalizar_lote(motivo="manual")

            self.assertIsNotNone(resumen)
            self.assertEqual(resumen["total_granos"], 3)
            self.assertEqual(resumen["total_sanos"], 1)
            self.assertEqual(resumen["total_defectuosos"], 2)
            self.assertEqual(resumen["conteo_crudo"]["Arabica_Agrio"], 1)
            self.assertEqual(resumen["conteo_crudo"]["Arabica_Bueno"], 1)
            self.assertEqual(resumen["conteo_crudo"]["Robusta_Brocado"], 1)
            self.assertEqual(resumen["modelo_activo"], "13_clases")
            self.assertTrue(resumen["modo_sahi"])
        finally:
            gestor.detener()

    def test_alerta_hardware_latencia(self):
        """Valida que verificar_alarma_valvula detecte latencias superiores a 35 ms."""
        self.assertFalse(verificar_alarma_valvula(20.0))
        self.assertTrue(verificar_alarma_valvula(36.5))


if __name__ == "__main__":
    unittest.main()
