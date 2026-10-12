"""HMI GR-01 (clasificadora óptica de granos) para pantalla táctil.

Instalar:  pip install customtkinter pillow
Ejecutar:  python hmi.py            (pantalla completa)
           python hmi.py --window   (ventana 1280x800, para desarrollo)

Diseñada para dedos: objetivos >= 56 px, sin menús desplegables nativos,
sin cuadros de diálogo del sistema (todo es un overlay propio) y tablas con
arrastre táctil + botones de desplazamiento.

La interfaz NO contiene lógica de negocio. Emite solicitudes mediante
callbacks y el backend confirma el estado con los setters (set_*).
Todas las llamadas a setters deben hacerse desde el hilo de Tk.
"""
from __future__ import annotations

import sys
import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from tkinter import ttk

import customtkinter as ctk

ctk.set_appearance_mode("light")

# --- Tokens -----------------------------------------------------------------
GROUND = "#DDE2DF"
PANEL = "#FFFFFF"
FILL = "#D6DBD8"
INK = "#131D19"
SOFT = "#46544D"
LINE = "#9AA7A0"
BRAND = "#17624D"
BRAND_DK = "#0C3D30"
GO, GO_DK = "#1F8A50", "#14693A"
STOP, STOP_DK = "#C0392B", "#8F2519"
AMBER, AMBER_DK = "#F1C453", "#A97C0F"
ON = "#2FC46F"
CAM_BG = "#141C19"
F = "Arial"

PAGES = ("Dashboard", "Analíticas", "Registros")
POSITIONS = ("Vista superior", "Vista frontal", "Vista lateral")
MODELS = ("Café · v2", "Arroz · v1", "Maíz · v1")
PERIODS = ("Hoy", "Últimos 3 días", "Última Semana", "Todos")
HISTORY_KINDS = ("Todos", "Finalizados", "En curso")
LOG_KINDS = ("Todos", "INFO", "WARN", "ERROR")
TOUCH = 64  # alto mínimo de controles


