"""
Capa de Configuración
Define los parámetros globales, rutas y multiplicadores de aumento de datos.
"""

from typing import Dict, Tuple, Union


class Configuracion:
    """
    Almacena y gestiona todos los parámetros de configuración del pipeline.
    """

    def __init__(
        self,
        directorio_imagenes_entrada: str = "dataset_bruto/images",
        directorio_etiquetas_entrada: str = "dataset_bruto/labels",
        directorio_salida: str = "dataset_yolo",
        tamano_objetivo: int = 640,
        proporcion_division: Tuple[float, float, float] = (0.8, 0.1, 0.1),
        objetivos_aumento: Dict[Union[str, int], int] = None,
        mapeo_nombres_a_ids: Dict[str, int] = None,
        semilla_aleatoria: int = 42,
    ):
        """
        Inicializa la configuración del preprocesamiento y aumento.

        :param directorio_imagenes_entrada: Ruta a la carpeta con las imágenes originales.
        :param directorio_etiquetas_entrada: Ruta a la carpeta con los archivos .txt de YOLO.
        :param directorio_salida: Carpeta de destino donde se guardará el dataset estructurado.
        :param tamano_objetivo: Dimensión de resolución cuadrada (por defecto 640x640).
        :param proporcion_division: Proporción (entrenamiento, validación, prueba).
        :param objetivos_aumento: Diccionario de clases minoritarias con su factor de multiplicación.
        :param mapeo_nombres_a_ids: Mapeo opcional de nombres de clases a IDs numéricos de YOLO.
        :param semilla_aleatoria: Semilla para garantizar reproducibilidad en la división de datos.
        """
        self.directorio_imagenes_entrada = directorio_imagenes_entrada
        self.directorio_etiquetas_entrada = directorio_etiquetas_entrada
        self.directorio_salida = directorio_salida
        self.tamano_objetivo = tamano_objetivo
        self.proporcion_division = proporcion_division
        self.semilla_aleatoria = semilla_aleatoria

        # Multiplicadores por defecto para balancear las clases minoritarias
        # Puede mapear tanto identificadores numéricos como nombres textuales
        if objetivos_aumento is not None:
            self.objetivos_aumento = objetivos_aumento
        else:
            self.objetivos_aumento = {
                # Clase cáscara de cereza (minoritaria: ~22 muestras -> ~16x)
                "cascara_cereza": 16,
                # Clase conchas (minoritaria: ~30 muestras -> ~12x)
                "conchas": 12,
                # Clase negros (minoritaria: ~36 muestras -> ~6x)
                "negros": 6,
            }

        # Mapeo de nombres a identificadores de clase en Label Studio / YOLO
        if mapeo_nombres_a_ids is not None:
            self.mapeo_nombres_a_ids = mapeo_nombres_a_ids
        else:
            self.mapeo_nombres_a_ids = {
                "bueno_arabica": 0,
                "bueno_robusta": 1,
                "cascara_cereza": 2,
                "conchas": 3,
                "negros": 4,
            }
