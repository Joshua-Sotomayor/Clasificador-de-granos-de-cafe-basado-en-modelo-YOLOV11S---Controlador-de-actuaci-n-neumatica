"""
Pruebas Unitarias para Arquitectura de Visión de Doble Cámara Maestro-Esclavo (v1.6.0)
Valida:
1. Acoplamiento espacial de granos con tolerancia horizontal (tolerancia_x_px = 25).
2. Fusión lógica booleana con operador OR inclusivo (Defecto_Top OR Defecto_Bottom).
3. Garantía anti-duplicidad cinemática de eyección mecatrónica (SeguidorGranos, Y >= 500, PROCESADO = True).
4. Autoridad exclusiva de la cámara superior (Master) sobre el puente ESP32Bridge.
5. Estructura y sincronización del payload dual para la interfaz gráfica.
"""

import os
import sys
import unittest
import queue
import time
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.detector import (
    YOLODetector,
    SeguidorGranos,
    GranoRastreado,
    fusionar_detecciones_doble_camara,
    calcular_centroide,
    asignar_canal,
    LINEA_DISPARO_Y,
    CAMERA_MATCHING_X_TOLERANCE_PX_DEFAULT,
)
from core.metricas import GestorMetricas
from storage.database import DatabaseManager
from ui.dashboard_ctk import DashboardCustomTkinter


class MockESP32Bridge:
    """Mock para verificar llamadas de actuación hacia el hardware sin puerto serial real."""
    def __init__(self):
        self.disparos = []

    def disparar_canal(self, canal: int) -> bool:
        self.disparos.append(canal)
        return True


