"""
Dashboard de Inferencia y Telemetría MOPPI basado en CustomTkinter.
Proporciona streaming nativo en tiempo real a 30-60 FPS con latencia cero,
gráficos analíticos reactivos con Matplotlib, tarjetas neumorfistas
y persistencia transaccional (MongoDB Atlas + SQLite Offline-First).
"""

import os
import time
import queue
import threading
import cv2
from PIL import Image
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from typing import Dict, Any, Optional, List, Union

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from core.detector import YOLODetector
from core.metricas import GestorMetricas
from storage.database import DatabaseManager, GestorLotes, MongoManager
from storage.telemetria import GestorTiempoUso


class VentanaLogsToplevel(ctk.CTkToplevel):
    """
    Ventana emergente independiente (Toplevel) para visualización y auditoría
    en tiempo real de logs locales y alarmas del clasificador MOPPI.
    """

    def __init__(
        self,
        parent: ctk.CTk,
        db_manager: Union[DatabaseManager, MongoManager],
    ) -> None:
        super().__init__(parent)
        self.db_manager = db_manager

        self.title("Auditoría de Eventos y Alarmas | MOPPI")
        self.geometry("960x600")
        self.minsize(750, 420)
        self.configure(fg_color="#F5F6F8")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._construir_ui()
        self._cargar_logs()

    def _construir_ui(self) -> None:
        # Barra superior con filtros
        frame_filtros = ctk.CTkFrame(
            self,
            fg_color="#FFFFFF",
            corner_radius=12,
            border_width=1,
            border_color="#E0E0E0",
        )
        frame_filtros.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")

        # Filtro Tipo
        lbl_tipo = ctk.CTkLabel(
            frame_filtros,
            text="Filtro Tipo:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#4A3B32",
        )
        lbl_tipo.pack(side="left", padx=(14, 4), pady=8)

        self.opt_tipo = ctk.CTkOptionMenu(
            frame_filtros,
            values=["TODOS", "INFO", "WARNING", "ALARM"],
            command=lambda _: self._cargar_logs(),
            width=110,
            fg_color="#197B30",
            button_color="#145F25",
        )
        self.opt_tipo.set("TODOS")
        self.opt_tipo.pack(side="left", padx=4, pady=8)

        # Filtro Fecha
        lbl_fecha = ctk.CTkLabel(
            frame_filtros,
            text="Rango Temporal:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#4A3B32",
        )
        lbl_fecha.pack(side="left", padx=(16, 4), pady=8)

        self.seg_fecha = ctk.CTkSegmentedButton(
            frame_filtros,
            values=["Hoy", "Últimos 3 días", "Última semana", "Todos"],
            command=lambda _: self._cargar_logs(),
            selected_color="#197B30",
            selected_hover_color="#145F25",
        )
        self.seg_fecha.set("Hoy")
        self.seg_fecha.pack(side="left", padx=4, pady=8)

        # Botón Refrescar
        btn_refresh = ctk.CTkButton(
            frame_filtros,
            text="↻ Refrescar",
            command=self._cargar_logs,
            width=95,
            fg_color="#197B30",
            hover_color="#145F25",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        btn_refresh.pack(side="right", padx=14, pady=8)

        # Consola de logs con CTkTextbox
        self.txt_logs = ctk.CTkTextbox(
            self,
            fg_color="#1E1E1E",
            text_color="#E0E0E0",
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=12,
            border_width=1,
            border_color="#E0E0E0",
            wrap="word",
        )
        self.txt_logs.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="nsew")

        # Configurar tags de color en el widget interno tk.Text
        try:
            raw_text = self.txt_logs._textbox
            raw_text.tag_config("ALARM", foreground="#FF5252", font=("Consolas", 11, "bold"))
            raw_text.tag_config("WARNING", foreground="#FFB74D", font=("Consolas", 11, "bold"))
            raw_text.tag_config("INFO", foreground="#81C784")
            raw_text.tag_config("TIMESTAMP", foreground="#64B5F6")
            raw_text.tag_config("DEF", foreground="#E0E0E0")
        except Exception:
            pass

    def _cargar_logs(self) -> None:
        """Consulta SQLite y renderiza los logs con estilos de color."""
        tipo_sel = self.opt_tipo.get()
        fecha_sel = self.seg_fecha.get()

        logs = self.db_manager.obtener_logs_locales(
            tipo=tipo_sel if tipo_sel != "TODOS" else None,
            filtro_fecha=fecha_sel,
            limite=500,
        )

        self.txt_logs.configure(state="normal")
        self.txt_logs.delete("1.0", "end")

        if not logs:
            self.txt_logs.insert("end", "No se encontraron logs locales para el criterio seleccionado.\n")
        else:
            for item in logs:
                ts = item.get("timestamp", "")
                t = str(item.get("tipo", "INFO")).upper()
                msg = item.get("mensaje", "")
                tag = t if t in ("ALARM", "WARNING", "INFO") else "DEF"
                try:
                    self.txt_logs._textbox.insert("end", f"[{ts}] ", "TIMESTAMP")
                    self.txt_logs._textbox.insert("end", f"[{t:7s}] ", tag)
                    self.txt_logs._textbox.insert("end", f"{msg}\n", "DEF")
                except Exception:
                    self.txt_logs.insert("end", f"[{ts}] [{t:7s}] {msg}\n")

        self.txt_logs.configure(state="disabled")
        self.txt_logs.see("end")


