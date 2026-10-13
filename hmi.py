import customtkinter as ctk

# Configuración inicial del tema y color visual
ctk.set_appearance_mode("light")  # Tu diseño usa fondo claro
ctk.set_default_color_theme("green")

# =====================================================================
# PALETA INSTITUCIONAL — Estilo tablero HMI industrial (Verdes/Grises)
# =====================================================================
VERDE          = "#1F7A3D"   # Verde institucional (acciones primarias / OK)
VERDE_HOVER    = "#145A2C"   # Verde oscuro para estados de hover
VERDE_CLARO    = "#57A773"   # Verde suave para acentos y bordes vivos
VERDE_LED      = "#35C759"   # Verde luminoso (luces indicadoras encendidas)
ROJO_PARO      = "#C0392B"   # Rojo industrial para PARO (convención HMI)
ROJO_HOVER     = "#96281B"
AMBAR_RESET    = "#B8860B"   # Ámbar industrial para RESET (convención HMI)
AMBAR_HOVER    = "#8F6A08"

GRIS_FONDO     = "#E9ECE8"   # Fondo general (gris verdoso muy claro)
GRIS_PANEL     = "#F7F8F7"   # Superficie del panel derecho
GRIS_SUAVE     = "#DDE2DE"   # Controles secundarios / inactivos
GRIS_SUAVE_HOV = "#C9CFCB"

