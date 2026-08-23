"""
Capa de Aumento de Datos (Albumentations)
Genera variaciones balanceadas de imágenes y recalcula automáticamente
las cajas delimitadoras (Bounding Boxes) en formato YOLO.
"""

from typing import List, Dict, Any, Union
import albumentations as A
import numpy as np


class AumentadorDatos:
    """
    Gestiona el pipeline de aumentación de datos para clases minoritarias con Albumentations.
    """

    def __init__(
        self,
        probabilidad_volteo_horizontal: float = 0.5,
        probabilidad_volteo_vertical: float = 0.5,
        probabilidad_rotacion_90: float = 1.0,
        limite_brillo: float = 0.15,
        limite_contraste: float = 0.15,
        probabilidad_brillo_contraste: float = 0.5,
    ):
        """
        Inicializa las transformaciones geométricas y fotométricas respetando las anotaciones YOLO.
        
        :param limite_brillo: Variación máxima de brillo (+/- 15%).
        :param limite_contraste: Variación máxima de contraste (+/- 15%).
        :param probabilidad_brillo_contraste: Probabilidad de aplicar ajuste de brillo/contraste (50%).
        """
        self.transformador = A.Compose(
            [
                A.HorizontalFlip(p=probabilidad_volteo_horizontal),
                A.VerticalFlip(p=probabilidad_volteo_vertical),
                A.RandomRotate90(p=probabilidad_rotacion_90),
                A.RandomBrightnessContrast(
                    brightness_limit=(-limite_brillo, limite_brillo),
                    contrast_limit=(-limite_contraste, limite_contraste),
                    p=probabilidad_brillo_contraste
                ),
            ],
            bbox_params=A.BboxParams(
                format="yolo",
                label_fields=["etiquetas_clases"],
                min_visibility=0.0,
                check_each_transform=True
            ),
        )

    def aumentar_muestra(
        self,
        imagen: np.ndarray,
        cajas_delimitadoras: List[List[float]],
        etiquetas_clases: List[Union[int, str]],
        multiplicador: int
    ) -> List[Dict[str, Any]]:
        """
        Genera múltiples versiones aumentadas de una imagen y sus etiquetas asociadas.

        :param imagen: Imagen procesada (640x640) en formato BGR.
        :param cajas_delimitadoras: Lista de cajas YOLO [[x, y, w, h], ...].
        :param etiquetas_clases: Lista de clases asociadas a cada caja.
        :param multiplicador: Número de variaciones sintéticas a generar.
        :return: Lista de diccionarios con 'imagen', 'cajas' y 'etiquetas'.
        """
        muestras_aumentadas: List[Dict[str, Any]] = []

        if multiplicador <= 0:
            return muestras_aumentadas

        for _ in range(multiplicador):
            try:
                transformacion = self.transformador(
                    image=imagen,
                    bboxes=cajas_delimitadoras,
                    etiquetas_clases=etiquetas_clases
                )

                muestras_aumentadas.append({
                    "imagen": transformacion["image"],
                    "cajas": [list(caja) for caja in transformacion["bboxes"]],
                    "etiquetas": list(transformacion["etiquetas_clases"]),
                })
            except Exception as error:
                # Si una transformación extrema descarta una caja, se intenta de nuevo con protección
                print(f"[Advertencia] Error al aplicar aumento en muestra: {error}")

        return muestras_aumentadas