class TestDualCameraVision(unittest.TestCase):
    def setUp(self):
        self.mock_bridge = MockESP32Bridge()
        self.cola = queue.Queue(maxsize=5)
        self.detector = YOLODetector(
            ruta_modelo="models/inexistente.pt",
            fuente_video="demo",
            cola_salida=self.cola,
            esp32_bridge=self.mock_bridge,
        )

    def tearDown(self):
        self.detector.detener()

    def test_tolerancia_x_acoplamiento(self):
        """Verifica que el emparejamiento entre cámaras dorsal y ventral respete la tolerancia de 25 px."""
        def crear_top():
            return [{
                "caja": (60, 200, 100, 240),
                "x_center": 80,
                "y_center": 220,
                "canal": 0,
                "es_defecto": False,
                "nombre_clase": "Arabica_Bueno",
            }]

        # Caso 1: Grano ventral a 15 px (delta <= 25) -> Debe emparejarse
        top1 = crear_top()
        bot_cercano = [{
            "caja": (75, 205, 115, 245),
            "x_center": 95,  # |80 - 95| = 15 <= 25
            "y_center": 225,
            "canal": 0,
            "es_defecto": True,
            "nombre_clase": "Arabica_Brocado",
        }]
        fused = fusionar_detecciones_doble_camara(top1, bot_cercano, tolerancia_x_px=25)
        self.assertTrue(fused[0]["match_bottom"])
        self.assertTrue(fused[0]["es_defecto"])  # OR inclusivo: False or True = True
        self.assertEqual(fused[0]["origen_defecto"], "BOTTOM")

        # Caso 2: Grano ventral a 35 px (delta > 25) -> NO debe emparejarse
        top2 = crear_top()
        bot_lejano = [{
            "caja": (95, 205, 135, 245),
            "x_center": 115,  # |80 - 115| = 35 > 25
            "y_center": 225,
            "canal": 0,
            "es_defecto": True,
            "nombre_clase": "Arabica_Brocado",
        }]
        fused_lejano = fusionar_detecciones_doble_camara(top2, bot_lejano, tolerancia_x_px=25)
        self.assertFalse(fused_lejano[0]["match_bottom"])
        self.assertFalse(fused_lejano[0]["es_defecto"])  # No hubo match, se mantiene False

        # Caso 3: Mismo delta X pero diferente canal -> NO debe emparejarse
        top3 = crear_top()
        bot_otro_canal = [{
            "caja": (150, 205, 190, 245),
            "x_center": 170,
            "y_center": 225,
            "canal": 1,  # Canal distinto al grano superior
            "es_defecto": True,
            "nombre_clase": "Arabica_Brocado",
        }]
        fused_otro_canal = fusionar_detecciones_doble_camara(top3, bot_otro_canal, tolerancia_x_px=25)
        self.assertFalse(fused_otro_canal[0]["match_bottom"])
        self.assertFalse(fused_otro_canal[0]["es_defecto"])

    def test_fusion_logica_or_inclusivo(self):
        """Verifica la tabla de verdad completa del operador booleano OR inclusivo."""
        # Top = False, Bottom = False -> Fused = False
        t_sano = [{"x_center": 100, "canal": 0, "es_defecto": False}]
        b_sano = [{"x_center": 105, "canal": 0, "es_defecto": False}]
        res = fusionar_detecciones_doble_camara(t_sano, b_sano, tolerancia_x_px=25)
        self.assertFalse(res[0]["es_defecto"])
        self.assertEqual(res[0]["origen_defecto"], "NINGUNO")

        # Top = False, Bottom = True -> Fused = True
        t_sano2 = [{"x_center": 100, "canal": 0, "es_defecto": False}]
        b_def = [{"x_center": 105, "canal": 0, "es_defecto": True}]
        res = fusionar_detecciones_doble_camara(t_sano2, b_def, tolerancia_x_px=25)
        self.assertTrue(res[0]["es_defecto"])
        self.assertEqual(res[0]["origen_defecto"], "BOTTOM")

        # Top = True, Bottom = False -> Fused = True
        t_def = [{"x_center": 100, "canal": 0, "es_defecto": True}]
        b_sano2 = [{"x_center": 105, "canal": 0, "es_defecto": False}]
        res = fusionar_detecciones_doble_camara(t_def, b_sano2, tolerancia_x_px=25)
        self.assertTrue(res[0]["es_defecto"])
        self.assertEqual(res[0]["origen_defecto"], "TOP")

        # Top = True, Bottom = True -> Fused = True
        t_def2 = [{"x_center": 100, "canal": 0, "es_defecto": True}]
        b_def2 = [{"x_center": 105, "canal": 0, "es_defecto": True}]
        res = fusionar_detecciones_doble_camara(t_def2, b_def2, tolerancia_x_px=25)
        self.assertTrue(res[0]["es_defecto"])
        self.assertEqual(res[0]["origen_defecto"], "AMBOS")

    def test_garantia_anti_duplicidad_seguidor_granos(self):
        """
        Verifica que SeguidorGranos despache el disparo mecatrónico EXACTAMENTE UNA VEZ
        cuando el grano defectuoso cruza Y >= 500 a lo largo de fotogramas sucesivos.
        """
        seguidor = SeguidorGranos(distancia_max_px=65.0, tiempo_vida_s=1.0)

        # Fotograma 1: Grano defectuoso en canal 1 antes de la línea (y=480 < 500)
        frame1 = [{"x_center": 240, "y_center": 480, "canal": 1, "es_defecto": True}]
        disparos_f1 = seguidor.actualizar_y_filtrar_disparos(frame1, linea_disparo_y=500)
        self.assertEqual(disparos_f1, [])
        self.assertFalse(frame1[0]["procesado"])

        # Fotograma 2: Mismo grano avanza y cruza la línea (y=510 >= 500)
        frame2 = [{"x_center": 241, "y_center": 510, "canal": 1, "es_defecto": True}]
        disparos_f2 = seguidor.actualizar_y_filtrar_disparos(frame2, linea_disparo_y=500)
        self.assertEqual(disparos_f2, [1])  # DISPARO ÚNICO
        self.assertTrue(frame2[0]["procesado"])
        self.assertEqual(frame2[0]["id_seguimiento"], frame1[0]["id_seguimiento"])

        # Fotograma 3: Grano persiste en zona de disparo en el siguiente frame (y=530 >= 500)
        frame3 = [{"x_center": 242, "y_center": 530, "canal": 1, "es_defecto": True}]
        disparos_f3 = seguidor.actualizar_y_filtrar_disparos(frame3, linea_disparo_y=500)
        self.assertEqual(disparos_f3, [])  # NO DEBE DISPARAR NUEVAMENTE (Inmunidad a doble eyección)
        self.assertTrue(frame3[0]["procesado"])

        # Fotograma 4: Grano sano en canal 2 cruza Y>=500 (y=520)
        frame4 = [{"x_center": 380, "y_center": 520, "canal": 2, "es_defecto": False}]
        disparos_f4 = seguidor.actualizar_y_filtrar_disparos(frame4, linea_disparo_y=500)
        self.assertEqual(disparos_f4, [])  # Grano sano nunca dispara

    def test_autoridad_maestro_en_detector_y_esp32(self):
        """Verifica que la cámara esclava no emita comandos de actuación de forma independiente."""
        # Simular una detección sólo en cámara inferior sin correspondencia en la superior
        deteccion_esclavo_aislada = [{
            "caja": (100, 520, 140, 560),
            "x_center": 120,
            "y_center": 540,  # y >= 500
            "canal": 0,
            "es_defecto": True,
            "es_camara_inferior": True,
        }]

        # Fusión con lista superior vacía
        fused = fusionar_detecciones_doble_camara([], deteccion_esclavo_aislada)
        self.assertEqual(fused, [])  # Ningún grano maestro consolidado

        # Evaluar disparo con la lista consolidada vacía
        canales = self.detector._evaluar_disparo_esp32(fused)
        self.assertEqual(canales, [])
        self.assertEqual(self.mock_bridge.disparos, [])

    def test_payload_dual_sincronizado(self):
        """Verifica que el ciclo del detector genere el payload completo con ambas vistas sincronizadas."""
        self.detector.iniciar()
        time.sleep(0.3)

        payload = self.cola.get(timeout=2.5)
        self.assertIsNotNone(payload)
        self.assertIn("frame_top", payload)
        self.assertIn("frame_bottom", payload)
        self.assertIn("frame_bgr", payload)
        self.assertIn("detecciones", payload)
        self.assertIn("detecciones_top", payload)
        self.assertIn("detecciones_bottom", payload)
        self.assertIn("dual_sync", payload)
        self.assertTrue(payload["dual_sync"])

        self.detector.detener()




