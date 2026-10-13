import json
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

ctk.set_appearance_mode('light')
ctk.set_default_color_theme('blue')

C = dict(
    bg='#F3F4F6',        # Fondo gris muy claro general
    white='#FFFFFF', 
    navy='#14283F', 
    muted='#65758B', 
    blue='#2563EB', 
    teal='#0891B2', 
    green='#10B981', 
    red='#EF4444', 
    amber='#F59E0B', 
    border='#D7E3EF', 
    light='#F3F7FC'
)
MODELS = ['Tri-Clase', '13 Clases', 'Tri-Clase + SAGI', '13 Clases + SAGI']
CONFIG = Path('storage/config_trigger.json')

class HMI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('ALVIZUA | Panel de clasificación')
        self.geometry('1200x800')
        self.minsize(1200, 800)
        self.configure(fg_color=C['bg'])
        
        self.state_machine = 'STANDBY'
        self.camera_mapping = {'SUPERIOR': 'A', 'INFERIOR': 'B'}
        self.visible_camera = 'SUPERIOR'
        self.model = MODELS[0]
        self.trigger_confirmed = self.read_trigger()
        self.channel_jobs = {}
        
        # 🟢 REJILLA PRINCIPAL UNIFICADA (4 Columnas para alinear arriba y abajo a la perfección)
        # Columna 0, 1, 2 asignadas al bloque Izquierdo (Cámara y Botones Ovalados) -> 640px en total
        self.grid_columnconfigure(0, weight=0) 
        self.grid_columnconfigure(1, weight=0)
        self.grid_columnconfigure(2, weight=0)
        # Columna 3 asignada al bloque Derecho (Panel de Control y Pestañas Segmentadas) -> Elástica
        self.grid_columnconfigure(3, weight=1)
        
        self.grid_rowconfigure(0, weight=0) # Fila superior (Herramientas)
        self.grid_rowconfigure(1, weight=1) # Fila inferior (Visor y Controles)
        
        self.make_header()
        self.make_viewer()
        self.make_controls()
        self.refresh()

    def read_trigger(self):
        try:
            value = float(json.loads(CONFIG.read_text(encoding='utf-8')).get('trigger_percent', 12.5))
            return max(0, min(25, value))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return 12.5

    def pill(self, parent, text, color=C['light'], fg=C['navy'], width=100, command=None):
        return ctk.CTkButton(parent, text=text, command=command, width=width, height=80,
                             corner_radius=40, fg_color=color, hover_color='#C8E3F4' if color == C['light'] else color,
                             text_color=fg, font=('Arial', 24, 'bold'))

    def make_header(self):
        # 🟢 Los botones izquierdos se posicionan en las columnas 0, 1 y 2 correspondientes al ancho del visor
        self.btn_posicion = self.pill(self, 'Cambiar posición', '#D1D5DB', 'black', 305, self.swap_positions)
        self.btn_posicion.grid(row=0, column=0, sticky='w', padx=(20, 10), pady=15)
        
        self.model_menu = ctk.CTkOptionMenu(self, values=MODELS, command=self.select_model,
            width=185, height=80, corner_radius=40, fg_color='#D1D5DB', button_color='#D1D5DB',
            button_hover_color='#9CA3AF', text_color='black', dropdown_fg_color=C['white'],
            dropdown_text_color=C['navy'], font=('Arial', 24, 'bold'))
        self.model_menu.grid(row=0, column=1, sticky='w', padx=10, pady=15)
        self.model_menu.set(self.model)
        
        self.btn_orden = self.pill(self, '↕', '#D1D5DB', 'black', 92, self.toggle_camera)
        self.btn_orden.grid(row=0, column=2, sticky='w', padx=(10, 10), pady=15)
        
        # 🟢 Las pestañas se colocan en la Columna 3 con sticky='ew' para alinearse con el panel de abajo
        self.tabs = ctk.CTkSegmentedButton(self, values=['Dashboard', 'Analíticas', 'Registros'],
            command=self.change_tab, height=80, corner_radius=40, fg_color='#D1D5DB',
            selected_color='#9CA3AF', unselected_color='#D1D5DB', text_color='black',
            font=('Arial', 24, 'bold'))
        self.tabs.grid(row=0, column=3, sticky='ew', padx=(10, 20), pady=15)
        self.tabs.set('Dashboard')

    def make_viewer(self):
        # 🟢 El visor ocupa las columnas 0, 1 y 2 de forma combinada (Ancho total exacto = 640px)
        self.viewer = ctk.CTkFrame(self, width=640, height=640, fg_color='#152B43', corner_radius=15)
        self.viewer.grid(row=1, column=0, columnspan=3, padx=(20, 10), pady=(0, 20), sticky='nw')
        self.viewer.grid_propagate(False)
        self.viewer.pack_propagate(False)
        
        self.canvas = tk.Canvas(self.viewer, width=640, height=640, bg='#152B43', highlightthickness=0, borderwidth=0)
        self.canvas.place(x=0, y=0)
        for x in (160, 320, 480):
            self.canvas.create_line(x, 45, x, 630, fill='#44647C', dash=(3, 5), width=1)
        self.trigger_line = self.canvas.create_line(0, 320, 640, 320, fill='#FBBF24', width=2, dash=(12, 6))
        self.canvas.create_text(320, 320, text='VISTA PREVIA SIN SEÑAL DE CÁMARA', fill='#A8C3D9', font=('Arial', 17, 'bold'))
        self.camera_text = self.canvas.create_text(16, 24, text='', anchor='w', fill='#FFFFFF', font=('Arial', 13, 'bold'))
        
        self.canvas.create_rectangle(440, 6, 635, 38, fill='#244A67', outline='')
        self.canvas.create_text(537, 22, text='ms: ---    FPS: ---', fill='#FFFFFF', font=('Arial', 12, 'bold'))
        self.update_trigger_line()

    def make_controls(self):
        # 🟢 El panel de control se asigna a la columna 3 para heredar la simetría de las pestañas superiores
        panel = ctk.CTkFrame(self, fg_color=C['white'], corner_radius=15, border_width=1, border_color=C['border'])
        panel.grid(row=1, column=3, padx=(10, 20), pady=(0, 20), sticky='nsew')
        
        for i in range(3): panel.grid_columnconfigure(i, weight=1)
        panel.grid_rowconfigure(1, weight=1)
        
        # Títulos de las columnas internos del panel
        for i, (title, size) in enumerate([('BOTONERÍA', 24), ('CANALES', 24), ('TRIGGER', 24)]):
            ctk.CTkLabel(panel, text=title, text_color='black', font=('Arial', size, 'bold')).grid(row=0, column=i, pady=(24, 14))
            
        for i in (1, 2):
            ctk.CTkFrame(panel, width=2, fg_color=C['border']).place(relx=i/3, rely=.10, relheight=.83)
            
        # ----------------------------------------------------
        # COLUMNA 1: BOTONERÍA (Grid elástico vertical)
        # ----------------------------------------------------
        cmd = ctk.CTkFrame(panel, fg_color='transparent')
        cmd.grid(row=1, column=0, sticky='nsew', padx=6, pady=(0, 15))
        cmd.grid_columnconfigure(0, weight=1)
        cmd.grid_rowconfigure(0, weight=2) # Fila M
        cmd.grid_rowconfigure(1, weight=2) # Fila P
        cmd.grid_rowconfigure(2, weight=2) # Fila R
        
        self.buttons = {}
        for idx, (letter, color, callback) in enumerate([('M', C['green'], self.start), ('P', C['red'], self.stop), ('R', '#64748B', self.reset)]):
            # Restaurados diámetros grandes a 130 y 140 para el Reset
            radio = 70 if letter == 'R' else 65
            w_h = 140 if letter == 'R' else 130
            b = ctk.CTkButton(cmd, text=letter, command=callback, width=w_h, height=w_h,
                corner_radius=radio, fg_color=color, hover_color=color, border_width=5,
                border_color='#DCE7F2', text_color='white', font=('Arial', 36, 'bold'))
            b.grid(row=idx, column=0, sticky='')
            self.buttons[letter] = b
            
        # ----------------------------------------------------
        # COLUMNA 2: CANALES (Alineados desde fila 0 con Marcha)
        # ----------------------------------------------------
        channels = ctk.CTkFrame(panel, fg_color='transparent')
        channels.grid(row=1, column=1, sticky='nsew', padx=4, pady=(0, 15))
        channels.grid_columnconfigure(0, weight=1)
        for r in range(4): channels.grid_rowconfigure(r, weight=2) # 4 filas elásticas idénticas
        
        self.lamps = []
        for i in range(4):
            lamp = ctk.CTkLabel(channels, text=str(i), width=80, height=80, corner_radius=40,
                fg_color='#E5E7EB', text_color='black', font=('Arial', 24, 'bold'))
            lamp.grid(row=i, column=0, sticky='')
            self.lamps.append(lamp)
            
        # ----------------------------------------------------
        # COLUMNA 3: TRIGGER Y ACCIONES
        # ----------------------------------------------------
        trig = ctk.CTkFrame(panel, fg_color='transparent')
        trig.grid(row=1, column=2, sticky='nsew', padx=5, pady=(0, 15))
        trig.grid_columnconfigure(0, weight=1)
        trig.grid_rowconfigure(0, weight=1) # Texto dinámico
        trig.grid_rowconfigure(1, weight=5) # Slider
        trig.grid_rowconfigure(2, weight=1) # Texto fijo 0%
        trig.grid_rowconfigure(3, weight=2) # Botones inferiores
        
        self.trigger_label = ctk.CTkLabel(trig, text='', text_color='#4B5563', font=('Arial', 16, 'bold'))
        self.trigger_label.grid(row=0, column=0, sticky='s', pady=(0, 5))
        
        self.slider = ctk.CTkSlider(trig, from_=0, to=25, number_of_steps=100, orientation='vertical',
            width=8, button_length=24, fg_color='#E5E7EB', progress_color='#9CA3AF', corner_radius=4,
            button_color='#9CA3AF', button_hover_color='#767E8B', command=self.on_trigger)
        self.slider.grid(row=1, column=0, sticky='ns', pady=5)
        self.slider.set(self.trigger_confirmed)
        
        ctk.CTkLabel(trig, text='0%', text_color='#9CA3AF', font=('Arial', 14, 'bold')).grid(row=2, column=0, sticky='n', pady=(5, 0))
        
        frame_acciones = ctk.CTkFrame(trig, fg_color='transparent')
        frame_acciones.grid(row=3, column=0, sticky='s')
        
        self.cancel_btn = ctk.CTkButton(frame_acciones, text='Cancelar', command=self.cancel_trigger,
                                        width=135, height=55, corner_radius=30, fg_color='#D1D5DB',text_color='black', font=('Arial', 24, 'bold'))
        self.cancel_btn.pack(pady=5)

        self.apply_btn = ctk.CTkButton(
            frame_acciones, text='Aplicar', command=self.apply_trigger,
            width=150, height=55, corner_radius=30, fg_color='#D1D5DB',
            text_color='black', font=('Arial', 24, 'bold')
        )
        self.apply_btn.pack(pady=5)
        self.on_trigger(self.trigger_confirmed)

    def refresh(self):
        self.canvas.itemconfigure(self.camera_text, text=f'CÁMARA {self.visible_camera}  ·  DISPOSITIVO {self.camera_mapping[self.visible_camera]}')
        allowed = self.state_machine != 'MARCHA'
        self.slider.configure(state='normal' if allowed else 'disabled')
        self.apply_btn.configure(state='normal' if allowed else 'disabled')
        self.cancel_btn.configure(state='normal' if allowed else 'disabled')
        for letter, enabled in [('M', self.state_machine != 'MARCHA'), ('P', self.state_machine == 'MARCHA'), ('R', self.state_machine != 'MARCHA')]:
            self.buttons[letter].configure(state='normal' if enabled else 'disabled')

    def start(self):
        self.state_machine = 'MARCHA'
        self.refresh()

    def stop(self):
        self.state_machine = 'PARO'
        self.refresh()

    def reset(self):
        self.state_machine = 'STANDBY'
        self.cancel_trigger()
        self.refresh()

    def swap_positions(self):
        if self.state_machine == 'MARCHA':
            messagebox.showwarning('Cambio bloqueado', 'Detenga el proceso antes de intercambiar las cámaras.')
            return
        self.camera_mapping['SUPERIOR'], self.camera_mapping['INFERIOR'] = self.camera_mapping['INFERIOR'], self.camera_mapping['SUPERIOR']
        self.refresh()

    def toggle_camera(self):
        self.visible_camera = 'INFERIOR' if self.visible_camera == 'SUPERIOR' else 'SUPERIOR'
        self.refresh()

    def select_model(self, model):
        if self.state_machine == 'MARCHA':
            self.model_menu.set(self.model)
            messagebox.showwarning('Modelo bloqueado', 'Detenga el proceso para cambiar el modelo.')
            return
        self.model = model
        self.refresh()

    def change_tab(self, name):
        if name != 'Dashboard':
            messagebox.showinfo(name, f'La vista {name} está reservada para su implementación posterior.')
            self.tabs.set('Dashboard')

    def on_trigger(self, value):
        self.trigger_label.configure(text=f'{float(value):.1f}%')
        self.update_trigger_line(float(value))

    def update_trigger_line(self, value=None):
        if value is None: value = self.trigger_confirmed
        y = 630 - (value / 25) * 585
        self.canvas.coords(self.trigger_line, 18, y, 622, y)

    def cancel_trigger(self):
        self.slider.set(self.trigger_confirmed)
        self.on_trigger(self.trigger_confirmed)

    def apply_trigger(self):
        if self.state_machine == 'MARCHA': return
        value = round(self.slider.get(), 2)
        dialog = ctk.CTkToplevel(self)
        dialog.title('Confirmar calibración')
        dialog.geometry('455x230')
        dialog.configure(fg_color=C['white'])
        dialog.transient(self)
        dialog.grab_set()
        dialog.lift()
        
        ctk.CTkLabel(dialog, text='CONFIRMAR TRIGGER', text_color=C['navy'], font=('Arial', 22, 'bold')).pack(pady=(28, 10))
        ctk.CTkLabel(dialog, text=f'¿Confirmar nueva posición de la línea de disparo al {value:.1f}%?',
                     text_color=C['muted'], wraplength=405, font=('Arial', 15)).pack(pady=8)
        
        row = ctk.CTkFrame(dialog, fg_color='transparent')
        row.pack(pady=15)
        
        def confirm():
            try:
                CONFIG.parent.mkdir(parents=True, exist_ok=True)
                CONFIG.write_text(json.dumps({'trigger_percent': value}, indent=2), encoding='utf-8')
            except OSError as exc:
                messagebox.showerror('Error al guardar', str(exc), parent=dialog)
                return
            self.trigger_confirmed = value
            dialog.destroy()
            self.refresh()

        btn_c = ctk.CTkButton(row, text='Cancelar', command=dialog.destroy, width=125, height=50, corner_radius=25, fg_color='#FEE2E2', text_color='#B91C1C', font=('Arial', 15, 'bold'))
        btn_c.pack(side='left', padx=8)
        
        btn_ok = ctk.CTkButton(row, text='Confirmar', command=confirm, width=125, height=50, corner_radius=25, fg_color=C['green'], text_color='white', font=('Arial', 15, 'bold'))
        btn_ok.pack(side='left', padx=8)

        dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
        dialog.wait_visibility()
        dialog.focus_force()

    def pulse_channel(self, index):
        if index not in range(4): return
        if index in self.channel_jobs:
            self.after_cancel(self.channel_jobs[index])
        self.lamps[index].configure(fg_color=C['green'], text_color='white')
        def off():
            self.lamps[index].configure(fg_color='#E5E7EB', text_color='black')
            self.channel_jobs.pop(index, None)
        self.channel_jobs[index] = self.after(120, off)

if __name__ == '__main__':
    HMI().mainloop()
