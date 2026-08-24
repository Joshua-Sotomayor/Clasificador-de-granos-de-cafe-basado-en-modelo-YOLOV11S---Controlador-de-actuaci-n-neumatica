"""
Componentes de Tarjeta de Estadística y Badges de Estado
"""

import flet as ft
from ui.theme import InstitucionalTheme


class StatCard(ft.Container):
    """
    Tarjeta KPI elegante para mostrar métricas individuales (Tiempo, Consumo kWh, Granos, etc.).
    """

    def __init__(
        self,
        titulo: str,
        valor_inicial: str = "0",
        subtitulo: str = "",
        icono: str = ft.Icons.ANALYTICS,
        color_icono: str = InstitucionalTheme.VERDE_ULSA,
        fondo_icono: str = InstitucionalTheme.VERDE_CLARO,
        expand: bool = True,
    ):
        self.texto_titulo = ft.Text(titulo, style=InstitucionalTheme.estilo_titulo(14))
        self.texto_valor = ft.Text(valor_inicial, style=InstitucionalTheme.estilo_valor_kpi(22))
        self.texto_subtitulo = ft.Text(subtitulo, style=InstitucionalTheme.estilo_subtitulo(11))

        self.contenedor_icono = ft.Container(
            content=ft.Icon(icono, color=color_icono, size=24),
            bgcolor=fondo_icono,
            border_radius=10,
            padding=10,
            alignment=ft.alignment.center,
        )

        contenido = ft.Row(
            controls=[
                self.contenedor_icono,
                ft.Column(
                    controls=[
                        self.texto_titulo,
                        self.texto_valor,
                        self.texto_subtitulo,
                    ],
                    spacing=2,
                    alignment=ft.MainAxisAlignment.CENTER,
                    expand=True,
                ),
            ],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=15,
        )

        super().__init__(
            content=contenido,
            expand=expand,
            **InstitucionalTheme.estilo_tarjeta()
        )

    def actualizar_valor(self, nuevo_valor: str, nuevo_subtitulo: str = None) -> None:
        """Actualiza el texto numérico y el subtítulo de la tarjeta."""
        self.texto_valor.value = nuevo_valor
        if nuevo_subtitulo is not None:
            self.texto_subtitulo.value = nuevo_subtitulo


class StatusBadge(ft.Container):
    """
    Pill/Badge compacto para indicar estados del sistema de hardware o inferencia.
    """

    def __init__(
        self,
        etiqueta: str,
        activo: bool = False,
        color_activo: str = InstitucionalTheme.VERDE_ULSA,
        color_inactivo: str = InstitucionalTheme.GRIS_TERCIARIO,
    ):
        self.color_activo = color_activo
        self.color_inactivo = color_inactivo

        self.circulo_estado = ft.Container(
            width=8,
            height=8,
            border_radius=4,
            bgcolor=self.color_activo if activo else self.color_inactivo,
        )
        self.texto_etiqueta = ft.Text(
            etiqueta,
            size=12,
            weight=ft.FontWeight.BOLD,
            color=InstitucionalTheme.CAFE_TEXTO,
        )

        super().__init__(
            content=ft.Row(
                controls=[self.circulo_estado, self.texto_etiqueta],
                spacing=6,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=InstitucionalTheme.BLANCO_PURO,
            border_radius=20,
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            border=ft.border.all(1, InstitucionalTheme.CAFE_CLARO),
        )

    def set_estado(self, activo: bool, texto_nuevo: str = None) -> None:
        """Actualiza el estado visual del badge."""
        self.circulo_estado.bgcolor = self.color_activo if activo else self.color_inactivo
        if texto_nuevo:
            self.texto_etiqueta.value = texto_nuevo