class TestDualCameraSelectorsAndHotReload(unittest.TestCase):
    """
    Pruebas Unitarias para Versión 1.6.1:
    - Swap automático por colisión de índice entre cámaras dorsal y ventral.
    - Persistencia diferencial de índices físicos de captura.
    - Reconfiguración dinámica de fuentes en caliente en YOLODetector.
    """
    @classmethod
    def setUpClass(cls):
        cls.ruta_db = "storage/test_dual_cam_db.db"

    def setUp(self):
        self.metricas = GestorMetricas(potencia_nominal_kw=0.5)
        self.db_manager = DatabaseManager(
            uri_mongo="",
            ruta_sqlite=self.ruta_db,
            dias_retencion=30,
        )
        self.cola = queue.Queue(maxsize=5)
        self.detector = YOLODetector(
            ruta_modelo="models/inexistente.pt",
            fuente_video_top=0,
            fuente_video_bottom=1,
            cola_salida=self.cola,
        )

    def tearDown(self):
        if hasattr(self, "detector") and self.detector.ejecutando:
            self.detector.detener()
        self.db_manager.cerrar()
        if os.path.exists(self.ruta_db):
            try:
                os.remove(self.ruta_db)
            except Exception:
                pass

    def test_swap_automatico_por_colision(self):
        """
        Verifica que al seleccionar para la cámara superior el índice que tiene la inferior,
        la cámara inferior se reasigne automáticamente al índice previo de la superior (y viceversa).
        """
        app = DashboardCustomTkinter(
            detector=self.detector,
            metricas=self.metricas,
            db_manager=self.db_manager,
        )
        try:
            # Estado base inicial: Top = 0 ("Cámara 0"), Bottom = 1 ("Cámara 1")
            self.assertEqual(app._fuente_top_actual, 0)
            self.assertEqual(app._fuente_bottom_actual, 1)
            self.assertEqual(app.combo_cam_top.get(), "Cámara 0")
            self.assertEqual(app.combo_cam_bottom.get(), "Cámara 1")

            # 1. Colisión provocada en Top: Seleccionamos Cámara 1 (actualmente asignada a Bottom)
            # Regla: Bottom debe conmutar automáticamente a Cámara 0 (anterior Top)
            app._al_cambiar_camara_top("Cámara 1")
            self.assertEqual(app._fuente_top_actual, 1)
            self.assertEqual(app._fuente_bottom_actual, 0)
            self.assertEqual(app.combo_cam_top.get(), "Cámara 1")
            self.assertEqual(app.combo_cam_bottom.get(), "Cámara 0")
            self.assertEqual(self.detector.fuente_video_top, 1)
            self.assertEqual(self.detector.fuente_video_bottom, 0)

            # 2. Colisión inversa provocada en Bottom: Seleccionamos Cámara 1 (actualmente asignada a Top)
            # Regla: Top debe conmutar automáticamente a Cámara 0 (anterior Bottom)
            app._al_cambiar_camara_bottom("Cámara 1")
            self.assertEqual(app._fuente_bottom_actual, 1)
            self.assertEqual(app._fuente_top_actual, 0)
            self.assertEqual(app.combo_cam_bottom.get(), "Cámara 1")
            self.assertEqual(app.combo_cam_top.get(), "Cámara 0")
            self.assertEqual(self.detector.fuente_video_top, 0)
            self.assertEqual(self.detector.fuente_video_bottom, 1)
        finally:
            app._al_cerrar()

    def test_persistencia_diferencial_de_indices(self):
        """
        Verifica que tras múltiples selecciones y alternancias manuales,
        las dos cámaras mantengan siempre índices físicos diferenciales distintos.
        """
        app = DashboardCustomTkinter(
            detector=self.detector,
            metricas=self.metricas,
            db_manager=self.db_manager,
        )
        try:
            # Secuencia 1: Top pasa a Cámara 2 (no hay colisión con Bottom=1)
            app._al_cambiar_camara_top("Cámara 2")
            self.assertEqual(app._fuente_top_actual, 2)
            self.assertEqual(app._fuente_bottom_actual, 1)
            self.assertNotEqual(app._fuente_top_actual, app._fuente_bottom_actual)

            # Secuencia 2: Bottom pasa a Cámara 2 (colisión -> Top debe conmutar a 1)
            app._al_cambiar_camara_bottom("Cámara 2")
            self.assertEqual(app._fuente_top_actual, 1)
            self.assertEqual(app._fuente_bottom_actual, 2)
            self.assertNotEqual(app._fuente_top_actual, app._fuente_bottom_actual)

            # Secuencia 3: Top pasa a Cámara 0 (no hay colisión con Bottom=2)
            app._al_cambiar_camara_top("Cámara 0")
            self.assertEqual(app._fuente_top_actual, 0)
            self.assertEqual(app._fuente_bottom_actual, 2)
            self.assertNotEqual(app._fuente_top_actual, app._fuente_bottom_actual)

            # Secuencia 4: Bottom pasa a Cámara 0 (colisión -> Top debe conmutar a 2)
            app._al_cambiar_camara_bottom("Cámara 0")
            self.assertEqual(app._fuente_top_actual, 2)
            self.assertEqual(app._fuente_bottom_actual, 0)
            self.assertNotEqual(app._fuente_top_actual, app._fuente_bottom_actual)

            # Secuencia 5: Top pasa a Demo / Sintético
            app._al_cambiar_camara_top("Demo / Sintético")
            self.assertEqual(app._fuente_top_actual, "demo")
            self.assertEqual(app._fuente_bottom_actual, 0)
            self.assertNotEqual(str(app._fuente_top_actual), str(app._fuente_bottom_actual))
        finally:
            app._al_cerrar()

    def test_reconfiguracion_fuentes_en_caliente(self):
        """
        Verifica que invocar cambiar_fuentes_video en caliente con el detector en ejecución
        procese la solicitud sin excepciones no controladas y continúe publicando payloads sincronizados.
        """
        detector_demo = YOLODetector(
            ruta_modelo="models/inexistente.pt",
            fuente_video="demo",
            cola_salida=queue.Queue(maxsize=5),
        )
        detector_demo.iniciar()
        try:
            time.sleep(0.3)

            # Primer payload con fuentes iniciales demo
            payload1 = detector_demo.cola_salida.get(timeout=3.0)
            self.assertIsNotNone(payload1)
            self.assertTrue(payload1["dual_sync"])

            # Reconfiguración en caliente a índices de hardware (con fallback automático tolerante a fallos)
            detector_demo.cambiar_fuentes_video(0, 1)

            # Segundo payload post-reconfiguración (debe continuar emitiendo fotogramas duales válidos)
            payload2 = detector_demo.cola_salida.get(timeout=4.0)
            self.assertIsNotNone(payload2)
            self.assertIn("frame_top", payload2)
            self.assertIn("frame_bottom", payload2)
            self.assertIn("dual_sync", payload2)
            self.assertTrue(payload2["dual_sync"])
            self.assertTrue(detector_demo.ejecutando)

            # Reconfiguración en caliente de regreso a modo demo
            detector_demo.cambiar_fuentes_video("demo", "demo")
            payload3 = detector_demo.cola_salida.get(timeout=3.0)
            self.assertIsNotNone(payload3)
            self.assertTrue(payload3["dual_sync"])
            self.assertTrue(detector_demo.ejecutando)
        finally:
            detector_demo.detener()

    def test_modelo_global_compartido_y_switch(self):
        """
        Verifica que el sistema utilice un modelo de IA único compartido para ambas cámaras
        y que el switch del dashboard conmute el modelo simultáneamente para ambas vistas.
        """
        # Estado inicial del detector: Tri-clase (Campeón V10)
        self.assertFalse(self.detector.es_modo_13clases)
        self.assertEqual(self.detector.ruta_modelo, self.detector.ruta_modelo_triclase)

        # Conmutar globalmente a 13 Clases
        self.detector.cambiar_modelo(usar_13_clases=True)
        self.assertTrue(self.detector.es_modo_13clases)

        # Conmutar de regreso a Tri-clase
        self.detector.cambiar_modelo(usar_13_clases=False)
        self.assertFalse(self.detector.es_modo_13clases)

        # Probar integración con el switch del Dashboard
        app = DashboardCustomTkinter(
            detector=self.detector,
            metricas=self.metricas,
            db_manager=self.db_manager,
        )
        try:
            self.assertEqual(app.switch_modelo.get(), 0)
            self.assertFalse(self.detector.es_modo_13clases)

            # Operario activa switch a 13 Clases en cabecera
            app.switch_modelo.select()
            app._al_cambiar_switch_modelo()
            self.assertTrue(self.detector.es_modo_13clases)
            self.assertTrue(app.gestor_lotes.modelo_13_clases)

            # Operario regresa a Tri-clase
            app.switch_modelo.deselect()
            app._al_cambiar_switch_modelo()
            self.assertFalse(self.detector.es_modo_13clases)
            self.assertFalse(app.gestor_lotes.modelo_13_clases)
        finally:
            app._al_cerrar()

if __name__ == "__main__":
    unittest.main()
