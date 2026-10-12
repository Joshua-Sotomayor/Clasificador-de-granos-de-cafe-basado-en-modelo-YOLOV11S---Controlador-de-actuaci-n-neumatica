"""
Dashboard de Inferencia y Telemetría MOPPI basado en CustomTkinter (v1.7.0).
Optimizado para pantallas táctiles de 10.1" (1280x800 px) en Modo Kiosk.
Arquitectura de Tres Vistas Integradas:
1. Dashboard: Vista en vivo monocámara alternable (↕), badge FPS/ms, botonera FSM
   (Marcha/Reanudar, Paro, Reset), indicadores circulares de 4 canales y calibración vertical de trigger.
2. Analíticas: Gráfico de barras horizontales reactivo con acrónimos compactos para 13 clases/tri-clase,
   4 StatCards (Tiempo, Consumo, Estadísticas, Rendimiento) y gestión de lotes.
3. Registros: Histórico estructurado de lotes con filtros temporales y visor de logs locales SQLite.
"""

import os
import time
import json
import queue
import threading
import cv2
from PIL import Image
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from typing import Dict, Any, Optional, List, Union, Tuple

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from core.detector import YOLODetector, calcular_desplazamiento_cinematico
from core.metricas import GestorMetricas
from storage.database import DatabaseManager, GestorLotes, MongoManager
from storage.telemetria import GestorTiempoUso
from hardware.serial_bridge import ESP32Bridge

# Configuración de Entorno HMI Táctil 1280x800
HMI_FULLSCREEN = os.getenv("HMI_FULLSCREEN", "True").lower() in ("true", "1", "yes")
HMI_WIDTH = int(os.getenv("HMI_WIDTH", "1280"))
HMI_HEIGHT = int(os.getenv("HMI_HEIGHT", "800"))

# Mapeo de Acrónimos Compactos para Pantalla de 10.1"
MAPA_ACRONIMOS_13 = {
    "Arabica_Agrio": "AAG",
    "Arabica_Brocado": "ABR",
    "Arabica_Bueno": "AB",
    "Arabica_Cereza": "AC",
    "Arabica_Concha": "ACO",
    "Arabica_Inmaduro": "AI",
    "Arabica_Negro": "AN",
    "Arabica_Quebrado": "AQ",
    "Robusta_Brocado": "RBR",
    "Robusta_Bueno": "RB",
    "Robusta_Cereza": "RC",
    "Robusta_Negro": "RN",
    "Robusta_Quebrado": "RQ",
}

MAPA_ACRONIMOS_TRI = {
    "Arabica_Bueno": "AB",
    "Robusta_Bueno": "RB",
    "Grano_Defecto": "DEF",
}


