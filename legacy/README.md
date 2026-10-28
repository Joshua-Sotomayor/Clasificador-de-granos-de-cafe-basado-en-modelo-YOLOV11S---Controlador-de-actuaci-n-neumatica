# Modulos y Prototipos Legacy - Proyecto MOPPI

Este directorio contiene modulos, componentes de interfaz grafica y scripts de prueba historicos que han sido reemplazados y desacoplados del sistema en produccion.

## Motivo del Archivado

1. **Interfaz Grafica Flet (`legacy/flet_ui/`)**:
   - En las versiones v1.0 y v1.1 se utilizo Flet (Flutter para Python) como framework visual.
   - El modelo de renderizado mediante WebSockets/IPC genero cuellos de botella severos para la transmision de video en tiempo real (latencia de 200 a 300 ms y caida de cuadros por segundo), lo cual imposibilitaba la sincronizacion con las electrovalvulas neumaticas de eyeccion.
   - Se migro definitivamente a CustomTkinter (`ui/dashboard_ctk.py`), alcanzando 30 a 60 FPS estables con latencia visual en microsegundos, gestion de doble camara simultanea y lienzos directos de Matplotlib (`FigureCanvasTkAgg`).
   - Las versiones recientes de Flet (>=1.0.0) introdujeron cambios que rompen retrocompatibilidad (eliminacion de `ft.ElevatedButton` y `ft.OutlinedButton`).
   - Todo el codigo visual de Flet se preserva aqui unicamente para fines de auditoria, referencia y trazabilidad historica del proyecto.

2. **Prototipos Wireframe de CustomTkinter (`legacy/prototipos_ctk/`)**:
   - `hmi.py`: Primer boceto de 728 lineas con maqueta estatica en CustomTkinter. Sus disenos de paneles y paleta oscura fueron consolidados e implementados en `ui/dashboard_ctk.py`.
   - `hmi_2.py`: Prototipo experimental de trigger y FSM de 309 lineas para la activacion de electrovalvulas, hoy formalizado en la arquitectura de `core/detector.py` y `hardware/serial_bridge.py`.

3. **Pruebas Unitarias Legacy (`legacy/tests/`)**:
   - `test_ui_build.py`: Prueba unitaria que evaluaba la construccion del arbol de widgets del prototipo de Flet (`InterfazClasificadora`). Se aislo en esta carpeta para que la suite de pruebas unitarias principal de produccion (`tests/`) sea 100% independiente de Flet.

## Requisitos para Ejecucion Historica

Si en el futuro se requiere ejecutar el prototipo de Flet, se debe utilizar un entorno aislado con las versiones indicadas en `legacy/requirements_flet.txt`:

```bash
pip install -r legacy/requirements_flet.txt
```
