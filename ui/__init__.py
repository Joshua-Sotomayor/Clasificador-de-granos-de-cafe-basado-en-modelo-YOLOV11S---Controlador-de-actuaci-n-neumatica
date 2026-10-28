"""
Capa de Presentacion e Interfaz Visual Industrial (CustomTkinter)
Proyecto MOPPI - Clasificador Optico de Cafe
"""
from ui.dashboard_ctk import (
    DashboardCustomTkinter,
    VentanaConfirmacionTrigger,
    VentanaAdvertenciaCamaras,
    VentanaLogsToplevel,
)

# Alias de compatibilidad semantica para la HMI Industrial
TableroIndustrial = DashboardCustomTkinter
DashboardIndustrial = DashboardCustomTkinter

__all__ = [
    "DashboardCustomTkinter",
    "TableroIndustrial",
    "DashboardIndustrial",
    "VentanaConfirmacionTrigger",
    "VentanaAdvertenciaCamaras",
    "VentanaLogsToplevel",
]
