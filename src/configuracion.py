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
                # --- VARIEDAD ARÁBICA (Referencia Buenos: 372 granos) ---
                "Arabica_Bueno": 0,       # 372 granos (Base)
                "Arabica_Negro": 2,       # 195 granos -> 372/195 ≈ 1.9x -> +2 variaciones
                "Arabica_Quebrado": 2,    # 157 granos -> 372/157 ≈ 2.4x -> +2 variaciones
                "Arabica_Brocado": 5,     # 79 granos  -> 372/79 ≈ 4.7x  -> +5 variaciones
                "Arabica_Agrio": 6,       # 67 granos  -> 372/67 ≈ 5.5x  -> +6 variaciones
                "Arabica_Inmaduro": 8,    # 46 granos  -> 372/46 ≈ 8.1x  -> +8 variaciones
                "Arabica_Concha": 12,     # 30 granos  -> 372/30 ≈ 12.4x -> +12 variaciones
                "Arabica_Cereza": 17,     # 22 granos  -> 372/22 ≈ 16.9x -> +17 variaciones

                # --- VARIEDAD ROBUSTA (Referencia Buenos: 244 granos) ---
                "Robusta_Bueno": 0,       # 244 granos (Base)
                "Robusta_Brocado": 1,     # 201 granos -> 244/201 ≈ 1.2x -> +1 variación
                "Robusta_Quebrado": 6,    # 38 granos  -> 244/38 ≈ 6.4x  -> +6 variaciones
                "Robusta_Negro": 7,       # 36 granos  -> 244/36 ≈ 6.8x  -> +7 variaciones
                "Robusta_Cereza": 11,     # 23 granos  -> 244/23 ≈ 10.6x -> +11 variaciones

                # Mapeo por IDs numéricos directos (0 a 12 de YOLO / Label Studio)
                0: 0,   # Arabica_Bueno
                1: 8,   # Arabica_Inmaduro
                2: 12,  # Arabica_Concha
                3: 6,   # Arabica_Agrio
                4: 5,   # Arabica_Brocado
                5: 2,   # Arabica_Negro
                6: 2,   # Arabica_Quebrado
                7: 17,  # Arabica_Cereza
                8: 0,   # Robusta_Bueno
                9: 1,   # Robusta_Brocado
                10: 7,  # Robusta_Negro
                11: 6,  # Robusta_Quebrado
                12: 11, # Robusta_Cereza
            }

        # Mapeo exacto de las 13 etiquetas de Label Studio a IDs de YOLO
        if mapeo_nombres_a_ids is not None:
            self.mapeo_nombres_a_ids = mapeo_nombres_a_ids
        else:
            self.mapeo_nombres_a_ids = {
                "Arabica_Bueno": 0,
                "Arabica_Inmaduro": 1,
                "Arabica_Concha": 2,
                "Arabica_Agrio": 3,
                "Arabica_Brocado": 4,
                "Arabica_Negro": 5,
                "Arabica_Quebrado": 6,
                "Arabica_Cereza": 7,
                "Robusta_Bueno": 8,
                "Robusta_Brocado": 9,
                "Robusta_Negro": 10,
                "Robusta_Quebrado": 11,
                "Robusta_Cereza": 12,
            }