class HMI(ctk.CTk):
    """Callbacks (dict[str, Callable]) que el backend puede registrar:

    start()                      stop()                    reset()
    camera(camera_id: int)       position(name: str)       model(name: str)
    trigger(percent: int)        # 0-100 del recorrido del slider; el recorrido
                                 # completo equivale a 25 % de la altura de imagen
    finish_batch(reason: str)    # "manual" | "inactivity"
    sync()
    history_filter(kind: str, period: str)
    log_filter(kind: str, period: str)

    Los callbacks no deben bloquear Tk: haz el I/O en un worker y publica el
    resultado por una cola que el hilo principal lea con after().
    """

    def __init__(self, callbacks: dict[str, Callable] | None = None, fullscreen: bool = True):
        super().__init__()
        self.callbacks = callbacks or {}
        self.running = False
        self.camera_id = 1
        self.position_name = POSITIONS[0]
        self.model_name = MODELS[0]
        self.trigger_saved = 48
        self.fps = None
        self.latency = None
        self._frame_image = None
        self._overlay = None
        self._toast_job = None
        self._inactivity_job = None
        self._batch_pending = False
        self._batch_active = False
        self._db_widgets: list[ctk.CTkLabel] = []
        self._lot_widgets: list[ctk.CTkLabel] = []
        self._model_buttons: list[ctk.CTkButton] = []
        self._filters = {"history": ["Todos", "Hoy"], "log": ["Todos", "Hoy"]}

        self.title("GR-01 · HMI")
        self.geometry("1280x800")
        self.configure(fg_color=GROUND)
        if fullscreen:
            self.attributes("-fullscreen", True)
            self.config(cursor="none")  # pantalla táctil: sin puntero
        self.bind("<Escape>", lambda _: self.attributes("-fullscreen", False))
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.pages: dict[str, ctk.CTkFrame] = {}
        for name in PAGES:
            page = ctk.CTkFrame(self, fg_color=GROUND, corner_radius=0)
            page.grid(row=0, column=0, sticky="nsew", padx=26, pady=(22, 24))
            page.grid_columnconfigure(0, weight=1)
            self.pages[name] = page
        self._build_dashboard(self.pages["Dashboard"])
        self._build_analytics(self.pages["Analíticas"])
        self._build_records(self.pages["Registros"])
        self.toast = ctk.CTkLabel(self, text="", fg_color=INK, text_color="white", corner_radius=28, font=(F, 20, "bold"), height=56)
        self._style_tables()
        self.show_page("Dashboard")

    # --- Comunicación con el backend -------------------------------------
    def emit(self, event: str, *args) -> bool:
        callback = self.callbacks.get(event)
        if not callback:
            self.notify(f"Sin backend: «{event}» no se ejecutó")
            return False
        try:
            callback(*args)
        except Exception as exc:  # noqa: BLE001
            self.notify(f"Error en {event}: {exc}")
            self.add_log("ERROR", f"Falló la solicitud: {event}")
            return False
        return True

    def notify(self, text: str, ms: int = 2600):
        self.toast.configure(text=f"   {text}   ")
        self.toast.place(relx=0.5, rely=1.0, y=-30, anchor="s")
        self.toast.lift()
        if self._toast_job:
            self.after_cancel(self._toast_job)
        self._toast_job = self.after(ms, self.toast.place_forget)

    # --- Piezas reutilizables ----------------------------------------------
    def _pill(self, parent, text, command=None, width=0, **kw):
        return ctk.CTkButton(
            parent, text=text, command=command, width=width, height=TOUCH, corner_radius=32,
            fg_color=PANEL, hover_color=FILL, text_color=INK, border_width=3, border_color=LINE,
            font=(F, 20, "bold"), text_color_disabled="#8A978F", **kw,
        )

    def _tabs(self, parent, active):
        bar = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=32, border_width=3, border_color=LINE, height=TOUCH)
        for name in PAGES:
            is_active = name == active
            ctk.CTkButton(
                bar, text=name, width=150, height=TOUCH - 8, corner_radius=28,
                fg_color=BRAND if is_active else PANEL, hover_color=BRAND if is_active else FILL,
                text_color="white" if is_active else INK, font=(F, 20, "bold"),
                command=lambda n=name: self.show_page(n),
            ).pack(side="left", padx=2, pady=2)
        return bar

    def _status_pills(self, parent, with_model=False):
        db = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=32, border_width=3, border_color=LINE, height=TOUCH)
        ctk.CTkLabel(db, text="Base de Datos", font=(F, 20, "bold"), text_color=INK).pack(side="left", padx=(20, 10))
        led = ctk.CTkLabel(db, text="", width=26, height=26, corner_radius=13, fg_color=PANEL)
        led.pack(side="left", padx=(0, 18))
        self._db_widgets.append(led)
        lots = ctk.CTkLabel(parent, text="Lotes: ---", font=(F, 20, "bold"), text_color=INK, fg_color=PANEL, corner_radius=32, height=TOUCH, width=150)
        self._lot_widgets.append(lots)
        widgets = [db, lots]
        if with_model:
            widgets.append(self._model_button(parent))
        return widgets

    def _model_button(self, parent):
        button = self._pill(parent, f"{self.model_name}  ▾", command=self._pick_model, width=200)
        self._model_buttons.append(button)
        return button

    def _topbar(self, parent, left_widgets, active):
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(98, weight=1)
        for i, w in enumerate(left_widgets(bar)):
            w.grid(row=0, column=i, padx=(0, 12))
        self._tabs(bar, active).grid(row=0, column=99)
        return bar

    # --- Overlays táctiles (reemplazan messagebox y OptionMenu) -----------------
    def _close_overlay(self):
        if self._overlay:
            self._overlay.destroy()
            self._overlay = None

    def _scrim(self):
        self._close_overlay()
        self._overlay = ctk.CTkFrame(self, fg_color="#0D1A14", corner_radius=0)
        self._overlay.place(x=0, y=0, relwidth=1, relheight=1)
        return self._overlay

    def _confirm(self, title, text, ok_text, on_ok, danger=False):
        scrim = self._scrim()
        box = ctk.CTkFrame(scrim, fg_color=PANEL, corner_radius=22, border_width=3, border_color=INK, width=640)
        box.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(box, text=title, font=(F, 30, "bold"), text_color=INK, wraplength=580, justify="left").pack(anchor="w", padx=34, pady=(34, 8))
        ctk.CTkLabel(box, text=text, font=(F, 20), text_color=SOFT, wraplength=580, justify="left").pack(anchor="w", padx=34, pady=(0, 26))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=34, pady=(0, 34))
        row.grid_columnconfigure((0, 1), weight=1, uniform="b")
        ctk.CTkButton(row, text="Cancelar", height=82, corner_radius=41, fg_color=FILL, hover_color=LINE, text_color=INK, border_width=3, border_color=LINE, font=(F, 24, "bold"), command=self._close_overlay).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(row, text=ok_text, height=82, corner_radius=41, fg_color=STOP if danger else BRAND, hover_color=STOP_DK if danger else BRAND_DK, font=(F, 24, "bold"), command=lambda: (self._close_overlay(), on_ok())).grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def _pick(self, title, items, current, on_pick):
        scrim = self._scrim()
        scrim.bind("<Button-1>", lambda _: self._close_overlay())
        box = ctk.CTkFrame(scrim, fg_color=PANEL, corner_radius=22, border_width=3, border_color=INK, width=520)
        box.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(box, text=title.upper(), font=(F, 16, "bold"), text_color=SOFT).pack(anchor="w", padx=28, pady=(24, 8))
        for item in items:
            selected = item == current
            ctk.CTkButton(
                box, text=f"{item}{'   ✓' if selected else ''}", height=76, corner_radius=14, anchor="w",
                fg_color="#DCEFE6" if selected else PANEL, hover_color=FILL, text_color=BRAND if selected else INK,
                font=(F, 22, "bold" if selected else "normal"),
                command=lambda v=item: (self._close_overlay(), on_pick(v)),
            ).pack(fill="x", padx=14, pady=3)
        ctk.CTkButton(box, text="Cerrar", height=64, corner_radius=32, fg_color=FILL, hover_color=LINE, text_color=INK, font=(F, 20, "bold"), command=self._close_overlay).pack(fill="x", padx=14, pady=(10, 16))

    # --- Navegación -------------------------------------------------------------
    def show_page(self, name):
        self._close_overlay()
        self.pages[name].tkraise()

    # --- DASHBOARD (wireframe: pantalla principal) ------------------------------
    def _build_dashboard(self, page):
        page.grid_rowconfigure(1, weight=1)

        def left(bar):
            self.position_button = self._pill(bar, f"{self.position_name}  ▾", command=self._pick_position, width=210)
            model = self._model_button(bar)
            cam = ctk.CTkButton(bar, text="⇅", width=TOUCH, height=TOUCH, corner_radius=32, fg_color=PANEL, hover_color=FILL, text_color=INK, border_width=3, border_color=LINE, font=(F, 28, "bold"), command=self._switch_camera)
            return [self.position_button, model, cam]

        self._topbar(page, left, "Dashboard")
        body = ctk.CTkFrame(page, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=10, uniform="d")
        body.grid_columnconfigure(1, weight=11, uniform="d")

        self.canvas = tk.Canvas(body, bg=CAM_BG, highlightthickness=3, highlightbackground=INK)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(0, 26))
        self.canvas.bind("<Configure>", lambda _: self._draw_camera())

        controls = ctk.CTkFrame(body, fg_color="transparent")
        controls.grid(row=0, column=1, sticky="nsew")
        controls.grid_rowconfigure(1, weight=1)
        controls.grid_columnconfigure((0, 2, 4), weight=1, uniform="c")
        controls.grid_columnconfigure((1, 3), weight=0)
        for col, title in ((0, "BOTONERÍA"), (2, "CANALES"), (4, "TRIGGER")):
            ctk.CTkLabel(controls, text=title, font=(F, 18, "bold"), text_color=SOFT).grid(row=0, column=col, pady=(4, 6))
        for col in (1, 3):
            ctk.CTkFrame(controls, width=3, fg_color=INK, corner_radius=0).grid(row=0, column=col, rowspan=2, sticky="ns")

        # Botonería
        buttons = ctk.CTkFrame(controls, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="nsew")
        buttons.grid_columnconfigure(0, weight=1)
        for r in range(3):
            buttons.grid_rowconfigure(r, weight=1)

        def round_button(row, text, fg, border, command, text_color="white"):
            b = ctk.CTkButton(buttons, text=text, width=128, height=128, corner_radius=64, fg_color=fg, hover_color=border, border_width=4, border_color=border, text_color=text_color, text_color_disabled="#E9EEEB", font=(F, 22, "bold"), command=command)
            b.grid(row=row, column=0)
            return b

        self.start_button = round_button(0, "▶\nMarcha", GO, GO_DK, lambda: self.emit("start"))
        self.stop_button = round_button(1, "■\nParo", STOP, STOP_DK, lambda: self.emit("stop"))
        self.reset_button = round_button(2, "↺\nReset", AMBER, AMBER_DK, self._reset, text_color=INK)

        # Canales
        channels = ctk.CTkFrame(controls, fg_color="transparent")
        channels.grid(row=1, column=2, sticky="nsew")
        channels.grid_columnconfigure(0, weight=1)
        self.channel_labels = []
        for i in range(4):
            channels.grid_rowconfigure(i, weight=1)
            lbl = ctk.CTkLabel(channels, text=f"{i}\nINACTIVO", width=92, height=92, corner_radius=46, fg_color=FILL, text_color=SOFT, font=(F, 15, "bold"))
            lbl.grid(row=i, column=0)
            self.channel_labels.append(lbl)

        # Trigger
        trig = ctk.CTkFrame(controls, fg_color="transparent")
        trig.grid(row=1, column=4, sticky="nsew")
        trig.grid_rowconfigure(0, weight=1)
        trig.grid_columnconfigure(0, weight=1)
        slider_row = ctk.CTkFrame(trig, fg_color="transparent")
        slider_row.grid(row=0, column=0, sticky="ns", pady=(4, 0))
        ctk.CTkLabel(slider_row, text="100%", font=("Courier", 16, "bold"), text_color=INK).grid(row=0, column=1, sticky="n", padx=8)
        ctk.CTkLabel(slider_row, text="0%", font=("Courier", 16, "bold"), text_color=INK).grid(row=2, column=1, sticky="s", padx=8)
        slider_row.grid_rowconfigure(1, weight=1)
        self.slider = ctk.CTkSlider(slider_row, orientation="vertical", from_=0, to=100, number_of_steps=100, width=56, height=300, button_length=14, button_corner_radius=28, corner_radius=10, border_width=6, fg_color=FILL, progress_color=BRAND, button_color=PANEL, button_hover_color=PANEL, command=self._preview_trigger)
        self.slider.set(self.trigger_saved)
        self.slider.grid(row=0, column=0, rowspan=3, sticky="ns")
        self.trigger_label = ctk.CTkLabel(trig, text="", font=(F, 28, "bold"), text_color=INK)
        self.trigger_label.grid(row=1, column=0, pady=(6, 0))
        self.trigger_hint = ctk.CTkLabel(trig, text="", font=(F, 14, "bold"), text_color=STOP, height=30)
        self.trigger_hint.grid(row=2, column=0)
        self.cancel_trigger = ctk.CTkButton(trig, text="Cancelar", height=60, corner_radius=30, fg_color=FILL, hover_color=LINE, text_color=INK, text_color_disabled="#8A978F", border_width=3, border_color=LINE, font=(F, 20, "bold"), command=self._cancel_trigger)
        self.cancel_trigger.grid(row=3, column=0, sticky="ew", padx=6, pady=(0, 8))
        self.apply_trigger = ctk.CTkButton(trig, text="Aplicar", height=60, corner_radius=30, fg_color=BRAND, hover_color=BRAND_DK, text_color_disabled="#DCE6E1", font=(F, 20, "bold"), command=self._apply_trigger)
        self.apply_trigger.grid(row=4, column=0, sticky="ew", padx=6)
        self._preview_trigger(self.trigger_saved)
        self.set_running(False)

    def _pick_position(self):
        self._pick("Posición de cámaras", POSITIONS, self.position_name, lambda v: self.emit("position", v))

    def _pick_model(self):
        if self.running:
            self.notify("Detén la máquina para cambiar el modelo")
            return
        self._pick("Modelo de clasificación", MODELS, self.model_name, lambda v: self.emit("model", v))

    def _switch_camera(self):
        self.emit("camera", 2 if self.camera_id == 1 else 1)

    def _screen_pct(self, value):
        return value * 0.25

    def _draw_camera(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if self._frame_image:
            c.create_image(w / 2, h / 2, image=self._frame_image)
        else:
            c.create_text(w / 2, h / 2, text="Esperando imagen del backend", fill="#94A99E", font=(F, 18))
        c.create_text(14, 18, anchor="w", text=f"CAM {self.camera_id:02d} · {self.position_name.upper()}", fill="#D4E4DA", font=("Courier", 13, "bold"))
        for i, (label, value) in enumerate((("ms", self.latency), ("FPS", self.fps))):
            x1 = w - 12 - (2 - i) * 130 + 10
            x0 = x1 - 120
            c.create_rectangle(x0, 46, x1, 86, fill="white", outline=INK, width=2)
            c.create_text((x0 + x1) / 2, 66, text=f"{label}: {'---' if value is None else f'{value:.1f}' if label == 'ms' else f'{value:.0f}'}", fill=INK, font=("Courier", 16, "bold"))
        y = h * (1 - self._screen_pct(self.trigger_saved) / 100)
        c.create_line(0, y, w, y, fill="#46E3A8", width=3)
        c.create_text(w - 12, y - 14, anchor="e", text=f"TRIGGER · {self._screen_pct(self.trigger_saved):.1f} %", fill="#8BF0C8", font=("Courier", 13, "bold"))
        pending = int(self.slider.get())
        if pending != self.trigger_saved:
            y2 = h * (1 - self._screen_pct(pending) / 100)
            c.create_line(0, y2, w, y2, fill="#FFD36B", width=3, dash=(10, 6))

    def set_camera_frame(self, pil_image):
        """Recibe PIL.Image (hilo principal). Mantiene la proporción."""
        from PIL import ImageTk

        image = pil_image.copy()
        image.thumbnail((max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())))
        self._frame_image = ImageTk.PhotoImage(image)
        self._draw_camera()

    def set_camera(self, camera_id):
        self.camera_id = camera_id
        self._draw_camera()

    def set_position(self, name):
        self.position_name = name
        self.position_button.configure(text=f"{name}  ▾")
        self._draw_camera()

    def set_model(self, name):
        self.model_name = name
        for b in self._model_buttons:
            b.configure(text=f"{name}  ▾")

    def set_performance(self, fps, latency_ms):
        self.fps, self.latency = fps, latency_ms
        self._draw_camera()

    def set_running(self, running):
        """Estado confirmado por el backend (no es un enclavamiento de seguridad)."""
        self.running = bool(running)
        idle = "normal" if not running else "disabled"
        self.start_button.configure(state=idle)
        self.stop_button.configure(state="normal" if running else "disabled")
        self.reset_button.configure(state=idle)
        self.slider.configure(state=idle, progress_color=LINE if running else BRAND)
        for b in self._model_buttons:
            b.configure(state=idle)
        for b in getattr(self, "batch_buttons", []):
            b.configure(state=idle)
        self.trigger_hint.configure(text="Detén la máquina para configurar" if running else "")
        self._refresh_trigger_buttons()

    def set_channels(self, states):
        for i, (lbl, active) in enumerate(zip(self.channel_labels, states)):
            lbl.configure(text=f"{i}\n{'ACTIVO' if active else 'INACTIVO'}", fg_color=ON if active else FILL, text_color="#04230F" if active else SOFT)

    def _preview_trigger(self, value):
        v = int(round(value))
        self.trigger_label.configure(text=f"{v}%")
        self._refresh_trigger_buttons()
        self._draw_camera() if hasattr(self, "canvas") else None

    def _refresh_trigger_buttons(self):
        if not hasattr(self, "apply_trigger"):
            return
        changed = int(round(self.slider.get())) != self.trigger_saved
        state = "normal" if changed and not self.running else "disabled"
        self.cancel_trigger.configure(state=state)
        self.apply_trigger.configure(state=state)

    def _cancel_trigger(self):
        self.slider.set(self.trigger_saved)
        self._preview_trigger(self.trigger_saved)

    def _apply_trigger(self):
        if self.running:
            return
        value = int(round(self.slider.get()))
        self._confirm("¿Aplicar nueva línea de disparo?", f"La línea quedará a {self._screen_pct(value):.1f} % de la altura de pantalla, medido desde el borde inferior.", "Aplicar", lambda: self.emit("trigger", value))

    def set_trigger(self, value):
        """Posición aplicada, confirmada por el backend (0-100 del slider)."""
        if not 0 <= value <= 100:
            raise ValueError("El trigger debe estar entre 0 y 100 %")
        self.trigger_saved = int(value)
        self.slider.set(self.trigger_saved)
        self._preview_trigger(self.trigger_saved)

    def _reset(self):
        if not self.running:
            self._confirm("¿Restablecer controles?", "Se solicitará el restablecimiento. La máquina debe estar detenida.", "Restablecer", lambda: self.emit("reset"))

    # --- ANALÍTICAS --------------------------------------------------------------
    def _build_analytics(self, page):
        page.grid_rowconfigure(1, weight=1)
        self._topbar(page, lambda bar: self._status_pills(bar, with_model=True), "Analíticas")
        body = ctk.CTkFrame(page, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure((0, 1), weight=1, uniform="a")

        chart = ctk.CTkFrame(body, fg_color=FILL, corner_radius=10, border_width=3, border_color=LINE)
        chart.grid(row=0, column=0, sticky="nsew", padx=(0, 26))
        ctk.CTkLabel(chart, text="Frecuencia / Categoría", font=(F, 22, "bold"), text_color=INK).pack(pady=(18, 6))
        self.category_widgets = []
        colors = (GO, "#B7791F", STOP)
        for name, color in zip(("Buenos", "Defectuosos", "Material extraño"), colors):
            row = ctk.CTkFrame(chart, fg_color="transparent")
            row.pack(fill="both", expand=True, padx=24, pady=4)
            label = ctk.CTkLabel(row, text=f"{name}\n—", font=(F, 20, "bold"), text_color=INK, justify="left", anchor="w")
            label.pack(anchor="w")
            bar = ctk.CTkProgressBar(row, height=46, corner_radius=6, progress_color=color, fg_color="#C4CBC7")
            bar.set(0)
            bar.pack(fill="x", pady=(4, 0))
            self.category_widgets.append((label, bar, name))

        side = ctk.CTkFrame(body, fg_color="transparent")
        side.grid(row=0, column=1, sticky="nsew")
        side.grid_columnconfigure((0, 1), weight=1, uniform="s")
        side.grid_rowconfigure((0, 1), weight=1, uniform="r")
        self.metrics: dict[str, ctk.CTkLabel] = {}
        cards = (("usage", "Tiempo de Uso", "00:00 h"), ("energy", "Consumo", "--- kWh"), ("stats", "Estadísticas", "--- grs\n--- %"), ("performance", "Rendimiento (Prom)", "--- FPS\n--- ms"))
        for i, (key, title, empty) in enumerate(cards):
            card = ctk.CTkFrame(side, fg_color=FILL, corner_radius=36, border_width=3, border_color=LINE)
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0 if i % 2 == 0 else 7, 7 if i % 2 == 0 else 0), pady=(0, 14))
            ctk.CTkLabel(card, text=title, font=(F, 18, "bold"), text_color=INK).pack(pady=(24, 0))
            ctk.CTkFrame(card, height=3, fg_color=INK, corner_radius=0).pack(fill="x", padx=36, pady=(2, 6))
            lbl = ctk.CTkLabel(card, text=empty, font=(F, 32, "bold"), text_color=INK)
            lbl.pack(expand=True)
            self.metrics[key] = lbl
        self.batch_buttons = []
        finish = ctk.CTkButton(side, text="Terminar Lote", height=82, corner_radius=41, fg_color=BRAND, hover_color=BRAND_DK, text_color_disabled="#DCE6E1", font=(F, 24, "bold"), command=self._finish_batch)
        finish.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.batch_buttons.append(finish)
        ctk.CTkLabel(side, text="Cierre automático tras 2 min de inactividad", font=(F, 14, "bold"), text_color=SOFT).grid(row=3, column=0, columnspan=2, pady=(0, 8))
        ctk.CTkButton(side, text="⟳  Sincronizar con Base de Datos", height=82, corner_radius=41, fg_color=FILL, hover_color=LINE, text_color=INK, border_width=3, border_color=LINE, font=(F, 24, "bold"), command=lambda: self.emit("sync")).grid(row=4, column=0, columnspan=2, sticky="ew")

    def set_statistics(self, *, usage="00:00 h", energy="--- kWh", processed=None, acceptance=None, fps=None, latency_ms=None, categories=(0, 0, 0)):
        """usage/energy: texto ya formateado. categories: (buenos, defectuosos, extraño)."""
        self.metrics["usage"].configure(text=str(usage))
        self.metrics["energy"].configure(text=str(energy))
        self.metrics["stats"].configure(text=f"{'---' if processed is None else f'{processed:,}'} grs\n{'---' if acceptance is None else f'{acceptance:.1f}'} %")
        self.metrics["performance"].configure(text=f"{'---' if fps is None else f'{fps:.0f}'} FPS\n{'---' if latency_ms is None else f'{latency_ms:.1f}'} ms")
        total = sum(categories)
        for (label, bar, name), count in zip(self.category_widgets, categories):
            ratio = count / total if total else 0
            label.configure(text=f"{name}\n{count:,} grs · {ratio:.1%}")
            bar.set(ratio)

    def set_database_connected(self, connected):
        for led in self._db_widgets:
            led.configure(fg_color=ON if connected else STOP)

    def set_lot_count(self, count):
        for w in self._lot_widgets:
            w.configure(text=f"Lotes: {count}")

    def notify_activity(self):
        """Llamar cuando el backend detecte granos (hilo de Tk)."""
        self._batch_active = True
        if self._inactivity_job:
            self.after_cancel(self._inactivity_job)
        self._inactivity_job = self.after(120_000, self._auto_finish)

    def _auto_finish(self):
        self._inactivity_job = None
        if self._batch_active and not self._batch_pending:
            self._batch_pending = self.emit("finish_batch", "inactivity")

    def _finish_batch(self):
        if self.running or self._batch_pending:
            return
        self._confirm("¿Terminar el lote actual?", "Se cerrará el lote y se preparará el siguiente.", "Terminar lote", self._send_finish)

    def _send_finish(self):
        self._batch_pending = self.emit("finish_batch", "manual")

    def confirm_batch_finished(self):
        if self._inactivity_job:
            self.after_cancel(self._inactivity_job)
            self._inactivity_job = None
        self._batch_pending = False
        self._batch_active = False

    def batch_finish_failed(self):
        self._batch_pending = False
        self.notify("No se pudo cerrar el lote. Puedes reintentar.")

    # --- REGISTROS ---------------------------------------------------------------
    def _style_tables(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Touch.Treeview", background=FILL, fieldbackground=FILL, foreground=INK, rowheight=56, font=(F, 16), borderwidth=0)
        s.configure("Touch.Treeview.Heading", background="#CDD3CF", foreground=INK, font=(F, 14, "bold"), relief="flat", padding=(8, 14))
        s.map("Touch.Treeview", background=[("selected", "#BFD8CC")], foreground=[("selected", INK)])
        s.configure("Touch.Vertical.TScrollbar", arrowsize=56, width=56, background="#FFFFFF", troughcolor="#CDD3CF", bordercolor=LINE, arrowcolor=INK)

    def _filter_row(self, parent, key, title, event, kinds):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        kind_btn = self._pill(row, f"{kinds[0]}  ▾", width=150)
        kind_btn.pack(side="left", padx=(0, 12))
        period = ctk.CTkSegmentedButton(row, values=list(PERIODS), height=TOUCH - 4, corner_radius=30, font=(F, 18, "bold"), fg_color=PANEL, selected_color=BRAND, selected_hover_color=BRAND, unselected_color=PANEL, unselected_hover_color=FILL, text_color=INK, border_width=3, command=lambda v: self._set_filter(key, event, 1, v, kind_btn))
        period.set("Hoy")
        period.pack(side="left")
        kind_btn.configure(command=lambda: self._pick(f"Filtro · {title}", kinds, self._filters[key][0], lambda v: self._set_filter(key, event, 0, v, kind_btn)))
        ctk.CTkLabel(row, text=title.upper(), font=(F, 28, "bold"), text_color=INK).pack(side="right")

    def _set_filter(self, key, event, index, value, kind_btn):
        self._filters[key][index] = value
        if index == 0:
            kind_btn.configure(text=f"{value}  ▾")
        self.emit(event, *self._filters[key])

    def _touch_table(self, parent, columns, headings, widths):
        box = ctk.CTkFrame(parent, fg_color=FILL, corner_radius=8, border_width=3, border_color=LINE)
        box.pack(fill="both", expand=True)
        tree = ttk.Treeview(box, columns=columns, show="headings", style="Touch.Treeview", selectmode="none")
        for key, title, width in zip(columns, headings, widths):
            tree.heading(key, text=title, anchor="w")
            tree.column(key, width=width, minwidth=60, stretch=True, anchor="w")
        scroll = ttk.Scrollbar(box, orient="vertical", command=tree.yview, style="Touch.Vertical.TScrollbar")
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y", padx=(0, 2), pady=2)
        tree.pack(fill="both", expand=True, padx=2, pady=2)
        # Arrastre táctil: deslizar el dedo desplaza la tabla.
        state = {"y": 0}
        tree.bind("<ButtonPress-1>", lambda e: state.update(y=e.y))
        def drag(e):
            step = (state["y"] - e.y) // 56
            if step:
                tree.yview_scroll(int(step), "units")
                state["y"] = e.y
        tree.bind("<B1-Motion>", drag)
        return tree

    def _build_records(self, page):
        page.grid_rowconfigure(1, weight=1)
        self._topbar(page, lambda bar: self._status_pills(bar), "Registros")
        body = ctk.CTkFrame(page, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        body.grid_rowconfigure((0, 1), weight=0)
        body.pack_propagate(False)
        history = ctk.CTkFrame(body, fg_color="transparent")
        history.pack(fill="both", expand=True)
        self._filter_row(history, "history", "Historial", "history_filter", HISTORY_KINDS)
        cols = ("date", "lot", "processed", "good", "percent", "minutes")
        self.history = self._touch_table(history, cols, ("Fecha", "N° de Lote", "Granos Procesados", "Granos buenos (N)", "Granos buenos (%)", "Tiempo (min)"), (170, 120, 200, 190, 190, 140))
        logs = ctk.CTkFrame(body, fg_color="transparent", height=270)
        logs.pack(fill="x", pady=(14, 0))
        logs.pack_propagate(False)
        self._filter_row(logs, "log", "Logs", "log_filter", LOG_KINDS)
        self.logs = self._touch_table(logs, ("time", "level", "msg"), ("Fecha / hora", "Nivel", "Mensaje"), (210, 100, 700))
        self.logs.tag_configure("ERROR", foreground=STOP)
        self.logs.tag_configure("WARN", foreground="#8A5B00")

    def set_history(self, rows):
        """Filas: (fecha, lote, procesados, buenos_n, buenos_pct, tiempo_min)."""
        self.history.delete(*self.history.get_children())
        for row in rows:
            self.history.insert("", "end", values=row)

    def add_log(self, level, text, timestamp=None):
        timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logs.insert("", 0, values=(timestamp, level, text), tags=(level,))

    def set_logs(self, rows):
        """Filas (timestamp, nivel, mensaje), ya filtradas por el backend."""
        self.logs.delete(*self.logs.get_children())
        for timestamp, level, text in reversed(list(rows)):
            self.add_log(level, text, timestamp)

    def _close(self):
        if self.running:
            self.notify("Detén la máquina antes de cerrar la interfaz")
            return
        if self._inactivity_job:
            self.after_cancel(self._inactivity_job)
        self.destroy()


if __name__ == "__main__":
    HMI(fullscreen="--window" not in sys.argv).mainloop()
