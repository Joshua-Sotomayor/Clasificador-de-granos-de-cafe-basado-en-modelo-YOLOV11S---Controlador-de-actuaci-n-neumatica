"""
Pruebas Unitarias para Telemetría Anti-Apagones y Auditoría de Logs Locales (MOPPI v1.4.0).
Verifica:
1. GestorTiempoUso:
   - Inicialización sin archivo.
   - Formato HH:MM:SS.
   - Persistencia atómica anti-apagones.
   - Retención de progreso en la misma fecha.
   - Reseteo automático a 0 al cambiar de fecha.
   - Acumulación condicional de tiempo solo cuando clasificacion_activa es True.
2. Logs Locales y Retención SQLite:
   - Inserción de logs con tipos INFO, WARNING, ALARM.
   - Filtrado por tipo y por rangos de fecha (Hoy, 3 días, 7 días, Todos).
   - Purga automática a los 7 días en purgar_datos_antiguos().
   - Aislamiento total: logs_locales nunca se envían a MongoDB Atlas.
"""

import os
import sys
import json
import time
import sqlite3
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storage.telemetria import GestorTiempoUso
from storage.database import DatabaseManager


class TestTelemetriaLogs(unittest.TestCase):
    def setUp(self):
        self.test_dir = "storage/test_telemetria"
        os.makedirs(self.test_dir, exist_ok=True)
        self.ruta_json = os.path.join(self.test_dir, "estado_maquina.json")
        self.ruta_db = os.path.join(self.test_dir, "test_logs.db")

        if os.path.exists(self.ruta_json):
            os.remove(self.ruta_json)
        if os.path.exists(self.ruta_db):
            os.remove(self.ruta_db)

        self.db_manager = DatabaseManager(
            uri_mongo="",
            ruta_sqlite=self.ruta_db,
            dias_retencion=30,
        )

    def tearDown(self):
        self.db_manager.cerrar()
        if os.path.exists(self.ruta_json):
            try:
                os.remove(self.ruta_json)
            except Exception:
                pass
        tmp_file = f"{self.ruta_json}.tmp"
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass
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
    # PRUEBAS DE TELEMETRÍA Y ANTI-APAGONES (GestorTiempoUso)
    # =========================================================================

    def test_inicializacion_sin_archivo(self):
        """Si no existe estado_maquina.json, inicia en 0 con fecha de hoy."""
        gestor = GestorTiempoUso(ruta_archivo=self.ruta_json)
        hoy = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(gestor.fecha_actual, hoy)
        self.assertEqual(gestor.segundos_uso, 0.0)
        self.assertEqual(gestor.obtener_tiempo_formateado(), "00:00:00")

    def test_formateo_tiempo(self):
        """Verifica el cálculo y formato HH:MM:SS."""
        gestor = GestorTiempoUso(ruta_archivo=self.ruta_json)
        gestor.agregar_segundos(3665)  # 1 hora, 1 minuto, 5 segundos
        self.assertEqual(gestor.obtener_tiempo_formateado(), "01:01:05")

        gestor.segundos_uso = 86399  # 23:59:59
        self.assertEqual(gestor.obtener_tiempo_formateado(), "23:59:59")

    def test_persistencia_atomica_y_recuperacion_mismo_dia(self):
        """Simula corte de energía y reinicio de máquina el mismo día."""
        gestor1 = GestorTiempoUso(ruta_archivo=self.ruta_json)
        gestor1.agregar_segundos(1250)
        gestor1.guardar_estado()

        self.assertTrue(os.path.exists(self.ruta_json))
        with open(self.ruta_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["segundos_uso"], 1250.0)
        self.assertEqual(data["fecha"], datetime.now().strftime("%Y-%m-%d"))

        # Reinicio de máquina el mismo día
        gestor2 = GestorTiempoUso(ruta_archivo=self.ruta_json)
        self.assertEqual(gestor2.segundos_uso, 1250.0)
        self.assertEqual(gestor2.obtener_tiempo_formateado(), "00:20:50")

    def test_reinicio_al_cambiar_de_fecha(self):
        """Si el archivo guardado tiene fecha de ayer, se reinicia a 0 hoy."""
        ayer = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        with open(self.ruta_json, "w", encoding="utf-8") as f:
            json.dump({"fecha": ayer, "segundos_uso": 15000.0}, f)

        gestor = GestorTiempoUso(ruta_archivo=self.ruta_json)
        hoy = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(gestor.fecha_actual, hoy)
        self.assertEqual(gestor.segundos_uso, 0.0)
        self.assertEqual(gestor.obtener_tiempo_formateado(), "00:00:00")

    def test_tick_solo_cuando_clasificacion_activa(self):
        """El contador solo avanza si clasificacion_activa es True."""
        gestor = GestorTiempoUso(ruta_archivo=self.ruta_json, intervalo_guardado_seg=1)
        gestor._ultimo_tick_ts = time.time() - 2.0

        # Cuando no está activa: no debe sumar segundos
        gestor.tick(clasificacion_activa=False)
        self.assertEqual(gestor.segundos_uso, 0)

        # Cuando está activa: debe sumar la diferencia transcurrida
        gestor._ultimo_tick_ts = time.time() - 3.0
        gestor.tick(clasificacion_activa=True)
        self.assertGreaterEqual(gestor.segundos_uso, 2)

    # =========================================================================
    # PRUEBAS DE LOGS LOCALES Y PURGA DE 7 DÍAS (DatabaseManager)
    # =========================================================================

    def test_registro_y_consulta_logs_locales(self):
        """Inserta logs locales con diferentes niveles y los consulta correctamente."""
        self.db_manager.registrar_log_local("INFO", "Sistema iniciado correctamente")
        self.db_manager.registrar_log_local("WARNING", "Latencia de inferencia elevada (42 ms)")
        self.db_manager.registrar_log_local("ALARM", "Válvula neumática no responde (48 ms)")

        # Consulta general
        todos = self.db_manager.obtener_logs_locales(tipo=None, filtro_fecha="Hoy")
        self.assertEqual(len(todos), 3)

        # Filtro por tipo ALARM
        alarmas = self.db_manager.obtener_logs_locales(tipo="ALARM")
        self.assertEqual(len(alarmas), 1)
        self.assertIn("Válvula neumática", alarmas[0]["mensaje"])

        # Filtro por tipo WARNING
        warnings = self.db_manager.obtener_logs_locales(tipo="WARNING")
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["tipo"], "WARNING")

        # Filtro por tipo INFO
        infos = self.db_manager.obtener_logs_locales(tipo="INFO")
        self.assertEqual(len(infos), 1)

    def test_purga_automatica_logs_7_dias(self):
        """Verifica que registros con más de 7 días se eliminen y los recientes se mantengan."""
        hoy_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hace_5_dias = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
        hace_8_dias = (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")
        hace_20_dias = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")

        with self.db_manager._conectar_sqlite() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT INTO logs_locales (timestamp, tipo, mensaje) VALUES (?, ?, ?)",
                [
                    (hoy_str, "INFO", "Evento actual"),
                    (hace_5_dias, "WARNING", "Evento de hace 5 días"),
                    (hace_8_dias, "ALARM", "Evento viejo de hace 8 días"),
                    (hace_20_dias, "INFO", "Evento viejo de hace 20 días"),
                ],
            )
            conn.commit()

        # Ejecutar purga
        self.db_manager.purgar_datos_antiguos()

        # Verificar logs remanentes
        logs_restantes = self.db_manager.obtener_logs_locales(tipo=None, filtro_fecha="Todos")
        self.assertEqual(len(logs_restantes), 2)
        mensajes_restantes = [l["mensaje"] for l in logs_restantes]
        self.assertIn("Evento actual", mensajes_restantes)
        self.assertIn("Evento de hace 5 días", mensajes_restantes)
        self.assertNotIn("Evento viejo de hace 8 días", mensajes_restantes)
        self.assertNotIn("Evento viejo de hace 20 días", mensajes_restantes)

    def test_aislamiento_total_frente_a_mongodb(self):
        """Garantiza que la sincronización con la nube no intente transmitir logs_locales."""
        self.db_manager.registrar_log_local("ALARM", "Falla de presión neumática local")
        
        # Sincronización en modo desconectado no debe dar error y sólo opera sobre lotes_offline
        resultado = self.db_manager.sincronizar_pendientes()
        self.assertEqual(resultado, 0)

        # La tabla de logs debe seguir intacta
        logs = self.db_manager.obtener_logs_locales()
        self.assertEqual(len(logs), 1)


if __name__ == "__main__":
    unittest.main()
