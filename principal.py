"""
Punto de Entrada Principal para el Preprocesamiento y Aumento de Datos
Finca Alvizua - Dataset de Café para YOLO
"""

from src.configuracion import Configuracion
from src.gestor_dataset import GestorDataset


def ejecutar():
    """
    Función principal que inicializa la configuración y corre el pipeline.
    """
    # 1. Instanciar configuración con parámetros de la Finca Alvizua
    configuracion = Configuracion(
        directorio_imagenes_entrada="dataset_bruto/images",
        directorio_etiquetas_entrada="dataset_bruto/labels",
        directorio_salida="dataset_yolo",
        tamano_objetivo=640,
        proporcion_division=(0.8, 0.1, 0.1),
        objetivos_aumento={
            "cascara_cereza": 16,
            "conchas": 12,
            "negros": 6,
            # También soportar mapeo directo por IDs numéricos si aplica
            2: 16,
            3: 12,
            4: 6,
        },
        mapeo_nombres_a_ids={
            "bueno_arabica": 0,
            "bueno_robusta": 1,
            "cascara_cereza": 2,
            "conchas": 3,
            "negros": 4,
        },
        semilla_aleatoria=42,
    )

    # 2. Instanciar el gestor y ejecutar el pipeline
    pipeline = GestorDataset(configuracion)
    pipeline.ejecutar_pipeline()


if __name__ == "__main__":
    ejecutar()
