"""
Capa de Interfaz de Usuario Principal (Consumidor Flet)
Implementa el Dashboard con pestañas 'Vista en Vivo' y 'Panel Analítico',
conectado al detector YOLO y al gestor de métricas en tiempo real.
"""

import time
import queue
import threading
import flet as ft
from typing import Optional

from ui.theme import InstitucionalTheme
from ui.components.stat_card import StatCard, StatusBadge
from ui.components.charts import GraficoBarrasGranos, GraficoPastelDefectos
from core.detector import YOLODetector
from core.metricas import GestorMetricas
from storage.database import MongoManager


class InterfazClasificadora:
    """
    Controlador principal de la interfaz Flet.
    Consume los frames del YOLODetector, actualiza los gráficos analíticos
    y permite interactuar con la base de datos MongoDB Atlas.
    """

    def __init__(
        self,
        page: ft.Page,
        detector: YOLODetector,
        metricas: GestorMetricas,
        db_manager: MongoManager,
    ):
        self.page = page
        self.detector = detector
        self.metricas = metricas
        self.db_manager = db_manager

        # Configuración inicial de la página
        self.page.title = "MOPPI - Clasificador Óptico de Café (Finca Alvizua)"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.bgcolor = InstitucionalTheme.BLANCO_FONDO
        self.page.padding = 20
        self.page.width = 1280
        self.page.height = 860

        # Control del bucle de actualización visual
        self._hilo_consumidor_activo = True
        self._hilo_consumidor: Optional[threading.Thread] = None

        self._construir_componentes()
        self._construir_interfaz()
        self._iniciar_bucle_consumidor()

    def _construir_componentes(self) -> None:
        """Inicializa los controles y componentes de UI."""
        # --- Cabecera ---
        self.badge_db = StatusBadge(
            etiqueta="MongoDB Atlas: Conectando...",
            activo=False,
            color_activo=InstitucionalTheme.VERDE_ULSA,
            color_inactivo=InstitucionalTheme.AMARILLO_ALERTA,
        )
        self.badge_modelo = StatusBadge(
            etiqueta="Modelo: YOLOv8" if not self.detector.modo_simulado else "Modo Simulación",
            activo=not self.detector.modo_simulado,
            color_activo=InstitucionalTheme.VERDE_ULSA,
            color_inactivo=InstitucionalTheme.GRIS_TERCIARIO,
        )

        # --- Pestaña 1: Vista en Vivo ---
        self.img_video = ft.Image(
            src=b"",
            fit=ft.BoxFit.CONTAIN,
            width=680,
            height=460,
            border_radius=10,
        )
        self.placeholder_video = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.VIDEOCAM_OFF_OUTLINED, size=56, color=InstitucionalTheme.GRIS_TERCIARIO),
                    ft.Text("Transmisión en espera", style=InstitucionalTheme.estilo_titulo(16)),
                    ft.Text("Presione 'Iniciar Clasificación' para comenzar la captura", style=InstitucionalTheme.estilo_subtitulo(12)),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            alignment=ft.Alignment.CENTER,
            width=680,
            height=460,
        )

        self.contenedor_feed = ft.Container(
            content=self.placeholder_video,
            alignment=ft.Alignment.CENTER,
            bgcolor=InstitucionalTheme.BLANCO_PURO,
            border_radius=15,
            padding=10,
            expand=True,
            **InstitucionalTheme.estilo_tarjeta()
        )

        # Controles y Telemetría de Vista en Vivo
        self.dropdown_fuente = ft.Dropdown(
            label="Fuente de Video",
            value=str(self.detector.fuente_video),
            options=[
                ft.dropdown.Option("0", "Cámara Web Principal (ID: 0)"),
                ft.dropdown.Option("1", "Cámara Secundaria (ID: 1)"),
                ft.dropdown.Option("demo", "Modo Simulación (Banda Sintética)"),
            ],
            width=280,
            border_color=InstitucionalTheme.CAFE_CLARO,
            focused_border_color=InstitucionalTheme.VERDE_ULSA,
            on_change=self._cambiar_fuente_video,
        )

        self.btn_iniciar = ft.ElevatedButton(
            text="Iniciar Clasificación",
            icon=ft.Icons.PLAY_ARROW,
            style=ft.ButtonStyle(
                color=InstitucionalTheme.BLANCO_PURO,
                bgcolor=InstitucionalTheme.VERDE_ULSA,
                padding=ft.Padding.symmetric(horizontal=18, vertical=12),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._iniciar_detector,
        )
        self.btn_pausar = ft.OutlinedButton(
            text="Pausar",
            icon=ft.Icons.PAUSE,
            style=ft.ButtonStyle(
                color=InstitucionalTheme.CAFE_TEXTO,
                side=ft.BorderSide(1.5, InstitucionalTheme.CAFE_TEXTO),
                padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._pausar_detector,
            disabled=True,
        )
        self.btn_detener = ft.OutlinedButton(
            text="Detener",
            icon=ft.Icons.STOP,
            style=ft.ButtonStyle(
                color=InstitucionalTheme.ROJO_DEFECTO,
                side=ft.BorderSide(1.5, InstitucionalTheme.ROJO_DEFECTO),
                padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._detener_detector,
            disabled=True,
        )

        # Indicadores en Vivo
        self.txt_fps_vivo = ft.Text("0.0 FPS", style=InstitucionalTheme.estilo_valor_kpi(18))
        self.txt_latencia_vivo = ft.Text("0.0 ms", style=InstitucionalTheme.estilo_valor_kpi(18))
        self.badge_valvula = StatusBadge("Válvula: STANDBY", activo=False)
        self.txt_granos_frame = ft.Text("0", style=InstitucionalTheme.estilo_valor_kpi(18))

        # --- Pestaña 2: Panel Analítico ---
        self.card_tiempo = StatCard(
            titulo="Tiempo de Operación",
            valor_inicial="00:00:00 Hrs",
            subtitulo="Cronómetro activo",
            icono=ft.Icons.TIMER_OUTLINED,
            color_icono=InstitucionalTheme.CAFE_TEXTO,
            fondo_icono=InstitucionalTheme.CAFE_CLARO,
        )
        self.card_consumo = StatCard(
            titulo="Consumo Energético",
            valor_inicial="0.0000 kWh",
            subtitulo=f"P. Nom: {self.metricas.potencia_nominal_kw} kW",
            icono=ft.Icons.BOLT,
            color_icono=InstitucionalTheme.AMARILLO_ALERTA,
            fondo_icono="#FFF8E1",
        )
        self.card_total_granos = StatCard(
            titulo="Granos Procesados",
            valor_inicial="0",
            subtitulo="Calidad: 100.0%",
            icono=ft.Icons.GRAIN,
            color_icono=InstitucionalTheme.VERDE_ULSA,
            fondo_icono=InstitucionalTheme.VERDE_CLARO,
        )
        self.card_latencia_prom = StatCard(
            titulo="Latencia Promedio",
            valor_inicial="0.0 ms",
            subtitulo="FPS Promedio: 0.0",
            icono=ft.Icons.SPEED,
            color_icono=InstitucionalTheme.CAFE_TEXTO,
            fondo_icono=InstitucionalTheme.CAFE_CLARO,
        )

        # Gráficos
        self.grafico_barras = GraficoBarrasGranos(expand=True)
        self.grafico_pastel = GraficoPastelDefectos(expand=True)

        # Acciones de lote
        self.btn_guardar_lote = ft.ElevatedButton(
            text="Guardar Resumen en MongoDB Atlas",
            icon=ft.Icons.CLOUD_UPLOAD_OUTLINED,
            style=ft.ButtonStyle(
                color=InstitucionalTheme.BLANCO_PURO,
                bgcolor=InstitucionalTheme.VERDE_ULSA,
                padding=ft.Padding.symmetric(horizontal=20, vertical=12),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._guardar_lote_mongodb,
        )
        self.btn_reiniciar_sesion = ft.OutlinedButton(
            text="Reiniciar Estadísticas / Nuevo Lote",
            icon=ft.Icons.REFRESH,
            style=ft.ButtonStyle(
                color=InstitucionalTheme.CAFE_TEXTO,
                side=ft.BorderSide(1.5, InstitucionalTheme.CAFE_TEXTO),
                padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._reiniciar_estadisticas,
        )

    def _construir_interfaz(self) -> None:
        """Ensambla el árbol de widgets y pestañas."""
        # Barra Superior / Encabezado
        cabecera = ft.Row(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.COFFEE, size=32, color=InstitucionalTheme.VERDE_ULSA),
                        ft.Column(
                            controls=[
                                ft.Text(
                                    "MOPPI | CLASIFICADOR ÓPTICO DE CAFÉ",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color=InstitucionalTheme.CAFE_TEXTO,
                                ),
                                ft.Text(
                                    "Inferencia en Tiempo Real & Telemetría Electromecánica (Finca Alvizua)",
                                    size=12,
                                    color=InstitucionalTheme.GRIS_TERCIARIO,
                                ),
                            ],
                            spacing=1,
                        ),
                    ],
                    spacing=12,
                ),
                ft.Row(
                    controls=[
                        self.badge_modelo,
                        self.badge_db,
                    ],
                    spacing=10,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Contenido Pestaña 1: Vista en Vivo
        panel_lateral_vivo = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("Configuración de Captura", style=InstitucionalTheme.estilo_titulo(15)),
                    self.dropdown_fuente,
                    ft.Divider(color=InstitucionalTheme.CAFE_CLARO, height=15),
                    ft.Text("Control de Inferencia", style=InstitucionalTheme.estilo_titulo(15)),
                    ft.Row(controls=[self.btn_iniciar], alignment=ft.MainAxisAlignment.START),
                    ft.Row(controls=[self.btn_pausar, self.btn_detener], spacing=10),
                    ft.Divider(color=InstitucionalTheme.CAFE_CLARO, height=15),
                    ft.Text("Telemetría en Vivo", style=InstitucionalTheme.estilo_titulo(15)),
                    ft.Row([ft.Text("Tasa de Procesamiento:", style=InstitucionalTheme.estilo_subtitulo(12)), self.txt_fps_vivo], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([ft.Text("Latencia de Inferencia:", style=InstitucionalTheme.estilo_subtitulo(12)), self.txt_latencia_vivo], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([ft.Text("Granos en Cuadro:", style=InstitucionalTheme.estilo_subtitulo(12)), self.txt_granos_frame], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Container(height=5),
                    ft.Row([ft.Text("Respuesta Neumática (<35ms):", style=InstitucionalTheme.estilo_subtitulo(11)), self.badge_valvula], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ],
                spacing=10,
            ),
            width=320,
            **InstitucionalTheme.estilo_tarjeta()
        )

        vista_vivo_tab = ft.Row(
            controls=[
                self.contenedor_feed,
                panel_lateral_vivo,
            ],
            expand=True,
            spacing=15,
        )

        # Contenido Pestaña 2: Panel Analítico
        fila_metricas = ft.Row(
            controls=[
                self.card_tiempo,
                self.card_consumo,
                self.card_total_granos,
                self.card_latencia_prom,
            ],
            spacing=15,
        )

        fila_graficos = ft.Row(
            controls=[
                self.grafico_barras,
                self.grafico_pastel,
            ],
            expand=True,
            spacing=15,
        )

        fila_acciones = ft.Row(
            controls=[
                self.btn_guardar_lote,
                self.btn_reiniciar_sesion,
            ],
            spacing=12,
            alignment=ft.MainAxisAlignment.END,
        )

        dashboard_tab = ft.Column(
            controls=[
                fila_metricas,
                fila_graficos,
                fila_acciones,
            ],
            expand=True,
            spacing=15,
        )

        # Control de Pestañas Principal
        tabs = ft.Tabs(
            selected_index=0,
            animation_duration=250,
            label_color=InstitucionalTheme.VERDE_ULSA,
            unselected_label_color=InstitucionalTheme.CAFE_TEXTO,
            indicator_color=InstitucionalTheme.VERDE_ULSA,
            indicator_tab_size=True,
            tabs=[
                ft.Tab(
                    text="Vista en Vivo",
                    icon=ft.Icons.VIDEOCAM,
                    content=ft.Container(content=vista_vivo_tab, padding=ft.Padding.only(top=12), expand=True),
                ),
                ft.Tab(
                    text="Dashboard Analítico",
                    icon=ft.Icons.INSERT_CHART_OUTLINED,
                    content=ft.Container(content=dashboard_tab, padding=ft.Padding.only(top=12), expand=True),
                ),
            ],
            expand=True,
        )

        self.page.add(
            ft.Column(
                controls=[
                    cabecera,
                    tabs,
                ],
                expand=True,
                spacing=10,
            )
        )

    def _iniciar_bucle_consumidor(self) -> None:
        """Inicia el hilo consumidor para procesar la cola de frames y actualizar la UI."""
        self._hilo_consumidor = threading.Thread(
            target=self._bucle_consumidor,
            daemon=True,
            name="HiloConsumidorUI"
        )
        self._hilo_consumidor.start()

    def _bucle_consumidor(self) -> None:
        """Consume payloads de la cola del detector y refresca los controles Flet."""
        ultimo_refresco_kpi = time.time()

        while self._hilo_consumidor_activo:
            try:
                # Obtener payload del detector
                payload = self.detector.cola_salida.get(timeout=0.1)
                frame_bytes = payload.get("frame_bytes")
                if frame_bytes is None:
                    frame_b64 = payload.get("frame_base64", "")
                    if frame_b64:
                        import base64
                        frame_bytes = base64.b64decode(frame_b64)

                detecciones = payload.get("detecciones", [])
                fps = payload.get("fps", 0.0)
                latencia_ms = payload.get("latencia_ms", 0.0)
                valvula_activa = payload.get("valvula_activa", False)

                # Registrar en el gestor de métricas
                if self.metricas.esta_activo:
                    self.metricas.registrar_detecciones(detecciones, fps, latencia_ms)

                # Actualizar Feed de Video en la UI
                if frame_bytes:
                    if self.contenedor_feed.content != self.img_video:
                        self.contenedor_feed.content = self.img_video
                    self.img_video.src = frame_bytes

                # Actualizar indicadores en vivo
                self.txt_fps_vivo.value = f"{fps:.1f} FPS"
                self.txt_latencia_vivo.value = f"{latencia_ms:.1f} ms"
                self.txt_granos_frame.value = str(len(detecciones))
                self.badge_valvula.set_estado(
                    activo=valvula_activa,
                    texto_nuevo="VÁLVULA: DISPARO" if valvula_activa else "VÁLVULA: STANDBY"
                )

            except queue.Empty:
                pass
            except Exception as e:
                print(f"[UI Consumidor] Error en procesamiento de frame: {e}")

            # Refresco periódico de métricas globales y gráficos (cada 400ms)
            ahora = time.time()
            if ahora - ultimo_refresco_kpi >= 0.4:
                ultimo_refresco_kpi = ahora
                self._actualizar_metricas_ui()

            try:
                self.page.update()
            except Exception:
                pass

            time.sleep(0.01)

    def _actualizar_metricas_ui(self) -> None:
        """Actualiza las tarjetas de KPIs y gráficos analíticos."""
        # 1. Estado de conexión MongoDB
        if self.db_manager.esta_conectado:
            self.badge_db.set_estado(True, "MongoDB: Conectado")
        else:
            self.badge_db.set_estado(False, "MongoDB: Modo Offline")

        # 2. Métricas de tarjetas
        tiempo_str = self.metricas.obtener_tiempo_formateado()
        consumo_kwh = self.metricas.calcular_consumo_kwh()
        calidad_pct = self.metricas.obtener_porcentaje_calidad()
        latencia_prom = self.metricas.obtener_latencia_promedio()
        fps_prom = self.metricas.obtener_fps_promedio()

        self.card_tiempo.actualizar_valor(tiempo_str)
        self.card_consumo.actualizar_valor(f"{consumo_kwh:.4f} kWh")
        self.card_total_granos.actualizar_valor(
            str(self.metricas.total_granos),
            nuevo_subtitulo=f"Calidad: {calidad_pct:.1f}% ({self.metricas.total_sanos} Sanos)"
        )
        self.card_latencia_prom.actualizar_valor(
            f"{latencia_prom:.1f} ms",
            nuevo_subtitulo=f"FPS Promedio: {fps_prom:.1f}"
        )

        # 3. Gráfico de Barras (Sanos vs Defectos)
        self.grafico_barras.actualizar(
            sanos=self.metricas.total_sanos,
            defectos=self.metricas.total_defectuosos,
        )

        # 4. Gráfico de Pastel (Distribución de Defectos)
        porcentajes = self.metricas.obtener_porcentajes_defectos()
        self.grafico_pastel.actualizar(
            porcentajes_defectos=porcentajes,
            conteos_defectos=self.metricas.conteo_por_defecto,
        )

    # --- Manejadores de Eventos ---

    def _iniciar_detector(self, e) -> None:
        """Inicia la inferencia y el cronómetro."""
        self.detector.iniciar()
        self.metricas.iniciar_sesion()

        self.btn_iniciar.disabled = True
        self.btn_pausar.disabled = False
        self.btn_detener.disabled = False
        self.dropdown_fuente.disabled = True
        self.page.update()

    def _pausar_detector(self, e) -> None:
        """Pausa o reanuda la inferencia."""
        if self.detector._pausado:
            self.detector.reanudar()
            self.metricas.iniciar_sesion()
            self.btn_pausar.text = "Pausar"
            self.btn_pausar.icon = ft.Icons.PAUSE
        else:
            self.detector.pausar()
            self.metricas.pausar_sesion()
            self.btn_pausar.text = "Reanudar"
            self.btn_pausar.icon = ft.Icons.PLAY_ARROW
        self.page.update()

    def _detener_detector(self, e) -> None:
        """Detiene completamente la inferencia y pausa métricas."""
        self.detector.detener()
        self.metricas.pausar_sesion()

        self.btn_iniciar.disabled = False
        self.btn_pausar.disabled = True
        self.btn_detener.disabled = True
        self.dropdown_fuente.disabled = False
        self.contenedor_feed.content = self.placeholder_video
        self.page.update()

    def _cambiar_fuente_video(self, e) -> None:
        """Actualiza la fuente de video del detector."""
        valor = self.dropdown_fuente.value
        nueva_fuente = int(valor) if valor.isdigit() else valor
        self.detector.cambiar_fuente(nueva_fuente)

    def _guardar_lote_mongodb(self, e) -> None:
        """Guarda el resumen del lote actual en MongoDB Atlas."""
        resumen = self.metricas.generar_resumen_lote()

        def _on_resultado(exito: bool, mensaje: str):
            color = ft.Colors.GREEN_700 if exito else ft.Colors.RED_700
            snack = ft.SnackBar(
                content=ft.Text(mensaje, color=ft.Colors.WHITE),
                bgcolor=color,
                duration=4000,
                open=True,
            )
            self.page.overlay.append(snack)
            self.page.update()

        self.db_manager.guardar_resumen_lote_async(resumen, callback_resultado=_on_resultado)

    def _reiniciar_estadisticas(self, e) -> None:
        """Limpia contadores y reinicia el lote."""
        self.metricas.reiniciar()
        self._actualizar_metricas_ui()
        snack = ft.SnackBar(
            content=ft.Text("Estadísticas del lote reiniciadas.", color=ft.Colors.WHITE),
            bgcolor=InstitucionalTheme.CAFE_TEXTO,
            duration=2500,
            open=True,
        )
        self.page.overlay.append(snack)
        self.page.update()
