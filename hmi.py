import customtkinter as ctk
import tkinter as tk

# Configuración inicial del tema y color visual
ctk.set_appearance_mode("light")  # El diseño usa fondo claro
ctk.set_default_color_theme("green")

# =====================================================================
# PALETA INSTITUCIONAL — Estilo tablero HMI industrial (Verdes/Grises)
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


class InterfazApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configuración de la ventana principal
        self.title("Panel de Control")
        self.geometry("1280x800")
        self.configure(fg_color=GRIS_FONDO) # Fondo gris muy claro general

        # Configurar pesos de la cuadrícula principal
        self.grid_columnconfigure(0, weight=0) 
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)    

        # --- 1. BARRA SUPERIOR COMPARTIDA (pestañas + bloques izquierdos) ---
        self.crear_barra_superior()

        # --- 2. PÁGINAS (se intercambian en la misma celda row=1) ---
        self.crear_pagina_dashboard()
        self.crear_pagina_analiticas()
        self.crear_pagina_registros()

        # Mapas para el cambio de ventanas
        self._paginas = {
            "Dashboard":  self.pagina_dashboard,
            "Analíticas": self.pagina_analiticas,
            "Registros":  self.pagina_registros
        }
        self._barras_izq = {
            "Dashboard":  self.barra_izq_dashboard,
            "Analíticas": self.barra_izq_analiticas
            # "Registros" no tiene controles propios todavía
        }

        # Conectar las pestañas con el cambio de ventana real
        # (se configura aquí, cuando las páginas ya existen)
        self.pestañas.configure(command=self.cambiar_pagina)

        # Ventana inicial
        self.cambiar_pagina("Dashboard")

    # =====================================================================
    #  BARRA SUPERIOR
    # =====================================================================
    def crear_barra_superior(self):
        # ----------------------------------------------
        # BLOQUE DERECHO COMPARTIDO: El botón segmentado (Pestañas)
        # Siempre vive en la columna 1 con los mismos márgenes que
        # el panel inferior (padx=(10, 20)) -> extremos alineados.
        # ----------------------------------------------
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
            font=("Arial", 24), 
            corner_radius=40
        )
        self.pestañas.set("Dashboard")
        self.pestañas.grid(row=0, column=1, sticky="new", padx=(10, 20), pady=15)

        # Configuración compartida de los controles verdes de la barra
        self.config_btn_superior = {
            "fg_color": VERDE,
            "hover_color": VERDE_HOVER,
            "text_color": "white",
            "corner_radius": 40,
            "border_width": 2,
            "border_color": VERDE_CLARO,
            "height": 80,
            "font": ("Arial", 24, "bold")
        }

        self.crear_bloque_izq_dashboard()
        self.crear_bloque_izq_analiticas()

    def crear_bloque_izq_dashboard(self):
        # Bloque izquierdo del DASHBOARD: ocupa la misma columna 0 que el visor
        self.barra_izq_dashboard = ctk.CTkFrame(self, fg_color="transparent")
        self.barra_izq_dashboard.grid(row=0, column=0, sticky="new", padx=(20, 10), pady=15)

        # Sus 3 columnas con el mismo peso elástico
        self.barra_izq_dashboard.grid_columnconfigure(0, weight=1)
        self.barra_izq_dashboard.grid_columnconfigure(1, weight=1)
        self.barra_izq_dashboard.grid_columnconfigure(2, weight=1)

        btn_posicion = ctk.CTkButton(
            self.barra_izq_dashboard, 
            text="Cambiar Posición  ▾", 
            **self.config_btn_superior
        )
        btn_posicion.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        btn_modelos = ctk.CTkButton(
            self.barra_izq_dashboard, 
            text="Modelos  ▾", 
            **self.config_btn_superior
        )
        btn_modelos.grid(row=0, column=1, sticky="ew", padx=10)

        btn_orden = ctk.CTkButton(
            self.barra_izq_dashboard, 
            text="↕", 
            **self.config_btn_superior
        )
        btn_orden.grid(row=0, column=2, sticky="ew", padx=(10, 20))

    def crear_bloque_izq_analiticas(self):
        # Bloque izquierdo de ANALÍTICAS:
        # 1) Indicador de conexión MongoDB (píldora con LED interno)
        # 2) Contador de número de lotes (solo lectura, el backend lo actualiza)
        # 3) Botón de cambio de modelo (igual que en Dashboard)
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
            "height": 80
        }

        # --- 1) Indicador "Base de Datos" con círculo interno ---
        pill_db = ctk.CTkFrame(self.barra_izq_analiticas, **config_pildora, width=250)
        pill_db.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        pill_db.pack_propagate(False) # Mantener altura exacta de 80px

        inner_db = ctk.CTkFrame(pill_db, fg_color="transparent")
        inner_db.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(inner_db, text="Base de Datos", font=("Arial", 24), text_color=GRIS_TEXTO).pack(side="left", padx=(0, 10))

        # 🔘 LED interno (se conserva como self.led_mongo para el backend):
        #   Conectado   -> fg_color=VERDE_LED
        #   Desconectado-> fg_color=GRIS_MEDIO   (estado inicial)
        #   Error       -> fg_color=ROJO_PARO
        self.led_mongo = ctk.CTkFrame(inner_db, width=34, height=34, corner_radius=17, fg_color=GRIS_MEDIO)
        self.led_mongo.pack(side="left")

        # --- 2) Contador de lotes (indicador de solo lectura) ---
        pill_lotes = ctk.CTkFrame(self.barra_izq_analiticas, **config_pildora)
        pill_lotes.grid(row=0, column=1, sticky="ew", padx=10)
        pill_lotes.pack_propagate(False)

        # Se conserva como self.lbl_lotes: el backend hace
        #   self.lbl_lotes.configure(text=f"Lotes:  {n}")
        self.lbl_lotes = ctk.CTkLabel(pill_lotes, text="Lotes:  ---", font=("Arial", 24), text_color=GRIS_TEXTO)
        self.lbl_lotes.place(relx=0.5, rely=0.5, anchor="center")

        # --- 3) Botón Modelos (idéntico al del Dashboard) ---
        btn_modelos = ctk.CTkButton(
            self.barra_izq_analiticas, 
            text="Modelos  ▾", 
            **self.config_btn_superior
        )
        btn_modelos.grid(row=0, column=2, sticky="ew", padx=(10, 20))

    # =====================================================================
    #  CAMBIO DE VENTANAS
    # =====================================================================
    def cambiar_pagina(self, nombre):
        # Ocultar todo y mostrar solo la ventana pedida
        for pagina in self._paginas.values():
            pagina.grid_remove()
        for barra in self._barras_izq.values():
            barra.grid_remove()

        self._paginas[nombre].grid()
        if nombre in self._barras_izq:
            self._barras_izq[nombre].grid()

        # Subrayado de la pestaña activa (como en el wireframe)
        for nombre_btn, boton in self.pestañas._buttons_dict.items():
            if nombre_btn == nombre:
                boton.configure(font=("Arial", 24, "underline"), text_color="white")
            else:
                boton.configure(font=("Arial", 24), text_color=GRIS_TEXTO)

    # =====================================================================
    #  PÁGINA: DASHBOARD
    # =====================================================================
    def crear_pagina_dashboard(self):
        # Contenedor que abarca ambas columnas: al replicar internamente
        # los pesos (0 fijo / 1 elástico) y márgenes, la geometría queda
        # idéntica a la del wireframe original.
        self.pagina_dashboard = ctk.CTkFrame(self, fg_color="transparent")
        self.pagina_dashboard.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.pagina_dashboard.grid_columnconfigure(0, weight=0)
        self.pagina_dashboard.grid_columnconfigure(1, weight=1)
        self.pagina_dashboard.grid_rowconfigure(0, weight=1)

        self.crear_area_visualizador()
        self.crear_panel_control()

    def crear_area_visualizador(self):
        # Visor de cámara estilo pantalla HMI: acero oscuro con bisel verde
        self.frame_grafico = ctk.CTkFrame(
            self.pagina_dashboard, 
            fg_color=GRIS_OSCURO, 
            corner_radius=15,
            border_width=2,
            border_color=VERDE_CLARO,
            width=640,
            height=640)
        self.frame_grafico.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=(0, 20))

        # Evita que los widgets internos deformen las medidas de 640x640
        self.frame_grafico.grid_propagate(False)
        self.frame_grafico.pack_propagate(False)

        # Insignias oscuras con texto verde (estilo telemetría)
        config_insignia = {
            "fg_color": GRIS_OSCURO_2,
            "text_color": VERDE_LED,
            "corner_radius": 15,
            "width": 80,
            "height": 30,
            "font": ("Consolas", 16, "bold")
        }
        lbl_ms = ctk.CTkLabel(self.frame_grafico, text="ms:  --", **config_insignia)
        lbl_ms.place(relx=0.75, rely=0.03, anchor="ne")

        lbl_fps = ctk.CTkLabel(self.frame_grafico, text="FPS: --", **config_insignia)
        lbl_fps.place(relx=0.95, rely=0.03, anchor="ne")

        # Nota: aquí se incrustará el reproductor de video de la cámara seleccionada.

    def crear_panel_control(self):
        # Contenedor principal derecho (Superficie clara con ribete sutil)
        panel_derecho = ctk.CTkFrame(
            self.pagina_dashboard, 
            fg_color=GRIS_PANEL, 
            corner_radius=15,
            border_width=1,
            border_color=GRIS_BORDE)
        panel_derecho.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=(0, 20))

        # Sub-distribución en 3 columnas dentro del panel de control
        panel_derecho.grid_columnconfigure(0, weight=1) # Columna BOTONERIA
        panel_derecho.grid_columnconfigure(1, weight=1) # Columna CANALES
        panel_derecho.grid_columnconfigure(2, weight=1) # Columna TRIGGER y Aplicar
        panel_derecho.grid_rowconfigure(1, weight=1)

        # ----------------------------------------------------
        # COLUMNA 1: BOTONERÍA (Grandes)
        # ----------------------------------------------------
        col_botoneria = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        col_botoneria.grid(row=1, column=0, sticky="nsew", pady=10)

        ctk.CTkLabel(col_botoneria, text="BOTONERÍA", font=("Arial", 24, "bold"), text_color=GRIS_TEXTO).pack(pady=(10, 20))
        
        # Botonera con la convención cromática industrial HMI:
        # Marcha = Verde | Paro = Rojo | Reset = Ámbar
        config_marcha = {"fg_color": VERDE,      "hover_color": VERDE_HOVER, "text_color": "white", "border_width": 2, "border_color": VERDE_HOVER}
        config_paro   = {"fg_color": ROJO_PARO,  "hover_color": ROJO_HOVER,  "text_color": "white", "border_width": 2, "border_color": ROJO_HOVER}
        config_reset  = {"fg_color": AMBAR_RESET,"hover_color": AMBAR_HOVER, "text_color": "white", "border_width": 2, "border_color": AMBAR_HOVER}
        
        ctk.CTkButton(col_botoneria, text="M", font=("Arial", 24, "bold"), width=140, height=140, corner_radius=70, **config_marcha).pack(pady=10)
        ctk.CTkButton(col_botoneria, text="P", font=("Arial", 24, "bold"), width=140, height=140, corner_radius=70, **config_paro).pack(pady=20)
        ctk.CTkButton(col_botoneria, text="R", font=("Arial", 24, "bold"), width=140, height=140, corner_radius=70, **config_reset).pack(pady=10)

        # Línea divisoria derecha
        div_intermedio = ctk.CTkFrame(panel_derecho, width=2, fg_color=GRIS_BORDE)
        div_intermedio.grid(row=1, column=0, sticky="nse", pady=20)

        # ----------------------------------------------------
        # COLUMNA 2: CANALES (Luces indicadoras con líneas divisorias)
        # ----------------------------------------------------
        div_izq = ctk.CTkFrame(panel_derecho, width=2, fg_color=GRIS_BORDE)
        div_izq.grid(row=1, column=1, sticky="nsw", pady=20)

        col_canales = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        col_canales.grid(row=1, column=1, sticky="nsew", pady=10)

        ctk.CTkLabel(col_canales, text="CANALES", font=("Arial", 24, "bold"), text_color=GRIS_TEXTO).pack(side="top", pady=(10, 20))
        
        frame_grid_canales = ctk.CTkFrame(col_canales, fg_color="transparent")
        frame_grid_canales.pack(side="top", fill="both", expand=True)

        frame_grid_canales.grid_columnconfigure(0, weight=1)
        frame_grid_canales.grid_rowconfigure(0, weight=2) # Canal 0
        frame_grid_canales.grid_rowconfigure(1, weight=2) # Canal 1
        frame_grid_canales.grid_rowconfigure(2, weight=2) # Canal 2
        frame_grid_canales.grid_rowconfigure(3, weight=2) # Canal 3

        # Canales como LÁMPARAS INDICADORAS (LED de tablero):
        # son SOLO indicadores visuales -> sin hover ni cursor interactivo.
        # Se encenderán únicamente cuando el programa detecte el cruce de un grano:
        #   canal.configure(fg_color=VERDE_LED,  text_color="white")    # encender
        #   canal.configure(fg_color=GRIS_SUAVE, text_color=GRIS_MEDIO) # apagar
        config_botones_pequeños = {
            "fg_color": GRIS_SUAVE, 
            "text_color": GRIS_MEDIO, 
            "border_width": 2, 
            "border_color": VERDE_CLARO, 
            "hover": False,              # La luz NO reacciona al cursor, solo al sistema
            "cursor": "arrow",           # Cursor neutro: no es un control, es un indicador
            "width": 80, 
            "height": 80, 
            "corner_radius": 40, 
            "font": ("Arial", 24, "bold")
        }
        
        # Se guardan en self.luces_canales para que el backend las encienda/apague
        self.luces_canales = []
        for i in range(4):
            btn_canal = ctk.CTkButton(frame_grid_canales, text=str(i), **config_botones_pequeños)
            btn_canal.grid(row=i, column=0, sticky="", pady=0)
            self.luces_canales.append(btn_canal)

        # Línea divisoria derecha
        div_der = ctk.CTkFrame(panel_derecho, width=2, fg_color=GRIS_BORDE)
        div_der.grid(row=1, column=1, sticky="nse", pady=20)

        # ----------------------------------------------------
        # COLUMNA 3: TRIGGER Y ACCIONES
        # ----------------------------------------------------
        col_trigger = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        col_trigger.grid(row=1, column=2, sticky="nsew", pady=10)

        ctk.CTkLabel(col_trigger, text="TRIGGER", font=("Arial", 24, "bold"), text_color=GRIS_TEXTO).pack(pady=(10, 10))

        frame_slider_grupo = ctk.CTkFrame(col_trigger, fg_color="transparent")
        frame_slider_grupo.pack(pady=10)

        # Indicador superior que cambia en tiempo real
        self.lbl_valor = ctk.CTkLabel(frame_slider_grupo, text="50%", font=("Arial", 16, "bold"), text_color=VERDE)
        self.lbl_valor.pack(side="top", pady=(0, 5))

        def actualizar_valor_slider(valor_actual):
            valor_entero = int(valor_actual)
            self.lbl_valor.configure(text=f"{valor_entero}%")

        # Slider vertical integrado con la lógica dinámica
        slider = ctk.CTkSlider(
            frame_slider_grupo, 
            orientation="vertical", 
            from_=0, 
            to=100, 
            number_of_steps=100, 
            fg_color=GRIS_SUAVE, 
            progress_color=VERDE, 
            button_color=VERDE, 
            button_hover_color=VERDE_HOVER,
            height=260, 
            width=30, 
            corner_radius=15,
            button_length=24,
            command=actualizar_valor_slider
        )
        slider.pack(side="top")
        slider.set(50)

        lbl_min = ctk.CTkLabel(frame_slider_grupo, text="0%", font=("Arial", 14, "bold"), text_color=GRIS_MEDIO)
        lbl_min.pack(side="top", pady=(5, 0))

        # Botones de acción inferiores (Cancelar / Aplicar)
        btn_cancelar = ctk.CTkButton(col_trigger, text="Cancelar", fg_color=GRIS_SUAVE, hover_color=GRIS_SUAVE_HOV, text_color=GRIS_TEXTO, corner_radius=30, width=135, height=55, font=("Arial", 24, "bold"))
        btn_cancelar.pack(pady=(20, 5))

        btn_aplicar = ctk.CTkButton(col_trigger, text="Aplicar", fg_color=VERDE, hover_color=VERDE_HOVER, text_color="white", corner_radius=30, width=150, height=55, font=("Arial", 24, "bold"))
        btn_aplicar.pack(pady=5)

    # =====================================================================
    #  PÁGINA: ANALÍTICAS
    # =====================================================================
    def crear_pagina_analiticas(self):
        # Contenedor que abarca ambas columnas, con la misma grilla raíz
        # que el Dashboard: col 0 fija (gráfico 634x619), col 1 elástica.
        self.pagina_analiticas = ctk.CTkFrame(self, fg_color="transparent")
        self.pagina_analiticas.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.pagina_analiticas.grid_columnconfigure(0, weight=0)
        self.pagina_analiticas.grid_columnconfigure(1, weight=1)
        self.pagina_analiticas.grid_rowconfigure(0, weight=1)

        self.crear_area_grafico()
        self.crear_panel_estadisticas()

    def crear_area_grafico(self):
        # Gráfico de barras horizontales (cantidad de granos por categoría).
        # Mismo lenguaje visual que el visor de cámara:
        # pantalla HMI de acero oscuro con bisel verde. Tamaño: 634 x 619.
        self.frame_grafico_analiticas = ctk.CTkFrame(
            self.pagina_analiticas,
            fg_color=GRIS_OSCURO,
            corner_radius=15,
            border_width=2,
            border_color=VERDE_CLARO,
            width=634,
            height=619)
        self.frame_grafico_analiticas.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=(0, 20))

        self.frame_grafico_analiticas.grid_propagate(False)
        self.frame_grafico_analiticas.pack_propagate(False)

        # Leyenda superior
        ctk.CTkLabel(
            self.frame_grafico_analiticas, 
            text="Frecuencia / Categoría", 
            font=("Arial", 24, "bold"), 
            text_color=TEXTO_CLARO
        ).place(relx=0.5, rely=0.065, anchor="center")

        # Ejes del gráfico (placeholder en forma de "L", como el wireframe).
        # Aquí se incrustarán las barras horizontales cuando llegue el backend.
        self.canvas_ejes = tk.Canvas(
            self.frame_grafico_analiticas, 
            bg=GRIS_OSCURO, 
            highlightthickness=0,
            width=545, 
            height=470)
        self.canvas_ejes.place(relx=0.5, rely=0.56, anchor="center")
        # Eje Y (categorías) y eje X (frecuencia)
        self.canvas_ejes.create_line(40, 10, 40, 465, fill=TEXTO_CLARO, width=3)
        self.canvas_ejes.create_line(40, 465, 540, 465, fill=TEXTO_CLARO, width=3)

    def crear_panel_estadisticas(self):
        # Panel derecho: tarjetas de estadísticas globales + acciones de lote
        panel_estats = ctk.CTkFrame(
            self.pagina_analiticas,
            fg_color=GRIS_PANEL,
            corner_radius=15,
            border_width=1,
            border_color=GRIS_BORDE)
        panel_estats.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=(0, 20))

        panel_estats.grid_columnconfigure(0, weight=1)
        panel_estats.grid_columnconfigure(1, weight=1)

        # --- Fábrica de tarjetas (indicadores de solo lectura) ---
        # Títulos tamaño 24 subrayados | Contenido tamaño 40 (según especificación)
        # Pequeñas: 236x136 | Grandes: 276x185
        def crear_tarjeta(titulo, lineas, grande=False, destacada=False):
            ancho, alto = (276, 155) if grande else (276, 100)
            tarjeta = ctk.CTkFrame(
                panel_estats,
                fg_color=VERDE_TARJETA if destacada else GRIS_SUAVE,
                corner_radius=alto/4,
                border_width=2,
                border_color=VERDE if destacada else GRIS_BORDE,
                width=ancho,
                height=alto)
            tarjeta.grid_propagate(False)
            tarjeta.pack_propagate(False)

            ctk.CTkLabel(tarjeta, text=titulo, font=("Arial", 24, "bold", "underline"), text_color=GRIS_TEXTO).pack(pady=(12, 4))

            etiquetas_valor = []
            for linea in lineas:
                # Valor en verde profundo en la tarjeta destacada para mayor contraste
                lbl = ctk.CTkLabel(tarjeta, text=linea, font=("Arial", 40, "bold"),
                                   text_color=VERDE_HOVER if destacada else GRIS_TEXTO)
                lbl.pack()
                etiquetas_valor.append(lbl)
            return tarjeta, etiquetas_valor

        # --- FILA 1: tarjetas PEQUEÑAS (236x136) ---
        tarjeta_tiempo, lbls_tiempo = crear_tarjeta("Tiempo de Uso", ["00:00 h"])
        tarjeta_tiempo.grid(row=0, column=0, padx=(25, 8), pady=(28, 12))

        tarjeta_consumo, lbls_consumo = crear_tarjeta("Consumo", ["--- kWh"])
        tarjeta_consumo.grid(row=0, column=1, padx=(8, 25), pady=(28, 12))

        # --- FILA 2: tarjetas GRANDES (276x185) ---
        # "Estadísticas" es la tarjeta principal: fondo verdoso y borde verde
        tarjeta_estats, lbls_estats = crear_tarjeta("Estadísticas", ["--- grs", "--- %"], grande=True, destacada=True)
        tarjeta_estats.grid(row=1, column=0, padx=(25, 8), pady=12)

        tarjeta_rendimiento, lbls_rend = crear_tarjeta("Rendimiento (Prom)", ["--- FPS", "--- ms"], grande=True)
        tarjeta_rendimiento.grid(row=1, column=1, padx=(8, 25), pady=12)

        # Referencias para el backend (actualizar valores en tiempo real)
        self.stat_tiempo    = lbls_tiempo[0]
        self.stat_consumo   = lbls_consumo[0]
        self.stat_granos    = lbls_estats[0]
        self.stat_precision = lbls_estats[1]
        self.stat_fps       = lbls_rend[0]
        self.stat_ms        = lbls_rend[1]

        # --- FILAS 3 y 4: botones de acción (fuente 32, píldora ancha) ---
        # "Terminar Lote" en ámbar: acción de cierre que requiere atención
        btn_terminar = ctk.CTkButton(
            panel_estats,
            text="Terminar Lote",
            fg_color=AMBAR_RESET,
            hover_color=AMBAR_HOVER,
            text_color="white",
            corner_radius=45,
            height=80,
            width=578,
            font=("Arial", 32, "bold"))
        btn_terminar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=25, pady=(25, 12))

        # "Sincronizar con Base de Datos" en verde: acción positiva principal
        btn_sincronizar = ctk.CTkButton(
            panel_estats,
            text="Sincronizar con Base de Datos",
            fg_color=VERDE,
            hover_color=VERDE_HOVER,
            text_color="white",
            corner_radius=45,
            height=80,
            width=578,
            font=("Arial", 32, "bold"))
        btn_sincronizar.grid(row=3, column=0, columnspan=2, sticky="ew", padx=25, pady=12)

    # =====================================================================
    #  PÁGINA: REGISTROS (pendiente de diseño)
    # =====================================================================
    def crear_pagina_registros(self):
        self.pagina_registros = ctk.CTkFrame(self, fg_color="transparent")
        self.pagina_registros.grid(row=1, column=0, columnspan=2, sticky="nsew")

        ctk.CTkLabel(
            self.pagina_registros,
            text="Ventana de Registros\n(pendiente de diseño)",
            font=("Arial", 24, "bold"),
            text_color=GRIS_MEDIO
        ).place(relx=0.5, rely=0.5, anchor="center")


if __name__ == "__main__":
    app = InterfazApp()
    app.mainloop()
