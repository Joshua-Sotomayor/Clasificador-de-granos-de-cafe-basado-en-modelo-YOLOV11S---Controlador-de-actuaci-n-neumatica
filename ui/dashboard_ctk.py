"""
=============================================================================
MOPPI - CLASIFICADOR ÓPTICO Y CINEMÁTICO DE GRANOS DE CAFÉ (HMI v1.7.0)
Finca Alvizua - Panel de Operación Industrial Táctil de 10.1" (1280x800 px)
Diseño Visual Ergonométrico bajo Norma ISO 9241-10
=============================================================================
"""

import os
import sys
import time
import json
import logging
import threading
import queue
from datetime import datetime, timedelta
from typing import Optional, Union, Tuple, Dict, List, Any, Callable
from dotenv import load_dotenv

# Cargar variables de entorno prioritarias desde .env
load_dotenv()

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import cv2
import numpy as np

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.ticker import MaxNLocator

from core.detector import YOLODetector, calcular_desplazamiento_cinematico
from core.metricas import GestorMetricas
from storage.database import DatabaseManager, GestorLotes, MongoManager
from storage.telemetria import GestorTiempoUso
from hardware.serial_bridge import ESP32Bridge

logger = logging.getLogger("MOPPI.UI")

# Configuración inicial del tema y color visual (Fondo claro institucional)
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("green")

# =====================================================================
# PALETA INSTITUCIONAL — Estilo tablero HMI industrial (ISO 9241-10)
# =====================================================================
VERDE          = "#1F7A3D"   # Verde institucional (acciones primarias / OK)
VERDE_HOVER    = "#145A2C"   # Verde oscuro para estados de hover
VERDE_CLARO    = "#57A773"   # Verde suave para acentos y bordes vivos
VERDE_LED      = "#35C759"   # Verde luminoso (luces indicadoras encendidas)
VERDE_TARJETA  = "#CEE4D4"   # Fondo verdoso suave para tarjeta destacada
ROJO_PARO      = "#C0392B"   # Rojo industrial para PARO (convención HMI)
ROJO_HOVER     = "#96281B"
AMBAR_RESET    = "#B8860B"   # Ámbar industrial para RESET (convención HMI)
AMBAR_HOVER    = "#8F6A08"

# Tonos oscurecidos para modo bloqueado (disabled) evidente
VERDE_BLOQUEADO     = "#0F3D1E"   # Verde oscuro apagado para botón M bloqueado
VERDE_BLOQUEADO_TXT = "#557A60"   # Texto tenue para botón M bloqueado
ROJO_BLOQUEADO      = "#4A1510"   # Rojo oscuro apagado para botón P bloqueado
ROJO_BLOQUEADO_TXT  = "#804A45"   # Texto tenue para botón P bloqueado
AMBAR_BLOQUEADO     = "#3E2D03"   # Ámbar oscuro apagado para botón R bloqueado
AMBAR_BLOQUEADO_TXT = "#7A6840"   # Texto tenue para botón R bloqueado

# Celeste para botón de Marcha en estado PARO (Reanudar)
CELESTE_REANUDAR    = "#1E88E5"   # Celeste industrial
CELESTE_HOVER       = "#1976D2"
CELESTE_BORDE       = "#64B5F6"

GRIS_FONDO     = "#E9ECE8"   # Fondo general (gris verdoso muy claro)
GRIS_PANEL     = "#F7F8F7"   # Superficie de paneles
GRIS_SUAVE     = "#DDE2DE"   # Controles secundarios / inactivos
GRIS_SUAVE_HOV = "#C9CFCB"

GRIS_BORDE     = "#B9C0BB"   # Divisores y bordes sutiles
GRIS_MEDIO     = "#7A827D"   # Textos secundarios / LED apagado
GRIS_TEXTO     = "#2B322D"   # Texto principal
GRIS_OSCURO    = "#333A35"   # Acero oscuro (visor / gráficas, estilo HMI)
GRIS_OSCURO_2  = "#434B45"   # Relieve interno del visor

TEXTO_CLARO    = "#E8EDE9"   # Texto claro sobre superficies oscuras

# Aliases de compatibilidad con versiones anteriores del dashboard
COLOR_FONDO_APP        = GRIS_FONDO
COLOR_VERDE_ULSA       = VERDE
COLOR_VERDE_HOVER      = VERDE_HOVER
COLOR_ROJO_DEFECTO     = ROJO_PARO
COLOR_AMARILLO_ALERTA  = AMBAR_RESET
COLOR_AZUL_ACCION      = AMBAR_RESET
COLOR_GRIS_SEC         = GRIS_MEDIO
COLOR_BORDE_NEUMORFICO = GRIS_BORDE

# Dimensiones base táctiles
HMI_WIDTH: int = int(os.getenv("HMI_WIDTH", "1280"))
HMI_HEIGHT: int = int(os.getenv("HMI_HEIGHT", "800"))
HMI_FULLSCREEN: bool = os.getenv("HMI_FULLSCREEN", "False").lower() in ("true", "1", "yes")

# Mapeo estandarizado de acrónimos estructurados para la gráfica (Finca Alvizua)
ACRONIMOS_13 = {
    "Arabica_Agrio": "A_AGR",
    "Arabica_Brocado": "A_BRO",
    "Arabica_Bueno": "A_BUE",
    "Arabica_Cereza": "A_CER",
    "Arabica_Concha": "A_CON",
    "Arabica_Inmaduro": "A_INM",
    "Arabica_Negro": "A_NEG",
    "Arabica_Quebrado": "A_QUE",
    "Robusta_Brocado": "R_BRO",
    "Robusta_Bueno": "R_BUE",
    "Robusta_Cereza": "R_CER",
    "Robusta_Negro": "R_NEG",
    "Robusta_Quebrado": "R_QUE",
}
ORDEN_13 = [
    "A_BUE", "R_BUE", "A_NEG", "R_NEG", "A_BRO", "R_BRO",
    "A_QUE", "R_QUE", "A_AGR", "A_INM", "A_CON", "A_CER", "R_CER"
]

ACRONIMOS_TRI = {
    "Arabica_Bueno": "A_BUE",
    "Robusta_Bueno": "R_BUE",
    "Grano_Defecto": "G_DEF",
}
ORDEN_TRI = ["A_BUE", "R_BUE", "G_DEF"]


# =========================================================================
# MODAL DE CONFIRMACIÓN DE TRIGGER
# =========================================================================