GRIS_BORDE     = "#B9C0BB"   # Divisores y bordes sutiles
GRIS_MEDIO     = "#7A827D"   # Textos secundarios
GRIS_TEXTO     = "#2B322D"   # Texto principal
GRIS_OSCURO    = "#333A35"   # Acero oscuro (fondo del visor, estilo HMI)
GRIS_OSCURO_2  = "#434B45"   # Relieve interno del visor

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

        # --- 1. BARRA SUPERIOR (HERRAMIENTAS) ---
        self.crear_barra_superior()

        # --- 2. ÁREA IZQUIERDA (VISUALIZADOR / GRÁFICO) ---
        self.crear_area_visualizador()

        # --- 3. PANEL DERECHO (CONTROL Y BOTONERÍA) ---
        self.crear_panel_control()

    def crear_barra_superior(self):
        # 🟢 La barra superior ya NO usa un contenedor con 'columnspan'.
        # Cada bloque se coloca en la MISMA columna de la cuadrícula principal
        # que el elemento de abajo, para que los extremos coincidan por construcción:
        #   - Botones izq  -> columna 0 (encima exacto del visor de cámara)
        #   - Pestañas     -> columna 1 (encima exacto del panel BOTONERÍA/CANALES/TRIGGER)

        # ----------------------------------------------------
        # BLOQUE IZQUIERDO: Sub-contenedor para agrupar los 3 botones ovalados
        # ----------------------------------------------------
        frame_botones_izq = ctk.CTkFrame(self, fg_color="transparent")
        # Mismos márgenes que el visor de abajo: padx=(20, 10)
        frame_botones_izq.grid(row=0, column=0, sticky="new", padx=(20, 10), pady=15)

        # Configuramos sus 3 columnas con el mismo peso elástico para mantener tu distribución anterior
        frame_botones_izq.grid_columnconfigure(0, weight=1)
        frame_botones_izq.grid_columnconfigure(1, weight=1)
        frame_botones_izq.grid_columnconfigure(2, weight=1)

        # Estilo compartido: controles primarios en verde institucional
        config_btn_superior = {
            "fg_color": VERDE,
            "hover_color": VERDE_HOVER,
            "text_color": "white",
            "corner_radius": 40,
            "border_width": 2,
            "border_color": VERDE_CLARO,
            "height": 80,
            "font": ("Arial", 24, "bold")
        }

        btn_posicion = ctk.CTkButton(
            frame_botones_izq, 
            text="Cambiar Posición  ▾", 
            **config_btn_superior
        )
        btn_posicion.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        btn_modelos = ctk.CTkButton(
            frame_botones_izq, 
            text="Modelos  ▾", 
            **config_btn_superior
        )
        btn_modelos.grid(row=0, column=1, sticky="ew", padx=10)

        btn_orden = ctk.CTkButton(
            frame_botones_izq, 
            text="↕", 
            **config_btn_superior
        )
        btn_orden.grid(row=0, column=2, sticky="ew", padx=(10, 20))

        # ----------------------------------------------------
        # BLOQUE DERECHO: El botón segmentado (Pestañas)
        # ----------------------------------------------------
        pestañas = ctk.CTkSegmentedButton(
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
            # 🟢 Eliminamos el 'width=486' para que tome la medida dinámicamente según el panel inferior
        )
        pestañas.set("Dashboard") 

        # 🟢 Subrayado de la pestaña activa (como en el wireframe):
        # accedemos a los botones internos para aplicar fuente subrayada solo al seleccionado
        def resaltar_pestaña(valor_seleccionado):
            for nombre, boton in pestañas._buttons_dict.items():
                if nombre == valor_seleccionado:
                    boton.configure(font=("Arial", 24, "underline"), text_color="white")
                else:
                    boton.configure(font=("Arial", 24), text_color=GRIS_TEXTO)

        pestañas.configure(command=resaltar_pestaña)
        resaltar_pestaña("Dashboard") # Estado inicial subrayado

        # 🟢 CLAVE: mismos márgenes del panel de control de abajo (padx=(10, 20)).
        # Como ambos viven en la misma columna elástica (weight=1), el borde izquierdo
        # y derecho de esta barra coinciden EXACTAMENTE con los del panel inferior.
        pestañas.grid(row=0, column=1, sticky="new", padx=(10, 20), pady=15)


    def crear_area_visualizador(self):
        # Contenedor del cuadro con la "X" (Visor de cámara estilo pantalla HMI:
        # acero oscuro con bisel verde, típico de monitores industriales)
        self.frame_grafico = ctk.CTkFrame(
            self, 
            fg_color=GRIS_OSCURO, 
            corner_radius=15,
            border_width=2,
            border_color=VERDE_CLARO,
            width=640,
            height=640)
        self.frame_grafico.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=(0, 20))

        # 2. TRUCO CLAVE: Evita que los widgets internos deformen las medidas de 640x640
        self.frame_grafico.grid_propagate(False)
        self.frame_grafico.pack_propagate(False)

        # --- Las etiquetas flotantes (ms y FPS): insignias oscuras con texto verde,
        #     estilo lectura de telemetría sobre la pantalla ---
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

        # Nota: Para pintar la "X" gigante de tu boceto real, se requeriría un componente ctk.CTkCanvas.
        # He dejado este espacio limpio para que metas aquí tu gráfica, mapa o reproductor de video.

    def crear_panel_control(self):
        # Contenedor principal derecho (Superficie clara con ribete sutil, estilo tablero)
        panel_derecho = ctk.CTkFrame(
            self, 
            fg_color=GRIS_PANEL, 
            corner_radius=15,
            border_width=1,
            border_color=GRIS_BORDE)
        panel_derecho.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=(0, 20))

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
        
        # Botón RESET EXACTO de 140x140 píxeles tal cual tu Figma
        ctk.CTkButton(col_botoneria, text="R", font=("Arial", 24, "bold"), width=140, height=140, corner_radius=70, **config_reset).pack(pady=10)

        # Línea divisoria derecha
        div_intermedio = ctk.CTkFrame(panel_derecho, width=2, fg_color=GRIS_BORDE)
        div_intermedio.grid(row=1, column=0, sticky="nse", pady=20)

                # ----------------------------------------------------
        # COLUMNA 2: CANALES (Pequeños con líneas divisorias)
        # ----------------------------------------------------
        # Línea divisoria izquierda
        div_izq = ctk.CTkFrame(panel_derecho, width=2, fg_color=GRIS_BORDE)
        div_izq.grid(row=1, column=1, sticky="nsw", pady=20)

        col_canales = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        col_canales.grid(row=1, column=1, sticky="nsew", pady=10)

        # 🟢 TÍTULO FIJO: Lo dejamos arriba con el mismo espacio que tiene la BOTONERÍA
        ctk.CTkLabel(col_canales, text="CANALES", font=("Arial", 24, "bold"), text_color=GRIS_TEXTO).pack(side="top", pady=(10, 20))
        
        # 🟢 CONTENEDOR ELÁSTICO INTERNO: Aquí metemos solo los botones para controlar su rejilla
        frame_grid_canales = ctk.CTkFrame(col_canales, fg_color="transparent")
        frame_grid_canales.pack(side="top", fill="both", expand=True)

        # Configuración elástica idéntica a la botonería (Reparte el espacio solo en 4 filas)
        frame_grid_canales.grid_columnconfigure(0, weight=1)
        frame_grid_canales.grid_rowconfigure(0, weight=2) # Canal 0 (Fila superior alineada con M)
        frame_grid_canales.grid_rowconfigure(1, weight=2) # Canal 1
        frame_grid_canales.grid_rowconfigure(2, weight=2) # Canal 2
        frame_grid_canales.grid_rowconfigure(3, weight=2) # Canal 3

        # Canales como LÁMPARAS INDICADORAS (LED de tablero):
        # son SOLO indicadores visuales -> sin hover ni cursor interactivo.
        # Se encenderán únicamente cuando el programa detecte el cruce de un grano,
        # llamando desde el backend:
        #   canal.configure(fg_color=VERDE_LED, text_color="white")   # encender
        #   canal.configure(fg_color=GRIS_SUAVE, text_color=GRIS_MEDIO) # apagar
        config_botones_pequeños = {
            "fg_color": GRIS_SUAVE, 
            "text_color": GRIS_MEDIO, 
            "border_width": 2, 
            "border_color": VERDE_CLARO, 
            "hover": False,              # 👈 La luz NO reacciona al cursor, solo al sistema
            "cursor": "arrow",           # 👈 Cursor neutro: no es un control, es un indicador
            "width": 80, 
            "height": 80, 
            "corner_radius": 40, 
            "font": ("Arial", 24, "bold")
        }
        
        # 🟢 Posicionamos cada canal dentro del nuevo sub-frame desde la fila 0
        # Se guardan en self.luces_canales para que el backend pueda encenderlas/apagarlas
        self.luces_canales = []
        for i in range(4):
            btn_canal = ctk.CTkButton(frame_grid_canales, text=str(i), **config_botones_pequeños)
            btn_canal.grid(row=i, column=0, sticky="", pady=0) # 'row=i' inicia estrictamente en 0
            self.luces_canales.append(btn_canal)

        # Línea divisoria derecha
        div_der = ctk.CTkFrame(panel_derecho, width=2, fg_color=GRIS_BORDE)
        div_der.grid(row=1, column=1, sticky="nse", pady=20)



                # ----------------------------------------------------
        # COLUMNA 3: TRIGGER Y ACCIONES BARRAS
        # ----------------------------------------------------
        col_trigger = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        col_trigger.grid(row=1, column=2, sticky="nsew", pady=10)

        # Título principal
        ctk.CTkLabel(col_trigger, text="TRIGGER", font=("Arial", 24, "bold"), text_color=GRIS_TEXTO).pack(pady=(10, 10))

        # 🟢 CONTENEDOR GRUPO: Agrupa los textos y el slider verticalmente
        frame_slider_grupo = ctk.CTkFrame(col_trigger, fg_color="transparent")
        frame_slider_grupo.pack(pady=10)

        # 🟢 TEXTO DINÁMICO (Indicador superior que cambiará en tiempo real)
        # Lo guardamos en 'self.lbl_valor' para poder modificarlo desde la función de abajo
        self.lbl_valor = ctk.CTkLabel(frame_slider_grupo, text="50%", font=("Arial", 16, "bold"), text_color=VERDE)
        self.lbl_valor.pack(side="top", pady=(0, 5))

        # 🟢 FUNCIÓN INTERNA: Actualiza el texto dinámicamente
        def actualizar_valor_slider(valor_actual):
            # Convertimos a entero para quitar decimales (.0) y le concatenamos el "%"
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
            button_length=24,                  # 👈 Controla el diámetro del círculo de forma independiente
            command=actualizar_valor_slider    # 👈 Envía el valor en tiempo real a la función para actualizar la etiqueta
        )
        slider.pack(side="top")
        slider.set(50) # 👈 Ponemos el slider a la mitad por defecto para que coincida con el "50%" inicial

        # 🟢 Texto fijo al FINAL (Abajo del slider)
        lbl_min = ctk.CTkLabel(frame_slider_grupo, text="0%", font=("Arial", 14, "bold"), text_color=GRIS_MEDIO)
        lbl_min.pack(side="top", pady=(5, 0))

        # Botones de acción inferiores (Cancelar / Aplicar) - Permanecen intactos con tu escala
        btn_cancelar = ctk.CTkButton(col_trigger, text="Cancelar", fg_color=GRIS_SUAVE, hover_color=GRIS_SUAVE_HOV, text_color=GRIS_TEXTO, corner_radius=30, width=135, height=55, font=("Arial", 24, "bold"))
        btn_cancelar.pack(pady=(20, 5))

        btn_aplicar = ctk.CTkButton(col_trigger, text="Aplicar", fg_color=VERDE, hover_color=VERDE_HOVER, text_color="white", corner_radius=30, width=150, height=55, font=("Arial", 24, "bold"))
        btn_aplicar.pack(pady=5)


if __name__ == "__main__":
    app = InterfazApp()
    app.mainloop()
