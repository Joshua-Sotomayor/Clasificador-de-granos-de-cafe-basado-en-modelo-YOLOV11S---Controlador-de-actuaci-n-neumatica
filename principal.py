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
        semilla_aleatoria=42,
    )

    # 2. Instanciar el gestor y ejecutar el pipeline
    pipeline = GestorDataset(configuracion)
    pipeline.ejecutar_pipeline()


if __name__ == "__main__":
    ejecutar()
