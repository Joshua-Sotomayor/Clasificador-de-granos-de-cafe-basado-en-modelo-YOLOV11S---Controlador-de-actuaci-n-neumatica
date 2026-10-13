import customtkinter as ctk

# Configuración inicial del tema y color visual
ctk.set_appearance_mode("light")  # Tu diseño usa fondo claro
ctk.set_default_color_theme("blue")

class InterfazApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configuración de la ventana principal
        self.title("Panel de Control")
        self.geometry("1280x800")
        self.configure(fg_color="#F3F4F6") # Fondo gris muy claro general

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
                # Contenedor superior completo
        frame_superior = ctk.CTkFrame(self, fg_color="transparent")
        frame_superior.grid(row=0, column=0, columnspan=2, sticky="new", padx=20, pady=15) # Asegúrate de que tenga su .grid original en la app

        # 🟢 1. Sincronizamos las columnas de la barra con la cuadrícula de la app
        frame_superior.grid_columnconfigure(0, weight=0) # Bloque izquierdo (Mismo comportamiento que el cuadro de 640px)
        frame_superior.grid_columnconfigure(1, weight=1) # Bloque derecho (Se estira igual que el panel de control)

        # ----------------------------------------------------
        # BLOQUE IZQUIERDO: Sub-contenedor para agrupar los 3 botones ovalados
        # ----------------------------------------------------
        frame_botones_izq = ctk.CTkFrame(frame_superior, fg_color="transparent")
        frame_botones_izq.grid(row=0, column=0, sticky="w") # Pegado a la izquierda (West)

        # Configuramos sus 3 columnas con el mismo peso elástico para mantener tu distribución anterior
        frame_botones_izq.grid_columnconfigure(0, weight=1)
        frame_botones_izq.grid_columnconfigure(1, weight=1)
        frame_botones_izq.grid_columnconfigure(2, weight=1)

        btn_posicion = ctk.CTkButton(
            frame_botones_izq, 
            text="Cambiar Posición", 
            fg_color="#D1D5DB", 
            text_color="black", 
            corner_radius=40, 
            height=80, 
            font=("Arial", 24)
        )
        btn_posicion.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        btn_modelos = ctk.CTkButton(
            frame_botones_izq, 
            text="Modelos", 
            fg_color="#D1D5DB", 
            text_color="black", 
            corner_radius=40, 
            height=80, 
            font=("Arial", 24)
        )
        btn_modelos.grid(row=0, column=1, sticky="ew", padx=10)

        btn_orden = ctk.CTkButton(
            frame_botones_izq, 
            text="↕", 
            fg_color="#D1D5DB", 
            text_color="black", 
            corner_radius=40, 
            height=80, 
            font=("Arial", 24)
        )
        btn_orden.grid(row=0, column=2, sticky="ew", padx=(10, 20))

        # ----------------------------------------------------
        # BLOQUE DERECHO: El botón segmentado (Pestañas)
        # ----------------------------------------------------
        pestañas = ctk.CTkSegmentedButton(
            frame_superior, 
            values=["Dashboard", "Analíticas", "Registros"], 
            fg_color="#D1D5DB", 
            selected_color="#D1D5DB", 
            text_color="black", 
            height=80, 
            font=("Arial", 24), 
            corner_radius=40
            # 🟢 Eliminamos el 'width=486' para que tome la medida dinámicamente según el panel inferior
        )
        pestañas.set("Dashboard") 

        # 🟢 Colocado en la columna 1 con sticky="ew" para que obligatoriamente abarque todo el ancho horizontal
        pestañas.grid(row=0, column=1, sticky="ew", padx=(10, 0))


    def crear_area_visualizador(self):
        # Contenedor del cuadro con la "X"
        self.frame_grafico = ctk.CTkFrame(
            self, 
            fg_color="#D1D5DB", 
            corner_radius=15,
            width=640,
            height=640)
        self.frame_grafico.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=(0, 20))

        # 2. TRUCO CLAVE: Evita que los widgets internos deformen las medidas de 640x640
        self.frame_grafico.grid_propagate(False)
        self.frame_grafico.pack_propagate(False)

        # --- Las etiquetas flotantes (ms y FPS) se mantienen igual ---
        lbl_ms = ctk.CTkLabel(self.frame_grafico, text="ms:    ", fg_color="#E5E7EB", text_color="black", corner_radius=15, width=80, height=30)
        lbl_ms.place(relx=0.75, rely=0.03, anchor="ne")

        lbl_fps = ctk.CTkLabel(self.frame_grafico, text="FPS:    ", fg_color="#E5E7EB", text_color="black", corner_radius=15, width=80, height=30)
        lbl_fps.place(relx=0.95, rely=0.03, anchor="ne")

        # Nota: Para pintar la "X" gigante de tu boceto real, se requeriría un componente ctk.CTkCanvas.
        # He dejado este espacio limpio para que metas aquí tu gráfica, mapa o reproductor de video.

    def crear_panel_control(self):
        # Contenedor principal derecho (Blanco de fondo en tu boceto)
        panel_derecho = ctk.CTkFrame(self, fg_color="#F3F4F6", corner_radius=15)
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

        ctk.CTkLabel(col_botoneria, text="BOTONERÍA", font=("Arial", 24, "bold"), text_color="black").pack(pady=(10, 20))
        
        # Botones circulares con "Falso Borde" para simular relieve sutil
        config_botones_grandes = {"fg_color": "#E5E7EB", "text_color": "black", "border_width": 2, "border_color": "#9CA3AF", "hover_color": "#D1D5DB"}
        
        ctk.CTkButton(col_botoneria, text="M", font=("Arial", 24, "bold"), width=140, height=140, corner_radius=70, **config_botones_grandes).pack(pady=10)
        ctk.CTkButton(col_botoneria, text="P", font=("Arial", 24, "bold"), width=140, height=140, corner_radius=70, **config_botones_grandes).pack(pady=20)
        
        # Botón RESET EXACTO de 140x140 píxeles tal cual tu Figma
        ctk.CTkButton(col_botoneria, text="R", font=("Arial", 24, "bold"), width=140, height=140, corner_radius=70, **config_botones_grandes).pack(pady=10)

        # Línea divisoria derecha
        div_intermedio = ctk.CTkFrame(panel_derecho, width=2, fg_color="#D1D5DB")
        div_intermedio.grid(row=1, column=0, sticky="nse", pady=20)

                # ----------------------------------------------------
        # COLUMNA 2: CANALES (Pequeños con líneas divisorias)
        # ----------------------------------------------------
        # Línea divisoria izquierda
        div_izq = ctk.CTkFrame(panel_derecho, width=2, fg_color="#D1D5DB")
        div_izq.grid(row=1, column=1, sticky="nsw", pady=20)

        col_canales = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        col_canales.grid(row=1, column=1, sticky="nsew", pady=10)

        # 🟢 TÍTULO FIJO: Lo dejamos arriba con el mismo espacio que tiene la BOTONERÍA
        ctk.CTkLabel(col_canales, text="CANALES", font=("Arial", 24, "bold"), text_color="black").pack(side="top", pady=(10, 20))
        
        # 🟢 CONTENEDOR ELÁSTICO INTERNO: Aquí metemos solo los botones para controlar su rejilla
        frame_grid_canales = ctk.CTkFrame(col_canales, fg_color="transparent")
        frame_grid_canales.pack(side="top", fill="both", expand=True)

        # Configuración elástica idéntica a la botonería (Reparte el espacio solo en 4 filas)
        frame_grid_canales.grid_columnconfigure(0, weight=1)
        frame_grid_canales.grid_rowconfigure(0, weight=2) # Canal 0 (Fila superior alineada con M)
        frame_grid_canales.grid_rowconfigure(1, weight=2) # Canal 1
        frame_grid_canales.grid_rowconfigure(2, weight=2) # Canal 2
        frame_grid_canales.grid_rowconfigure(3, weight=2) # Canal 3

        # Generar canales circulares pequeños (0, 1, 2, 3)
        config_botones_pequeños = {
            "fg_color": "#E5E7EB", 
            "text_color": "black", 
            "border_width": 1, 
            "border_color": "#9CA3AF", 
            "width": 80, 
            "height": 80, 
            "corner_radius": 40, 
            "font": ("Arial", 24, "bold")
        }
        
        # 🟢 Posicionamos cada canal dentro del nuevo sub-frame desde la fila 0
        for i in range(4):
            btn_canal = ctk.CTkButton(frame_grid_canales, text=str(i), **config_botones_pequeños)
            btn_canal.grid(row=i, column=0, sticky="", pady=0) # 'row=i' inicia estrictamente en 0

        # Línea divisoria derecha
        div_der = ctk.CTkFrame(panel_derecho, width=2, fg_color="#D1D5DB")
        div_der.grid(row=1, column=1, sticky="nse", pady=20)



                # ----------------------------------------------------
        # COLUMNA 3: TRIGGER Y ACCIONES BARRAS
        # ----------------------------------------------------
        col_trigger = ctk.CTkFrame(panel_derecho, fg_color="transparent")
        col_trigger.grid(row=1, column=2, sticky="nsew", pady=10)

        # Título principal
        ctk.CTkLabel(col_trigger, text="TRIGGER", font=("Arial", 24, "bold"), text_color="black").pack(pady=(10, 10))

        # 🟢 CONTENEDOR GRUPO: Agrupa los textos y el slider verticalmente
        frame_slider_grupo = ctk.CTkFrame(col_trigger, fg_color="transparent")
        frame_slider_grupo.pack(pady=10)

        # 🟢 TEXTO DINÁMICO (Indicador superior que cambiará en tiempo real)
        # Lo guardamos en 'self.lbl_valor' para poder modificarlo desde la función de abajo
        self.lbl_valor = ctk.CTkLabel(frame_slider_grupo, text="50%", font=("Arial", 16, "bold"), text_color="#4B5563")
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
            fg_color="#E5E7EB", 
            progress_color="#9CA3AF", 
            button_color="#9CA3AF", 
            button_hover_color="#767E8B", 
            height=260, 
            width=30, 
            corner_radius=15,
            button_length=24,                  # 👈 Controla el diámetro del círculo de forma independiente
            command=actualizar_valor_slider    # 👈 Envía el valor en tiempo real a la función para actualizar la etiqueta
        )
        slider.pack(side="top")
        slider.set(50) # 👈 Ponemos el slider a la mitad por defecto para que coincida con el "50%" inicial

        # 🟢 Texto fijo al FINAL (Abajo del slider)
        lbl_min = ctk.CTkLabel(frame_slider_grupo, text="0%", font=("Arial", 14, "bold"), text_color="#9CA3AF")
        lbl_min.pack(side="top", pady=(5, 0))

        # Botones de acción inferiores (Cancelar / Aplicar) - Permanecen intactos con tu escala
        btn_cancelar = ctk.CTkButton(col_trigger, text="Cancelar", fg_color="#D1D5DB", text_color="black", corner_radius=30, width=135, height=55, font=("Arial", 24, "bold"))
        btn_cancelar.pack(pady=(20, 5))

        btn_aplicar = ctk.CTkButton(col_trigger, text="Aplicar", fg_color="#D1D5DB", text_color="black", corner_radius=30, width=150, height=55, font=("Arial", 24, "bold"))
        btn_aplicar.pack(pady=5)


if __name__ == "__main__":
    app = InterfazApp()
    app.mainloop()
