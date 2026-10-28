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

        # Iniciar cámara en vivo y consumidor de frames inmediatamente
        self.detector.iniciar()
        self._iniciar_bucle_consumidor()

    def _construir_componentes(self) -> None:
        """Inicializa los controles y componentes de UI."""
        # --- Cabecera ---
        self.badge_db = StatusBadge(
            etiqueta="MongoDB: Conectando...",
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
        placeholder_src = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        self.img_video = ft.Image(
            src=placeholder_src,
            fit="contain",
            width=700,
            height=480,
            border_radius=10,
            gapless_playback=True,
        )

        self.contenedor_feed = ft.Container(
            content=self.img_video,
            alignment=InstitucionalTheme.align_center(),
            expand=True,
            **InstitucionalTheme.estilo_tarjeta()
        )

        # Controles y Telemetría de Vista en Vivo
        dropdown_kwargs = {
            "label": "Seleccionar Cámara / Fuente",
            "value": str(self.detector.fuente_video),
            "options": [
                ft.dropdown.Option("0", "Cámara Web Principal (ID: 0)"),
                ft.dropdown.Option("1", "Cámara Secundaria (ID: 1)"),
                ft.dropdown.Option("demo", "Modo Simulación (Banda Sintética)"),
            ],
            "border_color": InstitucionalTheme.CAFE_CLARO,
            "focused_border_color": InstitucionalTheme.VERDE_ULSA,
            "expand": True,
        }
        try:
            self.dropdown_fuente = ft.Dropdown(on_select=self._cambiar_fuente_video, **dropdown_kwargs)
        except TypeError:
            self.dropdown_fuente = ft.Dropdown(on_change=self._cambiar_fuente_video, **dropdown_kwargs)

        self.btn_iniciar = ft.ElevatedButton(
            content="Iniciar Clasificación",
            icon=ft.Icons.PLAY_ARROW,
            style=ft.ButtonStyle(
                color=InstitucionalTheme.BLANCO_PURO,
                bgcolor=InstitucionalTheme.VERDE_ULSA,
                padding=InstitucionalTheme.pad_symmetric(horizontal=18, vertical=12),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._iniciar_clasificacion,
            expand=True,
        )
        self.btn_pausar = ft.OutlinedButton(
            content="Pausar",
            icon=ft.Icons.PAUSE,
            style=ft.ButtonStyle(
                color=InstitucionalTheme.CAFE_TEXTO,
                side=ft.BorderSide(1.5, InstitucionalTheme.CAFE_TEXTO),
                padding=InstitucionalTheme.pad_symmetric(horizontal=14, vertical=10),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._pausar_clasificacion,
            disabled=True,
            expand=True,
        )
        self.btn_detener = ft.OutlinedButton(
            content="Detener",
            icon=ft.Icons.STOP,
            style=ft.ButtonStyle(
                color=InstitucionalTheme.ROJO_DEFECTO,
                side=ft.BorderSide(1.5, InstitucionalTheme.ROJO_DEFECTO),
                padding=InstitucionalTheme.pad_symmetric(horizontal=14, vertical=10),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._detener_clasificacion,
            disabled=True,
            expand=True,
        )

        # Indicadores en Vivo
        self.txt_fps_vivo = ft.Text("30.0 FPS", size=15, weight=ft.FontWeight.BOLD, color=InstitucionalTheme.VERDE_ULSA)
        self.txt_latencia_vivo = ft.Text("0.0 ms", size=15, weight=ft.FontWeight.BOLD, color=InstitucionalTheme.CAFE_TEXTO)
        self.txt_granos_frame = ft.Text("0", size=15, weight=ft.FontWeight.BOLD, color=InstitucionalTheme.NEGRO_TERCIARIO)
        self.badge_valvula = StatusBadge("STANDBY", activo=False)

        # --- Pestaña 2: Panel Analítico ---
        self.card_tiempo = StatCard(
            titulo="Tiempo de Operación",
            valor_inicial="00:00:00 Hrs",
            subtitulo="Sesión activa",
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
            content="Guardar Resumen en MongoDB Atlas",
            icon=ft.Icons.CLOUD_UPLOAD_OUTLINED,
            style=ft.ButtonStyle(
                color=InstitucionalTheme.BLANCO_PURO,
                bgcolor=InstitucionalTheme.VERDE_ULSA,
                padding=InstitucionalTheme.pad_symmetric(horizontal=20, vertical=12),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._guardar_lote_mongodb,
        )
        self.btn_reiniciar_sesion = ft.OutlinedButton(
            content="Reiniciar Estadísticas / Nuevo Lote",
            icon=ft.Icons.REFRESH,
            style=ft.ButtonStyle(
                color=InstitucionalTheme.CAFE_TEXTO,
                side=ft.BorderSide(1.5, InstitucionalTheme.CAFE_TEXTO),
                padding=InstitucionalTheme.pad_symmetric(horizontal=16, vertical=10),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            on_click=self._reiniciar_estadisticas,
        )

    def _crear_tile_telemetria(self, etiqueta: str, valor_control: ft.Control, icono: str, color_icono: str, fondo_icono: str) -> ft.Container:
        """Crea una tarjeta compacta para mostrar telemetría de forma limpia."""
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Icon(icono, color=color_icono, size=18),
                        bgcolor=fondo_icono,
                        border_radius=8,
                        padding=6,
                    ),
                    ft.Text(etiqueta, size=12, color=InstitucionalTheme.CAFE_TEXTO, weight=ft.FontWeight.W_500, expand=True),
                    valor_control,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=InstitucionalTheme.BLANCO_FONDO,
            border_radius=10,
            padding=InstitucionalTheme.pad_symmetric(horizontal=12, vertical=8),
            border=InstitucionalTheme.border_all(1, InstitucionalTheme.CAFE_CLARO),
        )

    def _construir_interfaz(self) -> None:
        """Ensambla el árbol de widgets y pestañas."""
        # Barra Superior
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

        # Panel Lateral Derecho (Vista en Vivo)
        panel_lateral_vivo = ft.Container(
            content=ft.Column(
                controls=[
                    # 1. Configuración de Cámara
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.VIDEOCAM_OUTLINED, color=InstitucionalTheme.CAFE_TEXTO, size=18),
                            ft.Text("Origen de Video", style=InstitucionalTheme.estilo_titulo(14)),
                        ],
                        spacing=6,
                    ),
                    ft.Row(controls=[self.dropdown_fuente]),
                    ft.Divider(color=InstitucionalTheme.CAFE_CLARO, height=10),

                    # 2. Control de Inferencia
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.TUNE, color=InstitucionalTheme.CAFE_TEXTO, size=18),
                            ft.Text("Control de Sesión", style=InstitucionalTheme.estilo_titulo(14)),
                        ],
                        spacing=6,
                    ),
                    ft.Row(controls=[self.btn_iniciar]),
                    ft.Row(controls=[self.btn_pausar, self.btn_detener], spacing=10),
                    ft.Divider(color=InstitucionalTheme.CAFE_CLARO, height=10),

                    # 3. Telemetría de Hardware
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.SENSORS, color=InstitucionalTheme.CAFE_TEXTO, size=18),
                            ft.Text("Telemetría en Vivo", style=InstitucionalTheme.estilo_titulo(14)),
                        ],
                        spacing=6,
                    ),
                    self._crear_tile_telemetria("FPS de Cámara", self.txt_fps_vivo, ft.Icons.SPEED, InstitucionalTheme.VERDE_ULSA, InstitucionalTheme.VERDE_CLARO),
                    self._crear_tile_telemetria("Latencia Inferencia", self.txt_latencia_vivo, ft.Icons.TIMER_OUTLINED, InstitucionalTheme.CAFE_TEXTO, InstitucionalTheme.CAFE_CLARO),
                    self._crear_tile_telemetria("Granos en Cuadro", self.txt_granos_frame, ft.Icons.GRAIN, InstitucionalTheme.VERDE_ACENTO, InstitucionalTheme.VERDE_CLARO),
                    ft.Container(height=2),
                    ft.Row(
                        controls=[
                            ft.Text("Válvula Neumática:", size=12, weight=ft.FontWeight.W_600, color=InstitucionalTheme.CAFE_TEXTO),
                            self.badge_valvula,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
            ),
            width=370,
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

        # Panel Analítico
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

        # Pestañas
        tabs = self._construir_tabs_compatibles(
            vista_vivo_tab=vista_vivo_tab,
            dashboard_tab=dashboard_tab,
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

    def _construir_tabs_compatibles(self, vista_vivo_tab: ft.Control, dashboard_tab: ft.Control) -> ft.Control:
        """Construye el control de pestañas universalmente compatible con todas las versiones de Flet."""
        c1 = ft.Container(content=vista_vivo_tab, padding=InstitucionalTheme.pad_only(top=12), expand=True)
        c2 = ft.Container(content=dashboard_tab, padding=InstitucionalTheme.pad_only(top=12), expand=True)

        # Intento 1: Arquitectura Flet 0.8x (TabBar + TabBarView + Tabs con content y length)
        if hasattr(ft, "TabBar") and hasattr(ft, "TabBarView"):
            try:
                tab_bar = ft.TabBar(
                    tabs=[
                        ft.Tab(label="Vista en Vivo", icon=ft.Icons.VIDEOCAM),
                        ft.Tab(label="Dashboard Analítico", icon=ft.Icons.INSERT_CHART_OUTLINED),
                    ],
                    indicator_color=InstitucionalTheme.VERDE_ULSA,
                    label_color=InstitucionalTheme.VERDE_ULSA,
                    unselected_label_color=InstitucionalTheme.CAFE_TEXTO,
                )
                tab_view = ft.TabBarView(
                    controls=[c1, c2],
                    expand=True,
                )
                return ft.Tabs(
                    content=ft.Column(controls=[tab_bar, tab_view], expand=True),
                    length=2,
                    expand=True,
                )
            except Exception:
                pass

        # Intento 2: Arquitectura Flet 0.2x (Tabs con lista de Tab con content interno)
        try:
            t1 = ft.Tab(text="Vista en Vivo", icon=ft.Icons.VIDEOCAM, content=c1)
            t2 = ft.Tab(text="Dashboard Analítico", icon=ft.Icons.INSERT_CHART_OUTLINED, content=c2)
        except TypeError:
            t1 = ft.Tab(label="Vista en Vivo", icon=ft.Icons.VIDEOCAM, content=c1)
            t2 = ft.Tab(label="Dashboard Analítico", icon=ft.Icons.INSERT_CHART_OUTLINED, content=c2)

        return ft.Tabs(
            selected_index=0,
            animation_duration=250,
            tabs=[t1, t2],
            indicator_color=InstitucionalTheme.VERDE_ULSA,
            label_color=InstitucionalTheme.VERDE_ULSA,
            unselected_label_color=InstitucionalTheme.CAFE_TEXTO,
            expand=True,
        )

    def _iniciar_bucle_consumidor(self) -> None:
        """Inicia el hilo consumidor de video y telemetría."""
        self._hilo_consumidor = threading.Thread(
            target=self._bucle_consumidor,
            daemon=True,
            name="HiloConsumidorUI"
        )
        self._hilo_consumidor.start()

    def _bucle_consumidor(self) -> None:
        """
        Consume frames del detector y actualiza la UI y telemetría en tiempo real continuo.
        Asigna el Data URI directamente a img_video.src y despacha la actualización a Flet,
        logrando visualización fluida de los granos a 30 FPS sin necesidad de cambiar de pestaña.
        """
        ultimo_refresco_kpi = time.time()

        while self._hilo_consumidor_activo:
            try:
                payload = self.detector.cola_salida.get(timeout=0.03)

                # --- 1. Frame de video en tiempo real ---
                frame_src = payload.get("frame_src", "")
                if not frame_src:
                    frame_b64 = payload.get("frame_base64", "")
                    if frame_b64:
                        frame_src = f"data:image/jpeg;base64,{frame_b64}"

                if frame_src:
                    self.img_video.src = frame_src

                # --- 2. Telemetría de inferencia y hardware ---
                detecciones = payload.get("detecciones", [])
                fps = payload.get("fps", 0.0)
                latencia_ms = payload.get("latencia_ms", 0.0)
                valvula_activa = payload.get("valvula_activa", False)

                if self.metricas.esta_activo:
                    self.metricas.registrar_detecciones(detecciones, fps, latencia_ms)

                self.txt_fps_vivo.value = f"{fps:.1f} FPS"
                self.txt_latencia_vivo.value = f"{latencia_ms:.1f} ms"
                self.txt_granos_frame.value = str(len(detecciones))
                self.badge_valvula.set_estado(
                    activo=valvula_activa,
                    texto_nuevo="DISPARO" if valvula_activa else "STANDBY"
                )

                # --- 3. Refrescar métricas analíticas periódicamente (~2 Hz) ---
                ahora = time.time()
                if ahora - ultimo_refresco_kpi >= 0.5:
                    ultimo_refresco_kpi = ahora
                    self._actualizar_metricas_ui()

                # --- 4. Despachar actualización reactiva a la UI ---
                try:
                    self.page.update()
                except Exception:
                    pass

            except queue.Empty:
                pass
            except Exception as e:
                print(f"[UI Consumidor] Error: {e}")

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

        # 3. Gráficos en vivo
        self.grafico_barras.actualizar(
            sanos=self.metricas.total_sanos,
            defectos=self.metricas.total_defectuosos,
        )

        porcentajes = self.metricas.obtener_porcentajes_defectos()
        self.grafico_pastel.actualizar(
            porcentajes_defectos=porcentajes,
            conteos_defectos=self.metricas.conteo_por_defecto,
        )

    # --- Manejadores de Eventos ---

    def _iniciar_clasificacion(self, e) -> None:
        """Inicia la sesión activa de clasificación y cronometraje con YOLO."""
        self.detector.iniciar_clasificacion()
        self.metricas.iniciar_sesion()

        self.btn_iniciar.disabled = True
        self.btn_pausar.disabled = False
        self.btn_pausar.content = "Pausar"
        self.btn_pausar.icon = ft.Icons.PAUSE
        self.btn_detener.disabled = False
        self.dropdown_fuente.disabled = True
        self.page.update()

    def _pausar_clasificacion(self, e) -> None:
        """Pausa o reanuda el registro de métricas y la inferencia."""
        if not self.metricas.esta_activo:
            self.detector.reanudar()
            self.metricas.iniciar_sesion()
            self.btn_pausar.content = "Pausar"
            self.btn_pausar.icon = ft.Icons.PAUSE
        else:
            self.detector.pausar()
            self.metricas.pausar_sesion()
            self.btn_pausar.content = "Reanudar"
            self.btn_pausar.icon = ft.Icons.PLAY_ARROW
        self.page.update()

    def _detener_clasificacion(self, e) -> None:
        """Detiene la sesión de clasificación volviendo al modo preview."""
        self.detector.detener_clasificacion()
        self.metricas.pausar_sesion()

        self.btn_iniciar.disabled = False
        self.btn_pausar.disabled = True
        self.btn_pausar.content = "Pausar"
        self.btn_pausar.icon = ft.Icons.PAUSE
        self.btn_detener.disabled = True
        self.dropdown_fuente.disabled = False
        self.page.update()

    def _cambiar_fuente_video(self, e) -> None:
        """Actualiza la fuente de video del detector."""
        valor = self.dropdown_fuente.value
        nueva_fuente = int(valor) if str(valor).isdigit() else valor
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