class VentanaConfirmacionTrigger(ctk.CTkToplevel):
    """
    Modal táctil centrado para confirmar el cambio de línea de disparo Y_trigger.
    Botones sobredimensionados (>= 50 px) optimizados para dedos del operario.
    """

    def __init__(
        self,
        parent: "DashboardCustomTkinter",
        nueva_latencia_ms: float = 3.0,
        nuevo_y_px: int = 501,
        callback_confirmar: Any = None,
        latencia_ms: Optional[float] = None,
        y_calculado_px: Optional[int] = None,
        on_confirmar: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.nueva_latencia_ms = nueva_latencia_ms if latencia_ms is None else latencia_ms
        self.nuevo_y_px = nuevo_y_px if y_calculado_px is None else y_calculado_px
        self.callback_confirmar = callback_confirmar or on_confirmar
        self.lbl_mensaje: Optional[ctk.CTkLabel] = None

        self.title("Confirmación de Calibración | MOPPI")
        self.geometry("460x280")
        self.resizable(False, False)
        self.configure(fg_color="#FFFFFF")

        # Centrar sobre la ventana padre
        self.transient(parent)
        self.grab_set()

        self._construir_ui()

    def _construir_ui(self) -> None:
        lbl_icono = ctk.CTkLabel(
            self,
            text="⚡",
            font=ctk.CTkFont(size=36),
            text_color="#197B30",
        )
        lbl_icono.pack(pady=(18, 4))

        lbl_titulo = ctk.CTkLabel(
            self,
            text="¿Confirmar Nueva Latencia de Actuación?",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#4A3B32",
        )
        lbl_titulo.pack(pady=(0, 6))

        lbl_desc = ctk.CTkLabel(
            self,
            text=(
                f"Latencia Válvula: {self.nueva_latencia_ms:.1f} ms\n"
                f"Línea de Disparo Resultante: Y = {self.nuevo_y_px} px\n"
                "El cambio se guardará de forma persistente en storage/config_maquina.json."
            ),
            font=ctk.CTkFont(size=12),
            text_color="#616161",
            justify="center",
        )
        lbl_desc.pack(pady=(0, 16))
        self.lbl_mensaje = lbl_desc

        frame_botones = ctk.CTkFrame(self, fg_color="transparent")
        frame_botones.pack(fill="x", padx=24, pady=(4, 16))
        frame_botones.grid_columnconfigure((0, 1), weight=1)

        btn_cancelar = ctk.CTkButton(
            frame_botones,
            text="Cancelar",
            command=self.destroy,
            height=50,
            fg_color="#757575",
            hover_color="#616161",
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=10,
        )
        btn_cancelar.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        btn_confirmar = ctk.CTkButton(
            frame_botones,
            text="Confirmar Cambio",
            command=self._al_confirmar,
            height=50,
            fg_color="#197B30",
            hover_color="#145F25",
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=10,
        )
        btn_confirmar.grid(row=0, column=1, padx=(8, 0), sticky="ew")

    def _al_confirmar(self) -> None:
        self.destroy()
        if self.callback_confirmar:
            try:
                self.callback_confirmar(self.nueva_latencia_ms)
            except TypeError:
                self.callback_confirmar()


class VentanaLogsToplevel(ctk.CTkToplevel):
    """
    Ventana flotante independiente para visualización de logs locales SQLite.
    """

    def __init__(
        self,
        parent: ctk.CTk,
        db_manager: Union[DatabaseManager, MongoManager],
    ) -> None:
        super().__init__(parent)
        self.db_manager = db_manager

        self.title("Auditoría de Eventos y Alarmas | MOPPI")
        self.geometry("920x560")
        self.minsize(700, 380)
        self.configure(fg_color="#F5F6F8")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._construir_ui()
        self._cargar_logs()

    def _construir_ui(self) -> None:
        frame_filtros = ctk.CTkFrame(
            self,
            fg_color="#FFFFFF",
            corner_radius=12,
            border_width=1,
            border_color="#E0E0E0",
        )
        frame_filtros.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")

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

        lbl_fecha = ctk.CTkLabel(
            frame_filtros,
            text="Rango:",
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

        btn_refrescar = ctk.CTkButton(
            frame_filtros,
            text="↻ Actualizar",
            command=self._cargar_logs,
            width=100,
            fg_color="#197B30",
            hover_color="#145F25",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        btn_refrescar.pack(side="right", padx=12, pady=8)

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
        self.txt_logs.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")

        try:
            raw = self.txt_logs._textbox
            raw.tag_config("ALARM", foreground="#FF5252", font=("Consolas", 11, "bold"))
            raw.tag_config("WARNING", foreground="#FFB74D", font=("Consolas", 11, "bold"))
            raw.tag_config("INFO", foreground="#81C784")
            raw.tag_config("TIMESTAMP", foreground="#64B5F6")
            raw.tag_config("DEF", foreground="#E0E0E0")
        except Exception:
            pass

    def _cargar_logs(self) -> None:
        tipo = self.opt_tipo.get()
        fecha = self.seg_fecha.get()
        logs = self.db_manager.obtener_logs_locales(
            tipo=tipo if tipo != "TODOS" else None,
            filtro_fecha=fecha,
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
    Aplicación Principal HMI MOPPI con Pantalla Táctil de 10.1" (1280x800).
    Arquitectura de Tres Vistas (Dashboard, Analíticas, Registros),
    Botonera con Máquina de Estados, Indicadores de Válvulas Seriales
    y Compensación Cinemática de Disparo en Tiempo Real.
    """

    COLOR_FONDO_APP = "#F5F6F8"
    COLOR_FONDO_CARD_LIGHT = "#FFFFFF"
    COLOR_BORDE_NEUMORFICO = "#E0E0E0"
    COLOR_VERDE_ULSA = "#197B30"
    COLOR_VERDE_HOVER = "#145F25"
    COLOR_VERDE_CLARO = "#E8F5E9"
    COLOR_CAFE_TEXTO = "#4A3B32"
    COLOR_GRIS_SEC = "#616161"
    COLOR_ROJO_DEFECTO = "#D32F2F"
    COLOR_ROJO_HOVER = "#B71C1C"
    COLOR_AMARILLO_ALERTA = "#F57C00"
    COLOR_AZUL_ACCION = "#1976D2"

    RADIUS_CARD = 14
    RADIUS_SMALL = 10

    COLORES_TRI_CLASE = {
        "Arabica_Bueno": "#197B30",
        "Robusta_Bueno": "#0288D1",
        "Grano_Defecto": "#D32F2F",
    }

    COLORES_13_CLASES = {
        "Arabica_Agrio": "#FBC02D",
        "Arabica_Brocado": "#FFA000",
        "Arabica_Bueno": "#197B30",
        "Arabica_Cereza": "#D32F2F",
        "Arabica_Concha": "#F57C00",
        "Arabica_Inmaduro": "#7CB342",
        "Arabica_Negro": "#212121",
        "Arabica_Quebrado": "#8D6E63",
        "Robusta_Brocado": "#E65100",
        "Robusta_Bueno": "#0288D1",
        "Robusta_Cereza": "#C2185B",
        "Robusta_Negro": "#37474F",
        "Robusta_Quebrado": "#6D4C41",
    }

    def __init__(
        self,
        detector: YOLODetector,
        metricas: GestorMetricas,
        db_manager: Optional[Union[DatabaseManager, MongoManager]] = None,
        gestor_lotes: Optional[GestorLotes] = None,
        esp32_bridge: Optional[ESP32Bridge] = None,
    ) -> None:
        super().__init__()

        self.detector = detector
        self.metricas = metricas
        self.esp32_bridge = esp32_bridge or getattr(self.detector, "esp32_bridge", None)

        # Base de datos
        if db_manager is not None:
            self.db_manager = db_manager
        else:
            self.db_manager = DatabaseManager(dias_retencion=30)

        # Gestor de Lotes
        self.gestor_lotes = gestor_lotes or GestorLotes(
            db_manager=self.db_manager,
            potencia_hardware_kw=float(os.getenv("HARDWARE_POWER_KW", "0.5")),
            timeout_inactividad_seg=60,
            callback_lote_finalizado=self._al_lote_finalizado_auto,
        )

        # Enlace con callback serial de ESP32 para los indicadores de canales
        if self.esp32_bridge is not None:
            self.esp32_bridge.callback_respuesta = self._al_recibir_respuesta_serial

        # Configuración de ventana principal y modo Kiosk
        self.title("MOPPI - Clasificador Óptico y Cinemático de Café")
        self.geometry(f"{HMI_WIDTH}x{HMI_HEIGHT}")
        self.minsize(1024, 600)
        self.configure(fg_color=self.COLOR_FONDO_APP)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")

        if HMI_FULLSCREEN:
            try:
                self.attributes("-fullscreen", True)
            except Exception:
                pass

        # Atajo para alternar pantalla completa
        self.bind("<Escape>", self._toggle_fullscreen)

        # Control de bucle de UI y cámaras
        self._consumidor_activo = True
        self._bucle_id: Optional[str] = None
        self._ultimo_refresco_kpi = time.time()
        self._ctk_image_ref = None
        self.camara_vista_activa = "TOP"  # "TOP" (Maestro/Disparo) o "BOTTOM" (Ventral)
        self._fuente_top_actual = self.detector.fuente_video_top
        self._fuente_bottom_actual = self.detector.fuente_video_bottom
        self._ventana_logs: Optional[VentanaLogsToplevel] = None
        self.modal_trigger: Optional[VentanaConfirmacionTrigger] = None

        # Telemetría anti-apagones y recuperación de estado
        self.gestor_tiempo = GestorTiempoUso()

        # Matplotlib Reactivo
        self.fig_reactiva: Optional[Figure] = None
        self.ax_reactivo = None
        self.canvas_reactivo: Optional[FigureCanvasTkAgg] = None

        # Estado FSM de la botonera: "STANDBY", "EN_MARCHA", "PARO"
        self.estado_operativo = "STANDBY"

        # Construir Interfaz de Tres Vistas
        self._construir_interfaz()

        # Evaluar protección anti-corte abrupto al arranque
        self._verificar_corte_abrupto_al_arranque()

        # Iniciar detector en modo preview
        self.detector.iniciar()

        # Iniciar bucle de refresco nativo en UI (15 ms ~ 60 FPS)
        self._bucle_id = self.after(15, self._bucle_actualizacion_frame)

        # Protocolo de cierre ordenado
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

    def _toggle_fullscreen(self, event=None) -> None:
        """Alterna el modo de pantalla completa."""
        actual = bool(self.attributes("-fullscreen"))
        self.attributes("-fullscreen", not actual)

    # =========================================================================
    # CONSTRUCCIÓN DE LA INTERFAZ INTEGRAL
    # =========================================================================

    def _construir_interfaz(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- 1. BARRA SUPERIOR UNIFICADA (Idéntica en todas las vistas) ---
        self._construir_barra_superior()

        # --- 2. CONTENEDOR DE TRES VISTAS ---
        self.contenedor_vistas = ctk.CTkFrame(self, fg_color="transparent")
        self.contenedor_vistas.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="nsew")
        self.contenedor_vistas.grid_columnconfigure(0, weight=1)
        self.contenedor_vistas.grid_rowconfigure(0, weight=1)

        # Vista 1: Dashboard
        self.vista_dashboard = ctk.CTkFrame(self.contenedor_vistas, fg_color="transparent")
        self.vista_dashboard.grid(row=0, column=0, sticky="nsew")
        self._construir_vista_dashboard()

        # Vista 2: Analíticas
        self.vista_analiticas = ctk.CTkFrame(self.contenedor_vistas, fg_color="transparent")
        self.vista_analiticas.grid(row=0, column=0, sticky="nsew")
        self._construir_vista_analiticas()
        self.vista_analiticas.grid_remove()

        # Vista 3: Registros
        self.vista_registros = ctk.CTkFrame(self.contenedor_vistas, fg_color="transparent")
        self.vista_registros.grid(row=0, column=0, sticky="nsew")
        self._construir_vista_registros()
        self.vista_registros.grid_remove()

        # Alias para retrocompatibilidad con tests
        self.tab_analitico = self.vista_analiticas
        self.tab_logs = self.vista_registros

    def _construir_barra_superior(self) -> None:
        cabecera = ctk.CTkFrame(
            self,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            height=64,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        cabecera.grid(row=0, column=0, padx=12, pady=(8, 6), sticky="ew")
        cabecera.grid_columnconfigure(0, weight=1)

        # Sub-bloque izquierdo: Estado BD, Lotes, Cámara y Modelo
        frame_izq = ctk.CTkFrame(cabecera, fg_color="transparent")
        frame_izq.pack(side="left", padx=10, pady=6)

        # Indicador MongoDB
        self.badge_db = ctk.CTkButton(
            frame_izq,
            text="Base de Datos ●",
            fg_color="#E8F5E9" if self.db_manager.conectado_mongo else "#FFF8E1",
            text_color=self.COLOR_VERDE_ULSA if self.db_manager.conectado_mongo else self.COLOR_AMARILLO_ALERTA,
            hover=False,
            height=30,
            corner_radius=15,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.badge_db.pack(side="left", padx=(0, 6))

        # Contador de Lotes
        self.badge_lotes = ctk.CTkButton(
            frame_izq,
            text="Lotes: ---",
            fg_color="#ECEFF1",
            text_color=self.COLOR_CAFE_TEXTO,
            hover=False,
            height=30,
            corner_radius=15,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.badge_lotes.pack(side="left", padx=6)

        # Cambiar Posición de Cámaras (Dropdown)
        lbl_pos = ctk.CTkLabel(
            frame_izq, text="Posición:", font=ctk.CTkFont(size=11, weight="bold"), text_color=self.COLOR_GRIS_SEC
        )
        lbl_pos.pack(side="left", padx=(10, 3))

        self.combo_cam_pos = ctk.CTkOptionMenu(
            frame_izq,
            values=["Normal (0/1)", "Invertida (1/0)"],
            command=self._al_cambiar_posicion_camara,
            width=135,
            height=30,
            fg_color=self.COLOR_VERDE_ULSA,
            button_color=self.COLOR_VERDE_HOVER,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.combo_cam_pos.set("Invertida (1/0)" if self.detector.posicion_camara_invertida else "Normal (0/1)")
        self.combo_cam_pos.pack(side="left", padx=3)

        # Selector de Modelo (Dropdown)
        lbl_mod = ctk.CTkLabel(
            frame_izq, text="Modelo:", font=ctk.CTkFont(size=11, weight="bold"), text_color=self.COLOR_GRIS_SEC
        )
        lbl_mod.pack(side="left", padx=(10, 3))

        self.combo_modelo_hdr = ctk.CTkOptionMenu(
            frame_izq,
            values=["Tri-clase", "13 Clases"],
            command=self._al_cambiar_modelo_dropdown,
            width=115,
            height=30,
            fg_color="#6D4C41",
            button_color="#4E342E",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.combo_modelo_hdr.set("13 Clases" if self.detector.es_modo_13clases else "Tri-clase")
        self.combo_modelo_hdr.pack(side="left", padx=3)

        # Botón ↕ para alternar vista visible de cámara
        self.btn_toggle_camara = ctk.CTkButton(
            frame_izq,
            text="↕",
            command=self._alternar_vista_camara,
            width=36,
            height=30,
            fg_color=self.COLOR_VERDE_ULSA,
            hover_color=self.COLOR_VERDE_HOVER,
            font=ctk.CTkFont(size=16, weight="bold"),
            corner_radius=15,
        )
        self.btn_toggle_camara.pack(side="left", padx=(8, 0))

        # Switches internos para retrocompatibilidad con tests unitarios
        self.switch_modelo = ctk.CTkSwitch(
            cabecera,
            text="Tri-clase",
            command=self._al_cambiar_switch_modelo,
            font=ctk.CTkFont(size=11, weight="bold"),
            progress_color=self.COLOR_VERDE_ULSA,
        )
        self.switch_modelo.deselect()

        self.switch_sahi = ctk.CTkSwitch(
            cabecera,
            text="SAHI: OFF",
            command=self._al_cambiar_switch_sahi,
            font=ctk.CTkFont(size=11, weight="bold"),
            progress_color=self.COLOR_VERDE_ULSA,
        )
        self.switch_sahi.deselect()

        # Sub-bloque derecho: Badges FPS/ms y Selector de Tres Vistas
        frame_der = ctk.CTkFrame(cabecera, fg_color="transparent")
        frame_der.pack(side="right", padx=10, pady=6)

        self.badge_ms = ctk.CTkLabel(
            frame_der,
            text="ms: 0.0",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#0277BD",
            fg_color="#E1F5FE",
            corner_radius=12,
            padx=10,
            pady=4,
        )
        self.badge_ms.pack(side="left", padx=4)

        self.badge_fps = ctk.CTkLabel(
            frame_der,
            text="FPS: 30.0",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.COLOR_VERDE_ULSA,
            fg_color=self.COLOR_VERDE_CLARO,
            corner_radius=12,
            padx=10,
            pady=4,
        )
        self.badge_fps.pack(side="left", padx=4)

        # Botón segmentado para cambio de pantallas
        self.seg_ventanas = ctk.CTkSegmentedButton(
            frame_der,
            values=["Dashboard", "Analíticas", "Registros"],
            command=self._al_cambiar_ventana,
            selected_color=self.COLOR_VERDE_ULSA,
            selected_hover_color=self.COLOR_VERDE_HOVER,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=16,
        )
        self.seg_ventanas.set("Dashboard")
        self.seg_ventanas.pack(side="left", padx=(10, 0))

        # Aliases y selectores para retrocompatibilidad con tests existentes
        self.badge_modelo = self.combo_modelo_hdr
        self.combo_cam_top = ctk.CTkOptionMenu(
            self,
            values=["Cámara 0", "Cámara 1", "Cámara 2", "Demo / Sintético"],
            command=self._al_cambiar_camara_top,
        )
        self.combo_cam_top.set(self._formatear_fuente_texto(self.detector.fuente_video_top))

        self.combo_cam_bottom = ctk.CTkOptionMenu(
            self,
            values=["Cámara 0", "Cámara 1", "Cámara 2", "Demo / Sintético"],
            command=self._al_cambiar_camara_bottom,
        )
        self.combo_cam_bottom.set(self._formatear_fuente_texto(self.detector.fuente_video_bottom))
        self.opt_fuente = self.combo_cam_top

    # =========================================================================
    # VISTA 1: DASHBOARD (Pantalla Principal del HMI)
    # =========================================================================

    def _construir_vista_dashboard(self) -> None:
        self.vista_dashboard.grid_columnconfigure(0, weight=3)
        self.vista_dashboard.grid_columnconfigure(1, weight=2)
        self.vista_dashboard.grid_rowconfigure(0, weight=1)

        # --- A. Card de Video Monocámara Alternable ---
        card_video = ctk.CTkFrame(
            self.vista_dashboard,
            fg_color="#1E1E1E",
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        card_video.grid(row=0, column=0, padx=(0, 8), pady=0, sticky="nsew")
        card_video.grid_rowconfigure(1, weight=1)
        card_video.grid_columnconfigure(0, weight=1)

        # Barra superior sobre el video
        frame_hdr_video = ctk.CTkFrame(card_video, fg_color="#141414", corner_radius=8, height=34)
        frame_hdr_video.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="ew")

        self.lbl_camara_activa_badge = ctk.CTkLabel(
            frame_hdr_video,
            text="CÁMARA SUPERIOR (MAESTRO) | GUÍAS DE CARRIL Y DISPARO",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#A5D6A7",
        )
        self.lbl_camara_activa_badge.pack(side="left", padx=12, pady=4)

        lbl_ayuda_toggle = ctk.CTkLabel(
            frame_hdr_video,
            text="[Pulse ↕ para alternar cámara]",
            font=ctk.CTkFont(size=10),
            text_color="#B0BEC5",
        )
        lbl_ayuda_toggle.pack(side="right", padx=12, pady=4)

        # Lienzo visible del fotograma
        self.lbl_video = ctk.CTkLabel(
            card_video,
            text="Iniciando transmisión de video...",
            text_color="#888888",
        )
        self.lbl_video.grid(row=1, column=0, padx=6, pady=(0, 6), sticky="nsew")
        self.lbl_video_top = self.lbl_video  # Alias de compatibilidad

        # --- B. Panel Derecho de Control: Botonera, Canales y Trigger ---
        panel_derecho = ctk.CTkFrame(
            self.vista_dashboard,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        panel_derecho.grid(row=0, column=1, padx=(8, 0), pady=0, sticky="nsew")
        panel_derecho.grid_rowconfigure(1, weight=1)
        panel_derecho.grid_columnconfigure((0, 1, 2), weight=1)

        # -------------------------------------------------------------
        # Columna 1: BOTONERIA DE ACCIONES
        # -------------------------------------------------------------
        frame_col_botonera = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        frame_col_botonera.grid(row=0, column=0, rowspan=2, padx=6, pady=12, sticky="nsew")

        lbl_tit_bot = ctk.CTkLabel(
            frame_col_botonera,
            text="BOTONERIA",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_tit_bot.pack(pady=(4, 16))

        # Botón Marcha / Reanudar
        self.btn_marcha = ctk.CTkButton(
            frame_col_botonera,
            text="Marcha",
            command=self._al_pulsar_marcha,
            height=64,
            corner_radius=32,
            fg_color=self.COLOR_VERDE_ULSA,
            hover_color=self.COLOR_VERDE_HOVER,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.btn_marcha.pack(fill="x", padx=6, pady=10)

        # Botón Paro
        self.btn_paro = ctk.CTkButton(
            frame_col_botonera,
            text="Paro",
            command=self._al_pulsar_paro,
            height=64,
            corner_radius=32,
            fg_color=self.COLOR_ROJO_DEFECTO,
            hover_color=self.COLOR_ROJO_HOVER,
            font=ctk.CTkFont(size=14, weight="bold"),
            state="disabled",
        )
        self.btn_paro.pack(fill="x", padx=6, pady=10)

        # Botón Reset
        self.btn_reset = ctk.CTkButton(
            frame_col_botonera,
            text="Reset",
            command=self._al_pulsar_reset,
            height=64,
            corner_radius=32,
            fg_color=self.COLOR_AZUL_ACCION,
            hover_color="#0D47A1",
            font=ctk.CTkFont(size=14, weight="bold"),
            state="disabled",
        )
        self.btn_reset.pack(fill="x", padx=6, pady=10)

        # Indicador textual de estado
        self.lbl_estado_maquina = ctk.CTkLabel(
            frame_col_botonera,
            text="ESTADO: STANDBY",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.COLOR_GRIS_SEC,
        )
        self.lbl_estado_maquina.pack(pady=(16, 0))

        # Aliases para retrocompatibilidad con tests
        self.btn_iniciar = self.btn_marcha
        self.btn_pausar = self.btn_paro
        self.btn_detener = self.btn_reset

        # -------------------------------------------------------------
        # Columna 2: CANALES (Indicadores de Activación de Válvulas)
        # -------------------------------------------------------------
        frame_col_canales = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        frame_col_canales.grid(row=0, column=1, rowspan=2, padx=6, pady=12, sticky="nsew")

        lbl_tit_can = ctk.CTkLabel(
            frame_col_canales,
            text="CANALES",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_tit_can.pack(pady=(4, 16))

        self.indicadores_canales: List[ctk.CTkButton] = []
        for i in range(4):
            btn_ch = ctk.CTkButton(
                frame_col_canales,
                text=str(i),
                width=54,
                height=54,
                corner_radius=27,
                fg_color="#E0E0E0",
                text_color="#424242",
                hover=False,
                font=ctk.CTkFont(size=15, weight="bold"),
            )
            btn_ch.pack(pady=8)
            self.indicadores_canales.append(btn_ch)

        # -------------------------------------------------------------
        # Columna 3: TRIGGER (Calibración Cinemática Vertical)
        # -------------------------------------------------------------
        frame_col_trigger = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        frame_col_trigger.grid(row=0, column=2, rowspan=2, padx=6, pady=12, sticky="nsew")

        lbl_tit_trig = ctk.CTkLabel(
            frame_col_trigger,
            text="TRIGGER",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_tit_trig.pack(pady=(4, 6))

        # Lectura actual de latencia y píxel Y
        lat_actual = getattr(self.detector, "valvula_latencia_ms", 3.0)
        y_actual = getattr(self.detector, "y_trigger", 501)

        self.lbl_val_trigger = ctk.CTkLabel(
            frame_col_trigger,
            text=f"{lat_actual:.1f} ms\n(Y={y_actual})",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#0277BD",
            justify="center",
        )
        self.lbl_val_trigger.pack(pady=(0, 6))

        # Slider vertical con rango 1.0 ms a 25.0 ms
        self.slider_trigger = ctk.CTkSlider(
            frame_col_trigger,
            orientation="vertical",
            from_=1.0,
            to=25.0,
            number_of_steps=48,
            command=self._al_mover_slider_trigger,
            height=180,
            progress_color=self.COLOR_VERDE_ULSA,
        )
        self.slider_trigger.set(lat_actual)
        self.slider_trigger.pack(pady=(4, 10))

        # Botón Cancelar (Volver a dejarla como estaba)
        self.btn_cancelar_trigger = ctk.CTkButton(
            frame_col_trigger,
            text="Cancelar",
            command=self._cancelar_trigger,
            height=32,
            fg_color="#9E9E9E",
            hover_color="#757575",
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=8,
        )
        self.btn_cancelar_trigger.pack(fill="x", padx=6, pady=4)

        # Botón Aplicar (Despliega modal de confirmación)
        self.btn_aplicar_trigger = ctk.CTkButton(
            frame_col_trigger,
            text="Aplicar",
            command=self._abrir_modal_confirmar_trigger,
            height=32,
            fg_color=self.COLOR_VERDE_ULSA,
            hover_color=self.COLOR_VERDE_HOVER,
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=8,
        )
        self.btn_aplicar_trigger.pack(fill="x", padx=6, pady=4)

        # Aliases para retrocompatibilidad
        self.slider_latencia = self.slider_trigger
        self.btn_aplicar_latencia = self.btn_aplicar_trigger
        self.btn_cancelar_latencia = self.btn_cancelar_trigger

    # =========================================================================
    # VISTA 2: ANALÍTICAS (Gráfico Reactivo con Acrónimos y StatCards)
    # =========================================================================

    def _construir_vista_analiticas(self) -> None:
        self.vista_analiticas.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.vista_analiticas.grid_rowconfigure(1, weight=1)

        # Fila 0: 4 StatCards Principales
        self.card_kpi_tiempo = self._crear_statcard_neumorfica(
            self.vista_analiticas,
            0,
            "Tiempo de Uso",
            self.gestor_tiempo.obtener_tiempo_formateado(),
            "Persistencia anti-apagones",
        )
        self.card_kpi_consumo = self._crear_statcard_neumorfica(
            self.vista_analiticas,
            1,
            "Consumo kWh",
            "0.0000 kWh",
            f"Potencia: {self.gestor_lotes.potencia_hardware_kw:.2f} kW",
        )
        self.card_kpi_granos = self._crear_statcard_neumorfica(
            self.vista_analiticas,
            2,
            "Estadísticas grs/%",
            "0 Granos",
            "Calidad: 100.0% (0 Sanos)",
        )
        self.card_kpi_latencia = self._crear_statcard_neumorfica(
            self.vista_analiticas,
            3,
            "Rendimiento FPS/ms",
            "30.0 FPS",
            "Latencia: 0.0 ms",
        )

        # Aliases para retrocompatibilidad con tests existentes
        self.card_kpi_lotes = self.card_kpi_consumo

        # Fila 1: Panel Central con Gráfica Matplotlib y Acciones
        frame_central = ctk.CTkFrame(self.vista_analiticas, fg_color="transparent")
        frame_central.grid(row=1, column=0, columnspan=4, padx=0, pady=(10, 0), sticky="nsew")
        frame_central.grid_columnconfigure(0, weight=3)
        frame_central.grid_columnconfigure(1, weight=2)
        frame_central.grid_rowconfigure(0, weight=1)

        # Panel Izquierdo: Gráfico de Barras con Acrónimos
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
            text="Distribución de Granos y Defectos (Acrónimos Estandarizados)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_graf_hdr.pack(anchor="w", padx=14, pady=(10, 2))

        self.frame_canvas = ctk.CTkFrame(card_grafico, fg_color="transparent")
        self.frame_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self.fig_reactiva = Figure(figsize=(6.2, 4.2), dpi=95, facecolor="#FFFFFF")
        self.ax_reactivo = self.fig_reactiva.add_subplot(111)
        self.canvas_reactivo = FigureCanvasTkAgg(self.fig_reactiva, master=self.frame_canvas)
        self.canvas_widget = self.canvas_reactivo.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True)

        self._actualizar_grafico_reactivo()

        # Panel Derecho: Balance y Botones de Acción
        card_acciones = ctk.CTkFrame(
            frame_central,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        card_acciones.grid(row=0, column=1, padx=(6, 0), pady=0, sticky="nsew")

        lbl_bal_tit = ctk.CTkLabel(
            card_acciones,
            text="Balance de Clasificación del Lote",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_bal_tit.pack(anchor="w", padx=14, pady=(10, 8))

        # Barras Sanos vs Defectos
        frame_sanos_hdr = ctk.CTkFrame(card_acciones, fg_color="transparent")
        frame_sanos_hdr.pack(fill="x", padx=14, pady=(2, 2))
        ctk.CTkLabel(
            frame_sanos_hdr,
            text="Granos Sanos (Buenos)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.COLOR_VERDE_ULSA,
        ).pack(side="left")
        self.lbl_sanos_val = ctk.CTkLabel(
            frame_sanos_hdr,
            text="0 (100.0%)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.COLOR_VERDE_ULSA,
        )
        self.lbl_sanos_val.pack(side="right")

        self.bar_sanos = ctk.CTkProgressBar(
            card_acciones,
            progress_color=self.COLOR_VERDE_ULSA,
            fg_color="#E8F5E9",
            height=12,
            corner_radius=6,
        )
        self.bar_sanos.pack(fill="x", padx=14, pady=(0, 10))
        self.bar_sanos.set(1.0)

        frame_def_hdr = ctk.CTkFrame(card_acciones, fg_color="transparent")
        frame_def_hdr.pack(fill="x", padx=14, pady=(2, 2))
        ctk.CTkLabel(
            frame_def_hdr,
            text="Granos Defectuosos",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.COLOR_ROJO_DEFECTO,
        ).pack(side="left")
        self.lbl_defectos_val = ctk.CTkLabel(
            frame_def_hdr,
            text="0 (0.0%)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.COLOR_ROJO_DEFECTO,
        )
        self.lbl_defectos_val.pack(side="right")

        self.bar_defectos = ctk.CTkProgressBar(
            card_acciones,
            progress_color=self.COLOR_ROJO_DEFECTO,
            fg_color="#FFEBEE",
            height=12,
            corner_radius=6,
        )
        self.bar_defectos.pack(fill="x", padx=14, pady=(0, 16))
        self.bar_defectos.set(0.0)

        # Botones de Acción Táctiles
        btn_terminar_lote = ctk.CTkButton(
            card_acciones,
            text="Terminar Lote",
            command=self._finalizar_lote_manual,
            height=44,
            fg_color=self.COLOR_CAFE_TEXTO,
            hover_color="#372B24",
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=10,
        )
        btn_terminar_lote.pack(fill="x", padx=14, pady=6)

        btn_sinc_bd = ctk.CTkButton(
            card_acciones,
            text="Sincronizar BD",
            command=self._sincronizar_pendientes_manual,
            height=44,
            fg_color="#0288D1",
            hover_color="#0277BD",
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=10,
        )
        btn_sinc_bd.pack(fill="x", padx=14, pady=6)

        self.btn_reiniciar = ctk.CTkButton(
            card_acciones,
            text="Reiniciar Métricas",
            command=self._reiniciar_estadisticas,
            height=36,
            fg_color="#8D6E63",
            hover_color="#6D4C41",
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=10,
        )
        self.btn_reiniciar.pack(fill="x", padx=14, pady=(10, 8))

    # =========================================================================
    # VISTA 3: REGISTROS (Historial y Logs según Wireframe)
    # =========================================================================

    def _construir_vista_registros(self) -> None:
        self.vista_registros.grid_columnconfigure(0, weight=1)
        self.vista_registros.grid_rowconfigure(0, weight=3)
        self.vista_registros.grid_rowconfigure(1, weight=2)

        # --- SECCIÓN 1: HISTORIAL DE LOTES ---
        card_hist = ctk.CTkFrame(
            self.vista_registros,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        card_hist.grid(row=0, column=0, padx=0, pady=(0, 6), sticky="nsew")
        card_hist.grid_columnconfigure(0, weight=1)
        card_hist.grid_rowconfigure(1, weight=1)

        # Barra de Filtros Historial
        frame_flt_hist = ctk.CTkFrame(card_hist, fg_color="transparent")
        frame_flt_hist.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="ew")

        lbl_tit_hist = ctk.CTkLabel(
            frame_flt_hist,
            text="Historial",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_tit_hist.pack(side="left", padx=(4, 16))

        self.opt_filtro_modelo_hist = ctk.CTkOptionMenu(
            frame_flt_hist,
            values=["Todos", "Tri-clase", "13 Clases"],
            command=lambda _: self._cargar_historial_lotes(),
            width=110,
            height=28,
            fg_color=self.COLOR_VERDE_ULSA,
            button_color=self.COLOR_VERDE_HOVER,
        )
        self.opt_filtro_modelo_hist.set("Todos")
        self.opt_filtro_modelo_hist.pack(side="left", padx=4)

        self.seg_filtro_fecha_hist = ctk.CTkSegmentedButton(
            frame_flt_hist,
            values=["Hoy", "Últimos 3 días", "Última semana", "Todos"],
            command=lambda _: self._cargar_historial_lotes(),
            selected_color=self.COLOR_VERDE_ULSA,
            selected_hover_color=self.COLOR_VERDE_HOVER,
            height=28,
        )
        self.seg_filtro_fecha_hist.set("Hoy")
        self.seg_filtro_fecha_hist.pack(side="left", padx=4)

        btn_refrescar_hist = ctk.CTkButton(
            frame_flt_hist,
            text="↻",
            command=self._cargar_historial_lotes,
            width=32,
            height=28,
            fg_color=self.COLOR_VERDE_ULSA,
            hover_color=self.COLOR_VERDE_HOVER,
        )
        btn_refrescar_hist.pack(side="right", padx=6)

        # Contenedor con scroll para la tabla de historial
        self.scroll_historial = ctk.CTkScrollableFrame(
            card_hist,
            fg_color="#FAFAFA",
            corner_radius=8,
            border_width=1,
            border_color="#E0E0E0",
        )
        self.scroll_historial.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="nsew")
        self.scroll_historial.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        # Encabezados de la tabla
        headers = [
            "Fecha",
            "Nº de Lote",
            "Granos Procesados",
            "Granos buenos (N)",
            "Granos buenos (%)",
            "Tiempo (min)",
        ]
        for col_idx, h_text in enumerate(headers):
            lbl_h = ctk.CTkLabel(
                self.scroll_historial,
                text=h_text,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=self.COLOR_CAFE_TEXTO,
            )
            lbl_h.grid(row=0, column=col_idx, padx=6, pady=4, sticky="w")

        # --- SECCIÓN 2: HISTORIAL DE LOGS (Más pequeño que el historial) ---
        card_logs = ctk.CTkFrame(
            self.vista_registros,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        card_logs.grid(row=1, column=0, padx=0, pady=(6, 0), sticky="nsew")
        card_logs.grid_columnconfigure(0, weight=1)
        card_logs.grid_rowconfigure(1, weight=1)

        # Barra de Filtros Logs
        frame_flt_logs = ctk.CTkFrame(card_logs, fg_color="transparent")
        frame_flt_logs.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="ew")

        lbl_tit_logs = ctk.CTkLabel(
            frame_flt_logs,
            text="LOGS",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_tit_logs.pack(side="left", padx=(4, 16))

        self.opt_filtro_logs = ctk.CTkOptionMenu(
            frame_flt_logs,
            values=["TODOS", "INFO", "WARNING", "ALARM"],
            command=lambda _: self._actualizar_visor_logs(),
            width=110,
            height=28,
            fg_color=self.COLOR_VERDE_ULSA,
            button_color=self.COLOR_VERDE_HOVER,
        )
        self.opt_filtro_logs.set("TODOS")
        self.opt_filtro_logs.pack(side="left", padx=4)

        self.seg_filtro_fecha = ctk.CTkSegmentedButton(
            frame_flt_logs,
            values=["Hoy", "Últimos 3 días", "Última semana", "Todos"],
            command=lambda _: self._actualizar_visor_logs(),
            selected_color=self.COLOR_VERDE_ULSA,
            selected_hover_color=self.COLOR_VERDE_HOVER,
            height=28,
        )
        self.seg_filtro_fecha.set("Hoy")
        self.seg_filtro_fecha.pack(side="left", padx=4)

        btn_toplevel_logs = ctk.CTkButton(
            frame_flt_logs,
            text="⤢ Ventana",
            command=self._abrir_ventana_logs_toplevel,
            width=80,
            height=28,
            fg_color="#6D4C41",
            hover_color="#4E342E",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        btn_toplevel_logs.pack(side="right", padx=4)

        btn_refrescar_logs = ctk.CTkButton(
            frame_flt_logs,
            text="↻",
            command=self._actualizar_visor_logs,
            width=32,
            height=28,
            fg_color=self.COLOR_VERDE_ULSA,
            hover_color=self.COLOR_VERDE_HOVER,
        )
        btn_refrescar_logs.pack(side="right", padx=4)

        # Consola de Texto para Logs
        self.txt_logs = ctk.CTkTextbox(
            card_logs,
            fg_color="#1E1E1E",
            text_color="#E0E0E0",
            font=ctk.CTkFont(family="Consolas", size=10),
            corner_radius=8,
            border_width=1,
            border_color="#E0E0E0",
            wrap="word",
        )
        self.txt_logs.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="nsew")

        try:
            raw = self.txt_logs._textbox
            raw.tag_config("ALARM", foreground="#FF5252", font=("Consolas", 10, "bold"))
            raw.tag_config("WARNING", foreground="#FFB74D", font=("Consolas", 10, "bold"))
            raw.tag_config("INFO", foreground="#81C784")
            raw.tag_config("TIMESTAMP", foreground="#64B5F6")
            raw.tag_config("DEF", foreground="#E0E0E0")
        except Exception:
            pass

    # =========================================================================
    # NAVEGACIÓN Y CAMBIO DE VISTAS
    # =========================================================================

    def _al_cambiar_ventana(self, seleccion: str) -> None:
        """Conmuta dinámicamente el lienzo central entre las 3 vistas."""
        if seleccion == "Dashboard":
            self.vista_dashboard.grid()
            self.vista_analiticas.grid_remove()
            self.vista_registros.grid_remove()
        elif seleccion == "Analíticas":
            self.vista_dashboard.grid_remove()
            self.vista_analiticas.grid()
            self.vista_registros.grid_remove()
            self._actualizar_grafico_reactivo()
        elif seleccion == "Registros":
            self.vista_dashboard.grid_remove()
            self.vista_analiticas.grid_remove()
            self.vista_registros.grid()
            self._cargar_historial_lotes()
            self._actualizar_visor_logs()

    # =========================================================================
    # MÁQUINA DE ESTADOS FINITA (FSM) DE LA BOTONERA Y PROTECCIÓN ANTI-CORTE
    # =========================================================================

    def _verificar_corte_abrupto_al_arranque(self) -> None:
        """
        Protección anti-corte abrupto por Botón Payaso (Seta de Paro):
        Si al arrancar el sistema detecta que el estado previo era 'EN_MARCHA',
        bloquea la marcha, conmuta piloto a rojo (GPIO 18), registra alarma
        y exige pulsar Reset para purgar antes de operar.
        """
        if getattr(self.gestor_tiempo, "requiere_reset_por_corte", False):
            self.estado_operativo = "PARO"
            self.lbl_estado_maquina.configure(
                text="ALERTA: CORTE ABRUPTO", text_color=self.COLOR_ROJO_DEFECTO
            )
            self.btn_marcha.configure(state="disabled")
            self.btn_paro.configure(state="disabled")
            self.btn_reset.configure(state="normal", text="Reset (Purgar)", fg_color=self.COLOR_ROJO_DEFECTO)
            self.slider_trigger.configure(state="normal")

            if self.esp32_bridge:
                self.esp32_bridge.cambiar_piloto("RED")

            self.db_manager.registrar_log_local(
                "ALARM", "PARADA_ABRUPTA_DETECTADA: Sistema bloqueado hasta purga con Reset."
            )
        else:
            self._actualizar_estado_fsm("STANDBY")

    _verificar_estado_previo_maquina = _verificar_corte_abrupto_al_arranque

    def _actualizar_estado_fsm(self, nuevo_estado: str) -> None:
        """Aplica las transiciones de estado de la máquina operativa."""
        self.estado_operativo = nuevo_estado
        self.gestor_tiempo.actualizar_estado_operativo(nuevo_estado)

        if nuevo_estado == "STANDBY":
            self.lbl_estado_maquina.configure(text="ESTADO: STANDBY", text_color=self.COLOR_GRIS_SEC)
            self.btn_marcha.configure(state="normal", text="Marcha", fg_color=self.COLOR_VERDE_ULSA)
            self.btn_paro.configure(state="disabled")
            self.btn_reset.configure(state="disabled", text="Reset", fg_color=self.COLOR_AZUL_ACCION)
            self.slider_trigger.configure(state="normal")
            self.btn_aplicar_trigger.configure(state="normal")
            self.btn_cancelar_trigger.configure(state="normal")
            if self.esp32_bridge:
                self.esp32_bridge.cambiar_piloto("WHITE")

        elif nuevo_estado == "EN_MARCHA":
            self.lbl_estado_maquina.configure(text="ESTADO: EN MARCHA", text_color=self.COLOR_VERDE_ULSA)
            self.btn_marcha.configure(state="disabled", text="En Marcha")
            self.btn_paro.configure(state="normal")
            self.btn_reset.configure(state="disabled")
            # Inhibición estricta de configuración de trigger durante operación
            self.slider_trigger.configure(state="disabled")
            self.btn_aplicar_trigger.configure(state="disabled")
            self.btn_cancelar_trigger.configure(state="disabled")
            if self.esp32_bridge:
                self.esp32_bridge.control_banda(True)
                self.esp32_bridge.cambiar_piloto("GREEN")

        elif nuevo_estado == "PARO":
            self.lbl_estado_maquina.configure(text="ESTADO: PARO", text_color=self.COLOR_AMARILLO_ALERTA)
            self.btn_marcha.configure(state="normal", text="Reanudar", fg_color=self.COLOR_VERDE_ULSA)
            self.btn_paro.configure(state="disabled")
            self.btn_reset.configure(state="normal", text="Reset", fg_color=self.COLOR_AZUL_ACCION)
            self.slider_trigger.configure(state="normal")
            self.btn_aplicar_trigger.configure(state="normal")
            self.btn_cancelar_trigger.configure(state="normal")
            if self.esp32_bridge:
                self.esp32_bridge.control_banda(False)
                self.esp32_bridge.detener_todo()
                self.esp32_bridge.cambiar_piloto("YELLOW")

    def _al_pulsar_marcha(self) -> None:
        """Inicia o reanuda la clasificación mecatrónica activa."""
        if getattr(self.gestor_tiempo, "requiere_reset_por_corte", False):
            messagebox.showwarning(
                "Arranque Bloqueado",
                "Se detectó un apagado abrupto previo. Debe presionar Reset para purgar el sistema antes de iniciar.",
            )
            return

        if self.estado_operativo == "STANDBY":
            self.detector.iniciar_clasificacion()
            self.metricas.iniciar_sesion()
            self.gestor_lotes.iniciar_lote()
            self.db_manager.registrar_log_local("INFO", "Inicio de marcha en clasificadora.")
        elif self.estado_operativo == "PARO":
            self.detector.reanudar()
            self.metricas.iniciar_sesion()
            self.db_manager.registrar_log_local("INFO", "Reanudación de marcha en clasificadora.")

        self._actualizar_estado_fsm("EN_MARCHA")

    def _al_pulsar_paro(self) -> None:
        """Ejecuta un paro operacional deteniendo banda y clasificación."""
        if self.estado_operativo != "EN_MARCHA":
            return

        self.detector.pausar()
        self.metricas.pausar_sesion()
        self.db_manager.registrar_log_local("WARNING", "Paro operativo solicitado por operador.")
        self._actualizar_estado_fsm("PARO")

    def _al_pulsar_reset(self) -> None:
        """Purga el sistema, limpia alertas de corte y retorna a STANDBY."""
        if getattr(self.gestor_tiempo, "requiere_reset_por_corte", False):
            self.gestor_tiempo.reset_corte_abrupto()
            self.db_manager.registrar_log_local("INFO", "Purga de sistema completada tras corte abrupto.")

        self.detector.detener_clasificacion()
        self.metricas.pausar_sesion()
        self._actualizar_estado_fsm("STANDBY")

    # =========================================================================
    # CONTROL CINEMÁTICO DE TRIGGER Y MODAL DE CONFIRMACIÓN
    # =========================================================================

    def _al_mover_slider_trigger(self, valor: float) -> None:
        """
        Al mover el slider, calcula dinámicamente Y_trigger y dibuja una
        previsualización discontinua sobre el video sin alterar la línea real.
        """
        latencia_redondeada = round(float(valor) * 2.0) / 2.0
        _, y_prev = calcular_desplazamiento_cinematico(
            latencia_redondeada,
            belt_speed_m_s=self.detector.belt_speed_m_s,
            pixels_per_meter_y=self.detector.pixels_per_meter_y,
            y_nozzle_px=self.detector.y_nozzle_px,
        )
        self.lbl_val_trigger.configure(text=f"{latencia_redondeada:.1f} ms\n(Y={y_prev})")
        self.detector.previsualizar_latencia_actuador(latencia_redondeada)

    def _cancelar_trigger(self) -> None:
        """Restaura el slider al valor operativo real y descarta la previsualización."""
        lat_real = getattr(self.detector, "valvula_latencia_ms", 3.0)
        y_real = getattr(self.detector, "y_trigger", 501)
        self.slider_trigger.set(lat_real)
        self.lbl_val_trigger.configure(text=f"{lat_real:.1f} ms\n(Y={y_real})")
        self.detector.cancelar_previsualizacion_latencia()

    def _abrir_modal_confirmar_trigger(self) -> None:
        """Abre ventana modal táctil para confirmar el cambio de línea de disparo."""
        if self.estado_operativo == "EN_MARCHA":
            return

        val_slider = round(float(self.slider_trigger.get()) * 2.0) / 2.0
        _, y_calc = calcular_desplazamiento_cinematico(
            val_slider,
            belt_speed_m_s=self.detector.belt_speed_m_s,
            pixels_per_meter_y=self.detector.pixels_per_meter_y,
            y_nozzle_px=self.detector.y_nozzle_px,
        )

        if self.modal_trigger is not None and self.modal_trigger.winfo_exists():
            self.modal_trigger.lift()
            self.modal_trigger.focus_set()
        else:
            self.modal_trigger = VentanaConfirmacionTrigger(
                parent=self,
                nueva_latencia_ms=val_slider,
                nuevo_y_px=y_calc,
                callback_confirmar=self._aplicar_cambio_trigger,
            )

    def _aplicar_cambio_trigger(self, nueva_latencia_ms: float) -> None:
        """Aplica la nueva latencia al detector y persiste en JSON."""
        y_nuevo = self.detector.actualizar_latencia_actuador(nueva_latencia_ms)
        self.lbl_val_trigger.configure(text=f"{nueva_latencia_ms:.1f} ms\n(Y={y_nuevo})")
        self.db_manager.registrar_log_local(
            "INFO", f"Calibración de trigger actualizada: {nueva_latencia_ms:.1f} ms -> Y={y_nuevo} px"
        )
        messagebox.showinfo("Calibración Exitosa", f"Línea de disparo fijada en Y = {y_nuevo} px.")

    # =========================================================================
    # CONTROL DE INDICADORES VISUALES DE ELECTROVÁLVULAS (120 MS AFTER)
    # =========================================================================

    def activar_indicador_canal(self, canal: int) -> None:
        """
        Conmuta el indicador visual del canal a verde institucional (#197B30)
        durante 120 ms mediante after(), retornando automáticamente a gris pasivo.
        """
        if 0 <= canal < len(self.indicadores_canales):
            btn = self.indicadores_canales[canal]
            btn.configure(fg_color="#197B30", text_color="#FFFFFF")
            self.after(120, lambda b=btn: self._restablecer_indicador_canal(b))

    def _restablecer_indicador_canal(self, btn: ctk.CTkButton) -> None:
        try:
            if btn.winfo_exists():
                btn.configure(fg_color="#E0E0E0", text_color="#424242")
        except Exception:
            pass

    def _apagar_indicador_canal(self, canal: int) -> None:
        """Apaga forzadamente el indicador del canal dado."""
        if 0 <= canal < len(self.indicadores_canales):
            self._restablecer_indicador_canal(self.indicadores_canales[canal])

    def _al_recibir_respuesta_serial(self, linea: str) -> None:
        """Interpreta respuestas seriales del ESP32 para activar los pilotos visuales."""
        if linea.startswith("OK:"):
            canal_str = linea[3:].strip()
            if canal_str.isdigit():
                ch = int(canal_str)
                if threading.current_thread() is threading.main_thread():
                    self.activar_indicador_canal(ch)
                else:
                    self.after(0, lambda: self.activar_indicador_canal(ch))

    # =========================================================================
    # ALTERNANCIA DE CÁMARA (↕) Y RECONFIGURACIÓN DE FUENTES
    # =========================================================================

    def _alternar_vista_camara(self) -> None:
        """
        El botón ↕ alterna el lienzo visible entre la cámara superior (con carril
        y línea cinemática) y la inferior (reverso/ventral) sin detener la inferencia paralela.
        """
        if self.camara_vista_activa == "TOP":
            self.camara_vista_activa = "BOTTOM"
            self.lbl_camara_activa_badge.configure(
                text="CÁMARA INFERIOR (VENTRAL) | INSPECCIÓN DE REVERSO Y HENDIDURA",
                text_color="#81D4FA",
            )
        else:
            self.camara_vista_activa = "TOP"
            self.lbl_camara_activa_badge.configure(
                text="CÁMARA SUPERIOR (MAESTRO) | GUÍAS DE CARRIL Y DISPARO",
                text_color="#A5D6A7",
            )

    def _al_cambiar_posicion_camara(self, seleccion: str) -> None:
        """Invierte la asignación física de las cámaras (Top <-> Bottom) si se solicita."""
        es_invertida = "Invertida" in seleccion
        if es_invertida != self.detector.posicion_camara_invertida:
            nueva_top, nueva_bot = self.detector.alternar_posicion_camaras()
            self._fuente_top_actual = nueva_top
            self._fuente_bottom_actual = nueva_bot
            self.db_manager.registrar_log_local(
                "INFO", f"Posición de cámaras cambiada a: {seleccion} (Top: {nueva_top}, Bot: {nueva_bot})"
            )

    def _al_cambiar_modelo_dropdown(self, seleccion: str) -> None:
        """Sincroniza el cambio de modelo desde la barra superior."""
        es_13_clases = "13" in seleccion
        if es_13_clases != self.detector.es_modo_13clases:
            if hasattr(self.detector, "cambiar_modelo"):
                self.detector.cambiar_modelo(usar_13_clases=es_13_clases)
            self.gestor_lotes.configurar_modelo(
                modelo_13_clases=es_13_clases, modo_sahi=bool(self.switch_sahi.get())
            )
            if es_13_clases:
                self.switch_modelo.select()
                self.switch_modelo.configure(text="13 Clases")
            else:
                self.switch_modelo.deselect()
                self.switch_modelo.configure(text="Tri-clase")
            self._actualizar_grafico_reactivo()

    # Métodos y Handlers para retrocompatibilidad con tests existentes
    def _al_cambiar_camara_top(self, seleccion: str) -> None:
        nueva_top = self._parsear_fuente_texto(seleccion)
        anterior_top = self._fuente_top_actual
        actual_bot = self._fuente_bottom_actual

        if str(nueva_top) == str(actual_bot):
            nueva_bot = anterior_top
            self._fuente_bottom_actual = nueva_bot
            if hasattr(self, "combo_cam_bottom"):
                self.combo_cam_bottom.set(self._formatear_fuente_texto(nueva_bot))

        self._fuente_top_actual = nueva_top
        if hasattr(self, "combo_cam_top"):
            self.combo_cam_top.set(self._formatear_fuente_texto(nueva_top))
        self.detector.cambiar_fuentes_video(self._fuente_top_actual, self._fuente_bottom_actual)

    def _al_cambiar_camara_bottom(self, seleccion: str) -> None:
        nueva_bot = self._parsear_fuente_texto(seleccion)
        anterior_bot = self._fuente_bottom_actual
        actual_top = self._fuente_top_actual

        if str(nueva_bot) == str(actual_top):
            nueva_top = anterior_bot
            self._fuente_top_actual = nueva_top
            if hasattr(self, "combo_cam_top"):
                self.combo_cam_top.set(self._formatear_fuente_texto(nueva_top))

        self._fuente_bottom_actual = nueva_bot
        if hasattr(self, "combo_cam_bottom"):
            self.combo_cam_bottom.set(self._formatear_fuente_texto(nueva_bot))
        self.detector.cambiar_fuentes_video(self._fuente_top_actual, self._fuente_bottom_actual)

    @staticmethod
    def _parsear_fuente_texto(texto: str) -> Union[int, str]:
        s = str(texto).strip()
        if "Demo" in s or "Sintético" in s or "demo" in s.lower():
            return "demo"
        for digito in ("0", "1", "2"):
            if digito in s:
                return int(digito)
        return s

    @staticmethod
    def _formatear_fuente_texto(fuente: Union[int, str]) -> str:
        s = str(fuente).strip().lower()
        if s in ("demo", "simulado", "synthetic"):
            return "Demo / Sintético"
        return f"Cámara {fuente}"

    def _al_cambiar_switch_modelo(self) -> None:
        es_13_clases = bool(self.switch_modelo.get())
        if es_13_clases:
            self.switch_modelo.configure(text="13 Clases")
            if hasattr(self, "combo_modelo_hdr"):
                self.combo_modelo_hdr.set("13 Clases")
        else:
            self.switch_modelo.configure(text="Tri-clase")
            if hasattr(self, "combo_modelo_hdr"):
                self.combo_modelo_hdr.set("Tri-clase")
        if hasattr(self.detector, "cambiar_modelo"):
            self.detector.cambiar_modelo(usar_13_clases=es_13_clases)
        self.gestor_lotes.configurar_modelo(
            modelo_13_clases=es_13_clases, modo_sahi=bool(self.switch_sahi.get())
        )
        self._actualizar_grafico_reactivo()

    def _al_cambiar_switch_sahi(self) -> None:
        es_sahi = bool(self.switch_sahi.get())
        self.switch_sahi.configure(text=f"SAHI: {'ON' if es_sahi else 'OFF'}")
        es_13_clases = bool(self.switch_modelo.get())
        self.gestor_lotes.configurar_modelo(modelo_13_clases=es_13_clases, modo_sahi=es_sahi)

    # =========================================================================
    # REFRESH DE DATOS, HISTORIAL Y GRÁFICO REACTIVO
    # =========================================================================

    def _actualizar_grafico_reactivo(self) -> None:
        """
        Dibuja el gráfico de barras horizontales optimizado con los acrónimos
        cortos estandarizados para 13 clases y tri-clase.
        """
        if self.ax_reactivo is None or self.fig_reactiva is None:
            return

        self.ax_reactivo.clear()
        es_13_clases = self.detector.es_modo_13clases

        if es_13_clases:
            categorias = [
                "Arabica_Agrio",
                "Arabica_Brocado",
                "Arabica_Bueno",
                "Arabica_Cereza",
                "Arabica_Concha",
                "Arabica_Inmaduro",
                "Arabica_Negro",
                "Arabica_Quebrado",
                "Robusta_Brocado",
                "Robusta_Bueno",
                "Robusta_Cereza",
                "Robusta_Negro",
                "Robusta_Quebrado",
            ]
            etiquetas = [MAPA_ACRONIMOS_13.get(c, c) for c in categorias]
            valores = [self.gestor_lotes.conteo_crudo.get(c, 0) for c in categorias]
            colores = [self.COLORES_13_CLASES.get(c, "#757575") for c in categorias]
        else:
            categorias = [
                "Grano_Defecto",
                "Robusta_Bueno",
                "Arabica_Bueno",
            ]
            etiquetas = [MAPA_ACRONIMOS_TRI.get(c, c) for c in categorias]
            valores = [self.gestor_lotes.conteo_crudo.get(c, 0) for c in categorias]
            colores = [self.COLORES_TRI_CLASE.get(c, "#197B30") for c in categorias]

        self.ax_reactivo.set_facecolor("#FAFAFA")
        self.fig_reactiva.patch.set_facecolor("#FFFFFF")

        posiciones = range(len(categorias))
        barras = self.ax_reactivo.barh(posiciones, valores, color=colores, height=0.62)

        self.ax_reactivo.set_yticks(posiciones)
        self.ax_reactivo.set_yticklabels(etiquetas, fontsize=9, color="#4A3B32", weight="bold")
        self.ax_reactivo.xaxis.grid(True, linestyle="--", alpha=0.4, color="#CFD8DC")
        self.ax_reactivo.set_axisbelow(True)

        for spine in ["top", "right"]:
            self.ax_reactivo.spines[spine].set_visible(False)
        for spine in ["left", "bottom"]:
            self.ax_reactivo.spines[spine].set_color("#CFD8DC")

        max_val = max(valores) if valores and max(valores) > 0 else 5
        self.ax_reactivo.set_xlim(0, max_val * 1.25)
        self.ax_reactivo.tick_params(axis="x", labelsize=8, colors="#757575")

        try:
            self.ax_reactivo.bar_label(barras, padding=3, fontsize=8.5, color="#4A3B32", weight="bold")
        except Exception:
            pass

        self.fig_reactiva.tight_layout()
        if self.canvas_reactivo:
            self.canvas_reactivo.draw_idle()

    def _cargar_historial_lotes(self) -> None:
        """Carga y renderiza el historial de lotes en la tabla de VistaRegistros."""
        if not hasattr(self, "scroll_historial"):
            return

        filtro_mod = self.opt_filtro_modelo_hist.get()
        filtro_fec = self.seg_filtro_fecha_hist.get()
        lotes = self.db_manager.obtener_historial_lotes(
            filtro_modelo=filtro_mod if filtro_mod != "Todos" else None,
            filtro_fecha=filtro_fec,
            limite=150,
        )

        # Limpiar filas existentes (a partir de la fila 1 para preservar encabezados)
        for w in self.scroll_historial.grid_slaves():
            info = w.grid_info()
            if int(info.get("row", 0)) > 0:
                w.destroy()

        if not lotes:
            lbl_vacio = ctk.CTkLabel(
                self.scroll_historial,
                text="No hay registros históricos de lotes disponibles.",
                text_color="#9E9E9E",
                font=ctk.CTkFont(size=12),
            )
            lbl_vacio.grid(row=1, column=0, columnspan=6, pady=20)
            return

        for r_idx, item in enumerate(lotes, start=1):
            bg = "#FFFFFF" if r_idx % 2 == 0 else "#F5F5F5"
            valores = [
                item.get("fecha", ""),
                item.get("id_lote", ""),
                str(item.get("total_granos", 0)),
                str(item.get("total_sanos", 0)),
                f"{item.get('porcentaje_calidad', 100.0):.1f}%",
                f"{item.get('tiempo_min', 0.0):.1f}",
            ]
            for c_idx, val in enumerate(valores):
                lbl = ctk.CTkLabel(
                    self.scroll_historial,
                    text=val,
                    font=ctk.CTkFont(size=11),
                    text_color="#424242",
                    fg_color=bg,
                    corner_radius=4,
                    padx=6,
                    pady=4,
                )
                lbl.grid(row=r_idx, column=c_idx, padx=2, pady=2, sticky="ew")

    def _actualizar_visor_logs(self) -> None:
        """Carga registros de logs locales en el visor de VistaRegistros."""
        if not hasattr(self, "txt_logs"):
            return

        tipo_sel = self.opt_filtro_logs.get()
        fecha_sel = self.seg_filtro_fecha.get()
        logs = self.db_manager.obtener_logs_locales(
            tipo=tipo_sel if tipo_sel != "TODOS" else None,
            filtro_fecha=fecha_sel,
            limite=350,
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
        """Abre ventana independiente de logs."""
        if self._ventana_logs is not None and self._ventana_logs.winfo_exists():
            self._ventana_logs.lift()
            self._ventana_logs.focus_set()
        else:
            self._ventana_logs = VentanaLogsToplevel(self, self.db_manager)

    # =========================================================================
    # BUCLE NATIVO DE STREAMING DE VIDEO Y TELEMETRÍA (60 FPS)
    # =========================================================================

    def _bucle_actualizacion_frame(self) -> None:
        if not self._consumidor_activo:
            return

        try:
            # Consumir el fotograma más reciente de la cola
            payload = None
            try:
                while True:
                    payload = self.detector.cola_salida.get_nowait()
            except queue.Empty:
                pass

            if payload is not None:
                # 1. Seleccionar la vista de cámara elegida por el operador (↕)
                if self.camara_vista_activa == "BOTTOM" and "frame_bottom" in payload:
                    frame_bgr = payload["frame_bottom"]
                else:
                    frame_bgr = payload.get("frame_top", payload.get("frame_bgr"))

                # 2. Renderizar fotograma sobre el canvas
                if frame_bgr is not None:
                    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(rgb)
                    # Dimensionar adaptativamente preservando relación de aspecto
                    w_disp = max(400, min(760, self.lbl_video.winfo_width() or 640))
                    h_disp = max(300, min(600, self.lbl_video.winfo_height() or 580))
                    pil_img_resized = pil_img.resize((w_disp, h_disp), Image.Resampling.BILINEAR)

                    self._ctk_image_ref = ctk.CTkImage(
                        light_image=pil_img_resized,
                        dark_image=pil_img_resized,
                        size=(w_disp, h_disp),
                    )
                    self.lbl_video.configure(image=self._ctk_image_ref, text="")

                # 3. Actualizar Badges de FPS y Latencia
                fps = payload.get("fps", 30.0)
                lat = payload.get("latencia_ms", 0.0)
                self.badge_fps.configure(text=f"FPS: {fps:.1f}")
                self.badge_ms.configure(text=f"ms: {lat:.1f}")

                # 4. Actualizar métricas del lote
                if self.estado_operativo == "EN_MARCHA":
                    dets = payload.get("detecciones", [])
                    for d in dets:
                        nombre = d.get("nombre_clase", "")
                        es_def = d.get("es_defecto", False)
                        self.gestor_lotes.registrar_grano(nombre, es_defecto=es_def)
                        self.metricas.registrar_grano(nombre, es_defecto=es_def)

            # Refresco periódico de métricas (cada 500 ms)
            ahora = time.time()
            if ahora - self._ultimo_refresco_kpi >= 0.5:
                self._actualizar_metricas_ui()
                self._ultimo_refresco_kpi = ahora

        except Exception as e:
            print(f"[DashboardCustomTkinter] Error en bucle de frame: {e}")

        # Programar siguiente iteración
        if self._consumidor_activo:
            self._bucle_id = self.after(15, self._bucle_actualizacion_frame)

    def _actualizar_metricas_ui(self) -> None:
        """Actualiza las StatCards, balances y tiempo de uso."""
        # 1. Tiempo de uso
        en_marcha = self.estado_operativo == "EN_MARCHA"
        self.gestor_tiempo.tick(en_marcha)
        self.card_kpi_tiempo["valor"].configure(text=self.gestor_tiempo.obtener_tiempo_formateado())

        # 2. Granos y calidad
        total_g = self.gestor_lotes.total_granos if self.gestor_lotes.lote_activo else self.metricas.total_granos
        sanos_g = self.gestor_lotes.total_sanos if self.gestor_lotes.lote_activo else self.metricas.total_sanos
        def_g = self.gestor_lotes.total_defectuosos if self.gestor_lotes.lote_activo else self.metricas.total_defectuosos
        calidad = (sanos_g / total_g * 100.0) if total_g > 0 else 100.0

        self.card_kpi_granos["valor"].configure(text=f"{total_g} Granos")
        self.card_kpi_granos["sub"].configure(text=f"Calidad: {calidad:.1f}% ({sanos_g} Sanos)")

        # 3. Consumo y rendimiento
        consumo = self.gestor_lotes.obtener_consumo_kwh() if self.gestor_lotes.lote_activo else self.metricas.calcular_consumo_kwh()
        self.card_kpi_consumo["valor"].configure(text=f"{consumo:.4f} kWh")

        self.card_kpi_latencia["valor"].configure(text=f"{self.detector._fps_captura:.1f} FPS")
        self.card_kpi_latencia["sub"].configure(text=f"Latencia: {self.detector._latencia_inferencia_ms:.1f} ms")

        # 4. Contador de Lotes en Header
        stats_hist = self.db_manager.obtener_estadisticas_acumuladas()
        tot_lotes = stats_hist.get("total_lotes", 0)
        self.badge_lotes.configure(text=f"Lotes: {tot_lotes}")

        # 5. Estado BD en Header
        if self.db_manager.conectado_mongo:
            self.badge_db.configure(text="Base de Datos ●", fg_color="#E8F5E9", text_color=self.COLOR_VERDE_ULSA)
        else:
            self.badge_db.configure(text="Base de Datos ○", fg_color="#FFF8E1", text_color=self.COLOR_AMARILLO_ALERTA)

        # 6. Barras de balance
        if total_g > 0:
            ps = sanos_g / total_g
            pd = def_g / total_g
            self.lbl_sanos_val.configure(text=f"{sanos_g} ({ps * 100:.1f}%)")
            self.bar_sanos.set(ps)
            self.lbl_defectos_val.configure(text=f"{def_g} ({pd * 100:.1f}%)")
            self.bar_defectos.set(pd)
        else:
            self.lbl_sanos_val.configure(text="0 (100.0%)")
            self.bar_sanos.set(1.0)
            self.lbl_defectos_val.configure(text="0 (0.0%)")
            self.bar_defectos.set(0.0)

    def _crear_statcard_neumorfica(
        self,
        parent: ctk.CTkBaseClass,
        col: int,
        titulo: str,
        valor_ini: str,
        sub_ini: str,
    ) -> Dict[str, ctk.CTkLabel]:
        card = ctk.CTkFrame(
            parent,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_BORDE_NEUMORFICO,
        )
        card.grid(row=0, column=col, padx=5, pady=4, sticky="ew")

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
            font=ctk.CTkFont(size=19, weight="bold"),
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

    # =========================================================================
    # ACCIONES DE LOTES Y AUDITORÍA
    # =========================================================================

    def _finalizar_lote_manual(self) -> None:
        if not self.gestor_lotes.lote_activo:
            messagebox.showinfo("MOPPI", "No hay ningún lote activo en curso para finalizar.")
            return

        resumen = self.gestor_lotes.finalizar_lote(motivo="manual")
        if resumen:
            self._actualizar_metricas_ui()
            self._cargar_historial_lotes()
            messagebox.showinfo(
                "Lote Finalizado",
                f"Lote {resumen['id_lote']} cerrado exitosamente.\n"
                f"Granos: {resumen['total_granos']} | Calidad: {resumen['porcentaje_calidad']}%\n"
                f"Consumo: {resumen['consumo_kwh']} kWh",
            )

    def _al_lote_finalizado_auto(self, resumen: Dict[str, Any]) -> None:
        self._actualizar_metricas_ui()
        print(f"[MOPPI] Lote {resumen.get('id_lote')} auto-finalizado por inactividad.")

    def _sincronizar_pendientes_manual(self) -> None:
        def _tarea():
            count = self.db_manager.sincronizar_pendientes()
            self._actualizar_metricas_ui()
            self._cargar_historial_lotes()
            msg = f"Se sincronizaron {count} lotes con MongoDB Atlas." if count > 0 else "No hay lotes pendientes de sincronizar."
            messagebox.showinfo("Sincronización Cloud", msg)

        threading.Thread(target=_tarea, daemon=True).start()

    def _reiniciar_estadisticas(self) -> None:
        self.metricas.reiniciar()
        self._actualizar_metricas_ui()
        messagebox.showinfo("MOPPI", "Estadísticas reiniciadas correctamente.")

    # =========================================================================
    # CIERRE SEGURO DE LA APLICACIÓN
    # =========================================================================

    def _al_cerrar(self) -> None:
        """Cierre ordenado de hilos, base de datos y detector."""
        self._consumidor_activo = False
        if self._bucle_id is not None:
            try:
                self.after_cancel(self._bucle_id)
            except Exception:
                pass
            self._bucle_id = None

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

        if self.modal_trigger is not None:
            try:
                if self.modal_trigger.winfo_exists():
                    self.modal_trigger.destroy()
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

        try:
            self.destroy()
        except Exception:
            pass
