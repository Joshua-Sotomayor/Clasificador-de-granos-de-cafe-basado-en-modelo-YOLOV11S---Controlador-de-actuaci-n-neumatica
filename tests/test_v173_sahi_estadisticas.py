import unittest
import numpy as np
from core.detector import YOLODetector
from storage.database import DatabaseManager, GestorLotes
from core.metricas import GestorMetricas


class TestV173SahiEstadisticas(unittest.TestCase):
    """Pruebas unitarias para validar las mejoras v1.7.3: SAHI, conteo por unidades y visor limpio."""

    def setUp(self):
        import uuid
        self.ruta_db = f"storage/test_v173_{uuid.uuid4().hex[:8]}.db"
        self.detector = YOLODetector(fuente_video="demo")
        self.db = DatabaseManager(ruta_sqlite=self.ruta_db)
        self.gestor_lotes = GestorLotes(db_manager=self.db, timeout_inactividad_seg=10)

    def tearDown(self):
        import os, time
        self.gestor_lotes.detener()
        self.detector.detener()
        self.db.cerrar()
        time.sleep(0.05)
        if os.path.exists(self.ruta_db):
            try:
                os.remove(self.ruta_db)
            except Exception:
                pass

    def test_selector_4_modos_y_sahi(self):
        """Valida que detector y gestor de lotes conmuten correctamente entre los 4 modos."""
        # 1. Tri-clase
        self.detector.cambiar_modelo(usar_13_clases=False, modo_sahi=False)
        self.assertFalse(self.detector.es_modo_13clases)
        self.assertFalse(self.detector.modo_sahi)

        # 2. 13 Clases
        self.detector.cambiar_modelo(usar_13_clases=True, modo_sahi=False)
        self.assertTrue(self.detector.es_modo_13clases)
        self.assertFalse(self.detector.modo_sahi)

        # 3. Tri-clase + SAHI
        self.detector.cambiar_modelo(usar_13_clases=False, modo_sahi=True)
        self.assertFalse(self.detector.es_modo_13clases)
        self.assertTrue(self.detector.modo_sahi)

        # 4. 13 Clases + SAHI
        self.detector.cambiar_modelo(usar_13_clases=True, modo_sahi=True)
        self.assertTrue(self.detector.es_modo_13clases)
        self.assertTrue(self.detector.modo_sahi)

    def test_inferencia_sahi_ejecucion(self):
        """Verifica que _ejecutar_inferencia_sahi procese un frame sintético sin excepciones."""
        self.detector.modo_sahi = True
        frame_dummy = np.full((480, 640, 3), 200, dtype=np.uint8)
        res = self.detector._ejecutar_inferencia_sahi(frame_dummy)
        self.assertIsInstance(res, list)

    def test_tarjeta_estadisticas_unidades_y_proporcion(self):
        """Verifica que el conteo en lote sea solo por unidades y la proporción de buenos sea exacta."""
        self.gestor_lotes.configurar_modelo(modelo_13_clases=True, modo_sahi=False)

        # Lote de 4 granos: 2 buenos (Arabica_Bueno, Robusta_Bueno) y 2 defectos (Arabica_Negro, Robusta_Brocado)
        detecciones = [
            {"id_seguimiento": 101, "nombre_clase": "Arabica_Bueno", "clase_id": 2, "es_defecto": False},
            {"id_seguimiento": 102, "nombre_clase": "Robusta_Bueno", "clase_id": 9, "es_defecto": False},
            {"id_seguimiento": 103, "nombre_clase": "Arabica_Negro", "clase_id": 6, "es_defecto": True},
            {"id_seguimiento": 104, "nombre_clase": "Robusta_Brocado", "clase_id": 8, "es_defecto": True},
        ]
        self.gestor_lotes.registrar_detecciones(detecciones, fps=30.0, latencia_ms=10.0)

        # Re-enviar los mismos IDs (simulando cuadros continuos de video a 30 fps)
        # La garantía anti-duplicidad NO debe incrementar el total
        self.gestor_lotes.registrar_detecciones(detecciones, fps=30.0, latencia_ms=10.0)

        tot_granos = self.gestor_lotes.total_granos
        self.assertEqual(tot_granos, 4)

        conteo = self.gestor_lotes.conteo_crudo
        ar_b = conteo.get("Arabica_Bueno", 0)
        ro_b = conteo.get("Robusta_Bueno", 0)
        buenos = ar_b + ro_b
        self.assertEqual(buenos, 2)

        proporcion = (buenos / tot_granos) * 100.0
        self.assertEqual(proporcion, 50.0)

    def test_tri_clase_defecto_no_suma_bueno(self):
        """Verifica que en Tri-clase un grano de defecto nunca incremente granos sanos."""
        self.gestor_lotes.configurar_modelo(modelo_13_clases=False, modo_sahi=False)

        detecciones = [
            {"id_seguimiento": 201, "nombre_clase": "Grano_Defecto", "clase_id": 2, "es_defecto": True},
        ]
        self.gestor_lotes.registrar_detecciones(detecciones, fps=30.0, latencia_ms=10.0)

        self.assertEqual(self.gestor_lotes.total_granos, 1)
        self.assertEqual(self.gestor_lotes.total_defectuosos, 1)
        self.assertEqual(self.gestor_lotes.total_sanos, 0)
        self.assertEqual(self.gestor_lotes.conteo_crudo.get("Arabica_Bueno", 0), 0)
        self.assertEqual(self.gestor_lotes.conteo_crudo.get("Grano_Defecto", 0), 1)

    def test_visor_hud_sin_recuadro_negro(self):
        """Verifica que _dibujar_hud no dibuje recuadros negros sobre el frame."""
        frame = np.full((480, 640, 3), 255, dtype=np.uint8)
        frame_orig = frame.copy()
        self.detector._dibujar_hud(frame, fps=30.0, latencia_ms=5.0, valvula_activa=False, total_granos=10)
        # El frame no debe alterarse por _dibujar_hud (visión limpia)
        np.testing.assert_array_equal(frame, frame_orig)

    def test_filtro_modelos_historial_sqlite(self):
        """Valida que obtener_historial_lotes matchee correctamente los 4 modelos y Todos sin falsos vacíos."""
        # Insertar lotes con diferentes configuraciones
        lote_13 = {
            "id_lote": "LOTE-TEST-13",
            "modelo_activo": "13_clases",
            "modo_sahi": False,
            "total_granos": 10,
            "total_sanos": 8,
            "total_defectuosos": 2,
            "porcentaje_calidad": 80.0,
            "duracion_segundos": 60,
        }
        lote_13_sahi = {
            "id_lote": "LOTE-TEST-13-SAHI",
            "modelo_activo": "13_clases",
            "modo_sahi": True,
            "total_granos": 20,
            "total_sanos": 18,
            "total_defectuosos": 2,
            "porcentaje_calidad": 90.0,
            "duracion_segundos": 120,
        }
        lote_tri = {
            "id_lote": "LOTE-TEST-TRI",
            "modelo_activo": "tri_clase",
            "modo_sahi": False,
            "total_granos": 15,
            "total_sanos": 12,
            "total_defectuosos": 3,
            "porcentaje_calidad": 80.0,
            "duracion_segundos": 90,
        }
        self.db.guardar_lote_transaccional(lote_13)
        self.db.guardar_lote_transaccional(lote_13_sahi)
        self.db.guardar_lote_transaccional(lote_tri)

        # 1. Filtro "Todos"
        res_todos = self.db.obtener_historial_lotes(filtro_modelo="Todos", filtro_fecha="Todos")
        self.assertEqual(len(res_todos), 3)

        # 2. Filtro "13 Clases"
        res_13 = self.db.obtener_historial_lotes(filtro_modelo="13 Clases", filtro_fecha="Todos")
        self.assertEqual(len(res_13), 1)
        self.assertEqual(res_13[0]["id_lote"], "LOTE-TEST-13")

        # 3. Filtro "13 Clases + SAHI"
        res_13_s = self.db.obtener_historial_lotes(filtro_modelo="13 Clases + SAHI", filtro_fecha="Todos")
        self.assertEqual(len(res_13_s), 1)
        self.assertEqual(res_13_s[0]["id_lote"], "LOTE-TEST-13-SAHI")

        # 4. Filtro "Tri-clase"
        res_tri = self.db.obtener_historial_lotes(filtro_modelo="Tri-clase", filtro_fecha="Todos")
        self.assertEqual(len(res_tri), 1)
        self.assertEqual(res_tri[0]["id_lote"], "LOTE-TEST-TRI")

    def test_acronimos_estructurados_constantes(self):
        """Valida la taxonomía de acrónimos estructurados oficial para 13 clases y tri-clase."""
        from ui.dashboard_ctk import ACRONIMOS_13, ACRONIMOS_TRI, ORDEN_13, ORDEN_TRI
        # Verificar Arábica
        self.assertEqual(ACRONIMOS_13["Arabica_Bueno"], "A_BUE")
        self.assertEqual(ACRONIMOS_13["Arabica_Agrio"], "A_AGR")
        self.assertEqual(ACRONIMOS_13["Arabica_Brocado"], "A_BRO")
        self.assertEqual(ACRONIMOS_13["Arabica_Cereza"], "A_CER")
        self.assertEqual(ACRONIMOS_13["Arabica_Concha"], "A_CON")
        self.assertEqual(ACRONIMOS_13["Arabica_Inmaduro"], "A_INM")
        self.assertEqual(ACRONIMOS_13["Arabica_Negro"], "A_NEG")
        self.assertEqual(ACRONIMOS_13["Arabica_Quebrado"], "A_QUE")

        # Verificar Robusta
        self.assertEqual(ACRONIMOS_13["Robusta_Bueno"], "R_BUE")
        self.assertEqual(ACRONIMOS_13["Robusta_Brocado"], "R_BRO")
        self.assertEqual(ACRONIMOS_13["Robusta_Cereza"], "R_CER")
        self.assertEqual(ACRONIMOS_13["Robusta_Negro"], "R_NEG")
        self.assertEqual(ACRONIMOS_13["Robusta_Quebrado"], "R_QUE")

        # Verificar Tri-clase
        self.assertEqual(ACRONIMOS_TRI["Arabica_Bueno"], "A_BUE")
        self.assertEqual(ACRONIMOS_TRI["Robusta_Bueno"], "R_BUE")
        self.assertEqual(ACRONIMOS_TRI["Grano_Defecto"], "G_DEF")


if __name__ == "__main__":
    unittest.main()
