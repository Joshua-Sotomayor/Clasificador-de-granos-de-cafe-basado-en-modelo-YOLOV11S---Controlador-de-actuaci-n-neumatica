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

        # Multiplicadores para balancear clases minoritarias respecto a la clase mayoritaria
        if objetivos_aumento is not None:
            self.objetivos_aumento = objetivos_aumento
        else:
            self.objetivos_aumento = {
                # --- VARIEDAD ARÁBICA (Referencia Buenos ID 2: 372 granos) ---
                "Arabica_Agrio": 6,       # ID 0 (67 granos -> +6 variaciones)
                "Arabica_Brocado": 5,     # ID 1 (79 granos -> +5 variaciones)
                "Arabica_Bueno": 0,       # ID 2 (372 granos -> Base)
                "Arabica_Cereza": 17,     # ID 3 (22 granos -> +17 variaciones)
                "Arabica_Concha": 12,     # ID 4 (30 granos -> +12 variaciones)
                "Arabica_Inmaduro": 8,    # ID 5 (46 granos -> +8 variaciones)
                "Arabica_Negro": 2,       # ID 6 (195 granos -> +2 variaciones)
                "Arabica_Quebrado": 2,    # ID 7 (157 granos -> +2 variaciones)

                # --- VARIEDAD ROBUSTA (Referencia Buenos ID 9: 244 granos) ---
                "Robusta_Brocado": 1,     # ID 8 (201 granos -> +1 variación)
                "Robusta_Bueno": 0,       # ID 9 (244 granos -> Base)
                "Robusta_Cereza": 11,     # ID 10 (23 granos -> +11 variaciones)
                "Robusta_Negro": 7,       # ID 11 (36 granos -> +7 variaciones)
                "Robusta_Quebrado": 6,    # ID 12 (38 granos -> +6 variaciones)

                # Mapeo por IDs numéricos directos de YOLO (según notes.json / classes.txt)
                0: 6,   # Arabica_Agrio
                1: 5,   # Arabica_Brocado
                2: 0,   # Arabica_Bueno
                3: 17,  # Arabica_Cereza
                4: 12,  # Arabica_Concha
                5: 8,   # Arabica_Inmaduro
                6: 2,   # Arabica_Negro
                7: 2,   # Arabica_Quebrado
                8: 1,   # Robusta_Brocado
                9: 0,   # Robusta_Bueno
                10: 11, # Robusta_Cereza
                11: 7,  # Robusta_Negro
                12: 6,  # Robusta_Quebrado
            }

        # Mapeo exacto de las 13 etiquetas de Label Studio a IDs de YOLO
        if mapeo_nombres_a_ids is not None:
            self.mapeo_nombres_a_ids = mapeo_nombres_a_ids
        else:
            self.mapeo_nombres_a_ids = {
                "Arabica_Agrio": 0,
                "Arabica_Brocado": 1,
                "Arabica_Bueno": 2,
                "Arabica_Cereza": 3,
                "Arabica_Concha": 4,
                "Arabica_Inmaduro": 5,
                "Arabica_Negro": 6,
                "Arabica_Quebrado": 7,
                "Robusta_Brocado": 8,
                "Robusta_Bueno": 9,
                "Robusta_Cereza": 10,
                "Robusta_Negro": 11,
                "Robusta_Quebrado": 12,
            }
