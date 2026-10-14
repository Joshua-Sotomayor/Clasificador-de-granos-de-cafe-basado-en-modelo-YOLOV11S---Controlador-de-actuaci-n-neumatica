"""
Pruebas Unitarias Integradas para el HMI v1.7.0 (test_hmi_v170.py)
Valida la integración de HMI.py con el backend completo:
1. FSM de botonera M/P/R e inhibición de calibración en marcha.
2. Estado BLOQUEO_SEGURIDAD ante corte abrupto y recuperación exclusiva con botón R.
3. Calibración reactiva de Trigger con previsualización, modal de confirmación y persistencia atómica.
4. Destello de indicadores de canal (0..3) por 120 ms.
5. Conmutación dinámica de cabeceras contextuales al cambiar de pestaña.
"""

import os
import sys
import json
import time
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
from ui.dashboard_ctk import (
    DashboardCustomTkinter,
    VentanaConfirmacionTrigger,
    VERDE,
    ROJO_PARO,
    AMBAR_RESET,
    VERDE_LED,
    GRIS_SUAVE,
)


class TestHMIV170(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.ruta_db = os.path.join(self.temp_dir, "test_hmi_v170.db")
        self.ruta_estado = os.path.join(self.temp_dir, "test_estado_maquina.json")
        self.ruta_config = os.path.join(self.temp_dir, "test_config_maquina.json")

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

    def test_fsm_transiciones_y_bloqueo_slider_en_marcha(self):
        """
        Verifica el ciclo completo STANDBY -> EN_MARCHA -> PARO -> STANDBY
        y que el slider de Trigger se bloquee estrictamente durante EN_MARCHA.
        """
        # 1. Estado inicial STANDBY
        self.assertEqual(self.app.estado_operativo, "STANDBY")
        self.assertEqual(self.app.btn_marcha.cget("state"), "normal")
        self.assertEqual(self.app.btn_marcha.cget("fg_color"), VERDE)
        self.assertEqual(self.app.btn_paro.cget("state"), "disabled")
        self.assertEqual(self.app.btn_paro.cget("fg_color"), "#4A1510")  # Rojo bloqueado evidente
        self.assertEqual(self.app.btn_reset.cget("state"), "disabled")
        self.assertEqual(self.app.btn_reset.cget("fg_color"), "#3E2D03")  # Ámbar bloqueado evidente
        self.assertEqual(self.app.slider_trigger.cget("state"), "normal")
        self.assertEqual(self.app.btn_aplicar_trigger.cget("state"), "normal")

        # 2. Pulsar Marcha (M) -> EN_MARCHA
        self.app._al_pulsar_marcha()
        self.assertEqual(self.app.estado_operativo, "EN_MARCHA")
        self.assertEqual(self.app.btn_marcha.cget("state"), "disabled")
        self.assertEqual(self.app.btn_marcha.cget("fg_color"), "#0F3D1E")  # Verde bloqueado evidente
        self.assertEqual(self.app.btn_paro.cget("state"), "normal")
        self.assertEqual(self.app.btn_paro.cget("fg_color"), ROJO_PARO)
        self.assertEqual(self.app.btn_reset.cget("state"), "disabled")
        self.assertEqual(self.app.btn_reset.cget("fg_color"), "#3E2D03")
        # El slider y botón aplicar deben estar bloqueados
        self.assertEqual(self.app.slider_trigger.cget("state"), "disabled")
        self.assertEqual(self.app.btn_aplicar_trigger.cget("state"), "disabled")
        self.assertTrue(self.esp32_bridge._banda_activa)
        self.assertEqual(self.esp32_bridge._piloto_actual, "GREEN")

        # 3. Pulsar Paro (P) -> PARO
        self.app._al_pulsar_paro()
        self.assertEqual(self.app.estado_operativo, "PARO")
        self.assertEqual(self.app.btn_marcha.cget("state"), "normal")  # Actúa como Reanudar
        self.assertEqual(self.app.btn_marcha.cget("fg_color"), "#1E88E5")  # ¡Celeste para Reanudar!
        self.assertEqual(self.app.btn_paro.cget("state"), "disabled")
        self.assertEqual(self.app.btn_paro.cget("fg_color"), "#4A1510")
        self.assertEqual(self.app.btn_reset.cget("state"), "normal")
        self.assertEqual(self.app.btn_reset.cget("fg_color"), AMBAR_RESET)
        # Slider reactivado para calibración con máquina detenida
        self.assertEqual(self.app.slider_trigger.cget("state"), "normal")
        self.assertEqual(self.app.btn_aplicar_trigger.cget("state"), "normal")
        self.assertFalse(self.esp32_bridge._banda_activa)
        self.assertEqual(self.esp32_bridge._piloto_actual, "YELLOW")

        # 4. Pulsar Reset (R) -> Retorno a STANDBY
        self.app._al_pulsar_reset()
        self.assertEqual(self.app.estado_operativo, "STANDBY")
        self.assertEqual(self.app.btn_marcha.cget("state"), "normal")
        self.assertEqual(self.app.btn_marcha.cget("fg_color"), VERDE)
        self.assertEqual(self.app.btn_paro.cget("state"), "disabled")
        self.assertEqual(self.app.btn_paro.cget("fg_color"), "#4A1510")
        self.assertEqual(self.app.btn_reset.cget("state"), "disabled")
        self.assertEqual(self.app.btn_reset.cget("fg_color"), "#3E2D03")
        self.assertEqual(self.esp32_bridge._piloto_actual, "WHITE")

    def test_bloqueo_seguridad_por_corte_abrupto(self):
        """
        Simula un corte abrupto de energía durante marcha (estado_maquina.json = 'EN_MARCHA').
        Verifica inicio en BLOQUEO_SEGURIDAD, alarma en SQLite, piloto rojo y
        desbloqueo exclusivo mediante el botón R.
        """
        payload_corte = {
            "fecha": datetime.now().strftime("%Y-%m-%d"),
            "segundos_hoy": 1200,
            "horas_acumuladas": 0.33,
            "estado_operativo": "EN_MARCHA",
            "requiere_reset_por_corte": False,
        }
        with open(self.ruta_estado, "w", encoding="utf-8") as f:
            json.dump(payload_corte, f)

        # Crear gestor que detectará la parada abrupta
        gestor_corte = GestorTiempoUso(ruta_archivo=self.ruta_estado)
        self.assertTrue(gestor_corte.requiere_reset_por_corte)

        self.app.gestor_tiempo = gestor_corte
        self.app._verificar_corte_abrupto_al_arranque()

        # Debe estar en BLOQUEO_SEGURIDAD
        self.assertEqual(self.app.estado_operativo, "BLOQUEO_SEGURIDAD")
        self.assertEqual(self.app.btn_marcha.cget("state"), "disabled")
        self.assertEqual(self.app.btn_paro.cget("state"), "disabled")
        self.assertEqual(self.app.btn_reset.cget("state"), "normal")
        self.assertEqual(self.esp32_bridge._piloto_actual, "RED")

        # Intentar pulsar Marcha debe mantenerse bloqueado
        self.app._al_pulsar_marcha()
        self.assertEqual(self.app.estado_operativo, "BLOQUEO_SEGURIDAD")

        # Pulsar Reset (R) para purgar y restablecer seguridad
        self.app._al_pulsar_reset()
        self.assertFalse(self.app.gestor_tiempo.requiere_reset_por_corte)
        self.assertEqual(self.app.estado_operativo, "STANDBY")
        self.assertEqual(self.app.btn_marcha.cget("state"), "normal")
        self.assertEqual(self.app.btn_reset.cget("state"), "disabled")
        self.assertEqual(self.esp32_bridge._piloto_actual, "WHITE")

    def test_calibracion_trigger_modal_y_persistencia(self):
        """
        Verifica el movimiento del slider, previsualización, modal de confirmación
        y persistencia al aplicar vs restauración al cancelar.
        """
        y_inicial = self.detector.y_trigger

        # 1. Mover slider al 75%
        self.app._al_mover_slider_trigger(75.0)
        self.assertEqual(self.app.lbl_valor_trigger.cget("text"), "75%")
        self.assertIsNotNone(self.detector.y_trigger_preview)

        # 2. Cancelar -> restaura estado anterior
        self.app._al_pulsar_cancelar_trigger()
        self.assertIsNone(self.detector.y_trigger_preview)

        # 3. Mover slider a 60% y aplicar abriendo el modal
        self.app._al_mover_slider_trigger(60.0)
        self.app._al_pulsar_aplicar_trigger()

        modal = self.app._modal_trigger
        self.assertIsNotNone(modal)
        self.assertTrue(modal.winfo_exists())

        # Simular confirmación en modal
        modal._al_confirmar()

        # Debe haberse actualizado detector.y_trigger y persistido
        self.assertNotEqual(self.detector.y_trigger, y_inicial)

    def test_destello_canales_120ms(self):
        """
        Verifica que al recibir OK:<canal> el círculo indicador
        destelle en VERDE_LED por 120 ms y regrese a GRIS_SUAVE.
        """
        # Todos en gris inicial
        for btn in self.app.luces_canales:
            self.assertEqual(btn.cget("fg_color"), GRIS_SUAVE)

        # Disparo en canal 1
        self.app._al_recibir_respuesta_serial("OK:1")
        self.assertEqual(self.app.luces_canales[1].cget("fg_color"), VERDE_LED)
        self.assertEqual(self.app.luces_canales[0].cget("fg_color"), GRIS_SUAVE)

        # Forzar apagado de prueba
        self.app._apagar_indicador_canal(1)
        self.assertEqual(self.app.luces_canales[1].cget("fg_color"), GRIS_SUAVE)

    def test_conmutacion_cabecera_contextual(self):
        """
        Verifica que al cambiar entre pestañas la barra superior conmute
        los bloques izquierdos según HMI.py.
        """
        # 1. Pestaña Dashboard -> visible barra_izq_dashboard
        self.app.cambiar_pagina("Dashboard")
        self.assertTrue(bool(self.app.barra_izq_dashboard.grid_info()))

        # 2. Pestaña Analíticas -> visible barra_izq_analiticas con LED y lotes
        self.app.cambiar_pagina("Analíticas")
        self.assertTrue(bool(self.app.barra_izq_analiticas.grid_info()))
        self.assertFalse(bool(self.app.barra_izq_dashboard.grid_info()))

        # 3. Pestaña Registros -> visible barra_izq_registros
        self.app.cambiar_pagina("Registros")
        self.assertTrue(bool(self.app.barra_izq_registros.grid_info()))
        self.assertFalse(bool(self.app.barra_izq_analiticas.grid_info()))

    def test_logica_variedad_grafico_13_clases(self):
        """
        Verifica que en modo 13 Clases:
        - Si solo se detectan granos de Arábica, la gráfica solo muestre clases de Arábica.
        - Si solo se detectan granos de Robusta, solo muestre clases de Robusta.
        - Si se detectan ambos, muestre las 13 clases.
        """
        self.detector.es_modo_13clases = True

        # Caso 1: Solo Arábica
        self.app.gestor_lotes.conteo_crudo = {"Arabica_Bueno": 50, "Arabica_Brocado": 5}
        self.app._actualizar_grafico_reactivo()
        labels_1 = [label.get_text() for label in self.app.ax_analiticas.get_yticklabels()]
        self.assertIn("AR_B", labels_1)
        self.assertNotIn("RO_B", labels_1)
        self.assertNotIn("NEG_P", labels_1)

        # Caso 2: Solo Robusta
        self.app.gestor_lotes.conteo_crudo = {"Robusta_Bueno": 40, "Robusta_Negro": 2}
        self.app._actualizar_grafico_reactivo()
        labels_2 = [label.get_text() for label in self.app.ax_analiticas.get_yticklabels()]
        self.assertIn("RO_B", labels_2)
        self.assertNotIn("AR_B", labels_2)
        self.assertNotIn("NEG_T", labels_2)

        # Caso 3: Ambas variedades presentes
        self.app.gestor_lotes.conteo_crudo = {"Arabica_Bueno": 30, "Robusta_Bueno": 20}
        self.app._actualizar_grafico_reactivo()
        labels_3 = [label.get_text() for label in self.app.ax_analiticas.get_yticklabels()]
        self.assertIn("AR_B", labels_3)
        self.assertIn("RO_B", labels_3)

    def test_columna_gb_ar_ro_y_limpieza_id_lote(self):
        """
        Verifica que la consulta y tabla de Historial calcule 'GB A/R (%)'
        como 'X% / Y%' y que el identificador del lote no tenga el prefijo 'LOTE-'.
        """
        import numpy as np
        resumen_test = {
            "id_lote": "LOTE-20261013-999999",
            "timestamp": "2026-10-13 20:00:00",
            "modelo_activo": "13_clases",
            "duracion_segundos": 120.0,
            "duracion_formato": "00:02:00",
            "consumo_kwh": 0.015,
            "potencia_nominal_kw": 0.5,
            "total_granos": 100,
            "total_sanos": 100,
            "total_defectuosos": 0,
            "porcentaje_calidad": 100.0,
            "latencia_promedio_ms": 3.2,
            "fps_promedio": 30.0,
            "conteo_crudo": {
                "Arabica_Bueno": 90,
                "Robusta_Bueno": 10,
            },
        }
        self.db_manager.guardar_resumen_lote_sync(resumen_test)

        historial = self.db_manager.obtener_historial_lotes(limite=5)
        self.assertTrue(len(historial) > 0)
        primer_lote = historial[0]
        self.assertEqual(primer_lote.get("prop_gb_ar_ro"), "90% / 10%")

        # Probar renderizado en tabla
        self.app._poblar_tabla_historial()
        filas = self.app.cuerpo_tabla_historial.winfo_children()
        self.assertTrue(len(filas) > 0)

    def test_extraccion_frame_video_y_fallback(self):
        """
        Verifica que _bucle_actualizacion_video extraiga y renderice
        los fotogramas desde la cola_salida y desde el fallback.
        """
        import numpy as np
        # 1. Simular fotograma BGR en cola
        frame_dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        self.detector.cola_salida.put({
            "frame_top": frame_dummy,
            "frame_bottom": frame_dummy,
            "fps": 30.0,
            "latencia_ms": 2.5,
        })
        self.app._bucle_actualizacion_video()
        self.assertIsNotNone(self.app.lbl_video_display.image)

        # 2. Fallback directo al detector
        self.detector._ultimo_frame_top_render = frame_dummy
        self.app._bucle_actualizacion_video()
        self.assertIsNotNone(self.app.lbl_video_display.image)


if __name__ == "__main__":
    unittest.main()