class DashboardCustomTkinter(ctk.CTk):
    """
    Ventana principal de la interfaz MOPPI implementada con CustomTkinter.
    Aplica estilo neomórfico con bordes redondeados y colores de fondo suaves,
    manteniendo la paleta de colores institucionales ULSA.
    """

    # --- Paleta de Colores Institucionales ULSA y Neumorfismo ---
    COLOR_VERDE_ULSA = "#197B30"
    COLOR_VERDE_HOVER = "#145F25"
    COLOR_VERDE_CLARO = "#E8F5E9"
    COLOR_ROJO_DEFECTO = "#C62828"
    COLOR_ROJO_HOVER = "#9A1F1F"
    COLOR_CAFE_TEXTO = "#4A3B32"
    COLOR_CAFE_CLARO = "#D7CCC8"
    COLOR_GRIS_SEC = "#757575"
    COLOR_FONDO_APP = "#F5F6F8"
    COLOR_FONDO_CARD_LIGHT = "#FFFFFF"
    COLOR_BORDE_NEUMORFICO = "#E0E0E0"
    COLOR_AMARILLO_ALERTA = "#F57F17"

    # Paleta para las 13 Clases individuales
    COLORES_13_CLASES = {
        "Arabica_Bueno": "#197B30",
        "Robusta_Bueno": "#2E7D32",
        "Arabica_Agrio": "#FB8C00",
        "Arabica_Brocado": "#E53935",
        "Arabica_Cereza": "#8E24AA",
        "Arabica_Concha": "#3949AB",
        "Arabica_Inmaduro": "#00897B",
        "Arabica_Negro": "#37474F",
        "Arabica_Quebrado": "#8D6E63",
        "Robusta_Brocado": "#D32F2F",
        "Robusta_Cereza": "#AB47BC",
        "Robusta_Negro": "#263238",
        "Robusta_Quebrado": "#6D4C41",
    }

    # Paleta para el Modelo Tri-Clase (Campeón V10)
    COLORES_TRI_CLASE = {
        "Arabica_Bueno": "#197B30",
        "Robusta_Bueno": "#2E7D32",
        "Grano_Defecto": "#C62828",
    }

    RADIUS_CARD = 14
    RADIUS_SMALL = 10

    def __init__(
        self,
        detector: YOLODetector,
        metricas: GestorMetricas,
        db_manager: Union[DatabaseManager, MongoManager],
        gestor_lotes: Optional[GestorLotes] = None,
        esp32_bridge: Optional[Any] = None,
    ) -> None:
        super().__init__()

        self.detector = detector
        self.metricas = metricas
        self.db_manager = db_manager
        self.gestor_lotes = gestor_lotes or GestorLotes(
            db_manager=self.db_manager,
            callback_lote_finalizado=self._al_lote_finalizado_auto,
        )
        self.esp32_bridge = esp32_bridge or getattr(self.detector, "esp32_bridge", None)

        # Configuración de ventana principal
        self.title("Clasificadora de Granos de Café Oro | Finca Alvizua")
        self.geometry("1320x840")
        self.minsize(1080, 720)
        self.configure(fg_color=self.COLOR_FONDO_APP)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")

        self._consumidor_activo = True
        self._ultimo_refresco_kpi = time.time()
        self._ctk_image_ref = None
        self._ctk_img_top = None
        self._ctk_img_bot = None
        self._ventana_logs: Optional[VentanaLogsToplevel] = None

        # Gestor de tiempo de uso diario con persistencia anti-apagones
        self.gestor_tiempo = GestorTiempoUso()

        # Variables para Matplotlib Reactivo
        self.fig_reactiva: Optional[Figure] = None
        self.ax_reactivo = None
        self.canvas_reactivo: Optional[FigureCanvasTkAgg] = None

        self._construir_interfaz()

        # Iniciar detector YOLO en modo preview
        self.detector.iniciar()

        # Iniciar bucle de refresco nativo en UI (15 ms ~ 60 FPS)
        self.after(15, self._bucle_actualizacion_frame)

        # Manejador de cierre ordenado
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

    def _construir_interfaz(self) -> None:
        """Construye el layout principal con estilo neomórfico y pestañas."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- 1. Cabecera Superior Neumórfica ---
        cabecera = ctk.CTkFrame(
            self,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            height=68,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        cabecera.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")
        cabecera.grid_columnconfigure(0, weight=1)

        frame_titulos = ctk.CTkFrame(cabecera, fg_color="transparent")
        frame_titulos.grid(row=0, column=0, padx=16, pady=8, sticky="w")

        lbl_titulo = ctk.CTkLabel(
            frame_titulos,
            text="Clasificadora de Granos de Café Oro",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_titulo.pack(anchor="w")

        lbl_subtitulo = ctk.CTkLabel(
            frame_titulos,
            text="Inferencia en Tiempo Real y Telemetría Electromecánica (Finca Alvizua)",
            font=ctk.CTkFont(size=12),
            text_color=self.COLOR_GRIS_SEC,
        )
        lbl_subtitulo.pack(anchor="w")

        # Controles y Badges en la cabecera
        frame_controles_hdr = ctk.CTkFrame(cabecera, fg_color="transparent")
        frame_controles_hdr.grid(row=0, column=1, padx=16, pady=8, sticky="e")

        # Badges de estado
        self.badge_db = ctk.CTkButton(
            frame_controles_hdr,
            text="MongoDB: Conectando...",
            fg_color="#FFF8E1",
            text_color=self.COLOR_AMARILLO_ALERTA,
            hover=False,
            height=28,
            corner_radius=14,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.badge_db.pack(side="left", padx=5)

        self.badge_modelo = ctk.CTkButton(
            frame_controles_hdr,
            text="Modo: Tri-clase",
            fg_color=self.COLOR_VERDE_CLARO,
            text_color=self.COLOR_VERDE_ULSA,
            hover=False,
            height=28,
            corner_radius=14,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.badge_modelo.pack(side="left", padx=5)

        # 1. Control de Modelo: Switch entre 13 Clases y Tri-clase
        self.switch_modelo = ctk.CTkSwitch(
            frame_controles_hdr,
            text="13 Clases",
            command=self._al_cambiar_switch_modelo,
            font=ctk.CTkFont(size=11, weight="bold"),
            progress_color=self.COLOR_VERDE_ULSA,
        )
        self.switch_modelo.pack(side="left", padx=8)
        # Por defecto: Tri-clase (switch apagado)
        self.switch_modelo.deselect()

        # 2. Control de Inferencia SAHI (On/Off)
        self.switch_sahi = ctk.CTkSwitch(
            frame_controles_hdr,
            text="SAHI: OFF",
            command=self._al_cambiar_switch_sahi,
            font=ctk.CTkFont(size=11, weight="bold"),
            progress_color=self.COLOR_VERDE_ULSA,
        )
        self.switch_sahi.pack(side="left", padx=8)
        self.switch_sahi.deselect()

        # --- 2. Pestañas Principales ---
        self.tabview = ctk.CTkTabview(
            self,
            segmented_button_selected_color=self.COLOR_VERDE_ULSA,
            segmented_button_selected_hover_color=self.COLOR_VERDE_HOVER,
            corner_radius=self.RADIUS_CARD,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            border_color=self.COLOR_BORDE_NEUMORFICO,
            border_width=1,
        )
        self.tabview.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="nsew")

        self.tab_vivo = self.tabview.add("Vista en Vivo")
        self.tab_analitico = self.tabview.add("Dashboard Analítico")
        self.tab_logs = self.tabview.add("Visor de Logs y Alarmas")

        self._construir_pestana_vivo()
        self._construir_pestana_analitico()
        self._construir_pestana_logs()

    def _construir_pestana_vivo(self) -> None:
        """Construye la vista de cámara en vivo y controles de hardware laterales."""
        self.tab_vivo.grid_columnconfigure(0, weight=1)
        self.tab_vivo.grid_columnconfigure(1, weight=0)
        self.tab_vivo.grid_rowconfigure(0, weight=1)

        # Card de Video (Arquitectura Dual de 2 Columnas)
        self.card_video = ctk.CTkFrame(
            self.tab_vivo,
            fg_color="#1E1E1E",
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        self.card_video.grid(row=0, column=0, padx=(0, 10), pady=5, sticky="nsew")
        self.card_video.grid_rowconfigure(1, weight=1)
        self.card_video.grid_columnconfigure((0, 1), weight=1)

        # Barra Superior de Sincronización Dual
        frame_sync_hdr = ctk.CTkFrame(self.card_video, fg_color="#141414", corner_radius=8, height=36)
        frame_sync_hdr.grid(row=0, column=0, columnspan=2, padx=8, pady=(8, 4), sticky="ew")
        frame_sync_hdr.grid_columnconfigure(0, weight=1)

        lbl_hdr_camaras = ctk.CTkLabel(
            frame_sync_hdr,
            text="SISTEMA DE INSPECCIÓN ÓPTICA DUAL | MAESTRO-ESCLAVO (FUSIÓN LÓGICA OR)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#BBBBBB",
        )
        lbl_hdr_camaras.grid(row=0, column=0, padx=12, pady=6, sticky="w")

        self.badge_dual_sync = ctk.CTkButton(
            frame_sync_hdr,
            text="DUAL CAMERA: SYNC",
            fg_color="#197B30",
            text_color="#FFFFFF",
            hover=False,
            height=24,
            corner_radius=12,
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        self.badge_dual_sync.grid(row=0, column=1, padx=10, pady=6, sticky="e")

        # Panel Izquierdo: Cámara Superior (Master / Dorsal)
        frame_cam_top = ctk.CTkFrame(self.card_video, fg_color="#121212", corner_radius=8)
        frame_cam_top.grid(row=1, column=0, padx=(8, 4), pady=(0, 8), sticky="nsew")
        frame_cam_top.grid_rowconfigure(1, weight=1)
        frame_cam_top.grid_columnconfigure(0, weight=1)

        lbl_tit_top = ctk.CTkLabel(
            frame_cam_top,
            text="CÁMARA SUPERIOR (DORSAL - MAESTRO) | CONTROL CINEMÁTICO Y DISPARO",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#A5D6A7",
        )
        lbl_tit_top.grid(row=0, column=0, padx=6, pady=(6, 2), sticky="w")

        self.lbl_video_top = ctk.CTkLabel(frame_cam_top, text="Iniciando cámara superior...", text_color="#888888")
        self.lbl_video_top.grid(row=1, column=0, padx=4, pady=4, sticky="nsew")
        # Mantener self.lbl_video como alias de la cámara superior para retrocompatibilidad
        self.lbl_video = self.lbl_video_top

        # Panel Derecho: Cámara Inferior (Slave / Ventral)
        frame_cam_bot = ctk.CTkFrame(self.card_video, fg_color="#121212", corner_radius=8)
        frame_cam_bot.grid(row=1, column=1, padx=(4, 8), pady=(0, 8), sticky="nsew")
        frame_cam_bot.grid_rowconfigure(1, weight=1)
        frame_cam_bot.grid_columnconfigure(0, weight=1)

        lbl_tit_bot = ctk.CTkLabel(
            frame_cam_bot,
            text="CÁMARA INFERIOR (VENTRAL - ESCLAVO) | INSPECCIÓN DE REVERSO",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#90CAF9",
        )
        lbl_tit_bot.grid(row=0, column=0, padx=6, pady=(6, 2), sticky="w")

        self.lbl_video_bottom = ctk.CTkLabel(frame_cam_bot, text="Iniciando cámara inferior...", text_color="#888888")
        self.lbl_video_bottom.grid(row=1, column=0, padx=4, pady=4, sticky="nsew")

        # Panel Lateral Derecho (Controles y Telemetría)
        panel_lateral = ctk.CTkScrollableFrame(
            self.tab_vivo,
            width=340,
            corner_radius=self.RADIUS_CARD,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        panel_lateral.grid(row=0, column=1, padx=(5, 0), pady=5, sticky="nsew")

        # 1. Fuente de Video
        lbl_sec1 = ctk.CTkLabel(
            panel_lateral,
            text="Origen de Video",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_sec1.pack(anchor="w", pady=(5, 5))

        self.opt_fuente = ctk.CTkOptionMenu(
            panel_lateral,
            values=["Cámara 0 (Principal)", "Cámara 1 (Secundaria)", "Modo Simulación (Demo)"],
            command=self._cambiar_fuente_video_ctk,
            fg_color=self.COLOR_VERDE_ULSA,
            button_color=self.COLOR_VERDE_HOVER,
        )
        if str(self.detector.fuente_video) == "1":
            self.opt_fuente.set("Cámara 1 (Secundaria)")
        elif str(self.detector.fuente_video) == "demo":
            self.opt_fuente.set("Modo Simulación (Demo)")
        else:
            self.opt_fuente.set("Cámara 0 (Principal)")
        self.opt_fuente.pack(fill="x", pady=(0, 15))

        # 2. Control de Inferencia
        lbl_sec2 = ctk.CTkLabel(
            panel_lateral,
            text="Control de Inferencia YOLO",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_sec2.pack(anchor="w", pady=(5, 5))

        self.btn_iniciar = ctk.CTkButton(
            panel_lateral,
            text="▶ Iniciar Clasificación",
            command=self._iniciar_clasificacion,
            fg_color=self.COLOR_VERDE_ULSA,
            hover_color=self.COLOR_VERDE_HOVER,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.btn_iniciar.pack(fill="x", pady=4)

        frame_ctrl_btns = ctk.CTkFrame(panel_lateral, fg_color="transparent")
        frame_ctrl_btns.pack(fill="x", pady=4)
        frame_ctrl_btns.grid_columnconfigure((0, 1), weight=1)

        self.btn_pausar = ctk.CTkButton(
            frame_ctrl_btns,
            text="Pausar",
            command=self._pausar_clasificacion,
            fg_color="#FBC02D",
            hover_color="#F9A825",
            text_color="#212121",
            state="disabled",
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.btn_pausar.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.btn_detener = ctk.CTkButton(
            frame_ctrl_btns,
            text="Detener",
            command=self._detener_clasificacion,
            fg_color=self.COLOR_ROJO_DEFECTO,
            hover_color=self.COLOR_ROJO_HOVER,
            state="disabled",
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.btn_detener.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        # 3. Telemetría en Vivo
        lbl_sec3 = ctk.CTkLabel(
            panel_lateral,
            text="Telemetría en Vivo",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_sec3.pack(anchor="w", pady=(15, 6))

        self.tile_fps = self._crear_tile_telemetria(panel_lateral, "FPS de Cámara", "0.0 FPS", self.COLOR_VERDE_ULSA)
        self.tile_latencia = self._crear_tile_telemetria(panel_lateral, "Latencia Inferencia", "0.0 ms", self.COLOR_CAFE_TEXTO)
        self.tile_granos = self._crear_tile_telemetria(panel_lateral, "Granos en Frame", "0", self.COLOR_VERDE_ULSA)

        # Estado del Actuador Neumático
        frame_valv = ctk.CTkFrame(
            panel_lateral,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_SMALL,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        frame_valv.pack(fill="x", pady=6)

        ctk.CTkLabel(
            frame_valv,
            text="Válvula Expulsora",
            font=ctk.CTkFont(size=12),
            text_color=self.COLOR_CAFE_TEXTO,
        ).pack(side="left", padx=10, pady=8)

        self.badge_valvula = ctk.CTkButton(
            frame_valv,
            text="STANDBY",
            fg_color="#EEEEEE",
            text_color="#666666",
            hover=False,
            height=24,
            corner_radius=12,
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        self.badge_valvula.pack(side="right", padx=10, pady=8)

    def _crear_tile_telemetria(
        self, parent: ctk.CTkBaseClass, etiqueta: str, valor_ini: str, color_valor: str
    ) -> ctk.CTkLabel:
        """Crea un tile visual para telemetría con estilo neomórfico."""
        frame = ctk.CTkFrame(
            parent,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_SMALL,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        frame.pack(fill="x", pady=4)

        lbl_etiq = ctk.CTkLabel(frame, text=etiqueta, font=ctk.CTkFont(size=12), text_color=self.COLOR_CAFE_TEXTO)
        lbl_etiq.pack(side="left", padx=10, pady=8)

        lbl_val = ctk.CTkLabel(frame, text=valor_ini, font=ctk.CTkFont(size=13, weight="bold"), text_color=color_valor)
        lbl_val.pack(side="right", padx=10, pady=8)
        return lbl_val

    def _construir_pestana_analitico(self) -> None:
        """Construye el dashboard analítico con StatCards neumorfistas y gráfico reactivo."""
        self.tab_analitico.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        self.tab_analitico.grid_rowconfigure(1, weight=1)

        # -----------------------------------------------------------------
        # Fila 0: 5 StatCards Neumorfistas Principales
        # -----------------------------------------------------------------
        self.card_kpi_tiempo = self._crear_statcard_neumorfica(
            self.tab_analitico,
            0,
            "Tiempo de Uso (Hoy)",
            self.gestor_tiempo.obtener_tiempo_formateado(),
            "Persistencia anti-apagones",
        )
        self.card_kpi_lotes = self._crear_statcard_neumorfica(
            self.tab_analitico, 1, "Lotes Procesados", "0 Lotes", "Activo: En espera"
        )
        self.card_kpi_granos = self._crear_statcard_neumorfica(
            self.tab_analitico, 2, "Estadísticas Generales", "0 Granos", "Calidad: 100.0% (0 Sanos)"
        )
        self.card_kpi_consumo = self._crear_statcard_neumorfica(
            self.tab_analitico, 3, "Consumo Energético", "0.0000 kWh", f"Potencia: {self.gestor_lotes.potencia_hardware_kw:.2f} kW"
        )
        self.card_kpi_latencia = self._crear_statcard_neumorfica(
            self.tab_analitico, 4, "Latencia y Hardware", "0.0 ms", "Válvula límite: 35.0 ms"
        )

        # -----------------------------------------------------------------
        # Fila 1: Panel Central Dividido (Gráfico Reactivo + Control de Lote)
        # -----------------------------------------------------------------
        frame_central = ctk.CTkFrame(self.tab_analitico, fg_color="transparent")
        frame_central.grid(row=1, column=0, columnspan=5, padx=0, pady=8, sticky="nsew")
        frame_central.grid_columnconfigure(0, weight=3)  # Gráfico más amplio
        frame_central.grid_columnconfigure(1, weight=2)  # Panel lateral de balance y acciones
        frame_central.grid_rowconfigure(0, weight=1)

        # Panel Izquierdo: Gráfico Reactivo con Matplotlib FigureCanvasTkAgg
        card_grafico = ctk.CTkFrame(
            frame_central,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        card_grafico.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="nsew")

        lbl_graf_hdr = ctk.CTkLabel(
            card_grafico,
            text="Frecuencia por Categoría de Granos (Reactivo en Tiempo Real)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_graf_hdr.pack(anchor="w", padx=16, pady=(12, 4))

        self.frame_canvas = ctk.CTkFrame(card_grafico, fg_color="transparent")
        self.frame_canvas.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        # Inicialización de la figura Matplotlib
        self.fig_reactiva = Figure(figsize=(6.4, 4.4), dpi=95, facecolor="#FFFFFF")
        self.ax_reactivo = self.fig_reactiva.add_subplot(111)
        self.canvas_reactivo = FigureCanvasTkAgg(self.fig_reactiva, master=self.frame_canvas)
        self.canvas_widget = self.canvas_reactivo.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True)

        # Renderizar vista inicial de la gráfica
        self._actualizar_grafico_reactivo()

        # Panel Derecho: Balance Sanos vs Defectos y Gestión Transaccional de Lote
        card_derecha = ctk.CTkFrame(
            frame_central,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        card_derecha.grid(row=0, column=1, padx=(6, 0), pady=0, sticky="nsew")

        lbl_bal_tit = ctk.CTkLabel(
            card_derecha,
            text="Balance de Clasificación del Lote",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_bal_tit.pack(anchor="w", padx=16, pady=(12, 8))

        # Barra Sanos
        frame_sanos_hdr = ctk.CTkFrame(card_derecha, fg_color="transparent")
        frame_sanos_hdr.pack(fill="x", padx=16, pady=(4, 2))
        ctk.CTkLabel(
            frame_sanos_hdr,
            text="Granos Sanos (Buenos)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.COLOR_VERDE_ULSA,
        ).pack(side="left")
        self.lbl_sanos_val = ctk.CTkLabel(
            frame_sanos_hdr,
            text="0 (100.0%)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.COLOR_VERDE_ULSA,
        )
        self.lbl_sanos_val.pack(side="right")

        self.bar_sanos = ctk.CTkProgressBar(
            card_derecha,
            progress_color=self.COLOR_VERDE_ULSA,
            fg_color="#E8F5E9",
            height=14,
            corner_radius=7,
        )
        self.bar_sanos.pack(fill="x", padx=16, pady=(0, 12))
        self.bar_sanos.set(1.0)

        # Barra Defectos
        frame_def_hdr = ctk.CTkFrame(card_derecha, fg_color="transparent")
        frame_def_hdr.pack(fill="x", padx=16, pady=(4, 2))
        ctk.CTkLabel(
            frame_def_hdr,
            text="Granos Defectuosos",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.COLOR_ROJO_DEFECTO,
        ).pack(side="left")
        self.lbl_defectos_val = ctk.CTkLabel(
            frame_def_hdr,
            text="0 (0.0%)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.COLOR_ROJO_DEFECTO,
        )
        self.lbl_defectos_val.pack(side="right")

        self.bar_defectos = ctk.CTkProgressBar(
            card_derecha,
            progress_color=self.COLOR_ROJO_DEFECTO,
            fg_color="#FFEBEE",
            height=14,
            corner_radius=7,
        )
        self.bar_defectos.pack(fill="x", padx=16, pady=(0, 16))
        self.bar_defectos.set(0.0)

        # Separador / Info de Estado
        sep = ctk.CTkFrame(card_derecha, height=1, fg_color=self.COLOR_BORDE_NEUMORFICO)
        sep.pack(fill="x", padx=16, pady=4)

        # Botones de Acción de Lote y Sincronización
        lbl_acc_tit = ctk.CTkLabel(
            card_derecha,
            text="Gestor Transaccional de Lotes",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_acc_tit.pack(anchor="w", padx=16, pady=(8, 4))

        self.btn_finalizar_lote = ctk.CTkButton(
            card_derecha,
            text="⏹ Finalizar Lote Activo (Guardar)",
            command=self._finalizar_lote_manual,
            fg_color=self.COLOR_VERDE_ULSA,
            hover_color=self.COLOR_VERDE_HOVER,
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.btn_finalizar_lote.pack(fill="x", padx=16, pady=5)

        self.btn_sincronizar_nube = ctk.CTkButton(
            card_derecha,
            text="☁ Sincronizar Pendientes (Mongo)",
            command=self._sincronizar_pendientes_manual,
            fg_color="#0288D1",
            hover_color="#0277BD",
            height=32,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.btn_sincronizar_nube.pack(fill="x", padx=16, pady=5)

        self.btn_reiniciar = ctk.CTkButton(
            card_derecha,
            text="🔄 Reiniciar Estadísticas Globales",
            command=self._reiniciar_estadisticas,
            fg_color="#8D6E63",
            hover_color="#6D4C41",
            height=32,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.btn_reiniciar.pack(fill="x", padx=16, pady=5)

        # Actualizar datos históricos iniciales
        self._refrescar_estadisticas_historicas()

    def _crear_statcard_neumorfica(
        self,
        parent: ctk.CTkBaseClass,
        col: int,
        titulo: str,
        valor_ini: str,
        sub_ini: str,
    ) -> Dict[str, ctk.CTkLabel]:
        """Crea una tarjeta KPI estilizada con efecto neomórfico y bordes redondeados."""
        card = ctk.CTkFrame(
            parent,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        card.grid(row=0, column=col, padx=5, pady=5, sticky="ew")

        lbl_tit = ctk.CTkLabel(
            card,
            text=titulo,
            font=ctk.CTkFont(size=12),
            text_color=self.COLOR_GRIS_SEC,
        )
        lbl_tit.pack(anchor="w", padx=14, pady=(10, 2))

        lbl_val = ctk.CTkLabel(
            card,
            text=valor_ini,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_val.pack(anchor="w", padx=14, pady=0)

        lbl_sub = ctk.CTkLabel(
            card,
            text=sub_ini,
            font=ctk.CTkFont(size=11),
            text_color=self.COLOR_VERDE_ULSA,
        )
        lbl_sub.pack(anchor="w", padx=14, pady=(0, 10))

        return {"valor": lbl_val, "sub": lbl_sub}

    # -----------------------------------------------------------------
    # Visor de Logs y Auditoría Local
    # -----------------------------------------------------------------

    def _construir_pestana_logs(self) -> None:
        """Construye la vista integrada de auditoría de logs y alarmas."""
        self.tab_logs.grid_columnconfigure(0, weight=1)
        self.tab_logs.grid_rowconfigure(1, weight=1)

        # Barra de Controles y Filtros
        frame_filtros = ctk.CTkFrame(
            self.tab_logs,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        frame_filtros.grid(row=0, column=0, padx=10, pady=(6, 8), sticky="ew")

        # Filtro Tipo
        lbl_tipo = ctk.CTkLabel(
            frame_filtros,
            text="Filtro Tipo:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_tipo.pack(side="left", padx=(14, 4), pady=8)

        self.opt_filtro_logs = ctk.CTkOptionMenu(
            frame_filtros,
            values=["TODOS", "INFO", "WARNING", "ALARM"],
            command=lambda _: self._actualizar_visor_logs(),
            width=110,
            fg_color=self.COLOR_VERDE_ULSA,
            button_color=self.COLOR_VERDE_HOVER,
        )
        self.opt_filtro_logs.set("TODOS")
        self.opt_filtro_logs.pack(side="left", padx=4, pady=8)

        # Filtro Fecha
        lbl_fecha = ctk.CTkLabel(
            frame_filtros,
            text="Rango:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_fecha.pack(side="left", padx=(14, 4), pady=8)

        self.seg_filtro_fecha = ctk.CTkSegmentedButton(
            frame_filtros,
            values=["Hoy", "Últimos 3 días", "Última semana", "Todos"],
            command=lambda _: self._actualizar_visor_logs(),
            selected_color=self.COLOR_VERDE_ULSA,
            selected_hover_color=self.COLOR_VERDE_HOVER,
        )
        self.seg_filtro_fecha.set("Hoy")
        self.seg_filtro_fecha.pack(side="left", padx=4, pady=8)

        # Botón Desacoplar Ventana (CTkToplevel)
        btn_desacoplar = ctk.CTkButton(
            frame_filtros,
            text="⤢ Ventana Flotante",
            command=self._abrir_ventana_logs_toplevel,
            width=135,
            fg_color=self.COLOR_CAFE_TEXTO,
            hover_color="#372B24",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        btn_desacoplar.pack(side="right", padx=12, pady=8)

        # Botón Refrescar
        btn_refrescar = ctk.CTkButton(
            frame_filtros,
            text="↻ Actualizar Logs",
            command=self._actualizar_visor_logs,
            width=120,
            fg_color=self.COLOR_VERDE_ULSA,
            hover_color=self.COLOR_VERDE_HOVER,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        btn_refrescar.pack(side="right", padx=(0, 6), pady=8)

        # Área de Texto / Consola
        self.txt_logs = ctk.CTkTextbox(
            self.tab_logs,
            fg_color="#1E1E1E",
            text_color="#E0E0E0",
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
            wrap="word",
        )
        self.txt_logs.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # Configurar tags de color
        try:
            raw_text = self.txt_logs._textbox
            raw_text.tag_config("ALARM", foreground="#FF5252", font=("Consolas", 11, "bold"))
            raw_text.tag_config("WARNING", foreground="#FFB74D", font=("Consolas", 11, "bold"))
            raw_text.tag_config("INFO", foreground="#81C784")
            raw_text.tag_config("TIMESTAMP", foreground="#64B5F6")
            raw_text.tag_config("DEF", foreground="#E0E0E0")
        except Exception:
            pass

        self._actualizar_visor_logs()

    def _actualizar_visor_logs(self) -> None:
        """Carga y muestra los logs locales en la pestaña del visor."""
        if not hasattr(self, "txt_logs"):
            return

        tipo_sel = self.opt_filtro_logs.get()
        fecha_sel = self.seg_filtro_fecha.get()

        logs = self.db_manager.obtener_logs_locales(
            tipo=tipo_sel if tipo_sel != "TODOS" else None,
            filtro_fecha=fecha_sel,
            limite=500,
        )

        self.txt_logs.configure(state="normal")
        self.txt_logs.delete("1.0", "end")

        if not logs:
            self.txt_logs.insert("end", "No se encontraron logs locales para el criterio seleccionado.\n")
        else:
            for item in logs:
                ts = item.get("timestamp", "")
                t = str(item.get("tipo", "INFO")).upper()
                msg = item.get("mensaje", "")
                tag = t if t in ("ALARM", "WARNING", "INFO") else "DEF"
                try:
                    self.txt_logs._textbox.insert("end", f"[{ts}] ", "TIMESTAMP")
                    self.txt_logs._textbox.insert("end", f"[{t:7s}] ", tag)
                    self.txt_logs._textbox.insert("end", f"{msg}\n", "DEF")
                except Exception:
                    self.txt_logs.insert("end", f"[{ts}] [{t:7s}] {msg}\n")

        self.txt_logs.configure(state="disabled")
        self.txt_logs.see("end")

    def _abrir_ventana_logs_toplevel(self) -> None:
        """Abre o enfoca la ventana flotante independiente de auditoría de logs."""
        if self._ventana_logs is not None and self._ventana_logs.winfo_exists():
            self._ventana_logs.lift()
            self._ventana_logs.focus_set()
        else:
            self._ventana_logs = VentanaLogsToplevel(self, self.db_manager)

    # -----------------------------------------------------------------
    # Gráfica Reactiva con Matplotlib (Tiempo Real)
    # -----------------------------------------------------------------

    def _actualizar_grafico_reactivo(self) -> None:
        """
        Dibuja o actualiza la gráfica de barras horizontales reactiva:
        - Si switch_modelo está en 13 Clases: muestra las 2 variedades sanas y los 11 defectos.
        - Si switch_modelo está en Tri-clase: muestra Arabica_Bueno, Robusta_Bueno y Grano_Defecto.
        Utiliza draw_idle() para no congelar la UI de CustomTkinter.
        """
        if self.ax_reactivo is None or self.fig_reactiva is None:
            return

        self.ax_reactivo.clear()

        es_13_clases = bool(self.switch_modelo.get())

        if es_13_clases:
            # 13 Clases (11 Defectos + 2 Variedades Sanas)
            categorias = [
                "Arabica_Agrio",
                "Arabica_Brocado",
                "Arabica_Cereza",
                "Arabica_Concha",
                "Arabica_Inmaduro",
                "Arabica_Negro",
                "Arabica_Quebrado",
                "Robusta_Brocado",
                "Robusta_Cereza",
                "Robusta_Negro",
                "Robusta_Quebrado",
                "Robusta_Bueno",
                "Arabica_Bueno",
            ]
            etiquetas = [c.replace("_", " ") for c in categorias]
            valores = [self.gestor_lotes.conteo_crudo.get(c, 0) for c in categorias]
            colores = [self.COLORES_13_CLASES.get(c, "#757575") for c in categorias]
        else:
            # Modelo Tri-Clase (Campeón V10)
            categorias = [
                "Grano_Defecto",
                "Robusta_Bueno",
                "Arabica_Bueno",
            ]
            etiquetas = ["Grano Defecto", "Robusta Bueno", "Arábica Bueno"]
            valores = [self.gestor_lotes.conteo_crudo.get(c, 0) for c in categorias]
            colores = [self.COLORES_TRI_CLASE.get(c, "#197B30") for c in categorias]

        # Configurar fondo y ejes limpios estilo neomórfico
        self.ax_reactivo.set_facecolor("#FAFAFA")
        self.fig_reactiva.patch.set_facecolor("#FFFFFF")

        posiciones = range(len(categorias))
        barras = self.ax_reactivo.barh(posiciones, valores, color=colores, height=0.62)

        self.ax_reactivo.set_yticks(posiciones)
        self.ax_reactivo.set_yticklabels(etiquetas, fontsize=8.5, color="#4A3B32", weight="medium")
        self.ax_reactivo.xaxis.grid(True, linestyle="--", alpha=0.4, color="#CFD8DC")
        self.ax_reactivo.set_axisbelow(True)

        # Ocultar espinas innecesarias
        for spine in ["top", "right"]:
            self.ax_reactivo.spines[spine].set_visible(False)
        for spine in ["left", "bottom"]:
            self.ax_reactivo.spines[spine].set_color("#CFD8DC")

        max_val = max(valores) if valores and max(valores) > 0 else 5
        self.ax_reactivo.set_xlim(0, max_val * 1.25)
        self.ax_reactivo.tick_params(axis="x", labelsize=8, colors="#757575")

        # Agregar etiquetas de valor al final de cada barra
        try:
            self.ax_reactivo.bar_label(barras, padding=3, fontsize=8, color="#4A3B32", weight="bold")
        except Exception:
            pass

        self.fig_reactiva.tight_layout()
        if self.canvas_reactivo:
            self.canvas_reactivo.draw_idle()

    # -----------------------------------------------------------------
    # Bucle Principal de Video y Telemetría (Hilo UI)
    # -----------------------------------------------------------------

    def _bucle_actualizacion_frame(self) -> None:
        """
        Bucle nativo de alta frecuencia ejecutado en el hilo de UI.
        Consume el frame más reciente y actualiza la imagen directamente en memoria.
        """
        if not self._consumidor_activo:
            return

        try:
            # Drenar cola hasta el frame más reciente disponible
            payload = None
            while True:
                try:
                    payload = self.detector.cola_salida.get_nowait()
                except queue.Empty:
                    break

            if payload:
                # 1. Renderizar Frames sincronizados de Video (Cámara Superior e Inferior)
                frame_top = payload.get("frame_top")
                if frame_top is None:
                    frame_top = payload.get("frame_bgr")
                frame_bot = payload.get("frame_bottom")
                dual_sync = payload.get("dual_sync", True)

                target_w, target_h = 420, 360

                if frame_top is not None and hasattr(self, "lbl_video_top"):
                    frame_top_rgb = cv2.cvtColor(frame_top, cv2.COLOR_BGR2RGB)
                    pil_top = Image.fromarray(frame_top_rgb)
                    self._ctk_img_top = ctk.CTkImage(
                        light_image=pil_top, dark_image=pil_top, size=(target_w, target_h)
                    )
                    self.lbl_video_top.configure(image=self._ctk_img_top, text="")
                    self._ctk_image_ref = self._ctk_img_top
                elif frame_top is not None and hasattr(self, "lbl_video"):
                    frame_top_rgb = cv2.cvtColor(frame_top, cv2.COLOR_BGR2RGB)
                    pil_top = Image.fromarray(frame_top_rgb)
                    self._ctk_image_ref = ctk.CTkImage(
                        light_image=pil_top, dark_image=pil_top, size=(target_w, target_h)
                    )
                    self.lbl_video.configure(image=self._ctk_image_ref, text="")

                if frame_bot is not None and hasattr(self, "lbl_video_bottom"):
                    frame_bot_rgb = cv2.cvtColor(frame_bot, cv2.COLOR_BGR2RGB)
                    pil_bot = Image.fromarray(frame_bot_rgb)
                    self._ctk_img_bot = ctk.CTkImage(
                        light_image=pil_bot, dark_image=pil_bot, size=(target_w, target_h)
                    )
                    self.lbl_video_bottom.configure(image=self._ctk_img_bot, text="")

                if hasattr(self, "badge_dual_sync"):
                    if dual_sync:
                        self.badge_dual_sync.configure(
                            text="DUAL CAMERA: SYNC", fg_color="#197B30", text_color="#FFFFFF"
                        )
                    else:
                        self.badge_dual_sync.configure(
                            text="DUAL CAMERA: DESYNC", fg_color="#E65100", text_color="#FFFFFF"
                        )

                # 2. Telemetría y Registro en Gestor de Lotes
                detecciones = payload.get("detecciones", [])
                fps = payload.get("fps", 0.0)
                latencia_ms = payload.get("latencia_ms", 0.0)
                valvula_activa = payload.get("valvula_activa", False)

                if self.metricas.esta_activo:
                    self.metricas.registrar_detecciones(detecciones, fps, latencia_ms)
                    # El Gestor de Lotes acumula conteos por lote y evalúa timeout
                    self.gestor_lotes.registrar_detecciones(detecciones, fps, latencia_ms)

                self.tile_fps.configure(text=f"{fps:.1f} FPS")
                self.tile_latencia.configure(text=f"{latencia_ms:.1f} ms")
                self.tile_granos.configure(text=str(len(detecciones)))

                if valvula_activa:
                    self.badge_valvula.configure(text="DISPARO", fg_color=self.COLOR_VERDE_ULSA, text_color="#FFFFFF")
                else:
                    self.badge_valvula.configure(text="STANDBY", fg_color="#EEEEEE", text_color="#666666")

        except Exception as e:
            print(f"[CustomTkinter] Error al procesar frame: {e}")

        # Refrescar métricas analíticas cada 500 ms
        ahora = time.time()
        if ahora - self._ultimo_refresco_kpi >= 0.5:
            self._ultimo_refresco_kpi = ahora
            self._actualizar_metricas_ui()

        # Programar siguiente iteración (15ms ~ 60 FPS)
        if self._consumidor_activo:
            self.after(15, self._bucle_actualizacion_frame)

    def _actualizar_metricas_ui(self) -> None:
        """Actualiza los indicadores de KPIs, balance y la gráfica reactiva."""
        # 1. Estado de Conexión MongoDB Atlas
        if self.db_manager.esta_conectado:
            self.badge_db.configure(
                text="MongoDB: Conectado", fg_color=self.COLOR_VERDE_CLARO, text_color=self.COLOR_VERDE_ULSA
            )
        else:
            self.badge_db.configure(
                text="MongoDB: Modo Offline", fg_color="#FFF8E1", text_color=self.COLOR_AMARILLO_ALERTA
            )

        # 2. StatCards Neumorfistas
        tiempo_str = self.metricas.obtener_tiempo_formateado()
        consumo_kwh = self.metricas.calcular_consumo_kwh()
        calidad_pct = self.metricas.obtener_porcentaje_calidad()
        latencia_prom = self.metricas.obtener_latencia_promedio()
        fps_prom = self.metricas.obtener_fps_promedio()

        # Telemetría de Tiempo de Uso Anti-Apagones
        clasificacion_activa = getattr(self.detector, "clasificacion_activa", False) or self.metricas.esta_activo
        self.gestor_tiempo.tick(clasificacion_activa)
        self.card_kpi_tiempo["valor"].configure(text=self.gestor_tiempo.obtener_tiempo_formateado())

        # Card 0: Lotes
        id_lote_txt = self.gestor_lotes.id_lote_actual if self.gestor_lotes.lote_activo else "En espera"
        self.card_kpi_lotes["sub"].configure(text=f"Lote: {id_lote_txt}")

        # Card 1: Granos Totales
        total_g = self.gestor_lotes.total_granos if self.gestor_lotes.lote_activo else self.metricas.total_granos
        sanos_g = self.gestor_lotes.total_sanos if self.gestor_lotes.lote_activo else self.metricas.total_sanos
        def_g = self.gestor_lotes.total_defectuosos if self.gestor_lotes.lote_activo else self.metricas.total_defectuosos

        self.card_kpi_granos["valor"].configure(text=f"{total_g} Granos")
        self.card_kpi_granos["sub"].configure(text=f"Calidad: {calidad_pct:.1f}% ({sanos_g} Sanos)")

        # Card 2: Consumo Energético
        self.card_kpi_consumo["valor"].configure(text=f"{consumo_kwh:.4f} kWh")

        # Card 3: Latencia
        self.card_kpi_latencia["valor"].configure(text=f"{latencia_prom:.1f} ms")
        self.card_kpi_latencia["sub"].configure(text=f"FPS Prom: {fps_prom:.1f}")

        # 3. Balance Sanos vs Defectos
        if total_g > 0:
            pct_s = sanos_g / total_g
            pct_d = def_g / total_g
            self.lbl_sanos_val.configure(text=f"{sanos_g} ({pct_s * 100:.1f}%)")
            self.bar_sanos.set(pct_s)

            self.lbl_defectos_val.configure(text=f"{def_g} ({pct_d * 100:.1f}%)")
            self.bar_defectos.set(pct_d)
        else:
            self.lbl_sanos_val.configure(text="0 (100.0%)")
            self.bar_sanos.set(1.0)
            self.lbl_defectos_val.configure(text="0 (0.0%)")
            self.bar_defectos.set(0.0)

        # 4. Actualizar Gráfico Reactivo en Tiempo Real
        self._actualizar_grafico_reactivo()

    def _refrescar_estadisticas_historicas(self) -> None:
        """Carga datos históricos consolidados desde SQLite para las StatCards."""
        stats = self.db_manager.obtener_estadisticas_acumuladas()
        total_lotes = stats.get("total_lotes", 0)
        pendientes = stats.get("pendientes_sync", 0)
        self.card_kpi_lotes["valor"].configure(text=f"{total_lotes} Lotes")
        if not self.gestor_lotes.lote_activo:
            self.card_kpi_lotes["sub"].configure(text=f"Pendientes Sync: {pendientes}")

    # -----------------------------------------------------------------
    # Manejadores de Switches de Modelo y SAHI
    # -----------------------------------------------------------------

    def _al_cambiar_switch_modelo(self) -> None:
        """Alterna el paradigma de clasificación entre '13 Clases' y 'Tri-clase'."""
        es_13_clases = bool(self.switch_modelo.get())
        if es_13_clases:
            self.switch_modelo.configure(text="13 Clases")
            self.badge_modelo.configure(text="Modo: 13 Clases")
        else:
            self.switch_modelo.configure(text="Tri-clase")
            self.badge_modelo.configure(text="Modo: Tri-clase")

        modo_sahi = bool(self.switch_sahi.get())
        self.gestor_lotes.configurar_modelo(modelo_13_clases=es_13_clases, modo_sahi=modo_sahi)
        # Redibujar la gráfica inmediatamente con la nueva estructura de barras
        self._actualizar_grafico_reactivo()

    def _al_cambiar_switch_sahi(self) -> None:
        """Alterna la inferencia SAHI (Slicing Aided Hyper Inference) On/Off."""
        es_sahi = bool(self.switch_sahi.get())
        self.switch_sahi.configure(text=f"SAHI: {'ON' if es_sahi else 'OFF'}")
        es_13_clases = bool(self.switch_modelo.get())
        self.gestor_lotes.configurar_modelo(modelo_13_clases=es_13_clases, modo_sahi=es_sahi)

    # -----------------------------------------------------------------
    # Gestión de Lotes y Eventos
    # -----------------------------------------------------------------

    def _finalizar_lote_manual(self) -> None:
        """Fuerza la finalización manual y persistencia del lote activo."""
        if not self.gestor_lotes.lote_activo:
            messagebox.showinfo("MOPPI", "No hay ningún lote activo en curso para finalizar.")
            return

        resumen = self.gestor_lotes.finalizar_lote(motivo="manual")
        if resumen:
            self._refrescar_estadisticas_historicas()
            messagebox.showinfo(
                "Lote Finalizado",
                f"Lote {resumen['id_lote']} cerrado exitosamente.\n"
                f"Granos: {resumen['total_granos']} | Calidad: {resumen['porcentaje_calidad']}%\n"
                f"Consumo: {resumen['consumo_kwh']} kWh\n"
                f"Persistencia iniciada (SQLite + MongoDB).",
            )

    def _al_lote_finalizado_auto(self, resumen: Dict[str, Any]) -> None:
        """Callback invocado por GestorLotes cuando se cierra por inactividad."""
        self._refrescar_estadisticas_historicas()
        print(f"[MOPPI] Lote {resumen.get('id_lote')} auto-finalizado por inactividad.")

    def _sincronizar_pendientes_manual(self) -> None:
        """Dispara sincronización manual de lotes pendientes hacia MongoDB Atlas."""
        def _tarea():
            count = self.db_manager.sincronizar_pendientes()
            self._refrescar_estadisticas_historicas()
            msg = f"Se sincronizaron {count} lotes con MongoDB Atlas." if count > 0 else "No hay lotes pendientes de sincronizar."
            messagebox.showinfo("Sincronización Cloud", msg)

        threading.Thread(target=_tarea, daemon=True).start()

    def _iniciar_clasificacion(self) -> None:
        """Inicia la sesión activa de clasificación con YOLO."""
        self.detector.iniciar_clasificacion()
        self.metricas.iniciar_sesion()
        self.btn_iniciar.configure(state="disabled")
        self.btn_pausar.configure(state="normal", text="Pausar")
        self.btn_detener.configure(state="normal")
        self.opt_fuente.configure(state="disabled")

    def _pausar_clasificacion(self) -> None:
        """Pausa o reanuda la clasificación activa."""
        if not self.metricas.esta_activo:
            self.detector.reanudar()
            self.metricas.iniciar_sesion()
            self.btn_pausar.configure(text="Pausar")
        else:
            self.detector.pausar()
            self.metricas.pausar_sesion()
            self.btn_pausar.configure(text="Reanudar")

    def _detener_clasificacion(self) -> None:
        """Detiene la sesión de clasificación volviendo al modo preview."""
        self.detector.detener_clasificacion()
        self.metricas.pausar_sesion()
        self.btn_iniciar.configure(state="normal")
        self.btn_pausar.configure(state="disabled", text="Pausar")
        self.btn_detener.configure(state="disabled")
        self.opt_fuente.configure(state="normal")

    def _cambiar_fuente_video_ctk(self, opcion_texto: str) -> None:
        """Cambia la fuente de video según la selección."""
        if "Principal" in opcion_texto or "0" in opcion_texto:
            nueva_fuente = 0
        elif "Secundaria" in opcion_texto or "1" in opcion_texto:
            nueva_fuente = 1
        else:
            nueva_fuente = "demo"
        self.detector.cambiar_fuente(nueva_fuente)

    def _reiniciar_estadisticas(self) -> None:
        """Reinicia los contadores de sesión."""
        self.metricas.reiniciar()
        self._actualizar_metricas_ui()
        messagebox.showinfo("MOPPI", "Estadísticas reiniciadas correctamente.")

    def _al_cerrar(self) -> None:
        """Cierre ordenado de hilos, base de datos y detector."""
        self._consumidor_activo = False
        try:
            self.gestor_tiempo.guardar_estado()
        except Exception:
            pass
        if self._ventana_logs is not None:
            try:
                if self._ventana_logs.winfo_exists():
                    self._ventana_logs.destroy()
            except Exception:
                pass
        try:
            self.gestor_lotes.detener()
        except Exception:
            pass
        try:
            self.db_manager.cerrar()
        except Exception:
            pass
        try:
            self.detector.detener()
        except Exception:
            pass
        if self.esp32_bridge:
            try:
                self.esp32_bridge.cerrar()
            except Exception:
                pass
        self.destroy()
