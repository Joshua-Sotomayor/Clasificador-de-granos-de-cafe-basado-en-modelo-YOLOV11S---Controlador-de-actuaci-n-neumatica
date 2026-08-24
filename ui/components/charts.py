"""
Componentes de Gráficos Analíticos (Flet Charts)
Incluye Gráfico de Barras (Sanos vs Defectuosos) y Gráfico de Pastel (Distribución de Defectos).
"""

import flet as ft
from typing import Dict
from ui.theme import InstitucionalTheme


class GraficoBarrasGranos(ft.Container):
    """
    Gráfico de barras apiladas/comparativas para conteo acumulado de granos Sanos vs Defectuosos.
    """

    def __init__(self, expand: bool = True):
        self.rod_sanos = ft.BarChartRod(
            from_y=0,
            to_y=0,
            width=36,
            color=InstitucionalTheme.VERDE_ULSA,
            border_radius=ft.border_radius.only(top_left=6, top_right=6),
            tooltip="Granos Sanos",
        )

        self.rod_defectos = ft.BarChartRod(
            from_y=0,
            to_y=0,
            width=36,
            color=InstitucionalTheme.ROJO_DEFECTO,
            border_radius=ft.border_radius.only(top_left=6, top_right=6),
            tooltip="Granos Defectuosos",
        )

        self.chart = ft.BarChart(
            bar_groups=[
                ft.BarChartGroup(x=0, bar_rods=[self.rod_sanos]),
                ft.BarChartGroup(x=1, bar_rods=[self.rod_defectos]),
            ],
            bottom_axis=ft.ChartAxis(
                labels=[
                    ft.ChartAxisLabel(
                        value=0,
                        label=ft.Container(
                            content=ft.Text("Sanos", size=12, weight=ft.FontWeight.BOLD, color=InstitucionalTheme.VERDE_ULSA),
                            padding=5,
                        ),
                    ),
                    ft.ChartAxisLabel(
                        value=1,
                        label=ft.Container(
                            content=ft.Text("Defectuosos", size=12, weight=ft.FontWeight.BOLD, color=InstitucionalTheme.ROJO_DEFECTO),
                            padding=5,
                        ),
                    ),
                ],
                labels_size=32,
            ),
            left_axis=ft.ChartAxis(
                labels_size=35,
            ),
            border=ft.border.all(1, ft.Colors.TRANSPARENT),
            horizontal_grid_lines=ft.ChartGridLines(
                color=ft.Colors.with_opacity(0.1, ft.Colors.BLACK),
                width=1,
                dash_pattern=[4, 4],
            ),
            interactive=True,
            animate=300,
            expand=True,
        )

        contenido = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("Conteo en Vivo de Granos", style=InstitucionalTheme.estilo_titulo(15)),
                        ft.Row(
                            controls=[
                                self._crear_indicador_leyenda("Sanos", InstitucionalTheme.VERDE_ULSA),
                                self._crear_indicador_leyenda("Defectos", InstitucionalTheme.ROJO_DEFECTO),
                            ],
                            spacing=12,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Container(content=self.chart, expand=True, padding=ft.padding.only(top=10)),
            ],
            expand=True,
        )

        super().__init__(
            content=contenido,
            expand=expand,
            **InstitucionalTheme.estilo_tarjeta()
        )

    def _crear_indicador_leyenda(self, texto: str, color_hex: str) -> ft.Row:
        return ft.Row(
            controls=[
                ft.Container(width=10, height=10, border_radius=2, bgcolor=color_hex),
                ft.Text(texto, size=11, color=InstitucionalTheme.CAFE_TEXTO, weight=ft.FontWeight.W_500),
            ],
            spacing=5,
        )

    def actualizar(self, sanos: int, defectos: int) -> None:
        """Actualiza la altura de las barras con los conteos en vivo."""
        self.rod_sanos.to_y = sanos
        self.rod_defectos.to_y = defectos
        max_y = max(sanos, defectos, 10)
        self.chart.max_y = max_y * 1.15


class GraficoPastelDefectos(ft.Container):
    """
    Gráfico de pastel para la distribución porcentual de tipos de defectos detectados.
    """

    def __init__(self, expand: bool = True):
        self.secciones = []
        self.chart = ft.PieChart(
            sections=[],
            sections_space=2,
            center_space_radius=35,
            animate=300,
            expand=True,
        )

        self.leyenda_column = ft.Column(
            controls=[],
            spacing=4,
            alignment=ft.MainAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
        )

        contenido = ft.Column(
            controls=[
                ft.Text("Distribución de Defectos en el Lote", style=InstitucionalTheme.estilo_titulo(15)),
                ft.Row(
                    controls=[
                        ft.Container(content=self.chart, expand=3, alignment=ft.alignment.center),
                        ft.Container(content=self.leyenda_column, expand=2, padding=ft.padding.only(left=5)),
                    ],
                    expand=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            expand=True,
        )

        super().__init__(
            content=contenido,
            expand=expand,
            **InstitucionalTheme.estilo_tarjeta()
        )

    def actualizar(self, porcentajes_defectos: Dict[str, float], conteos_defectos: Dict[str, int]) -> None:
        """Actualiza las secciones del gráfico de pastel y su leyenda."""
        nuevas_secciones = []
        nuevas_leyendas = []

        total_defectos = sum(conteos_defectos.values())

        if total_defectos == 0:
            # Sección vacía / de espera
            nuevas_secciones.append(
                ft.PieChartSection(
                    value=100,
                    title="100% Sin Defectos",
                    color=InstitucionalTheme.VERDE_CLARO,
                    radius=50,
                    title_style=ft.TextStyle(size=11, weight=ft.FontWeight.BOLD, color=InstitucionalTheme.VERDE_ULSA),
                )
            )
            nuevas_leyendas.append(
                ft.Text("Lote 100% Sano", size=12, color=InstitucionalTheme.GRIS_TERCIARIO)
            )
        else:
            for defecto, porcentaje in porcentajes_defectos.items():
                if porcentaje <= 0:
                    continue

                color = InstitucionalTheme.COLORES_DEFECTOS.get(defecto, InstitucionalTheme.GRIS_TERCIARIO)
                conteo = conteos_defectos.get(defecto, 0)

                # Título en la rebanada si es mayor al 8%
                titulo = f"{porcentaje:.0f}%" if porcentaje >= 8 else ""

                nuevas_secciones.append(
                    ft.PieChartSection(
                        value=porcentaje,
                        title=titulo,
                        color=color,
                        radius=52,
                        title_style=ft.TextStyle(size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    )
                )

                # Elemento de leyenda
                nuevas_leyendas.append(
                    ft.Row(
                        controls=[
                            ft.Container(width=10, height=10, border_radius=2, bgcolor=color),
                            ft.Text(f"{defecto}: {conteo} ({porcentaje:.1f}%)", size=11, color=InstitucionalTheme.CAFE_TEXTO),
                        ],
                        spacing=6,
                    )
                )

        self.chart.sections = nuevas_secciones
        self.leyenda_column.controls = nuevas_leyendas