class VentanaConfirmacionTrigger(ctk.CTkToplevel):
    """
    Modal táctil centrado para confirmar el cambio de posición de la línea de disparo.
    Botones sobredimensionados (>= 50 px) optimizados para dedos del operario (ISO 9241-10).
    """

    def __init__(
        self,
        parent: "DashboardCustomTkinter",
        nueva_latencia_ms: float = 3.0,
        nuevo_y_px: int = 501,
        porcentaje_slider: int = 50,
        callback_confirmar: Any = None,
        latencia_ms: Optional[float] = None,
        y_calculado_px: Optional[int] = None,
        on_confirmar: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.nueva_latencia_ms = nueva_latencia_ms if latencia_ms is None else latencia_ms
        self.nuevo_y_px = nuevo_y_px if y_calculado_px is None else y_calculado_px
        self.porcentaje_slider = porcentaje_slider
        self.callback_confirmar = callback_confirmar or on_confirmar
        self.lbl_mensaje: Optional[ctk.CTkLabel] = None

        self.title("Confirmación de Calibración | MOPPI")
        self.resizable(False, False)
        self.configure(fg_color=GRIS_PANEL)

        ancho = 580
        alto = 360
        self.geometry(f"{ancho}x{alto}")
        try:
            self.update_idletasks()
            x = parent.winfo_x() + (parent.winfo_width() - ancho) // 2
            y = parent.winfo_y() + (parent.winfo_height() - alto) // 2
            self.geometry(f"{ancho}x{alto}+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self.transient(parent)
        self.grab_set()

        self._construir_ui()

    def _construir_ui(self) -> None:
        lbl_icono = ctk.CTkLabel(
            self,
            text="⚡",
            font=("Arial", 46),
            text_color=AMBAR_RESET,
        )
        lbl_icono.pack(pady=(20, 6))

        lbl_titulo = ctk.CTkLabel(
            self,
            text="¿Confirmar Calibración de Trigger?",
            font=("Arial", 20, "bold"),
            text_color=GRIS_TEXTO,
        )
        lbl_titulo.pack(pady=(0, 10))

        lbl_desc = ctk.CTkLabel(
            self,
            text=(
                f"Posición Trigger: Y = {self.nuevo_y_px} px ({self.porcentaje_slider}%)\n"
                f"Latencia estimada: {self.nueva_latencia_ms:.1f} ms\n\n"
                "La calibración se guardará de forma persistente."
            ),
            font=("Arial", 16),
            text_color=GRIS_TEXTO,
            justify="center",
        )
        lbl_desc.pack(pady=(0, 24))
        self.lbl_mensaje = lbl_desc

        frame_botones = ctk.CTkFrame(self, fg_color="transparent")
        frame_botones.pack(fill="x", padx=30, pady=(0, 20))
        frame_botones.grid_columnconfigure((0, 1), weight=1)

        btn_cancelar = ctk.CTkButton(
            frame_botones,
            text="Cancelar",
            command=self.destroy,
            height=56,
            fg_color=VERDE,
            hover_color=VERDE_HOVER,
            text_color="white",
            font=("Arial", 18, "bold"),
            corner_radius=28,
        )
        btn_cancelar.grid(row=0, column=0, padx=(0, 12), sticky="ew")

        btn_confirmar = ctk.CTkButton(
            frame_botones,
            text="Confirmar",
            command=self._al_confirmar,
            height=56,
            fg_color=AMBAR_RESET,
            hover_color=AMBAR_HOVER,
            text_color="white",
            font=("Arial", 18, "bold"),
            corner_radius=28,
        )
        btn_confirmar.grid(row=0, column=1, padx=(12, 0), sticky="ew")

    def _al_confirmar(self) -> None:
        self.destroy()
        if self.callback_confirmar:
            try:
                self.callback_confirmar(self.nueva_latencia_ms, self.nuevo_y_px)
            except TypeError:
                try:
                    self.callback_confirmar(self.nueva_latencia_ms)
                except TypeError:
                    self.callback_confirmar()


# =========================================================================
# MODAL DE ADVERTENCIA DE CÁMARAS (AL PULSAR MARCHA)
# =========================================================================

class VentanaAdvertenciaCamaras(ctk.CTkToplevel):
    """
    Modal de advertencia centrado de alta visibilidad que alerta al operador
    antes de iniciar la marcha si una o ambas cámaras de inspección no están dando video.
    """

    def __init__(
        self,
        parent: "DashboardCustomTkinter",
        estado_camaras: Dict[str, Any],
        on_continuar: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.estado_camaras = estado_camaras
        self.callback_continuar = on_continuar

        self.title("Alerta de Cámaras | MOPPI")
        self.resizable(False, False)
        self.configure(fg_color=GRIS_PANEL)

        ancho = 600
        alto = 380
        self.geometry(f"{ancho}x{alto}")
        try:
            self.update_idletasks()
            x = parent.winfo_x() + (parent.winfo_width() - ancho) // 2
            y = parent.winfo_y() + (parent.winfo_height() - alto) // 2
            self.geometry(f"{ancho}x{alto}+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        self.transient(parent)
        self.grab_set()

        self._construir_ui()

    def _construir_ui(self) -> None:
        ninguna = self.estado_camaras.get("ninguna_ok", False)
        top_ok = self.estado_camaras.get("top_ok", False)
        bottom_ok = self.estado_camaras.get("bottom_ok", False)

        lbl_icono = ctk.CTkLabel(
            self,
            text="⚠️",
            font=("Arial", 48),
            text_color=AMBAR_RESET,
        )
        lbl_icono.pack(pady=(22, 6))

        if ninguna:
            titulo = "ADVERTENCIA: CÁMARAS NO DETECTADAS"
            desc = (
                "No se ha detectado ninguna cámara transmitiendo video en vivo.\n\n"
                "El sistema no podrá clasificar granos físicos sin cámaras ópticas.\n"
                "¿Desea iniciar el proceso en modo simulación de todos modos?"
            )
        elif not top_ok:
            titulo = "ADVERTENCIA: CÁMARA SUPERIOR NO DISPONIBLE"
            desc = (
                "La CÁMARA SUPERIOR (Maestro / Control de disparo) no transmite video.\n\n"
                "La sincronización de eyección neumática no tendrá referencia dorsal.\n"
                "¿Desea iniciar el proceso de todos modos?"
            )
        else:
            titulo = "ADVERTENCIA: CÁMARA INFERIOR NO DISPONIBLE"
            desc = (
                "La CÁMARA INFERIOR (Esclavo / Inspección ventral) no transmite video.\n\n"
                "La inspección de defectos se realizará únicamente sobre la cara dorsal.\n"
                "¿Desea iniciar el proceso de todos modos?"
            )

        lbl_titulo = ctk.CTkLabel(
            self,
            text=titulo,
            font=("Arial", 19, "bold"),
            text_color=GRIS_TEXTO,
        )
        lbl_titulo.pack(pady=(0, 10))

        lbl_desc = ctk.CTkLabel(
            self,
            text=desc,
            font=("Arial", 15),
            text_color=GRIS_TEXTO,
            justify="center",
        )
        lbl_desc.pack(pady=(0, 24), padx=20)

        frame_botones = ctk.CTkFrame(self, fg_color="transparent")
        frame_botones.pack(fill="x", padx=30, pady=(0, 20))
        frame_botones.grid_columnconfigure((0, 1), weight=1)

        self.btn_cancelar = ctk.CTkButton(
            frame_botones,
            text="Cancelar",
            command=self.destroy,
            height=56,
            fg_color=VERDE,
            hover_color=VERDE_HOVER,
            text_color="white",
            font=("Arial", 18, "bold"),
            corner_radius=28,
        )
        self.btn_cancelar.grid(row=0, column=0, padx=(0, 12), sticky="ew")

        self.btn_continuar = ctk.CTkButton(
            frame_botones,
            text="Continuar",
            command=self._al_continuar,
            height=56,
            fg_color=AMBAR_RESET,
            hover_color=AMBAR_HOVER,
            text_color="white",
            font=("Arial", 18, "bold"),
            corner_radius=28,
        )
        self.btn_continuar.grid(row=0, column=1, padx=(12, 0), sticky="ew")

    def _al_continuar(self) -> None:
        self.destroy()
        if self.callback_continuar:
            self.callback_continuar()


# =========================================================================
# VENTANA FLOTANTE DE LOGS (COMPATIBILIDAD CON TESTS)
# =========================================================================

class VentanaLogsToplevel(ctk.CTkToplevel):
    def __init__(self, parent: "DashboardCustomTkinter", db_manager: DatabaseManager) -> None:
        super().__init__(parent)
        self.db_manager = db_manager
        self.title("Registro de Auditoría Local | MOPPI")
        self.geometry("720x480")
        self.configure(fg_color=GRIS_PANEL)
        self.transient(parent)

        self.txt_logs = ctk.CTkTextbox(
            self,
            fg_color=GRIS_OSCURO,
            text_color=VERDE_LED,
            font=("Consolas", 12),
            corner_radius=10,
        )
        self.txt_logs.pack(fill="both", expand=True, padx=16, pady=16)


# =========================================================================
# APLICACIÓN PRINCIPAL DEL HMI PRODUCTIVO (DASHBOARDOBJECT)
# =========================================================================

class DashboardCustomTkinter(ctk.CTk):
    """
    Controlador central del HMI MOPPI con visualización integrada de HMI.py,
    control de máquina de estados de botonera (M/P/R), compensación cinemática
    y recuperación anti-corte abrupto de energía.
    """

    def __init__(
        self,
        detector: YOLODetector,
        metricas: GestorMetricas,
        db_manager: Optional[Union[DatabaseManager, MongoManager]] = None,
        gestor_lotes: Optional[GestorLotes] = None,
        esp32_bridge: Optional[ESP32Bridge] = None,
        auto_iniciar_camara: bool = True,
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
            timeout_inactividad_seg=int(os.getenv("LOT_TIMEOUT_SECONDS", "120")),
            callback_lote_finalizado=self._al_lote_finalizado_auto,
        )

        # Telemetría de horas de uso y persistencia anti-corte
        self.gestor_tiempo = GestorTiempoUso(
            ruta_archivo="storage/estado_maquina.json",
            potencia_nominal_kw=float(os.getenv("HARDWARE_POWER_KW", "0.5")),
        )

        # Enlace con callback serial del ESP32 para respuesta de canales
        if self.esp32_bridge is not None:
            self.esp32_bridge.callback_respuesta = self._al_recibir_respuesta_serial

        # Variables de estado interno
        self.estado_operativo: str = "STANDBY"
        self.camara_vista_activa: str = "TOP"  # "TOP" (Maestro) o "BOTTOM" (Esclavo)
        self._fuente_top_actual: Union[int, str] = self.detector.fuente_video_top
        self._fuente_bottom_actual: Union[int, str] = self.detector.fuente_video_bottom
        self._latencia_guardada_ms: float = getattr(self.detector, "valvula_latencia_ms", 3.0)
        self._y_trigger_guardado_px: int = getattr(self.detector, "y_trigger", 501)
        self._latencia_preview_ms: float = self._latencia_guardada_ms
        self._porcentaje_slider_actual: int = 50
        self._ultimo_tiempo_frame = time.time()
        self._fps_actual: float = 0.0
        self._latencia_inferencia_actual: float = 0.0
        self._ventana_logs: Optional[VentanaLogsToplevel] = None
        self._modal_trigger: Optional[VentanaConfirmacionTrigger] = None

        # Configuración de ventana
        self.title("MOPPI - Panel de Control Industrial")
        self.geometry(f"{HMI_WIDTH}x{HMI_HEIGHT}")
        self.minsize(1024, 600)
        self.configure(fg_color=GRIS_FONDO)

        # Modo Kiosk en pantalla completa si está configurado
        self._pantalla_completa = HMI_FULLSCREEN
        if self._pantalla_completa:
            try:
                self.attributes("-fullscreen", True)
            except Exception:
                pass
        self.bind("<Escape>", self._alternar_pantalla_completa)
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

        # Pesos de la cuadrícula principal
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Construcción visual de HMI.py
        self._crear_barra_superior()
        self._crear_pagina_dashboard()
        self._crear_pagina_analiticas()
        self._crear_pagina_registros()

        # Mapas para el cambio dinámico de pestañas
        self._paginas = {
            "Dashboard": self.pagina_dashboard,
            "Analíticas": self.pagina_analiticas,
            "Registros": self.pagina_registros,
        }
        self._barras_izq = {
            "Dashboard": self.barra_izq_dashboard,
            "Analíticas": self.barra_izq_analiticas,
            "Registros": self.barra_izq_registros,
        }

        # Conectar las pestañas con el cambio de ventana
        self.pestañas.configure(command=self.cambiar_pagina)
        self.cambiar_pagina("Dashboard")

        # Configurar Aliases requeridos por retrocompatibilidad con tests existentes
        self._configurar_aliases_retrocompatibilidad()

        # Verificar si hubo corte abrupto previo para aplicar BLOQUEO_SEGURIDAD
        self._verificar_corte_abrupto_al_arranque()

        # Iniciar hilos de captura continua en el detector si no están ya ejecutando
        if auto_iniciar_camara and hasattr(self.detector, "iniciar") and not getattr(self.detector, "_ejecutando", False):
            try:
                self.detector.iniciar()
            except Exception as e:
                logger.warning(f"Error al iniciar captura del detector: {e}")

        # Iniciar bucle de actualización visual de video
        self._bucle_video_activo = True
        self._id_after_bucle = self.after(30, self._bucle_actualizacion_video)

        # Iniciar bucle de actualización periódica de analíticas (1 Hz)
        self._bucle_analiticas_activo = True
        self._id_after_analiticas = self.after(1000, self._bucle_actualizacion_analiticas)

    # =========================================================================
    # BARRA SUPERIOR CONTEXTUAL DINÁMICA
    # =========================================================================

    def _crear_barra_superior(self) -> None:
        self.pestañas = ctk.CTkSegmentedButton(
            self,
            values=["Dashboard", "Analíticas", "Registros"],
            fg_color=GRIS_SUAVE,
            unselected_color=GRIS_SUAVE,
            unselected_hover_color=GRIS_SUAVE_HOV,
            selected_color=VERDE,
            selected_hover_color=VERDE_HOVER,
            text_color=GRIS_TEXTO,
            text_color_disabled=GRIS_MEDIO,
            height=80,
            width=580,
            font=("Arial", 24),
            corner_radius=40,
        )
        self.pestañas.set("Dashboard")
        self.pestañas.grid(row=0, column=1, sticky="ne", padx=(10, 20), pady=15)

        self.config_btn_superior = {
            "fg_color": VERDE,
            "hover_color": VERDE_HOVER,
            "text_color": "white",
            "corner_radius": 40,
            "border_width": 2,
            "border_color": VERDE_CLARO,
            "height": 80,
            "font": ("Arial", 24, "bold"),
        }

        self.config_opt_superior = {
            "fg_color": VERDE,
            "button_color": VERDE,
            "button_hover_color": VERDE_HOVER,
            "text_color": "white",
            "corner_radius": 40,
            "height": 80,
            "font": ("Arial", 24, "bold"),
            "dropdown_font": ("Arial", 20),
        }

        self._crear_bloque_izq_dashboard()
        self._crear_bloque_izq_analiticas()
        self._crear_bloque_izq_registros()

    def _crear_bloque_izq_dashboard(self) -> None:
        self.barra_izq_dashboard = ctk.CTkFrame(self, fg_color="transparent")
        self.barra_izq_dashboard.grid(row=0, column=0, sticky="new", padx=(20, 10), pady=15)

        self.barra_izq_dashboard.grid_columnconfigure(0, weight=1)
        self.barra_izq_dashboard.grid_columnconfigure(1, weight=1)
        self.barra_izq_dashboard.grid_columnconfigure(2, weight=1)

        # 1. Menú Cambiar Posición
        self.btn_posicion = ctk.CTkOptionMenu(
            self.barra_izq_dashboard,
            values=["Posición Normal", "Posición Invertida"],
            command=self._al_cambiar_posicion_camaras,
            width=230,
            **self.config_opt_superior,
        )
        self.btn_posicion.set("Cambiar Posición")
        self.btn_posicion.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        # 2. Selector Modelos en Dashboard
        self.btn_modelos_dash = ctk.CTkOptionMenu(
            self.barra_izq_dashboard,
            values=["Tri-clase", "13 Clases", "Tri-clase + SAHI", "13 Clases + SAHI"],
            command=self._al_conmutar_modelo,
            width=210,
            **self.config_opt_superior,
        )
        self.btn_modelos_dash.set("Modelos")
        self.btn_modelos_dash.grid(row=0, column=1, sticky="ew", padx=10)

        # 3. Botón ↕ Alternar Vista de Cámara
        self.btn_orden = ctk.CTkButton(
            self.barra_izq_dashboard,
            text="↕",
            command=self._al_pulsar_alternar_camara,
            width=100,
            **self.config_btn_superior,
        )
        self.btn_orden.grid(row=0, column=2, sticky="ew", padx=(10, 20))

    def _crear_bloque_izq_analiticas(self) -> None:
        self.barra_izq_analiticas = ctk.CTkFrame(self, fg_color="transparent")
        self.barra_izq_analiticas.grid(row=0, column=0, sticky="new", padx=(20, 10), pady=15)

        self.barra_izq_analiticas.grid_columnconfigure(0, weight=1)
        self.barra_izq_analiticas.grid_columnconfigure(1, weight=1)
        self.barra_izq_analiticas.grid_columnconfigure(2, weight=1)

        config_pildora = {
            "fg_color": GRIS_SUAVE,
            "corner_radius": 40,
            "border_width": 2,
            "border_color": GRIS_BORDE,
            "height": 80,
        }

        # 1. Píldora Base de Datos
        pill_db = ctk.CTkFrame(self.barra_izq_analiticas, **config_pildora, width=250)
        pill_db.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        pill_db.pack_propagate(False)

        inner_db = ctk.CTkFrame(pill_db, fg_color="transparent")
        inner_db.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            inner_db, text="Base de Datos", font=("Arial", 24), text_color=GRIS_TEXTO
        ).pack(side="left", padx=(0, 10))

        color_led = VERDE_LED if getattr(self.db_manager, "esta_conectado_mongo", False) else GRIS_MEDIO
        self.led_mongo = ctk.CTkFrame(
            inner_db, width=34, height=34, corner_radius=17, fg_color=color_led
        )
        self.led_mongo.pack(side="left")

        # 2. Contador de Lotes
        pill_lotes = ctk.CTkFrame(self.barra_izq_analiticas, **config_pildora)
        pill_lotes.grid(row=0, column=1, sticky="ew", padx=10)
        pill_lotes.pack_propagate(False)

        self.lbl_lotes = ctk.CTkLabel(
            pill_lotes, text="Lotes:  ---", font=("Arial", 24), text_color=GRIS_TEXTO
        )
        self.lbl_lotes.place(relx=0.5, rely=0.5, anchor="center")

        # 3. Selector Modelos en Analíticas
        self.btn_modelos_analiticas = ctk.CTkOptionMenu(
            self.barra_izq_analiticas,
            values=["Tri-clase", "13 Clases", "Tri-clase + SAHI", "13 Clases + SAHI"],
            command=self._al_conmutar_modelo,
            width=210,
            **self.config_opt_superior,
        )
        self.btn_modelos_analiticas.set("Modelos")
        self.btn_modelos_analiticas.grid(row=0, column=2, sticky="ew", padx=(10, 20))

    def _crear_bloque_izq_registros(self) -> None:
        self.barra_izq_registros = ctk.CTkFrame(self, fg_color="transparent")
        self.barra_izq_registros.grid(row=0, column=0, sticky="new", padx=(20, 10), pady=15)

        self.barra_izq_registros.grid_columnconfigure(0, weight=1)
        self.barra_izq_registros.grid_columnconfigure(1, weight=1)
        self.barra_izq_registros.grid_columnconfigure(2, weight=1)

        config_pildora = {
            "fg_color": GRIS_SUAVE,
            "corner_radius": 40,
            "border_width": 2,
            "border_color": GRIS_BORDE,
            "height": 80,
        }

        # 1. Píldora Base de Datos (Registros)
        pill_db = ctk.CTkFrame(self.barra_izq_registros, **config_pildora, width=250)
        pill_db.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        pill_db.pack_propagate(False)

        inner_db = ctk.CTkFrame(pill_db, fg_color="transparent")
        inner_db.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            inner_db, text="Base de Datos", font=("Arial", 24), text_color=GRIS_TEXTO
        ).pack(side="left", padx=(0, 10))

        color_led = VERDE_LED if getattr(self.db_manager, "esta_conectado_mongo", False) else GRIS_MEDIO
        self.led_mongo_registros = ctk.CTkFrame(
            inner_db, width=34, height=34, corner_radius=17, fg_color=color_led
        )
        self.led_mongo_registros.pack(side="left")

        # 2. Contador de Lotes (Registros)
        pill_lotes = ctk.CTkFrame(self.barra_izq_registros, **config_pildora)
        pill_lotes.grid(row=0, column=1, sticky="ew", padx=(10, 10))
        pill_lotes.pack_propagate(False)

        self.lbl_lotes_registros = ctk.CTkLabel(
            pill_lotes, text="Lotes:  ---", font=("Arial", 24), text_color=GRIS_TEXTO
        )
        self.lbl_lotes_registros.place(relx=0.5, rely=0.5, anchor="center")

    def cambiar_pagina(self, nombre: str) -> None:
        self._pagina_actual = nombre
        for pagina in self._paginas.values():
            pagina.grid_remove()
        for barra in self._barras_izq.values():
            barra.grid_remove()

        if nombre in self._paginas:
            self._paginas[nombre].grid()
        if nombre in self._barras_izq:
            self._barras_izq[nombre].grid()

        for nombre_btn, boton in self.pestañas._buttons_dict.items():
            if nombre_btn == nombre:
                boton.configure(font=("Arial", 24, "underline"), text_color="white")
            else:
                boton.configure(font=("Arial", 24), text_color=GRIS_TEXTO)

        # Actualizar datos si se entra a analíticas o registros
        self._actualizar_indicador_bd_y_lotes()
        if nombre == "Analíticas":
            self._actualizar_tarjetas_estadisticas()
            self._actualizar_grafico_reactivo()
        elif nombre == "Registros":
            self._poblar_tabla_historial()
            self._cargar_consola_logs()

    # =========================================================================
    # VISTA 1: DASHBOARD (Operación en Vivo, Botonería y Trigger)
    # =========================================================================

    def _crear_pagina_dashboard(self) -> None:
        self.pagina_dashboard = ctk.CTkFrame(self, fg_color="transparent")
        self.pagina_dashboard.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.pagina_dashboard.grid_columnconfigure(0, weight=0)
        self.pagina_dashboard.grid_columnconfigure(1, weight=1)
        self.pagina_dashboard.grid_rowconfigure(0, weight=1)

        self._crear_area_visualizador()
        self._crear_panel_control()

    def _crear_area_visualizador(self) -> None:
        self.frame_grafico = ctk.CTkFrame(
            self.pagina_dashboard,
            fg_color=GRIS_OSCURO,
            corner_radius=15,
            border_width=2,
            border_color=VERDE_CLARO,
            width=640,
            height=640,
        )
        self.frame_grafico.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=(0, 20))
        self.frame_grafico.grid_propagate(False)
        self.frame_grafico.pack_propagate(False)

        # Canvas para renderizado de stream OpenCV
        self.lbl_video_display = tk.Label(self.frame_grafico, bg=GRIS_OSCURO)
        self.lbl_video_display.place(x=0, y=0, width=640, height=640)

        # Insignias de telemetría de video
        config_insignia = {
            "fg_color": GRIS_OSCURO_2,
            "text_color": VERDE_LED,
            "corner_radius": 5,
            "width": 90,
            "height": 30,
            "font": ("Consolas", 16, "bold"),
        }
        self.lbl_ms = ctk.CTkLabel(self.frame_grafico, text="ms:  --", **config_insignia)
        self.lbl_ms.place(relx=0.74, rely=0.03, anchor="ne")

        self.lbl_fps = ctk.CTkLabel(self.frame_grafico, text="FPS: --", **config_insignia)
        self.lbl_fps.place(relx=0.96, rely=0.03, anchor="ne")

        self.lbl_camara_activa_badge = ctk.CTkLabel(
            self.frame_grafico,
            text="CÁMARA SUPERIOR (MAESTRO) | CONTROL DE DISPARO",
            font=("Arial", 11, "bold"),
            fg_color=GRIS_OSCURO_2,
            text_color=VERDE_CLARO,
            corner_radius=5,
            height=24,
        )
        self.lbl_camara_activa_badge.place(relx=0.04, rely=0.03, anchor="nw")

    def _crear_panel_control(self) -> None:
        panel_derecho = ctk.CTkFrame(
            self.pagina_dashboard,
            fg_color=GRIS_PANEL,
            corner_radius=15,
            border_width=1,
            border_color=GRIS_BORDE,
        )
        panel_derecho.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=(0, 20))

        panel_derecho.grid_columnconfigure(0, weight=1)
        panel_derecho.grid_columnconfigure(1, weight=1)
        panel_derecho.grid_columnconfigure(2, weight=1)
        panel_derecho.grid_rowconfigure(1, weight=1)

        # ----------------------------------------------------
        # COLUMNA 1: BOTONERÍA (M, P, R)
        # ----------------------------------------------------
        col_botoneria = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        col_botoneria.grid(row=1, column=0, sticky="nsew", pady=10)

        ctk.CTkLabel(
            col_botoneria, text="BOTONERÍA", font=("Arial", 24, "bold"), text_color=GRIS_TEXTO
        ).pack(pady=(10, 20))

        config_marcha = {
            "fg_color": VERDE,
            "hover_color": VERDE_HOVER,
            "text_color": "white",
            "border_width": 2,
            "border_color": VERDE_HOVER,
        }
        config_paro = {
            "fg_color": ROJO_PARO,
            "hover_color": ROJO_HOVER,
            "text_color": "white",
            "border_width": 2,
            "border_color": ROJO_HOVER,
        }
        config_reset = {
            "fg_color": AMBAR_RESET,
            "hover_color": AMBAR_HOVER,
            "text_color": "white",
            "border_width": 2,
            "border_color": AMBAR_HOVER,
        }

        # Botón M (Marcha)
        self.btn_marcha = ctk.CTkButton(
            col_botoneria,
            text="M",
            font=("Arial", 28, "bold"),
            width=140,
            height=140,
            corner_radius=70,
            command=self._al_pulsar_marcha,
            **config_marcha,
        )
        self.btn_marcha.pack(pady=10)

        # Botón P (Paro)
        self.btn_paro = ctk.CTkButton(
            col_botoneria,
            text="P",
            font=("Arial", 28, "bold"),
            width=140,
            height=140,
            corner_radius=70,
            command=self._al_pulsar_paro,
            **config_paro,
        )
        self.btn_paro.pack(pady=20)

        # Botón R (Reset)
        self.btn_reset = ctk.CTkButton(
            col_botoneria,
            text="R",
            font=("Arial", 28, "bold"),
            width=140,
            height=140,
            corner_radius=70,
            command=self._al_pulsar_reset,
            **config_reset,
        )
        self.btn_reset.pack(pady=10)

        # Línea divisoria derecha
        div_intermedio = ctk.CTkFrame(panel_derecho, width=2, fg_color=GRIS_BORDE)
        div_intermedio.grid(row=1, column=0, sticky="nse", pady=20)

        # ----------------------------------------------------
        # COLUMNA 2: CANALES (0, 1, 2, 3)
        # ----------------------------------------------------
        div_izq = ctk.CTkFrame(panel_derecho, width=2, fg_color=GRIS_BORDE)
        div_izq.grid(row=1, column=1, sticky="nsw", pady=20)

        col_canales = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        col_canales.grid(row=1, column=1, sticky="nsew", pady=10)

        ctk.CTkLabel(
            col_canales, text="CANALES", font=("Arial", 24, "bold"), text_color=GRIS_TEXTO
        ).pack(side="top", pady=(10, 20))

        frame_grid_canales = ctk.CTkFrame(col_canales, fg_color="transparent")
        frame_grid_canales.pack(side="top", fill="both", expand=True)

        frame_grid_canales.grid_columnconfigure(0, weight=1)
        for i in range(4):
            frame_grid_canales.grid_rowconfigure(i, weight=2)

        config_luces = {
            "fg_color": GRIS_SUAVE,
            "text_color": GRIS_MEDIO,
            "border_width": 2,
            "border_color": VERDE_CLARO,
            "hover": False,
            "cursor": "arrow",
            "width": 80,
            "height": 80,
            "corner_radius": 40,
            "font": ("Arial", 24, "bold"),
        }

        self.luces_canales: List[ctk.CTkButton] = []
        for i in range(4):
            btn_ch = ctk.CTkButton(frame_grid_canales, text=str(i), **config_luces)
            btn_ch.grid(row=i, column=0, sticky="", pady=0)
            self.luces_canales.append(btn_ch)

        # Divisor derecho
        div_der = ctk.CTkFrame(panel_derecho, width=2, fg_color=GRIS_BORDE)
        div_der.grid(row=1, column=1, sticky="nse", pady=20)

        # ----------------------------------------------------
        # COLUMNA 3: TRIGGER Y ACCIONES
        # ----------------------------------------------------
        col_trigger = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        col_trigger.grid(row=1, column=2, sticky="nsew", pady=10)

        ctk.CTkLabel(
            col_trigger, text="TRIGGER", font=("Arial", 24, "bold"), text_color=GRIS_TEXTO
        ).pack(pady=(10, 10))

        frame_slider_grupo = ctk.CTkFrame(col_trigger, fg_color="transparent")
        frame_slider_grupo.pack(pady=10)

        lat_inicial = getattr(self, "_latencia_guardada_ms", 12.5)

        self.lbl_valor_trigger = ctk.CTkLabel(
            frame_slider_grupo,
            text=f"25 ms ({lat_inicial:.1f} ms)",
            font=("Arial", 16, "bold"),
            text_color=VERDE,
        )
        self.lbl_valor_trigger.pack(side="top", pady=(0, 5))

        self.slider_trigger = ctk.CTkSlider(
            frame_slider_grupo,
            orientation="vertical",
            from_=0.0,
            to=25.0,
            number_of_steps=50,
            fg_color=GRIS_SUAVE,
            progress_color=VERDE,
            button_color=VERDE,
            button_hover_color=VERDE_HOVER,
            height=260,
            width=30,
            corner_radius=15,
            button_length=24,
            command=self._al_mover_slider_trigger,
        )
        self.slider_trigger.pack(side="top")
        self.slider_trigger.set(lat_inicial)

        lbl_min = ctk.CTkLabel(
            frame_slider_grupo, text="0 ms", font=("Arial", 14, "bold"), text_color=GRIS_MEDIO
        )
        lbl_min.pack(side="top", pady=(5, 0))

        # Botones Cancelar y Aplicar
        self.btn_cancelar_trigger = ctk.CTkButton(
            col_trigger,
            text="Cancelar",
            fg_color=GRIS_SUAVE,
            hover_color=GRIS_SUAVE_HOV,
            text_color=GRIS_TEXTO,
            corner_radius=30,
            width=135,
            height=55,
            font=("Arial", 24, "bold"),
            command=self._al_pulsar_cancelar_trigger,
        )
        self.btn_cancelar_trigger.pack(pady=(20, 5))

        self.btn_aplicar_trigger = ctk.CTkButton(
            col_trigger,
            text="Aplicar",
            fg_color=VERDE,
            hover_color=VERDE_HOVER,
            text_color="white",
            corner_radius=30,
            width=150,
            height=55,
            font=("Arial", 24, "bold"),
            command=self._al_pulsar_aplicar_trigger,
        )
        self.btn_aplicar_trigger.pack(pady=5)

    # =========================================================================
    # VISTA 2: ANALÍTICAS (Gráfica Horizontal con Acrónimos y StatCards)
    # =========================================================================

    def _crear_pagina_analiticas(self) -> None:
        self.pagina_analiticas = ctk.CTkFrame(self, fg_color="transparent")
        self.pagina_analiticas.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.pagina_analiticas.grid_columnconfigure(0, weight=0)
        self.pagina_analiticas.grid_columnconfigure(1, weight=1)
        self.pagina_analiticas.grid_rowconfigure(0, weight=1)

        self._crear_area_grafico_analiticas()
        self._crear_panel_estadisticas()

    def _crear_area_grafico_analiticas(self) -> None:
        self.frame_grafico_analiticas = ctk.CTkFrame(
            self.pagina_analiticas,
            fg_color=GRIS_PANEL,
            corner_radius=15,
            border_width=2,
            border_color=GRIS_BORDE,
            width=634,
            height=619,
        )
        self.frame_grafico_analiticas.grid(
            row=0, column=0, sticky="nsew", padx=(20, 10), pady=(0, 20)
        )
        self.frame_grafico_analiticas.grid_propagate(False)
        self.frame_grafico_analiticas.pack_propagate(False)

        ctk.CTkLabel(
            self.frame_grafico_analiticas,
            text="Frecuencia / Categoría",
            font=("Arial", 24, "bold"),
            text_color=GRIS_TEXTO,
        ).place(relx=0.5, rely=0.038, anchor="center")

        # Figura y lienzo reactivo de Matplotlib incrustado en tema claro aprovechando todo el contenedor
        self.fig_analiticas = Figure(figsize=(5.80, 5.10), dpi=100, facecolor=GRIS_PANEL)
        self.ax_analiticas = self.fig_analiticas.add_subplot(111)
        self.ax_analiticas.set_facecolor("#FFFFFF")
        self.fig_analiticas.subplots_adjust(left=0.14, right=0.98, top=0.97, bottom=0.08)

        self.canvas_analiticas = FigureCanvasTkAgg(
            self.fig_analiticas, master=self.frame_grafico_analiticas
        )
        self.widget_canvas_analiticas = self.canvas_analiticas.get_tk_widget()
        self.widget_canvas_analiticas.configure(bg=GRIS_PANEL, highlightthickness=0)
        self.widget_canvas_analiticas.place(relx=0.5, rely=0.53, anchor="center", width=580, height=510)

    def _crear_panel_estadisticas(self) -> None:
        panel_estats = ctk.CTkFrame(
            self.pagina_analiticas,
            fg_color=GRIS_PANEL,
            corner_radius=15,
            border_width=1,
            border_color=GRIS_BORDE,
        )
        panel_estats.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=(0, 20))
        panel_estats.grid_columnconfigure(0, weight=1)
        panel_estats.grid_columnconfigure(1, weight=1)

        def crear_tarjeta(titulo: str, lineas: List[str], grande: bool = False, destacada: bool = False):
            ancho, alto = (276, 155) if grande else (276, 100)
            tarjeta = ctk.CTkFrame(
                panel_estats,
                fg_color=VERDE_TARJETA if destacada else GRIS_SUAVE,
                corner_radius=alto / 4,
                border_width=2,
                border_color=VERDE if destacada else GRIS_BORDE,
                width=ancho,
                height=alto,
            )
            tarjeta.grid_propagate(False)
            tarjeta.pack_propagate(False)

            ctk.CTkLabel(
                tarjeta,
                text=titulo,
                font=("Arial", 24, "bold", "underline"),
                text_color=GRIS_TEXTO,
            ).pack(pady=(12, 4))

            etiquetas = []
            for linea in lineas:
                lbl = ctk.CTkLabel(
                    tarjeta,
                    text=linea,
                    font=("Arial", 40, "bold"),
                    text_color=VERDE_HOVER if destacada else GRIS_TEXTO,
                )
                lbl.pack()
                etiquetas.append(lbl)
            return tarjeta, etiquetas

        # Tarjetas fila 1
        t_tiempo, lbls_tiempo = crear_tarjeta("Tiempo de Uso", ["00:00 h"])
        t_tiempo.grid(row=0, column=0, padx=(25, 8), pady=(28, 12))

        t_consumo, lbls_consumo = crear_tarjeta("Consumo", ["--- kWh"])
        t_consumo.grid(row=0, column=1, padx=(8, 25), pady=(28, 12))

        # Tarjetas fila 2
        t_estats, lbls_estats = crear_tarjeta("Estadísticas", ["--- grs", "--- %"], grande=True, destacada=True)
        t_estats.grid(row=1, column=0, padx=(25, 8), pady=12)

        t_rend, lbls_rend = crear_tarjeta("Rendimiento (Prom)", ["--- FPS", "--- ms"], grande=True)
        t_rend.grid(row=1, column=1, padx=(8, 25), pady=12)

        self.stat_tiempo = lbls_tiempo[0]
        self.stat_consumo = lbls_consumo[0]
        self.stat_granos = lbls_estats[0]
        self.stat_precision = lbls_estats[1]
        self.stat_fps = lbls_rend[0]
        self.stat_ms = lbls_rend[1]

        # Botones inferiores de acción
        btn_terminar = ctk.CTkButton(
            panel_estats,
            text="Terminar Lote",
            fg_color=AMBAR_RESET,
            hover_color=AMBAR_HOVER,
            text_color="white",
            corner_radius=45,
            height=80,
            width=578,
            font=("Arial", 32, "bold"),
            command=self._al_pulsar_terminar_lote,
        )
        btn_terminar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=25, pady=(25, 12))

        btn_sincronizar = ctk.CTkButton(
            panel_estats,
            text="Sincronizar con Base de Datos",
            fg_color=VERDE,
            hover_color=VERDE_HOVER,
            text_color="white",
            corner_radius=45,
            height=80,
            width=578,
            font=("Arial", 32, "bold"),
            command=self._al_pulsar_sincronizar_db,
        )
        btn_sincronizar.grid(row=3, column=0, columnspan=2, sticky="ew", padx=25, pady=12)

    # =========================================================================
    # VISTA 3: REGISTROS (Historial y Consola de Auditoría Local LOGS)
    # =========================================================================

    def _crear_pagina_registros(self) -> None:
        self.pagina_registros = ctk.CTkFrame(self, fg_color="transparent")
        self.pagina_registros.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.pagina_registros.grid_columnconfigure(0, weight=1)
        self.pagina_registros.grid_rowconfigure(0, weight=1)

        contenido = ctk.CTkFrame(self.pagina_registros, fg_color="transparent")
        contenido.grid(row=0, column=0, sticky="n")

        # Nivel 2: HISTORIAL
        fila_h = self._crear_fila_filtros_historial(contenido)
        fila_h.grid(row=0, column=0, pady=(0, 12))

        tabla_h = self._crear_tabla_historial(contenido)
        tabla_h.grid(row=1, column=0, pady=(0, 12))

        # Nivel 3: LOGS
        fila_l = self._crear_fila_filtros_logs(contenido)
        fila_l.grid(row=2, column=0, pady=(0, 12))

        caja_l = self._crear_caja_logs(contenido)
        caja_l.grid(row=3, column=0)

    def _actualizar_estilo_segmented_button(self, seg_btn: ctk.CTkSegmentedButton) -> None:
        """Asegura que el botón seleccionado tenga texto blanco para óptimo contraste visual."""
        try:
            seleccion = seg_btn.get()
            if hasattr(seg_btn, "_buttons_dict"):
                for k, btn in seg_btn._buttons_dict.items():
                    if k == seleccion:
                        btn.configure(text_color="white")
                    else:
                        btn.configure(text_color=GRIS_TEXTO)
        except Exception:
            pass

    def _crear_fila_filtros_historial(self, padre: ctk.CTkFrame) -> ctk.CTkFrame:
        fila = ctk.CTkFrame(padre, fg_color="transparent", width=1204, height=70)
        fila.pack_propagate(False)

        grupo = ctk.CTkFrame(fila, fg_color="transparent")
        grupo.pack(side="left")

        self.menu_cat_historial = ctk.CTkOptionMenu(
            grupo,
            values=["Todos", "Tri-clase", "13 Clases", "Tri-clase + SAHI", "13 Clases + SAHI"],
            width=230,
            height=70,
            font=("Arial", 22),
            dropdown_font=("Arial", 22),
            fg_color=VERDE,
            button_color=VERDE,
            button_hover_color=VERDE_CLARO,
            text_color="white",
            corner_radius=35,
            command=lambda _: self._poblar_tabla_historial(),
        )
        self.menu_cat_historial.pack(side="left", padx=(0, 14))

        self.seg_fecha_historial = ctk.CTkSegmentedButton(
            grupo,
            values=["Hoy", "Últimos 3 días", "Última Semana", "Todos"],
            fg_color=GRIS_SUAVE,
            unselected_color=GRIS_SUAVE,
            unselected_hover_color=GRIS_SUAVE_HOV,
            selected_color=VERDE,
            selected_hover_color=VERDE_HOVER,
            text_color=GRIS_TEXTO,
            text_color_disabled=GRIS_MEDIO,
            height=70,
            font=("Arial", 24),
            corner_radius=35,
            command=lambda _: (
                self._actualizar_estilo_segmented_button(self.seg_fecha_historial),
                self._poblar_tabla_historial(),
            ),
        )
        self.seg_fecha_historial.set("Hoy")
        self.seg_fecha_historial.pack(side="left")
        self.after(50, lambda: self._actualizar_estilo_segmented_button(self.seg_fecha_historial))

        ctk.CTkLabel(
            fila, text="Historial", font=("Arial", 36, "bold"), text_color=GRIS_TEXTO
        ).pack(side="right", padx=(10, 5))
        return fila

    def _crear_tabla_historial(self, padre: ctk.CTkFrame) -> ctk.CTkFrame:
        COLUMNAS = ["Fecha", "N°", "Granos Totales", "G buenos (N)", "GB A/R (%)", "Tiempo (min)"]
        ANCHOS = [185, 160, 210, 200, 205, 165]

        tabla = ctk.CTkFrame(
            padre,
            width=1204,
            height=230,
            fg_color=GRIS_PANEL,
            corner_radius=10,
            border_width=2,
            border_color=GRIS_BORDE,
        )
        tabla.pack_propagate(False)

        cabecera = ctk.CTkFrame(tabla, fg_color=VERDE, corner_radius=10, height=54)
        cabecera.pack(fill="x", padx=(6, 22), pady=(6, 4))
        cabecera.pack_propagate(False)
        for tit, w in zip(COLUMNAS, ANCHOS):
            ctk.CTkLabel(
                cabecera, text=tit, width=w, font=("Arial", 24, "bold"), text_color="white"
            ).pack(side="left", padx=2)

        self.cuerpo_tabla_historial = ctk.CTkScrollableFrame(tabla, fg_color=GRIS_BORDE, corner_radius=0)
        self.cuerpo_tabla_historial.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self.anchos_columnas_historial = ANCHOS
        return tabla

    def _crear_fila_filtros_logs(self, padre: ctk.CTkFrame) -> ctk.CTkFrame:
        fila = ctk.CTkFrame(padre, fg_color="transparent", width=1204, height=70)
        fila.pack_propagate(False)

        grupo = ctk.CTkFrame(fila, fg_color="transparent")
        grupo.pack(side="left")

        self.menu_tipo_logs = ctk.CTkOptionMenu(
            grupo,
            values=["Todos", "INFO", "WARNING", "ALARM"],
            width=160,
            height=70,
            font=("Arial", 24),
            dropdown_font=("Arial", 24),
            fg_color=VERDE,
            button_color=VERDE,
            button_hover_color=VERDE_CLARO,
            text_color="white",
            corner_radius=35,
            command=lambda _: self._cargar_consola_logs(),
        )
        self.menu_tipo_logs.pack(side="left", padx=(0, 14))

        self.seg_fecha_logs = ctk.CTkSegmentedButton(
            grupo,
            values=["Hoy", "Últimos 3 días", "Última Semana", "Todos"],
            fg_color=GRIS_SUAVE,
            unselected_color=GRIS_SUAVE,
            unselected_hover_color=GRIS_SUAVE_HOV,
            selected_color=VERDE,
            selected_hover_color=VERDE_HOVER,
            text_color=GRIS_TEXTO,
            text_color_disabled=GRIS_MEDIO,
            height=70,
            font=("Arial", 24),
            corner_radius=35,
            command=lambda _: (
                self._actualizar_estilo_segmented_button(self.seg_fecha_logs),
                self._cargar_consola_logs(),
            ),
        )
        self.seg_fecha_logs.set("Hoy")
        self.seg_fecha_logs.pack(side="left")
        self.after(50, lambda: self._actualizar_estilo_segmented_button(self.seg_fecha_logs))

        ctk.CTkLabel(
            fila, text="LOGS", font=("Arial", 36, "bold"), text_color=GRIS_TEXTO
        ).pack(side="right", padx=(10, 5))
        return fila

    def _crear_caja_logs(self, padre: ctk.CTkFrame) -> ctk.CTkTextbox:
        self.logs_box = ctk.CTkTextbox(
            padre,
            width=1204,
            height=155,
            fg_color=GRIS_OSCURO,
            text_color=VERDE_LED,
            border_width=2,
            border_color=VERDE_CLARO,
            corner_radius=10,
            font=("Consolas", 20),
        )
        self.logs_box.insert(
            "end",
            "[--:--:--] Sistema listo. Los eventos del proceso aparecerán aquí.\n",
        )
        self.logs_box.configure(state="disabled")

        # Configurar tags de severidad sobre el widget nativo
        try:
            raw = self.logs_box._textbox
            raw.tag_config("ALARM", foreground="#FF5252", font=("Consolas", 20, "bold"))
            raw.tag_config("WARNING", foreground="#FFB74D", font=("Consolas", 20, "bold"))
            raw.tag_config("INFO", foreground="#81C784")
            raw.tag_config("DEFAULT", foreground=VERDE_LED)
        except Exception:
            pass

        return self.logs_box

    # =========================================================================
    # COMPATIBILIDAD HACIA ATRÁS: ALIASES PARA SUITE DE PRUEBAS
    # =========================================================================

    def _configurar_aliases_retrocompatibilidad(self) -> None:
        """Expone propiedades y controles con los nombres esperados por tests existentes."""
        self.card_kpi_tiempo = self.stat_tiempo
        self.card_kpi_consumo = self.stat_consumo
        self.card_kpi_granos = self.stat_granos
        self.card_kpi_precision = self.stat_precision
        self.card_kpi_latencia = self.stat_ms
        self.card_kpi_lotes = self.lbl_lotes

        self.tab_logs = self.logs_box
        self.txt_logs = self.logs_box

        self.slider_latencia = self.slider_trigger
        self.btn_aplicar_latencia = self.btn_aplicar_trigger
        self.btn_cancelar_latencia = self.btn_cancelar_trigger

        self.indicadores_canales = self.luces_canales

        self.fig_reactiva = self.fig_analiticas
        self.ax_reactivo = self.ax_analiticas
        self.canvas_reactivo = self.canvas_analiticas

        # Emulación del switch de modelo para pruebas existentes
        self.switch_modelo = ctk.CTkSwitch(
            self,
            text="Tri-clase",
            command=self._al_cambiar_switch_modelo_compat,
        )
        self.switch_modelo.deselect()

        self.switch_sahi = ctk.CTkSwitch(
            self,
            text="SAHI: OFF",
            command=self._al_cambiar_switch_sahi_compat,
        )
        self.switch_sahi.deselect()

        # Emulación de selectores físicos de cámaras
        self.combo_cam_top = ctk.CTkOptionMenu(
            self,
            values=["Cámara 0", "Cámara 1", "Cámara 2", "Demo / Sintético"],
            command=self._al_cambiar_camara_top_compat,
        )
        self.combo_cam_top.set(self._formatear_fuente_texto(self.detector.fuente_video_top))

        self.combo_cam_bottom = ctk.CTkOptionMenu(
            self,
            values=["Cámara 0", "Cámara 1", "Cámara 2", "Demo / Sintético"],
            command=self._al_cambiar_camara_bottom_compat,
        )
        self.combo_cam_bottom.set(self._formatear_fuente_texto(self.detector.fuente_video_bottom))
        self.opt_fuente = self.combo_cam_top

        # Label de estado operativo
        self.lbl_estado_maquina = ctk.CTkLabel(
            self, text="ESTADO: STANDBY", font=("Arial", 14, "bold"), text_color=GRIS_MEDIO
        )

    # =========================================================================
    # MÁQUINA DE ESTADOS FINITA (FSM) DE BOTONERÍA (M, P, R) Y SEGURIDAD
    # =========================================================================

    def _verificar_corte_abrupto_al_arranque(self) -> None:
        """
        Detección de corte abrupto por paro de emergencia o apagón durante marcha:
        Si 'estado_operativo' previo era 'EN_MARCHA', bloquea el inicio,
        enciende piloto rojo en ESP32 y exige purga con botón R.
        """
        if getattr(self.gestor_tiempo, "requiere_reset_por_corte", False):
            self._actualizar_fsm("BLOQUEO_SEGURIDAD")
            self.db_manager.registrar_log_local(
                "ALARM", "Corte abrupto de energía detectado durante marcha. Pulse Reset (R) para purgar."
            )
            if self.esp32_bridge:
                self.esp32_bridge.cambiar_piloto("RED")

            if "unittest" not in sys.modules:
                messagebox.showwarning(
                    "Bloqueo de Seguridad | MOPPI",
                    "Se detectó un corte abrupto de energía durante la marcha previa.\n"
                    "El sistema ha sido bloqueado por seguridad (Piloto Rojo).\n"
                    "Presione 'R' (Reset) para purgar antes de operar.",
                )
        else:
            self._actualizar_fsm("STANDBY")

    _verificar_estado_previo_maquina = _verificar_corte_abrupto_al_arranque

    def _actualizar_fsm(self, nuevo_estado: str) -> None:
        self.estado_operativo = nuevo_estado
        self.gestor_tiempo.actualizar_estado_operativo(nuevo_estado)

        if nuevo_estado == "STANDBY":
            self.lbl_estado_maquina.configure(text="ESTADO: STANDBY", text_color=GRIS_MEDIO)
            self.btn_marcha.configure(
                state="normal", text="M", fg_color=VERDE, hover_color=VERDE_HOVER, border_color=VERDE_HOVER, text_color="white"
            )
            self.btn_paro.configure(
                state="disabled", text="P", fg_color=ROJO_BLOQUEADO, border_color=ROJO_BLOQUEADO, text_color=ROJO_BLOQUEADO_TXT
            )
            self.btn_reset.configure(
                state="disabled", text="R", fg_color=AMBAR_BLOQUEADO, border_color=AMBAR_BLOQUEADO, text_color=AMBAR_BLOQUEADO_TXT
            )

            # Controles de Trigger habilitados en reposo
            self.slider_trigger.configure(state="normal")
            self.btn_cancelar_trigger.configure(state="normal")
            self.btn_aplicar_trigger.configure(state="normal")

            if self.esp32_bridge:
                self.esp32_bridge.control_banda(False)
                self.esp32_bridge.cambiar_piloto("WHITE")

        elif nuevo_estado == "EN_MARCHA":
            self.lbl_estado_maquina.configure(text="ESTADO: EN MARCHA", text_color=VERDE)
            self.btn_marcha.configure(
                state="disabled", text="M", fg_color=VERDE_BLOQUEADO, border_color=VERDE_BLOQUEADO, text_color=VERDE_BLOQUEADO_TXT
            )
            self.btn_paro.configure(
                state="normal", text="P", fg_color=ROJO_PARO, hover_color=ROJO_HOVER, border_color=ROJO_HOVER, text_color="white"
            )
            self.btn_reset.configure(
                state="disabled", text="R", fg_color=AMBAR_BLOQUEADO, border_color=AMBAR_BLOQUEADO, text_color=AMBAR_BLOQUEADO_TXT
            )

            # Inhibición estricta de calibración en marcha
            self.slider_trigger.configure(state="disabled")
            self.btn_cancelar_trigger.configure(state="disabled")
            self.btn_aplicar_trigger.configure(state="disabled")

            if self.esp32_bridge:
                self.esp32_bridge.control_banda(True)
                self.esp32_bridge.cambiar_piloto("GREEN")

        elif nuevo_estado == "PARO":
            self.lbl_estado_maquina.configure(text="ESTADO: PARO", text_color=AMBAR_RESET)
            # Botón de Marcha en Celeste para Reanudar
            self.btn_marcha.configure(
                state="normal", text="M", fg_color=CELESTE_REANUDAR, hover_color=CELESTE_HOVER, border_color=CELESTE_BORDE, text_color="white"
            )
            self.btn_paro.configure(
                state="disabled", text="P", fg_color=ROJO_BLOQUEADO, border_color=ROJO_BLOQUEADO, text_color=ROJO_BLOQUEADO_TXT
            )
            self.btn_reset.configure(
                state="normal", text="R", fg_color=AMBAR_RESET, hover_color=AMBAR_HOVER, border_color=AMBAR_HOVER, text_color="white"
            )

            # Controles de Trigger habilitados para calibrar con máquina en reposo
            self.slider_trigger.configure(state="normal")
            self.btn_cancelar_trigger.configure(state="normal")
            self.btn_aplicar_trigger.configure(state="normal")

            if self.esp32_bridge:
                self.esp32_bridge.control_banda(False)
                self.esp32_bridge.cambiar_piloto("YELLOW")

        elif nuevo_estado == "BLOQUEO_SEGURIDAD":
            self.lbl_estado_maquina.configure(text="ALERTA: BLOQUEO DE SEGURIDAD", text_color=ROJO_PARO)
            self.btn_marcha.configure(
                state="disabled", text="M", fg_color=VERDE_BLOQUEADO, border_color=VERDE_BLOQUEADO, text_color=VERDE_BLOQUEADO_TXT
            )
            self.btn_paro.configure(
                state="disabled", text="P", fg_color=ROJO_BLOQUEADO, border_color=ROJO_BLOQUEADO, text_color=ROJO_BLOQUEADO_TXT
            )
            self.btn_reset.configure(
                state="normal", text="R", fg_color=ROJO_PARO, hover_color=ROJO_HOVER, border_color=ROJO_HOVER, text_color="white"
            )

            self.slider_trigger.configure(state="disabled")
            self.btn_cancelar_trigger.configure(state="disabled")
            self.btn_aplicar_trigger.configure(state="disabled")

            if self.esp32_bridge:
                self.esp32_bridge.control_banda(False)
                self.esp32_bridge.cambiar_piloto("RED")

    def _ejecutar_arranque_marcha(self) -> None:
        """Arranca físicamente la clasificación y pone la clasificadora EN_MARCHA."""
        if hasattr(self.detector, "iniciar") and not getattr(self.detector, "_ejecutando", False):
            try:
                self.detector.iniciar()
            except Exception as e:
                logger.warning(f"Error al iniciar captura de video: {e}")
        self.detector.iniciar_clasificacion()
        self.metricas.iniciar_sesion()
        if hasattr(self.gestor_lotes, "iniciar_lote"):
            self.gestor_lotes.iniciar_lote()
        elif hasattr(self.gestor_lotes, "iniciar_nuevo_lote"):
            self.gestor_lotes.iniciar_nuevo_lote()
        self.db_manager.registrar_log_local("INFO", "Inicio de marcha en clasificadora.")
        self._actualizar_fsm("EN_MARCHA")

    def _al_pulsar_marcha(self) -> None:
        """Manejador del botón M (Marcha / Reanudar)."""
        if getattr(self.gestor_tiempo, "requiere_reset_por_corte", False):
            if "unittest" not in sys.modules:
                messagebox.showwarning(
                    "Arranque Bloqueado",
                    "Corte abrupto previo detectado. Pulse 'R' para purgar antes de operar.",
                )
            return

        if self.estado_operativo == "STANDBY":
            # En entorno de pruebas automatizadas, permitir ejecución directa sin diálogo modal
            if "unittest" in sys.modules:
                self._ejecutar_arranque_marcha()
                return

            # Verificar disponibilidad real de cámaras de inspección
            if hasattr(self.detector, "verificar_estado_camaras"):
                estado_cam = self.detector.verificar_estado_camaras()
                if not estado_cam.get("todas_ok", True):
                    VentanaAdvertenciaCamaras(
                        parent=self,
                        estado_camaras=estado_cam,
                        on_continuar=self._ejecutar_arranque_marcha,
                    )
                    return

            self._ejecutar_arranque_marcha()

        elif self.estado_operativo == "PARO":
            self.detector.reanudar()
            self.metricas.iniciar_sesion()
            self.db_manager.registrar_log_local("INFO", "Reanudación de marcha en clasificadora.")
            self._actualizar_fsm("EN_MARCHA")

    def _al_pulsar_paro(self) -> None:
        """Manejador del botón P (Paro operativo)."""
        if self.estado_operativo != "EN_MARCHA":
            return
        self.detector.pausar()
        self.metricas.pausar_sesion()
        self.db_manager.registrar_log_local("WARNING", "Paro operativo solicitado por operador.")
        self._actualizar_fsm("PARO")

    def _al_pulsar_reset(self) -> None:
        """Manejador del botón R (Reset / Purga / Cierre de lote)."""
        if getattr(self.gestor_tiempo, "requiere_reset_por_corte", False):
            self.gestor_tiempo.reset_corte_abrupto()
            self.db_manager.registrar_log_local("INFO", "Sistema purgado tras corte de energía. Retorno a STANDBY.")
            self._actualizar_fsm("STANDBY")
            return

        if self.estado_operativo == "PARO":
            # Si hay granos procesados, cerrar y guardar el lote
            if getattr(self.gestor_lotes, "total_granos", 0) > 0:
                self.gestor_lotes.finalizar_lote()
            self.metricas.reiniciar()
            self.db_manager.registrar_log_local("INFO", "Reset de contadores y retorno a STANDBY.")
            self._actualizar_fsm("STANDBY")

    # =========================================================================
    # CANALES Y ACTUACIÓN NEUMÁTICA (DESTELLO LUMINOSO 120 MS)
    # =========================================================================

    def destellar_canal(self, canal: int) -> None:
        """
        Conmuta el indicador pasivo del canal a verde luminoso (VERDE_LED)
        durante 120 ms mediante after(), regresando a su gris de reposo.
        """
        if 0 <= canal < len(self.luces_canales):
            btn = self.luces_canales[canal]
            btn.configure(fg_color=VERDE_LED, text_color="white")
            self.after(120, lambda b=btn: self._apagar_luz_canal(b))

    activar_indicador_canal = destellar_canal

    def _apagar_luz_canal(self, btn: ctk.CTkButton) -> None:
        try:
            if btn.winfo_exists():
                btn.configure(fg_color=GRIS_SUAVE, text_color=GRIS_MEDIO)
        except Exception:
            pass

    def _apagar_indicador_canal(self, canal: int) -> None:
        if 0 <= canal < len(self.luces_canales):
            self._apagar_luz_canal(self.luces_canales[canal])

    def _al_recibir_respuesta_serial(self, linea: str) -> None:
        """Callback invocado por ESP32Bridge al recibir tramas como 'OK:<canal>'."""
        if linea.startswith("OK:"):
            ch_str = linea[3:].strip()
            if ch_str.isdigit():
                ch = int(ch_str)
                if threading.current_thread() is threading.main_thread():
                    self.destellar_canal(ch)
                else:
                    self.after(0, lambda: self.destellar_canal(ch))

    # =========================================================================
    # CALIBRACIÓN CINEMÁTICA Y SLIDER DE TRIGGER
    # =========================================================================

    def _al_mover_slider_trigger(self, valor: float) -> None:
        """
        Mapea el slider (0.0..25.0 ms) a la latencia de respuesta de la electroválvula neumática,
        calculando el nuevo Y_trigger dinámico y previsualizándolo en el visor en tiempo real.
        """
        lat_dinamica = round(float(valor), 1)
        self._latencia_preview_ms = lat_dinamica
        self.lbl_valor_trigger.configure(text=f"25 ms ({lat_dinamica:.1f} ms)")

        if hasattr(self.detector, "previsualizar_latencia_actuador"):
            self.detector.previsualizar_latencia_actuador(lat_dinamica)

    def _al_pulsar_cancelar_trigger(self) -> None:
        """Restaura el slider a la latencia guardada y descarta la previsualización."""
        if hasattr(self.detector, "cancelar_previsualizacion_latencia"):
            self.detector.cancelar_previsualizacion_latencia()
        # Restaurar slider y etiqueta
        self.slider_trigger.set(self._latencia_guardada_ms)
        self.lbl_valor_trigger.configure(text=f"25 ms ({self._latencia_guardada_ms:.1f} ms)")

    def _al_pulsar_aplicar_trigger(self) -> None:
        """Despliega el modal táctil para confirmar la nueva calibración cinemática."""
        y_dinamico = getattr(self.detector, "y_trigger_preview", None)
        if y_dinamico is None:
            y_dinamico = getattr(self.detector, "y_trigger", 501)
        porcentaje = int(round((self._latencia_preview_ms / 25.0) * 100))

        self._modal_trigger = VentanaConfirmacionTrigger(
            parent=self,
            nueva_latencia_ms=self._latencia_preview_ms,
            nuevo_y_px=y_dinamico,
            porcentaje_slider=porcentaje,
            callback_confirmar=self._confirmar_calibracion_trigger,
        )

    def _confirmar_calibracion_trigger(self, latencia_ms: float, y_px: Optional[int] = None) -> None:
        """Aplica y persiste la calibración cinemática confirmada."""
        if hasattr(self.detector, "actualizar_latencia_actuador"):
            y_real = self.detector.actualizar_latencia_actuador(latencia_ms)
        else:
            y_real = y_px or int(round(640 - ((latencia_ms / 25.0) * 160)))
            self.detector.y_trigger = y_real

        self._latencia_guardada_ms = latencia_ms
        self._y_trigger_guardado_px = y_real
        self.slider_trigger.set(latencia_ms)
        self.lbl_valor_trigger.configure(text=f"25 ms ({latencia_ms:.1f} ms)")
        self.db_manager.registrar_log_local(
            "INFO", f"Nueva posición de trigger aplicada: Y = {y_real} px ({latencia_ms:.1f} ms)."
        )

    # =========================================================================
    # VISTAS DE CÁMARAS Y CONTROL DE INFERENCIA DUAL
    # =========================================================================

    def _al_pulsar_alternar_camara(self) -> None:
        """El botón ↕ conmuta el lienzo visible entre Superior (Maestro) e Inferior (Esclavo)."""
        if self.camara_vista_activa == "TOP":
            self.camara_vista_activa = "BOTTOM"
            self.lbl_camara_activa_badge.configure(
                text="CÁMARA INFERIOR (ESCLAVO) | INSPECCIÓN DE REVERSO",
                text_color="#81D4FA",
            )
        else:
            self.camara_vista_activa = "TOP"
            self.lbl_camara_activa_badge.configure(
                text="CÁMARA SUPERIOR (MAESTRO) | CONTROL DE DISPARO",
                text_color=VERDE_CLARO,
            )

    def _al_conmutar_modelo(self, seleccion: str) -> None:
        """Conmuta globalmente el modelo de IA para ambas cámaras (Tri-clase / 13 Clases, con o sin SAHI)."""
        es_13 = "13" in seleccion
        es_sahi = "SAHI" in seleccion
        if hasattr(self.detector, "cambiar_modelo"):
            self.detector.cambiar_modelo(usar_13_clases=es_13, modo_sahi=es_sahi)
        self.gestor_lotes.configurar_modelo(modelo_13_clases=es_13, modo_sahi=es_sahi)

        # Sincronizar ambos selectores
        self.btn_modelos_dash.set(seleccion)
        self.btn_modelos_analiticas.set(seleccion)

        # Sincronizar switch de compatibilidad
        sahi_tag = " + SAHI" if es_sahi else ""
        if es_13:
            self.switch_modelo.select()
            self.switch_modelo.configure(text=f"13 Clases{sahi_tag}")
        else:
            self.switch_modelo.deselect()
            self.switch_modelo.configure(text=f"Tri-clase{sahi_tag}")

        self.db_manager.registrar_log_local("INFO", f"Modelo de inferencia actualizado a: {seleccion}.")
        self._actualizar_grafico_reactivo()

    def _al_cambiar_posicion_camaras(self, seleccion: str) -> None:
        """Alterna físicamente la correspondencia de las cámaras superior e inferior."""
        if hasattr(self.detector, "alternar_posicion_camaras"):
            self.detector.alternar_posicion_camaras()
            self.db_manager.registrar_log_local("INFO", "Asignación física de cámaras invertida.")

    # =========================================================================
    # ACTUALIZACIÓN EN VIVO: VIDEO, ESTADÍSTICAS Y GRÁFICAS
    # =========================================================================

    def _bucle_actualizacion_video(self) -> None:
        """Bucle periódico a 30-60 FPS para streaming visual sin congelamientos."""
        if not getattr(self, "_bucle_video_activo", True):
            return

        try:
            ahora = time.time()
            dt = ahora - self._ultimo_tiempo_frame
            if dt > 0:
                self._fps_actual = 0.9 * self._fps_actual + 0.1 * (1.0 / dt)
            self._ultimo_tiempo_frame = ahora

            # 1. Consumir todos los payloads disponibles de la cola de salida de YOLODetector
            payloads = []
            if self.detector and hasattr(self.detector, "cola_salida"):
                try:
                    while True:
                        payloads.append(self.detector.cola_salida.get_nowait())
                except queue.Empty:
                    pass

            # Si la clasificadora está en marcha, registrar detecciones en GestorLotes y GestorMetricas
            if payloads and self.estado_operativo == "EN_MARCHA":
                for p in payloads:
                    dets = p.get("detecciones", [])
                    if dets:
                        fps_p = float(p.get("fps", self._fps_actual))
                        lat_p = float(p.get("latencia_ms", self._latencia_inferencia_actual))
                        if self.gestor_lotes:
                            try:
                                self.gestor_lotes.registrar_detecciones(dets, fps_p, lat_p)
                            except Exception as e_lot:
                                logger.debug(f"Error registrando detecciones en GestorLotes: {e_lot}")
                        if self.metricas:
                            try:
                                self.metricas.registrar_detecciones(dets, fps_p, lat_p)
                            except Exception as e_met:
                                logger.debug(f"Error registrando detecciones en GestorMetricas: {e_met}")

            # Usar el payload más reciente para renderizado visual
            payload = payloads[-1] if payloads else None

            frame_render = None
            if payload is not None:
                if self.camara_vista_activa == "TOP":
                    frame_render = payload.get("frame_top")
                    if frame_render is None:
                        frame_render = payload.get("frame_bgr")
                else:
                    frame_render = payload.get("frame_bottom")
                    if frame_render is None:
                        frame_render = payload.get("frame_top")

                if "latencia_ms" in payload and payload["latencia_ms"] > 0:
                    self._latencia_inferencia_actual = float(payload["latencia_ms"])
                if "fps" in payload and payload["fps"] > 0:
                    self._fps_actual = float(payload["fps"])

            # 2. Fallback de acceso directo al detector si la cola no proveyó frame en este ciclo
            if frame_render is None and hasattr(self.detector, "obtener_frame_renderizado_dual"):
                frame_top, frame_bot, lat_ms = self.detector.obtener_frame_renderizado_dual()
                if frame_top is not None:
                    self._latencia_inferencia_actual = lat_ms
                    if self.camara_vista_activa == "TOP":
                        frame_render = frame_top
                    else:
                        frame_render = frame_bot if frame_bot is not None else frame_top

            if frame_render is not None:
                # Redimensionar exactamente a 640x640 px para respetar el contenedor de HMI.py
                h, w = frame_render.shape[:2]
                if w != 640 or h != 640:
                    frame_render = cv2.resize(frame_render, (640, 640), interpolation=cv2.INTER_LINEAR)

                # Convertir a RGB y mostrar sobre Tkinter Label
                frame_rgb = cv2.cvtColor(frame_render, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                img_tk = ImageTk.PhotoImage(image=img)
                self.lbl_video_display.image = img_tk  # Referencia persistente contra garbage collection
                self.lbl_video_display.imgtk = img_tk
                self.lbl_video_display.configure(image=img_tk)

            # Actualizar insignias flotantes
            self.lbl_fps.configure(text=f"FPS: {int(round(self._fps_actual))}")
            self.lbl_ms.configure(text=f"ms: {self._latencia_inferencia_actual:.1f}")

        except Exception as e:
            logger.debug(f"Aviso en bucle de video: {e}")

        # Agendar siguiente fotograma (~33 ms)
        self._id_after_bucle = self.after(33, self._bucle_actualizacion_video)

    def _bucle_actualizacion_analiticas(self) -> None:
        """Bucle periódico a 1 Hz para mantener actualizadas las 4 StatCards y gráfica en tiempo real."""
        if not getattr(self, "_bucle_analiticas_activo", True):
            return

        try:
            # Avanzar cronometraje acumulado y cómputo de energía si la máquina está en marcha
            clasificacion_activa = (self.estado_operativo == "EN_MARCHA")
            if hasattr(self, "gestor_tiempo") and self.gestor_tiempo is not None:
                self.gestor_tiempo.tick(clasificacion_activa)

            self._actualizar_tarjetas_estadisticas()
            self._actualizar_indicador_bd_y_lotes()
            if getattr(self, "_pagina_actual", "Dashboard") == "Analíticas":
                self._actualizar_grafico_reactivo()
        except Exception as e:
            logger.debug(f"Aviso en bucle de analíticas: {e}")

        self._id_after_analiticas = self.after(1000, self._bucle_actualizacion_analiticas)

    def _actualizar_indicador_bd_y_lotes(self) -> None:
        """Actualiza el LED de MongoDB y el contador de lotes en la cabecera."""
        conectado = getattr(self.db_manager, "esta_conectado_mongo", False)
        color_led = VERDE_LED if conectado else GRIS_MEDIO
        try:
            self.led_mongo.configure(fg_color=color_led)
            self.led_mongo_registros.configure(fg_color=color_led)
        except Exception:
            pass

        try:
            stats = self.db_manager.obtener_estadisticas_acumuladas()
            tot_lotes = stats.get("total_lotes", 0)
            txt = f"Lotes:  {tot_lotes}"
            self.lbl_lotes.configure(text=txt)
            self.lbl_lotes_registros.configure(text=txt)
        except Exception:
            pass

    def _actualizar_tarjetas_estadisticas(self) -> None:
        """Actualiza los valores de las 4 StatCards en Analíticas."""
        try:
            # 1. Tiempo de uso
            seg_hoy = getattr(self.gestor_tiempo, "segundos_hoy", 0)
            hrs = int(seg_hoy // 3600)
            mins = int((seg_hoy % 3600) // 60)
            self.stat_tiempo.configure(text=f"{hrs:02d}:{mins:02d} h")

            # 2. Consumo energético
            kwh = (seg_hoy / 3600.0) * float(os.getenv("HARDWARE_POWER_KW", "0.5"))
            self.stat_consumo.configure(text=f"{kwh:.2f} kWh")

            # 3. Estadísticas de granos (Solo unidades, proporción de buenos (Arabica_Bueno + Robusta_Bueno) / total)
            tot_granos = getattr(self.gestor_lotes, "total_granos", 0)
            if tot_granos == 0 and hasattr(self, "metricas"):
                tot_granos = getattr(self.metricas, "total_granos", 0)

            conteo_crudo = getattr(self.gestor_lotes, "conteo_crudo", {})
            if not any(conteo_crudo.values()) and hasattr(self, "metricas"):
                conteo_crudo = getattr(self.metricas, "conteo_por_clase", conteo_crudo)

            ar_b = conteo_crudo.get("Arabica_Bueno", 0)
            ro_b = conteo_crudo.get("Robusta_Bueno", 0)
            granos_buenos = ar_b + ro_b
            proporcion_buenos = (granos_buenos / tot_granos * 100.0) if tot_granos > 0 else 100.0

            # Tarjeta de granos: estrictamente unidades contabilizadas (cero cálculo de peso)
            self.stat_granos.configure(text=f"{tot_granos} u")
            # Segunda fila: Proporción exacta de granos buenos sobre el total
            self.stat_precision.configure(text=f"{proporcion_buenos:.1f} %")

            # 4. Rendimiento promedio
            self.stat_fps.configure(text=f"{int(round(self._fps_actual))} FPS")
            self.stat_ms.configure(text=f"{self._latencia_inferencia_actual:.1f} ms")
        except Exception as e:
            logger.debug(f"Error actualizando statcards: {e}")

    def _actualizar_grafico_reactivo(self) -> None:
        """Dibuja la gráfica de barras horizontales adaptada al tema claro y con filtrado de variedad."""
        if not hasattr(self, "ax_analiticas") or self.ax_analiticas is None:
            return

        self.ax_analiticas.clear()
        self.ax_analiticas.set_facecolor("#FFFFFF")
        self.fig_analiticas.set_facecolor(GRIS_PANEL)

        es_13 = getattr(self.detector, "es_modo_13clases", False)
        conteo_crudo = getattr(self.gestor_lotes, "conteo_crudo", {})
        if not any(conteo_crudo.values()) and hasattr(self, "metricas"):
            conteo_crudo = getattr(self.metricas, "conteo_por_clase", conteo_crudo)

        if es_13:
            total_ar = sum(cant for clase, cant in conteo_crudo.items() if "Arabica" in clase)
            total_ro = sum(cant for clase, cant in conteo_crudo.items() if "Robusta" in clase)

            if total_ar > 0 and total_ro == 0:
                # Solo se ha detectado variedad Arábica
                orden = ["A_BUE", "A_NEG", "A_BRO", "A_QUE", "A_AGR", "A_INM", "A_CON", "A_CER"]
            elif total_ro > 0 and total_ar == 0:
                # Solo se ha detectado variedad Robusta
                orden = ["R_BUE", "R_NEG", "R_BRO", "R_QUE", "R_CER"]
            else:
                # Ambas variedades detectadas o lote inicial
                orden = list(ORDEN_13)
            mapa_acronimos = ACRONIMOS_13
        else:
            orden = list(ORDEN_TRI)
            mapa_acronimos = ACRONIMOS_TRI

        # Agrupar conteo por acrónimo estructurado
        conteos_agrupados = {acro: 0 for acro in orden}
        for clase, cant in conteo_crudo.items():
            acro = mapa_acronimos.get(clase, "G_DEF" if not es_13 else "A_BRO")
            if acro in conteos_agrupados:
                conteos_agrupados[acro] += cant

        valores = [conteos_agrupados[acro] for acro in orden]
        posiciones = np.arange(len(orden))

        # Colores de barras: Verde para sanos, ámbar para defectos fitosanitarios/mecánicos, rojo para críticos
        colores_barras = []
        for acro in orden:
            if acro in ("A_BUE", "R_BUE"):
                colores_barras.append(VERDE)
            elif acro in ("A_BRO", "R_BRO", "A_QUE", "R_QUE", "A_CON", "A_INM"):
                colores_barras.append(AMBAR_RESET)
            else:
                colores_barras.append(ROJO_PARO)

        altura_barra = 0.55 if len(orden) <= 3 else 0.6
        self.ax_analiticas.barh(posiciones, valores, color=colores_barras, height=altura_barra, align="center")
        self.ax_analiticas.set_yticks(posiciones)
        self.ax_analiticas.set_yticklabels(orden, color=GRIS_TEXTO, fontsize=12, fontweight="bold")
        self.ax_analiticas.tick_params(axis="x", colors=GRIS_TEXTO, labelsize=11)
        self.ax_analiticas.tick_params(axis="y", colors=GRIS_TEXTO)

        # Límite horizontal y enteros estrictos (sin números negativos ni decimales)
        max_val = max(valores) if valores else 0
        lim_derecho = max(5, int(np.ceil(max_val * 1.15)) if max_val > 0 else 5)
        self.ax_analiticas.set_xlim(left=0, right=lim_derecho)
        self.ax_analiticas.xaxis.set_major_locator(MaxNLocator(integer=True, min_n_ticks=3, nbins=6))

        # Renderizar etiquetas numéricas al costado de las barras cuando val > 0
        for i, val in enumerate(valores):
            if val > 0:
                self.ax_analiticas.text(
                    val + (lim_derecho * 0.015),
                    i,
                    str(val),
                    va="center",
                    ha="left",
                    fontsize=11,
                    fontweight="bold",
                    color=GRIS_TEXTO,
                )

        # Rejilla sutil horizontal y espinas en gris borde
        self.ax_analiticas.grid(axis="x", color="#E9ECE8", linestyle="--", alpha=0.9)
        for spine in self.ax_analiticas.spines.values():
            spine.set_color(GRIS_BORDE)
            spine.set_linewidth(1.0)

        self.ax_analiticas.invert_yaxis()
        self.fig_analiticas.subplots_adjust(left=0.14, right=0.96, top=0.97, bottom=0.08)
        self.canvas_analiticas.draw()

    # =========================================================================
    # ACCIONES DE LOTE Y SINCRONIZACIÓN BAJO DEMANDA
    # =========================================================================

    def _al_pulsar_terminar_lote(self) -> None:
        """Cierra manualmente el lote activo y persiste sus métricas en SQLite."""
        if getattr(self.gestor_lotes, "lote_activo", False):
            self.gestor_lotes.finalizar_lote()
            self.db_manager.registrar_log_local("INFO", "Lote finalizado manualmente desde Analíticas.")
            if "unittest" not in sys.modules:
                messagebox.showinfo("Lote Finalizado", "El lote activo ha sido cerrado y guardado correctamente.")
            self._actualizar_tarjetas_estadisticas()
            self._actualizar_indicador_bd_y_lotes()
        else:
            if "unittest" not in sys.modules:
                messagebox.showinfo("Información", "No hay un lote activo en este momento.")

    def _al_pulsar_sincronizar_db(self) -> None:
        """Ejecuta la sincronización de lotes pendientes hacia MongoDB en un hilo secundario."""
        def tarea_sync():
            try:
                subidos = self.db_manager.sincronizar_pendientes()
                self.db_manager.registrar_log_local(
                    "INFO", f"Sincronización manual completada: {subidos} registros subidos a la nube."
                )
                self.after(0, self._actualizar_indicador_bd_y_lotes)
            except Exception as e:
                self.db_manager.registrar_log_local("WARNING", f"Falla en sincronización manual: {e}")

        threading.Thread(target=tarea_sync, daemon=True).start()

    def _al_lote_finalizado_auto(self, resumen: Dict[str, Any]) -> None:
        """Callback ejecutado por GestorLotes cuando se cierra por inactividad."""
        self.db_manager.registrar_log_local(
            "INFO", f"Lote {resumen.get('id_lote', '')} finalizado por inactividad ({resumen.get('total_granos', 0)} granos)."
        )
        self.after(0, self._actualizar_indicador_bd_y_lotes)

    # =========================================================================
    # RELLENO DE REGISTROS (HISTORIAL Y CONSOLA DE AUDITORÍA LOGS)
    # =========================================================================

    def _poblar_tabla_historial(self) -> None:
        """Consulta lotes en SQLite y puebla las filas de la tabla Historial."""
        for w in self.cuerpo_tabla_historial.winfo_children():
            w.destroy()

        cat = self.menu_cat_historial.get()
        fecha = self.seg_fecha_historial.get()
        filtro_mod = None if cat == "Todos" else cat
        lotes = self.db_manager.obtener_historial_lotes(filtro_modelo=filtro_mod, filtro_fecha=fecha, limite=50)

        if not lotes:
            lbl_vacio = ctk.CTkLabel(
                self.cuerpo_tabla_historial,
                text="No hay lotes registrados para el criterio seleccionado.",
                font=("Arial", 18),
                text_color=GRIS_TEXTO,
            )
            lbl_vacio.pack(pady=20)
            return

        for idx, item in enumerate(lotes):
            color_fila = GRIS_PANEL if idx % 2 == 0 else "white"
            fila = ctk.CTkFrame(self.cuerpo_tabla_historial, fg_color=color_fila, corner_radius=0, height=48)
            fila.pack(fill="x", pady=(0, 2))
            fila.pack_propagate(False)

            id_limpio = str(item.get("id_lote", "")).replace("LOTE-", "")
            prop_str = str(item.get("prop_gb_ar_ro", f"{item.get('porcentaje_calidad', 0.0):.1f}%"))

            valores = [
                str(item.get("fecha", ""))[:16],
                id_limpio,
                str(item.get("total_granos", 0)),
                str(item.get("total_sanos", 0)),
                prop_str,
                f"{item.get('tiempo_min', 0.0):.1f}",
            ]
            for val, w in zip(valores, self.anchos_columnas_historial):
                ctk.CTkLabel(
                    fila, text=val, width=w, font=("Arial", 18), text_color=GRIS_TEXTO
                ).pack(side="left", padx=2)

    def _cargar_consola_logs(self) -> None:
        """Lee los eventos de logs_locales desde SQLite y los despliega en la consola."""
        tipo = self.menu_tipo_logs.get()
        fecha = self.seg_fecha_logs.get()
        filtro_tipo = None if tipo == "Todos" else tipo
        logs = self.db_manager.obtener_logs_locales(tipo=filtro_tipo, filtro_fecha=fecha, limite=100)

        self.logs_box.configure(state="normal")
        self.logs_box.delete("1.0", "end")

        if not logs:
            self.logs_box.insert("end", "[--:--:--] No se encontraron logs para los filtros seleccionados.\n")
        else:
            for ev in logs:
                ts = str(ev.get("timestamp", ""))[-8:]
                t = str(ev.get("tipo", "INFO")).upper()
                msg = str(ev.get("mensaje", ""))
                linea = f"[{ts}] {t:<7} - {msg}\n"

                tag = t if t in ("ALARM", "WARNING", "INFO") else "DEFAULT"
                self.logs_box.insert("end", linea, tag)

        self.logs_box.configure(state="disabled")

    # =========================================================================
    # COMPATIBILIDAD CON TESTS UNITARIOS PREVIOS
    # =========================================================================

    def _al_cambiar_switch_modelo_compat(self) -> None:
        es_13 = bool(self.switch_modelo.get())
        self._al_conmutar_modelo("13 Clases" if es_13 else "Tri-clase")

    def _al_cambiar_switch_sahi_compat(self) -> None:
        es_sahi = bool(self.switch_sahi.get())
        self.switch_sahi.configure(text=f"SAHI: {'ON' if es_sahi else 'OFF'}")
        self.gestor_lotes.configurar_modelo(
            modelo_13_clases=self.detector.es_modo_13clases, modo_sahi=es_sahi
        )

    def _al_cambiar_camara_top_compat(self, seleccion: str) -> None:
        nueva_top = self._parsear_fuente_texto(seleccion)
        anterior_top = self._fuente_top_actual
        if str(nueva_top) == str(self._fuente_bottom_actual):
            self._fuente_bottom_actual = anterior_top
            if hasattr(self, "combo_cam_bottom"):
                self.combo_cam_bottom.set(self._formatear_fuente_texto(anterior_top))
        self._fuente_top_actual = nueva_top
        if hasattr(self, "combo_cam_top"):
            self.combo_cam_top.set(self._formatear_fuente_texto(nueva_top))
        self.detector.cambiar_fuentes_video(self._fuente_top_actual, self._fuente_bottom_actual)

    def _al_cambiar_camara_bottom_compat(self, seleccion: str) -> None:
        nueva_bot = self._parsear_fuente_texto(seleccion)
        anterior_bot = self._fuente_bottom_actual
        if str(nueva_bot) == str(self._fuente_top_actual):
            self._fuente_top_actual = anterior_bot
            if hasattr(self, "combo_cam_top"):
                self.combo_cam_top.set(self._formatear_fuente_texto(anterior_bot))
        self._fuente_bottom_actual = nueva_bot
        if hasattr(self, "combo_cam_bottom"):
            self.combo_cam_bottom.set(self._formatear_fuente_texto(nueva_bot))
        self.detector.cambiar_fuentes_video(self._fuente_top_actual, self._fuente_bottom_actual)

    _al_cambiar_switch_modelo = _al_cambiar_switch_modelo_compat
    _al_cambiar_switch_sahi = _al_cambiar_switch_sahi_compat
    _al_cambiar_camara_top = _al_cambiar_camara_top_compat
    _al_cambiar_camara_bottom = _al_cambiar_camara_bottom_compat

    @staticmethod
    def _parsear_fuente_texto(texto: str) -> Union[int, str]:
        s = str(texto).strip()
        if "Demo" in s or "Sintético" in s or "demo" in s.lower():
            return "demo"
        for dig in ("0", "1", "2"):
            if dig in s:
                return int(dig)
        return s

    @staticmethod
    def _formatear_fuente_texto(fuente: Union[int, str]) -> str:
        s = str(fuente).strip().lower()
        if s in ("demo", "simulado", "synthetic"):
            return "Demo / Sintético"
        return f"Cámara {fuente}"

    def _abrir_ventana_logs_toplevel(self) -> None:
        if self._ventana_logs is None or not self._ventana_logs.winfo_exists():
            self._ventana_logs = VentanaLogsToplevel(self, self.db_manager)
        else:
            self._ventana_logs.focus()

    def _alternar_pantalla_completa(self, event=None) -> None:
        self._pantalla_completa = not self._pantalla_completa
        self.attributes("-fullscreen", self._pantalla_completa)

    def _al_cerrar(self) -> None:
        """Cierre ordenado liberando recursos, hilos y cámara."""
        self._bucle_video_activo = False
        self._bucle_analiticas_activo = False
        try:
            if hasattr(self, "_id_after_bucle") and self._id_after_bucle is not None:
                self.after_cancel(self._id_after_bucle)
        except Exception:
            pass

        try:
            if hasattr(self, "_id_after_analiticas") and self._id_after_analiticas is not None:
                self.after_cancel(self._id_after_analiticas)
        except Exception:
            pass

        try:
            if self.detector:
                self.detector.detener()
        except Exception:
            pass

        try:
            if self.esp32_bridge:
                self.esp32_bridge.control_banda(False)
                self.esp32_bridge.desconectar()
        except Exception:
            pass

        self.destroy()


if __name__ == "__main__":
    from core.metricas import GestorMetricas
    det = YOLODetector(ruta_modelo="models/best.pt", fuente_video="demo")
    met = GestorMetricas()
    app = DashboardCustomTkinter(detector=det, metricas=met)
    app.mainloop()
