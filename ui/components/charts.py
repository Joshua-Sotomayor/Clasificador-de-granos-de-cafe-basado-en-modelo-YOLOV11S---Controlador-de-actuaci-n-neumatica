"""
Componentes de Gráficos Analíticos Visuales (Flet)
Incluye Gráfico Comparativo de Granos (Sanos vs Defectuosos) y Gráfico de Distribución de Defectos.
Diseñado con componentes nativos de Flet compatibles y optimizados para alta tasa de refresco.
"""

import flet as ft
from typing import Dict
from ui.theme import InstitucionalTheme


class GraficoBarrasGranos(ft.Container):
    """
    Gráfico comparativo y analítico para conteo en vivo de granos Sanos vs Defectuosos.
    """

    def __init__(self, expand: bool = True):
        # Textos de valores
        self.txt_sanos_val = ft.Text("0", size=22, weight=ft.FontWeight.W_900, color=InstitucionalTheme.VERDE_ULSA)
        self.txt_sanos_pct = ft.Text("100.0%", size=13, weight=ft.FontWeight.BOLD, color=InstitucionalTheme.VERDE_ULSA)
        self.bar_sanos = ft.ProgressBar(
            value=1.0,
            color=InstitucionalTheme.VERDE_ULSA,
            bgcolor="#E8F5E9",
            height=14,
            border_radius=7,
        )

        self.txt_defectos_val = ft.Text("0", size=22, weight=ft.FontWeight.W_900, color=InstitucionalTheme.ROJO_DEFECTO)
        self.txt_defectos_pct = ft.Text("0.0%", size=13, weight=ft.FontWeight.BOLD, color=InstitucionalTheme.ROJO_DEFECTO)
        self.bar_defectos = ft.ProgressBar(
            value=0.0,
            color=InstitucionalTheme.ROJO_DEFECTO,
            bgcolor="#FFEBEE",
            height=14,
            border_radius=7,
        )

        contenido = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("Balance de Clasificación en Vivo", style=InstitucionalTheme.estilo_titulo(15)),
                        ft.Container(
                            content=ft.Text("Sanos vs Defectos", size=11, weight=ft.FontWeight.BOLD, color=InstitucionalTheme.CAFE_TEXTO),
                            bgcolor=InstitucionalTheme.CAFE_CLARO,
                            border_radius=10,
                            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Container(height=10),
                # Bloque Granos Sanos
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Container(width=12, height=12, border_radius=3, bgcolor=InstitucionalTheme.VERDE_ULSA),
                                        ft.Text("Granos Sanos (Buenos)", size=13, weight=ft.FontWeight.BOLD, color=InstitucionalTheme.CAFE_TEXTO),
                                    ],
                                    spacing=8,
                                ),
                                ft.Row(
                                    controls=[
                                        self.txt_sanos_val,
                                        self.txt_sanos_pct,
                                    ],
                                    spacing=8,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        self.bar_sanos,
                    ],
                    spacing=6,
                ),
                ft.Container(height=10),
                # Bloque Granos Defectuosos
                ft.Column(
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Container(width=12, height=12, border_radius=3, bgcolor=InstitucionalTheme.ROJO_DEFECTO),
                                        ft.Text("Granos Defectuosos", size=13, weight=ft.FontWeight.BOLD, color=InstitucionalTheme.CAFE_TEXTO),
                                    ],
                                    spacing=8,
                                ),
                                ft.Row(
                                    controls=[
                                        self.txt_defectos_val,
                                        self.txt_defectos_pct,
                                    ],
                                    spacing=8,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        self.bar_defectos,
                    ],
                    spacing=6,
                ),
            ],
            spacing=5,
            expand=True,
            alignment=ft.MainAxisAlignment.START,
        )

        super().__init__(
            content=contenido,
            expand=expand,
            **InstitucionalTheme.estilo_tarjeta()
        )

    def actualizar(self, sanos: int, defectos: int) -> None:
        """Actualiza barras y porcentajes con los conteos acumulados."""
        total = sanos + defectos
        self.txt_sanos_val.value = str(sanos)
        self.txt_defectos_val.value = str(defectos)

        if total > 0:
            pct_s = (sanos / total)
            pct_d = (defectos / total)
            self.bar_sanos.value = pct_s
            self.bar_defectos.value = pct_d
            self.txt_sanos_pct.value = f"{pct_s * 100:.1f}%"
            self.txt_defectos_pct.value = f"{pct_d * 100:.1f}%"
        else:
            self.bar_sanos.value = 1.0
            self.bar_defectos.value = 0.0
            self.txt_sanos_pct.value = "100.0%"
            self.txt_defectos_pct.value = "0.0%"


class GraficoPastelDefectos(ft.Container):
    """
    Panel de desglose porcentual de tipos de defectos detectados en el lote.
    """

    def __init__(self, expand: bool = True):
        self.filas_defectos_column = ft.Column(
            controls=[],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        contenido = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("Distribución de Defectos en el Lote", style=InstitucionalTheme.estilo_titulo(15)),
                        ft.Text("Porcentajes relativos", style=InstitucionalTheme.estilo_subtitulo(11)),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(color=InstitucionalTheme.CAFE_CLARO, height=10),
                self.filas_defectos_column,
            ],
            expand=True,
            spacing=6,
        )

        super().__init__(
            content=contenido,
            expand=expand,
            **InstitucionalTheme.estilo_tarjeta()
        )

    def actualizar(self, porcentajes_defectos: Dict[str, float], conteos_defectos: Dict[str, int]) -> None:
        """Actualiza las barras y etiquetas individuales para cada tipo de defecto."""
        filas = []
        total_defectos = sum(conteos_defectos.values())

        if total_defectos == 0:
            filas.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=InstitucionalTheme.VERDE_ULSA, size=20),
                            ft.Text("Sin defectos detectados en el lote activo.", size=12, color=InstitucionalTheme.GRIS_TERCIARIO),
                        ],
                        spacing=8,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(vertical=20),
                    alignment=ft.Alignment.CENTER,
                )
            )
        else:
            for defecto, porcentaje in porcentajes_defectos.items():
                conteo = conteos_defectos.get(defecto, 0)
                color = InstitucionalTheme.COLORES_DEFECTOS.get(defecto, InstitucionalTheme.GRIS_TERCIARIO)
                valor_progreso = min(1.0, max(0.0, porcentaje / 100.0))

                filas.append(
                    ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Row(
                                        controls=[
                                            ft.Container(width=10, height=10, border_radius=2, bgcolor=color),
                                            ft.Text(defecto, size=12, weight=ft.FontWeight.W_600, color=InstitucionalTheme.CAFE_TEXTO),
                                        ],
                                        spacing=6,
                                    ),
                                    ft.Text(f"{conteo} ({porcentaje:.1f}%)", size=12, weight=ft.FontWeight.BOLD, color=InstitucionalTheme.CAFE_TEXTO),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ft.ProgressBar(
                                value=valor_progreso,
                                color=color,
                                bgcolor="#EEEEEE",
                                height=7,
                                border_radius=4,
                            ),
                        ],
                        spacing=3,
                    )
                )

        self.filas_defectos_column.controls = filas
