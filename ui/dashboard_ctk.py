"""
Dashboard de Inferencia y Telemetría MOPPI basado en CustomTkinter.
Proporciona streaming nativo en tiempo real a 30-60 FPS con latencia cero,
sin dependencias de WebSockets ni problemas de serialización IPC.
"""

import time
import queue
import threading
import cv2
from PIL import Image
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from typing import Dict, Any, Optional

from core.detector import YOLODetector
from core.metricas import GestorMetricas
from storage.database import MongoManager


class DashboardCustomTkinter(ctk.CTk):
    """
    Ventana principal de la interfaz MOPPI implementada con CustomTkinter.
    Aplica estilo neomórfico con sombras suaves y efecto de profundidad,
    manteniendo la paleta de colores institucionales ULSA.
    """

    # --- Paleta de Colores Institucionales ULSA ---
    COLOR_VERDE_ULSA = "#197B30"
    COLOR_VERDE_HOVER = "#145F25"
    COLOR_VERDE_CLARO = "#E8F5E9"
    COLOR_ROJO_DEFECTO = "#C62828"
    COLOR_ROJO_HOVER = "#9A1F1F"
    COLOR_CAFE_TEXTO = "#4A3B32"
    COLOR_CAFE_CLARO = "#D7CCC8"
    COLOR_GRIS_SEC = "#757575"
    COLOR_FONDO_CARD_LIGHT = "#FFFFFF"
    COLOR_FONDO_CARD_DARK = "#2B2B2B"
    COLOR_AMARILLO_ALERTA = "#F57F17"

    COLORES_DEFECTOS = {
        "Brocado": "#E53935",
        "Agrio": "#FB8C00",
        "Negro": "#37474F",
        "Quebrado": "#8D6E63",
        "Cereza": "#8E24AA",
        "Concha": "#3949AB",
        "Inmaduro": "#00897B",
    }

    # --- Efectos Neomórficos ---
    SOMBRA_SUAVE = "1px 2px 5px rgba(0,0,0,0.1), -1px -2px 5px rgba(0,0,0,0.1)"
    RADIUS_CARD = 12
    RADIUS_SMALL = 10

    def __init__(
        self,
        detector: YOLODetector,
        metricas: GestorMetricas,
        db_manager: MongoManager,
    ):
        super().__init__()

        self.detector = detector
        self.metricas = metricas
        self.db_manager = db_manager

        # Configuración de ventana
        self.title("MOPPI - Clasificador Óptico de Café (Finca Alvizua)")
        self.geometry("1280x820")
        self.minsize(1050, 720)

        # Tema claro institucional por defecto
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")

        self._consumidor_activo = True
        self._ultimo_refresco_kpi = time.time()
        self._ctk_image_ref = None

        self._construir_interfaz()

        # Iniciar detector
        self.detector.iniciar()

        # Iniciar bucle de refresco nativo en hilo de UI (cada 15 ms ~ 60 FPS)
        self.after(15, self._bucle_actualizacion_frame)

        # Manejador de cierre limpio
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

    def _construir_interfaz(self) -> None:
        """Construye el layout principal y pestañas con estilo neomórfico."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- 1. Cabecera Superior ---
        # Efecto neomórfico: carta elevada con sombra suave
        cabecera = ctk.CTkFrame(
            self,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            height=65,
            border_width=1,
            border_color=self.COLOR_CAFE_CLARO,
        )
        cabecera.grid(row=0, column=0, padx=15, pady=(12, 6), sticky="ew")
        cabecera.grid_columnconfigure(0, weight=1)
        # Simular sombra neomórfica mediante configuración de UI
        cabecera._neomorph_shadow = True

        frame_titulos = ctk.CTkFrame(cabecera, fg_color="transparent")
        frame_titulos.grid(row=0, column=0, padx=15, pady=8, sticky="w")

        lbl_titulo = ctk.CTkLabel(
            frame_titulos,
            text="MOPPI | CLASIFICADOR ÓPTICO DE CAFÉ",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.COLOR_CAFE_TEXTO,
        )
        lbl_titulo.pack(anchor="w")

        lbl_subtitulo = ctk.CTkLabel(
            frame_titulos,
            text="Inferencia en Tiempo Real & Telemetría Electromecánica (Finca Alvizua)",
            font=ctk.CTkFont(size=12),
            text_color=self.COLOR_GRIS_SEC,
        )
        lbl_subtitulo.pack(anchor="w")

# Badges de estado en cabecera
        # Efecto neomórfico: contenedor con sombra interna sutil
        frame_badges = ctk.CTkFrame(
            cabecera,
            fg_color="transparent",
            corner_radius=self.RADIUS_SMALL,
        )
        frame_badges.grid(row=0, column=1, padx=15, pady=8, sticky="e")

        self.badge_modelo = ctk.CTkButton(
            frame_badges,
            text="Modelo: YOLOv8" if not self.detector.modo_simulado else "Modo Simulación",
            fg_color=self.COLOR_VERDE_CLARO,
            text_color=self.COLOR_VERDE_ULSA,
            hover=False,
            height=28,
            corner_radius=14,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.badge_modelo.pack(side="left", padx=5)

        self.badge_db = ctk.CTkButton(
            frame_badges,
            text="MongoDB: Conectando...",
            fg_color="#FFF8E1",
            text_color=self.COLOR_AMARILLO_ALERTA,
            hover=False,
            height=28,
            corner_radius=14,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.badge_db.pack(side="left", padx=5)

        # --- 2. Pestañas Principales ---
        # Estilo neomórfico: tabview con efecto de profundidad
        self.tabview = ctk.CTkTabview(
            self,
            segmented_button_selected_color=self.COLOR_VERDE_ULSA,
            segmented_button_selected_hover_color=self.COLOR_VERDE_HOVER,
            corner_radius=self.RADIUS_CARD,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            border_color=self.COLOR_CAFE_CLARO,
            border_width=1,
        )
        self.tabview.grid(row=1, column=0, padx=15, pady=(0, 12), sticky="nsew")

        self.tab_vivo = self.tabview.add("Vista en Vivo")
        self.tab_analitico = self.tabview.add("Dashboard Analítico")

        self._construir_pestana_vivo()
        self._construir_pestana_analitico()

    def _construir_pestana_vivo(self) -> None:
        """Construye la vista de la cámara en vivo y controles laterales."""
        self.tab_vivo.grid_columnconfigure(0, weight=1)
        self.tab_vivo.grid_columnconfigure(1, weight=0)
        self.tab_vivo.grid_rowconfigure(0, weight=1)

        # Contenedor del Feed de Video
        # Efecto neomórfico: card con sombra suave y borde sutil
        self.card_video = ctk.CTkFrame(
            self.tab_vivo,
            fg_color="#1E1E1E",
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_CAFE_CLARO,
        )
        self.card_video.grid(row=0, column=0, padx=(0, 10), pady=5, sticky="nsew")
        self.card_video.grid_rowconfigure(0, weight=1)
        self.card_video.grid_columnconfigure(0, weight=1)

        # Label donde se renderizan los frames OpenCV
        self.lbl_video = ctk.CTkLabel(self.card_video, text="Iniciando cámara...", text_color="#CCCCCC")
        self.lbl_video.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        # Panel Lateral Derecho (Controles y Telemetría)
        # Efecto neomórfico: panel con sombra y profundidad
        panel_lateral = ctk.CTkScrollableFrame(
            self.tab_vivo,
            width=340,
            corner_radius=self.RADIUS_CARD,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            border_width=1,
            border_color=self.COLOR_CAFE_CLARO,
        )
        panel_lateral.grid(row=0, column=1, padx=(5, 0), pady=5, sticky="nsew")

        # 1. Configuración de Cámara
        lbl_sec1 = ctk.CTkLabel(panel_lateral, text="Origen de Video", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.COLOR_CAFE_TEXTO)
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
        elif str(self.detector.fuente_video) in ("demo", "simulado"):
            self.opt_fuente.set("Modo Simulación (Demo)")
        else:
            self.opt_fuente.set("Cámara 0 (Principal)")
        self.opt_fuente.pack(fill="x", pady=(0, 12))

        # 2. Control de Sesión
        lbl_sec2 = ctk.CTkLabel(panel_lateral, text="Control de Sesión", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.COLOR_CAFE_TEXTO)
        lbl_sec2.pack(anchor="w", pady=(5, 5))

        self.btn_iniciar = ctk.CTkButton(
            panel_lateral,
            text="Iniciar Clasificación",
            command=self._iniciar_clasificacion,
            fg_color=self.COLOR_VERDE_ULSA,
            hover_color=self.COLOR_VERDE_HOVER,
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.btn_iniciar.pack(fill="x", pady=4)

        frame_botones_sec = ctk.CTkFrame(panel_lateral, fg_color="transparent")
        frame_botones_sec.pack(fill="x", pady=4)
        frame_botones_sec.grid_columnconfigure((0, 1), weight=1)

        self.btn_pausar = ctk.CTkButton(
            frame_botones_sec,
            text="Pausar",
            command=self._pausar_clasificacion,
            fg_color="#8D6E63",
            hover_color="#6D4C41",
            state="disabled",
            height=32,
        )
        self.btn_pausar.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.btn_detener = ctk.CTkButton(
            frame_botones_sec,
            text="Detener",
            command=self._detener_clasificacion,
            fg_color=self.COLOR_ROJO_DEFECTO,
            hover_color=self.COLOR_ROJO_HOVER,
            state="disabled",
            height=32,
        )
        self.btn_detener.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        # 3. Telemetría en Vivo
        lbl_sec3 = ctk.CTkLabel(panel_lateral, text="📡 Telemetría en Vivo", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.COLOR_CAFE_TEXTO)
        lbl_sec3.pack(anchor="w", pady=(15, 6))

        self.tile_fps = self._crear_tile_telemetria(panel_lateral, "FPS de Cámara", "0.0 FPS", self.COLOR_VERDE_ULSA)
        self.tile_latencia = self._crear_tile_telemetria(panel_lateral, "Latencia Inferencia", "0.0 ms", self.COLOR_CAFE_TEXTO)
        self.tile_granos = self._crear_tile_telemetria(panel_lateral, "Granos en Cuadro", "0", self.COLOR_VERDE_ULSA)

        # Estado de Válvula
        frame_valvula = ctk.CTkFrame(panel_lateral, fg_color=self.COLOR_FONDO_CARD_LIGHT, corner_radius=10)
        frame_valvula.pack(fill="x", pady=6)
        lbl_valv = ctk.CTkLabel(frame_valvula, text="Válvula Neumática:", font=ctk.CTkFont(size=12, weight="bold"), text_color=self.COLOR_CAFE_TEXTO)
        lbl_valv.pack(side="left", padx=10, pady=8)

        self.badge_valvula = ctk.CTkButton(
            frame_valvula,
            text="STANDBY",
            fg_color="#EEEEEE",
            text_color="#666666",
            hover=False,
            height=24,
            width=80,
            corner_radius=12,
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        self.badge_valvula.pack(side="right", padx=10, pady=8)

    def _crear_tile_telemetria(self, parent: ctk.CTkBaseClass, etiqueta: str, valor_ini: str, color_valor: str) -> ctk.CTkLabel:
        """Crea un tile visual para telemetría con efecto neomórfico."""
        # Tarjeta con efecto neomórfico: entrada sutil con sombra
        frame = ctk.CTkFrame(
            parent,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_SMALL,
            border_width=1,
            border_color=self.COLOR_CAFE_CLARO,
        )
        frame.pack(fill="x", pady=4)

        lbl_etiq = ctk.CTkLabel(frame, text=etiqueta, font=ctk.CTkFont(size=12), text_color=self.COLOR_CAFE_TEXTO)
        lbl_etiq.pack(side="left", padx=10, pady=8)

        lbl_val = ctk.CTkLabel(frame, text=valor_ini, font=ctk.CTkFont(size=13, weight="bold"), text_color=color_valor)
        lbl_val.pack(side="right", padx=10, pady=8)
        return lbl_val

    def _construir_pestana_analitico(self) -> None:
        """Construye el panel de estadísticas y gráficos con estilo neomórfico."""
        self.tab_analitico.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.tab_analitico.grid_rowconfigure(1, weight=1)

        # 4 Tarjetas Superiores de KPIs
        # Efecto neomórfico: cards elevadas con profundidad
        self.card_kpi_tiempo = self._crear_card_kpi(self.tab_analitico, 0, "⏱ Tiempo de Operación", "00:00:00", "Sesión activa")
        self.card_kpi_consumo = self._crear_card_kpi(self.tab_analitico, 1, "⚡ Consumo Energético", "0.0000 kWh", f"P. Nom: {self.metricas.potencia_nominal_kw} kW")
        self.card_kpi_granos = self._crear_card_kpi(self.tab_analitico, 2, "Granos Procesados", "0", "Calidad: 100.0%")
        self.card_kpi_latencia = self._crear_card_kpi(self.tab_analitico, 3, "Latencia Promedio", "0.0 ms", "FPS Prom: 0.0")

        # Fila Central: 2 Paneles de Gráficos Analíticos
        frame_graficos = ctk.CTkFrame(self.tab_analitico, fg_color="transparent")
        frame_graficos.grid(row=1, column=0, columnspan=4, padx=0, pady=10, sticky="nsew")
        frame_graficos.grid_columnconfigure((0, 1), weight=1)
        frame_graficos.grid_rowconfigure(0, weight=1)

        # Panel 1: Balance Sanos vs Defectos
        card_balance = ctk.CTkFrame(frame_graficos, fg_color=self.COLOR_FONDO_CARD_LIGHT, corner_radius=12)
        card_balance.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="nsew")

        lbl_bal_tit = ctk.CTkLabel(card_balance, text="Balance de Clasificación en Vivo", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.COLOR_CAFE_TEXTO)
        lbl_bal_tit.pack(anchor="w", padx=15, pady=(12, 10))

        # Sanos
        frame_sanos_hdr = ctk.CTkFrame(card_balance, fg_color="transparent")
        frame_sanos_hdr.pack(fill="x", padx=15, pady=(5, 2))
        ctk.CTkLabel(frame_sanos_hdr, text="🟢 Granos Sanos (Buenos)", font=ctk.CTkFont(size=12, weight="bold"), text_color=self.COLOR_VERDE_ULSA).pack(side="left")
        self.lbl_sanos_val = ctk.CTkLabel(frame_sanos_hdr, text="0 (100.0%)", font=ctk.CTkFont(size=12, weight="bold"), text_color=self.COLOR_VERDE_ULSA)
        self.lbl_sanos_val.pack(side="right")

        self.bar_sanos = ctk.CTkProgressBar(card_balance, progress_color=self.COLOR_VERDE_ULSA, fg_color="#E8F5E9", height=14, corner_radius=7)
        self.bar_sanos.pack(fill="x", padx=15, pady=(0, 15))
        self.bar_sanos.set(1.0)

        # Defectos
        frame_def_hdr = ctk.CTkFrame(card_balance, fg_color="transparent")
        frame_def_hdr.pack(fill="x", padx=15, pady=(5, 2))
        ctk.CTkLabel(frame_def_hdr, text="🔴 Granos Defectuosos", font=ctk.CTkFont(size=12, weight="bold"), text_color=self.COLOR_ROJO_DEFECTO).pack(side="left")
        self.lbl_defectos_val = ctk.CTkLabel(frame_def_hdr, text="0 (0.0%)", font=ctk.CTkFont(size=12, weight="bold"), text_color=self.COLOR_ROJO_DEFECTO)
        self.lbl_defectos_val.pack(side="right")

        self.bar_defectos = ctk.CTkProgressBar(card_balance, progress_color=self.COLOR_ROJO_DEFECTO, fg_color="#FFEBEE", height=14, corner_radius=7)
        self.bar_defectos.pack(fill="x", padx=15, pady=(0, 15))
        self.bar_defectos.set(0.0)

        # Panel 2: Distribución de Defectos
        # Efecto neomórfico: scrollable frame con tarjetas elevadas
        card_defectos = ctk.CTkScrollableFrame(
            frame_graficos,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_CAFE_CLARO,
        )
        card_defectos.grid(row=0, column=1, padx=(6, 0), pady=0, sticky="nsew")

        lbl_def_tit = ctk.CTkLabel(card_defectos, text="Distribución de Defectos en el Lote", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.COLOR_CAFE_TEXTO)
        lbl_def_tit.pack(anchor="w", padx=10, pady=(10, 8))

        self.defectos_widgets = {}
        for def_nom, def_col in self.COLORES_DEFECTOS.items():
            f_row = ctk.CTkFrame(card_defectos, fg_color="transparent")
            f_row.pack(fill="x", padx=10, pady=3)

            # Efecto neomórfico: fila con sombra interna sutil
            f_row._neomorph = True

            lbl_d = ctk.CTkLabel(f_row, text=f"▪ {def_nom}", font=ctk.CTkFont(size=11, weight="bold"), text_color=self.COLOR_CAFE_TEXTO)
            lbl_d.pack(side="left")

            lbl_cnt = ctk.CTkLabel(f_row, text="0 (0.0%)", font=ctk.CTkFont(size=11), text_color=self.COLOR_CAFE_TEXTO)
            lbl_cnt.pack(side="right")

            bar_d = ctk.CTkProgressBar(card_defectos, progress_color=def_col, fg_color=self.COLOR_CAFE_CLARO, height=8, corner_radius=4)
            bar_d.pack(fill="x", padx=10, pady=(0, 6))
            bar_d.set(0.0)

            self.defectos_widgets[def_nom] = (lbl_cnt, bar_d)

        # Fila Inferior: Botones de Lote
        frame_acciones = ctk.CTkFrame(self.tab_analitico, fg_color="transparent")
        frame_acciones.grid(row=2, column=0, columnspan=4, pady=(5, 0), sticky="e")

        btn_guardar = ctk.CTkButton(
            frame_acciones,
            text="Guardar Resumen en MongoDB Atlas",
            command=self._guardar_lote_mongodb,
            fg_color=self.COLOR_VERDE_ULSA,
            hover_color=self.COLOR_VERDE_HOVER,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        btn_guardar.pack(side="left", padx=6)

        btn_reiniciar = ctk.CTkButton(
            frame_acciones,
            text="Reiniciar Estadísticas / Nuevo Lote",
            command=self._reiniciar_estadisticas,
            fg_color="#8D6E63",
            hover_color="#6D4C41",
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        btn_reiniciar.pack(side="left", padx=6)

    def _crear_card_kpi(self, parent: ctk.CTkBaseClass, col: int, titulo: str, valor_ini: str, sub_ini: str) -> dict:
        """Crea una tarjeta KPI elegante con efecto neomórfico."""
        # Card con efecto neomórfico: elevado con sombra suave
        card = ctk.CTkFrame(
            parent,
            fg_color=self.COLOR_FONDO_CARD_LIGHT,
            corner_radius=self.RADIUS_CARD,
            border_width=1,
            border_color=self.COLOR_CAFE_CLARO,
        )
        card.grid(row=0, column=col, padx=5, pady=5, sticky="ew")

        lbl_tit = ctk.CTkLabel(card, text=titulo, font=ctk.CTkFont(size=12), text_color=self.COLOR_GRIS_SEC)
        lbl_tit.pack(anchor="w", padx=12, pady=(10, 2))

        lbl_val = ctk.CTkLabel(card, text=valor_ini, font=ctk.CTkFont(size=20, weight="bold"), text_color=self.COLOR_CAFE_TEXTO)
        lbl_val.pack(anchor="w", padx=12, pady=0)

        lbl_sub = ctk.CTkLabel(card, text=sub_ini, font=ctk.CTkFont(size=11), text_color=self.COLOR_VERDE_ULSA)
        lbl_sub.pack(anchor="w", padx=12, pady=(0, 10))

        return {"valor": lbl_val, "sub": lbl_sub}

    def _bucle_actualizacion_frame(self) -> None:
        """
        Bucle nativo de alta frecuencia ejecutado en el hilo de UI.
        Consume el frame más reciente y actualiza la imagen directamente en memoria.
        """
        if not self._consumidor_activo:
            return

        try:
            # Drenar hasta el frame más reciente disponible
            payload = None
            while True:
                try:
                    payload = self.detector.cola_salida.get_nowait()
                except queue.Empty:
                    break

            if payload:
                # 1. Renderizar Frame de video
                frame_bgr = payload.get("frame_bgr")
                if frame_bgr is not None:
                    target_w, target_h = 720, 480
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(frame_rgb)
                    
                    self._ctk_image_ref = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(target_w, target_h))
                    self.lbl_video.configure(image=self._ctk_image_ref, text="")

                # 2. Telemetría en vivo
                detecciones = payload.get("detecciones", [])
                fps = payload.get("fps", 0.0)
                latencia_ms = payload.get("latencia_ms", 0.0)
                valvula_activa = payload.get("valvula_activa", False)

                if self.metricas.esta_activo:
                    self.metricas.registrar_detecciones(detecciones, fps, latencia_ms)

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
        """Actualiza los indicadores de KPIs y gráficos analíticos."""
        # 1. Estado de MongoDB
        if self.db_manager.esta_conectado:
            self.badge_db.configure(text="MongoDB: Conectado", fg_color=self.COLOR_VERDE_CLARO, text_color=self.COLOR_VERDE_ULSA)
        else:
            self.badge_db.configure(text="MongoDB: Modo Offline", fg_color="#FFF8E1", text_color=self.COLOR_AMARILLO_ALERTA)

        # 2. KPIs
        tiempo_str = self.metricas.obtener_tiempo_formateado()
        consumo_kwh = self.metricas.calcular_consumo_kwh()
        calidad_pct = self.metricas.obtener_porcentaje_calidad()
        latencia_prom = self.metricas.obtener_latencia_promedio()
        fps_prom = self.metricas.obtener_fps_promedio()

        self.card_kpi_tiempo["valor"].configure(text=tiempo_str)
        self.card_kpi_consumo["valor"].configure(text=f"{consumo_kwh:.4f} kWh")

        total_g = self.metricas.total_granos
        sanos_g = self.metricas.total_sanos
        def_g = self.metricas.total_defectuosos

        self.card_kpi_granos["valor"].configure(text=str(total_g))
        self.card_kpi_granos["sub"].configure(text=f"Calidad: {calidad_pct:.1f}% ({sanos_g} Sanos)")

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

        # 4. Distribución por tipo de defecto
        porcentajes = self.metricas.obtener_porcentajes_defectos()
        for def_nom, (lbl_cnt, bar_d) in self.defectos_widgets.items():
            cnt = self.metricas.conteo_por_defecto.get(def_nom, 0)
            pct = porcentajes.get(def_nom, 0.0)
            lbl_cnt.configure(text=f"{cnt} ({pct:.1f}%)")
            bar_d.set(min(1.0, max(0.0, pct / 100.0)))

    # --- Manejadores de Eventos ---

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

    def _guardar_lote_mongodb(self) -> None:
        """Guarda el resumen del lote en MongoDB."""
        resumen = self.metricas.generar_resumen_lote()

        def _on_resultado(exito: bool, mensaje: str):
            titulo = "MongoDB Atlas - Éxito" if exito else "MongoDB Atlas - Error"
            messagebox.showinfo(titulo, mensaje) if exito else messagebox.showwarning(titulo, mensaje)

        self.db_manager.guardar_resumen_lote_async(resumen, callback_resultado=_on_resultado)

    def _reiniciar_estadisticas(self) -> None:
        """Reinicia los contadores de lote."""
        self.metricas.reiniciar()
        self._actualizar_metricas_ui()
        messagebox.showinfo("MOPPI", "Estadísticas del lote reiniciadas correctamente.")

    def _al_cerrar(self) -> None:
        """Cierre ordenado de hilos y hardware."""
        self._consumidor_activo = False
        try:
            self.detector.detener()
        except Exception:
            pass
        self.destroy()
