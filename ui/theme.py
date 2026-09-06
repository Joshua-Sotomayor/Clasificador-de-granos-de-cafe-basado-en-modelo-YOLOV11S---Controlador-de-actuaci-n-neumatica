"""
Tema y Estilos Institucionales (Paleta ULSA y Modo Claro Limpio)
Define colores, tipografías, tarjetas con sombra suave y componentes estandarizados.
Soporte para estilo neomórfico con sombras suaves y efecto de profundidad.
"""

import flet as ft


class InstitucionalTheme:
    """
    Gestiona la paleta de colores y estilos visuales oficiales para la aplicación.
    Garantiza una estética limpia, profesional y libre de temas oscuros o neones agresivos.
    Incluye soporte para estilo neomórfico.
    """

    # --- Paleta de Colores Institucional ---
    BLANCO_PURO = "#FFFFFF"
    BLANCO_FONDO = "#F8F9FA"       # Fondo ligeramente grisáceo para dar contraste
    VERDE_ULSA = "#197B30"         # Verde institucional La Salle
    VERDE_ACENTO = "#2E7D32"       # Verde secundario
    VERDE_CLARO = "#E8F5E9"        # Fondo para badges e indicadores positivos
    CAFE_TEXTO = "#4A3B32"         # Café corporativo para títulos, textos y líneas
    CAFE_CLARO = "#D7CCC8"         # Café suave para bordes o divisores
    GRIS_TERCIARIO = "#757575"     # Gris para leyendas y textos secundarios
    NEGRO_TERCIARIO = "#212121"    # Negro suave para valores principales
    ROJO_DEFECTO = "#C62828"       # Rojo corporativo para granos defectuosos
    ROJO_CLARO = "#FFEBEE"         # Fondo suave para alertas de defectos
    AMARILLO_ALERTA = "#F57F17"    # Advertencias

    # Colores por defecto para gráficos
    COLORES_DEFECTOS = {
        "Brocado": "#E53935",
        "Agrio": "#FB8C00",
        "Negro": "#37474F",
        "Quebrado": "#8D6E63",
        "Cereza": "#8E24AA",
        "Concha": "#3949AB",
        "Inmaduro": "#00897B",
    }

    # --- Efectos Neomórficos ---
    SOMBRA_NEOMORFISMO = ft.BoxShadow(
        spread_radius=1,
        blur_radius=12,
        color=ft.Colors.with_opacity(0.1, ft.Colors.BLACK),
        offset=ft.Offset(2, 4),
    )
    SOMBRA_NEOMORFISMO_INSET = ft.BoxShadow(
        spread_radius=1,
        blur_radius=12,
        color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
        offset=ft.Offset(-2, -4),
    )

    @staticmethod
    def pad_symmetric(horizontal: float = 0, vertical: float = 0):
        """Genera Padding simétrico universalmente compatible con todas las versiones de Flet."""
        try:
            return ft.padding.symmetric(horizontal=horizontal, vertical=vertical)
        except Exception:
            try:
                return ft.Padding(horizontal, vertical, horizontal, vertical)
            except Exception:
                return (horizontal, vertical)

    @staticmethod
    def pad_only(left: float = 0, top: float = 0, right: float = 0, bottom: float = 0):
        """Genera Padding direccional universalmente compatible con todas las versiones de Flet."""
        try:
            return ft.padding.only(left=left, top=top, right=right, bottom=bottom)
        except Exception:
            try:
                return ft.Padding(left, top, right, bottom)
            except Exception:
                return (left, top, right, bottom)

    @staticmethod
    def border_all(width: float = 1, color: str = "#000000"):
        """Genera Border universalmente compatible con todas las versiones de Flet."""
        try:
            return ft.border.all(width, color)
        except Exception:
            try:
                return ft.Border.all(width, color)
            except Exception:
                try:
                    return ft.Border(
                        ft.BorderSide(width, color),
                        ft.BorderSide(width, color),
                        ft.BorderSide(width, color),
                        ft.BorderSide(width, color),
                    )
                except Exception:
                    return None

    @staticmethod
    def align_center():
        """Genera alineación central universalmente compatible con todas las versiones de Flet."""
        try:
            return ft.alignment.center
        except Exception:
            try:
                return ft.Alignment(0, 0)
            except Exception:
                return None

    @staticmethod
    def estilo_tarjeta(expand: bool = False, neomorph: bool = False) -> dict:
        """
        Genera el diseño de tarjeta con esquinas redondeadas y sombra suave difuminada.
        Si neomorph=True, aplica efecto neomórfico con sombras duales.
        """
        sombra = None
        if neomorph:
            sombra = ft.BoxShadow(
                spread_radius=1,
                blur_radius=15,
                color=ft.Colors.with_opacity(0.15, ft.Colors.BLACK),
                offset=ft.Offset(3, 6),
            )
        estilo = {
            "bgcolor": InstitucionalTheme.BLANCO_PURO,
            "border_radius": 15 if not neomorph else 12,
            "padding": 20 if not neomorph else 16,
            "shadow": sombra,
        }
        if expand:
            estilo["expand"] = True
        return estilo

    @staticmethod
    def estilo_titulo(size: int = 16) -> ft.TextStyle:
        """Estilo para títulos de sección y tarjetas."""
        return ft.TextStyle(
            size=size,
            weight=ft.FontWeight.BOLD,
            color=InstitucionalTheme.CAFE_TEXTO,
        )

    @staticmethod
    def estilo_subtitulo(size: int = 12) -> ft.TextStyle:
        """Estilo para subtítulos o etiquetas secundarias."""
        return ft.TextStyle(
            size=size,
            weight=ft.FontWeight.W_500,
            color=InstitucionalTheme.GRIS_TERCIARIO,
        )

    @staticmethod
    def estilo_valor_kpi(size: int = 24) -> ft.TextStyle:
        """Estilo para valores numéricos destacados."""
        return ft.TextStyle(
            size=size,
            weight=ft.FontWeight.W_900,
            color=InstitucionalTheme.NEGRO_TERCIARIO,
        )

    @staticmethod
    def boton_primario(texto: str, icono: str = None, on_click = None) -> ft.ElevatedButton:
        """Botón principal con Verde ULSA institucional."""
        return ft.ElevatedButton(
            content=texto,
            icon=icono,
            on_click=on_click,
            style=ft.ButtonStyle(
                color=InstitucionalTheme.BLANCO_PURO,
                bgcolor=InstitucionalTheme.VERDE_ULSA,
                padding=InstitucionalTheme.pad_symmetric(horizontal=20, vertical=12),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
        )

    @staticmethod
    def boton_secundario(texto: str, icono: str = None, on_click = None) -> ft.OutlinedButton:
        """Botón secundario con borde café."""
        return ft.OutlinedButton(
            content=texto,
            icon=icono,
            on_click=on_click,
            style=ft.ButtonStyle(
                color=InstitucionalTheme.CAFE_TEXTO,
                side=ft.BorderSide(1.5, InstitucionalTheme.CAFE_TEXTO),
                padding=InstitucionalTheme.pad_symmetric(horizontal=16, vertical=10),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
        )
