"""
Generador de Gráficos Científicos de Alto Impacto
Universidad Tecnológica La Salle (ULSA León, Nicaragua)
Proyecto: Clasificación Inteligente de Defectos en Café - Finca Alvizua
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# =====================================================================
# PALETA DE COLORES INSTITUCIONAL ULSA LEÓN (Verdes y Grises)
# =====================================================================
COLOR_VERDE_PRIMARIO = "#006837"     # Verde La Salle Principal (Bosque/Esmeralda)
COLOR_VERDE_SECUNDARIO = "#00843D"   # Verde Brillante La Salle
COLOR_VERDE_ACENTO = "#2BB673"       # Verde Acento
COLOR_VERDE_CLARO = "#E8F5E9"        # Verde Fondo Suave
COLOR_GRIS_OSCURO = "#2D3748"        # Gris Pizarra / Texto
COLOR_GRIS_MEDIO = "#718096"         # Gris Secundario
COLOR_GRIS_CLARO = "#E2E8F0"         # Gris Rejilla / Bordes
COLOR_BLANCO = "#FFFFFF"
COLOR_DORADO_ACENTO = "#D4AF37"      # Dorado de distinción

# Configuración global de estilo de Matplotlib
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['axes.edgecolor'] = COLOR_GRIS_MEDIO
plt.rcParams['axes.linewidth'] = 1.0
plt.rcParams['grid.color'] = COLOR_GRIS_CLARO
plt.rcParams['grid.linestyle'] = '--'
plt.rcParams['grid.alpha'] = 0.7

DIRECTORIO_SALIDA = "graficos_ulsa"
os.makedirs(DIRECTORIO_SALIDA, exist_ok=True)


def grafico_1_frontera_pareto():
    """
    Gráfico 1: Frontera de Pareto (Velocidad de Inferencia vs Precisión mAP50)
    Demuestra por qué YOLO11s es el 'Punto Dulce' ideal para producción.
    """
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=300)

    # Datos de los experimentos
    modelos = [
        {"nombre": "YOLO11n (Nano)", "latencia": 3.2, "map50": 41.8, "params": 2.58, "color": COLOR_GRIS_MEDIO, "marker": "o"},
        {"nombre": "YOLO11s (Small - Campeón)", "latencia": 6.1, "map50": 50.5, "params": 9.4, "color": COLOR_VERDE_PRIMARIO, "marker": "*"},
        {"nombre": "YOLO11m (Medium)", "latencia": 12.8, "map50": 51.9, "params": 20.0, "color": COLOR_VERDE_ACENTO, "marker": "s"},
        {"nombre": "YOLO11s (800px Nativo)", "latencia": 11.5, "map50": 38.9, "params": 9.4, "color": "#A0AEC0", "marker": "^"},
    ]

    for m in modelos:
        size = m["params"] * 35 + 150
        if "Campeón" in m["nombre"]:
            ax.scatter(m["latencia"], m["map50"], s=size * 1.6, color=COLOR_VERDE_PRIMARIO, edgecolors=COLOR_DORADO_ACENTO, linewidth=2.5, zorder=5)
            ax.annotate(
                f"★ {m['nombre']}\n(6.1 ms | 50.5% mAP | 164 FPS)\nPUNTO DULCE INDUSTRIAL",
                (m["latencia"] - 1.5, m["map50"] + 3.0),
                fontsize=10.0, fontweight='bold', color=COLOR_VERDE_PRIMARIO,
                bbox=dict(boxstyle="round,pad=0.4", fc=COLOR_VERDE_CLARO, ec=COLOR_VERDE_PRIMARIO, lw=1.5)
            )
        else:
            ax.scatter(m["latencia"], m["map50"], s=size, color=m["color"], edgecolors=COLOR_GRIS_OSCURO, linewidth=1.2, alpha=0.85, zorder=4)
            offset_y = 1.0 if m["map50"] > 45 else -2.2
            ax.annotate(
                f"{m['nombre']}\n({m['latencia']} ms | {m['map50']}%)",
                (m["latencia"] + 0.3, m["map50"] + offset_y),
                fontsize=9.5, color=COLOR_GRIS_OSCURO, fontweight='semibold'
            )

    # Curva de frontera de Pareto
    pareto_x = [3.2, 6.1, 12.8]
    pareto_y = [41.8, 50.5, 51.9]
    ax.plot(pareto_x, pareto_y, linestyle=':', color=COLOR_VERDE_SECUNDARIO, linewidth=2, label="Frontera de Pareto (Eficiencia)", zorder=3)

    # Zona de tiempo real en cinta transportadora (< 15 ms)
    ax.axvspan(0, 15, color=COLOR_VERDE_CLARO, alpha=0.35, label="Zona Óptima para Cinta Transportadora (>60 FPS)", zorder=1)

    ax.set_title("Frontera de Pareto: Velocidad de Inferencia vs. Precisión mAP@0.50\nULSA León - Finca Alvizua", fontsize=13, fontweight='bold', color=COLOR_GRIS_OSCURO, pad=15)
    ax.set_xlabel("Tiempo de Inferencia por Imagen en GPU (Milisegundos) — [Menor es Más Rápido]", fontsize=11, fontweight='bold', color=COLOR_GRIS_OSCURO)
    ax.set_ylabel("Precisión Media Promedio mAP@0.50 (%) — [Mayor es Mejor]", fontsize=11, fontweight='bold', color=COLOR_GRIS_OSCURO)
    ax.set_xlim(1.5, 15)
    ax.set_ylim(25, 62)
    ax.grid(True)
    ax.legend(loc="lower right", frameon=True, facecolor=COLOR_BLANCO, edgecolor=COLOR_GRIS_MEDIO, fontsize=9.5)

    plt.tight_layout()
    ruta_guardado = os.path.join(DIRECTORIO_SALIDA, "1_frontera_pareto_velocidad_vs_map.png")
    plt.savefig(ruta_guardado, dpi=300)
    plt.close()
    print(f"[OK] Generado: {ruta_guardado}")


def grafico_2_evolucion_experimentos():
    """
    Gráfico 2: Evolución Histórica de los 6 Experimentos de Entrenamiento
    """
    fig, ax = plt.subplots(figsize=(12.5, 6.5), dpi=300)

    versiones = [
        "v1: YOLO11m\n(Base AdamW)",
        "v2: YOLO11m\n(SGD + No Mosaic)",
        "v3: YOLO11m\n(AdamW cls=1.5)",
        "v4: YOLO11m\n(AdamW + Cosine)",
        "v5: YOLO11s\n★ (Small Campeón)",
        "v6: YOLO11n\n(Nano Ligero)",
        "v7: YOLO11s\n(800px Nativo)"
    ]

    map50_global = [43.8, 33.2, 23.0, 51.9, 50.5, 41.8, 38.9]
    pureza_robusta_bueno = [88.9, 42.9, 57.7, 72.7, 78.0, 38.5, 44.3]
    pureza_arabica_bueno = [52.0, 23.8, 37.3, 45.8, 61.8, 37.7, 15.3]

    x = np.arange(len(versiones))
    ancho = 0.25

    rects1 = ax.bar(x - ancho, map50_global, ancho, label='mAP@0.50 Global', color=COLOR_GRIS_MEDIO, edgecolor=COLOR_GRIS_OSCURO, lw=0.8)
    rects2 = ax.bar(x, pureza_robusta_bueno, ancho, label='Precisión Robusta Bueno', color=COLOR_VERDE_SECUNDARIO, edgecolor=COLOR_GRIS_OSCURO, lw=0.8)
    rects3 = ax.bar(x + ancho, pureza_arabica_bueno, ancho, label='Precisión Arábica Bueno', color=COLOR_VERDE_PRIMARIO, edgecolor=COLOR_GRIS_OSCURO, lw=0.8)

    # Resaltar la versión campeona v5
    ax.axvspan(3.6, 4.4, color=COLOR_DORADO_ACENTO, alpha=0.18, label="Modelo Seleccionado para Producción (v5)", zorder=0)

    # Añadir valores numéricos sobre las barras
    def autolabel(rects):
        for rect in rects:
            height = rect.get_height()
            if height > 0:
                ax.annotate(f'{height:.1f}%',
                            xy=(rect.get_x() + rect.get_width() / 2, height),
                            xytext=(0, 4), textcoords="offset points",
                            ha='center', va='bottom', fontsize=7.8, fontweight='bold', color=COLOR_GRIS_OSCURO)

    autolabel(rects1)
    autolabel(rects2)
    autolabel(rects3)

    ax.set_title("Evolución Experimental: Comparativa de Métricas por Versión\nULSA León - Sistema de Visión Artificial para Café", fontsize=13, fontweight='bold', color=COLOR_GRIS_OSCURO, pad=15)
    ax.set_ylabel("Porcentaje (%)", fontsize=11, fontweight='bold', color=COLOR_GRIS_OSCURO)
    ax.set_xticks(x)
    ax.set_xticklabels(versiones, fontsize=9.5, fontweight='semibold')
    ax.set_ylim(0, 115)
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    ax.legend(loc="upper right", frameon=True, facecolor=COLOR_BLANCO, edgecolor=COLOR_GRIS_MEDIO, fontsize=9.5)

    plt.tight_layout()
    ruta_guardado = os.path.join(DIRECTORIO_SALIDA, "2_evolucion_experimentos.png")
    plt.savefig(ruta_guardado, dpi=300)
    plt.close()
    print(f"[OK] Generado: {ruta_guardado}")


def grafico_3_radar_clases():
    """
    Gráfico 3: Gráfico de Radar / Telaraña por Clase (YOLO11s Campeón vs YOLO11n Nano)
    """
    clases = [
        "Robusta\nBueno", "Arabica\nBueno", "Robusta\nCereza", "Arabica\nCereza",
        "Robusta\nNegro", "Arabica\nNegro", "Arabica\nAgrio", "Arabica\nBrocado",
        "Robusta\nBrocado", "Arabica\nConcha", "Arabica\nInmaduro", "Robusta\nQuebrado", "Arabica\nQuebrado"
    ]

    # mAP50 por clase para v5 (YOLO11s) y Nano (YOLO11n)
    v5_scores = [83.1, 58.9, 99.5, 80.6, 65.2, 67.7, 48.1, 37.2, 7.5, 48.9, 17.9, 35.3, 6.6]
    nano_scores = [55.8, 51.3, 99.5, 80.0, 59.8, 88.6, 11.9, 9.8, 16.2, 20.6, 17.9, 24.2, 7.6]

    num_vars = len(clases)
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()

    # Cerrar el polígono
    v5_scores += v5_scores[:1]
    nano_scores += nano_scores[:1]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(9, 9), subplot_kw=dict(polar=True), dpi=300)

    # Graficar YOLO11s (Campeón)
    ax.plot(angles, v5_scores, color=COLOR_VERDE_PRIMARIO, linewidth=2.5, label="YOLO11s (Modelo Campeón - 9.4M)")
    ax.fill(angles, v5_scores, color=COLOR_VERDE_PRIMARIO, alpha=0.25)

    # Graficar YOLO11n (Nano)
    ax.plot(angles, nano_scores, color=COLOR_GRIS_MEDIO, linewidth=1.8, linestyle='--', label="YOLO11n (Nano - 2.5M)")
    ax.fill(angles, nano_scores, color=COLOR_GRIS_MEDIO, alpha=0.10)

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(clases, fontsize=9.0, fontweight='bold', color=COLOR_GRIS_OSCURO)
    ax.tick_params(pad=15)
    ax.set_ylim(0, 105)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20%", "40%", "60%", "80%", "100%"], fontsize=8, color=COLOR_GRIS_MEDIO)
    ax.grid(color=COLOR_GRIS_CLARO, linestyle='--')

    ax.set_title("Desempeño Comparativo por Clase (mAP@0.50)\nULSA León - YOLO11s vs. YOLO11n", fontsize=12.5, fontweight='bold', color=COLOR_GRIS_OSCURO, pad=30)
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.12), frameon=True, facecolor=COLOR_BLANCO, edgecolor=COLOR_GRIS_MEDIO, fontsize=9.5)

    plt.tight_layout()
    ruta_guardado = os.path.join(DIRECTORIO_SALIDA, "3_radar_desempeno_clases.png")
    plt.savefig(ruta_guardado, dpi=300)
    plt.close()
    print(f"[OK] Generado: {ruta_guardado}")


def grafico_4_matriz_produccion_binaria():
    """
    Gráfico 4: Matriz de Desempeño Operativo en Producción (Lógica Binaria: Buenos vs Desecho)
    Demuestra la tasa de éxito de la regla de negocio.
    """
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=300)

    categorias = [
        "Granos Buenos Reales\n(Arábica y Robusta - 160 granos)",
        "Defectos Críticos Reales\n(Negros y Cerezas - 71 granos)",
        "Defectos Fitosanitarios / Morfológicos\n(Agrios, Brocados, Quebrados - 142 granos)"
    ]

    porcentaje_saco_buenos = [75.0, 0.0, 4.2]    # Lo que el modelo acepta en el saco de exportación
    porcentaje_desecho = [25.0, 100.0, 95.8]      # Lo que el modelo expulsa al desecho

    x = np.arange(len(categorias))
    ancho = 0.52

    p1 = ax.bar(x, porcentaje_saco_buenos, ancho, label='Aceptado -> Canal Exportación (Café Sano)', color=COLOR_VERDE_PRIMARIO, edgecolor=COLOR_GRIS_OSCURO, lw=0.8)
    p2 = ax.bar(x, porcentaje_desecho, ancho, bottom=porcentaje_saco_buenos, label='Expulsado -> Canal Desecho (Actuador)', color=COLOR_GRIS_MEDIO, edgecolor=COLOR_GRIS_OSCURO, lw=0.8)

    # Etiquetas de porcentaje dentro de las barras
    for idx, (b, d) in enumerate(zip(porcentaje_saco_buenos, porcentaje_desecho)):
        if b >= 10:
            ax.text(idx, b / 2, f"{b:.1f}%\n(Aceptado)", ha='center', va='center', color=COLOR_BLANCO, fontweight='bold', fontsize=10.5)
        elif b > 0:
            ax.text(idx, b / 2, f"{b:.1f}%", ha='center', va='center', color=COLOR_BLANCO, fontweight='bold', fontsize=9.0)
            
        if d >= 10:
            ax.text(idx, b + d / 2, f"{d:.1f}%\n(Descartado)", ha='center', va='center', color=COLOR_BLANCO, fontweight='bold', fontsize=10.5)

    ax.set_title("Efectividad Operativa de la Regla de Negocio (Lógica Binaria)\nCero Fuga de Defectos Críticos al Lote de Exportación - ULSA León", fontsize=12.5, fontweight='bold', color=COLOR_GRIS_OSCURO, pad=20)
    ax.set_ylabel("Distribución de Decisiones (%)", fontsize=11, fontweight='bold', color=COLOR_GRIS_OSCURO)
    ax.set_xticks(x)
    ax.set_xticklabels(categorias, fontsize=9.5, fontweight='semibold')
    ax.set_ylim(0, 135)
    ax.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Leyenda centrada en la parte superior
    ax.legend(loc="upper left", frameon=True, facecolor=COLOR_BLANCO, edgecolor=COLOR_GRIS_MEDIO, fontsize=9.5)

    # Banner destacado a la derecha
    ax.annotate(
        "★ 100% de Defectos Críticos (Negros y Cerezas)\nson Expulsados sin Fugas",
        xy=(1.5, 116),
        ha='center', va='center', fontsize=9.5, fontweight='bold', color=COLOR_VERDE_PRIMARIO,
        bbox=dict(boxstyle="round,pad=0.45", fc=COLOR_VERDE_CLARO, ec=COLOR_VERDE_PRIMARIO, lw=1.3)
    )

    plt.tight_layout()
    ruta_guardado = os.path.join(DIRECTORIO_SALIDA, "4_matriz_flujo_produccion_binaria.png")
    plt.savefig(ruta_guardado, dpi=300)
    plt.close()
    print(f"[OK] Generado: {ruta_guardado}")


def main():
    print("=" * 60)
    print("  GENERANDO GRÁFICOS CIENTÍFICOS INSTITUCIONALES (ULSA LEÓN)")
    print("=" * 60)
    grafico_1_frontera_pareto()
    grafico_2_evolucion_experimentos()
    grafico_3_radar_clases()
    grafico_4_matriz_produccion_binaria()
    print("\n[ÉXITO] Todos los gráficos generados en alta definición (300 DPI) en 'graficos_ulsa/'")


if __name__ == "__main__":
    main()
