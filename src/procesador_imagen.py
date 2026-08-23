"""
Capa de Procesamiento de Imagen (OpenCV)
Maneja el filtro de autocontraste adaptativo (CLAHE) y el relleno negro (padding)
para redimensionar a 640x640 recalculando con precisión las coordenadas YOLO.
"""

from typing import List, Tuple, Optional
import cv2
import numpy as np


class ProcesadorImagen:
    """
    Contiene la lógica de transformación de imagen con OpenCV y ajuste matemático de anotaciones.
    """

    @staticmethod
    def aplicar_autocontraste(imagen: np.ndarray, limite_recorte: float = 2.0, tamano_rejilla: Tuple[int, int] = (8, 8)) -> np.ndarray:
        """
        Aplica estiramiento de histograma y ecualización adaptativa (CLAHE) en el canal de luminosidad (L)
        del espacio de color LAB para resaltar texturas, broca y decoloraciones sin sobre-saturar.

        :param imagen: Imagen en formato BGR (NumPy array).
        :param limite_recorte: Límite de contraste para el algoritmo CLAHE (por defecto 2.0).
        :param tamano_rejilla: Tamaño de las celdas para el histograma contextual (por defecto 8x8).
        :return: Imagen con autocontraste aplicado en formato BGR.
        """
        if imagen is None:
            raise ValueError("La imagen proporcionada es nula o inválida.")

        espacio_lab = cv2.cvtColor(imagen, cv2.COLOR_BGR2LAB)
        canal_luminosidad, canal_a, canal_b = cv2.split(espacio_lab)

        ecualizador_clahe = cv2.createCLAHE(clipLimit=limite_recorte, tileGridSize=tamano_rejilla)
        canal_luminosidad_mejorado = ecualizador_clahe.apply(canal_luminosidad)

        lab_fusionado = cv2.merge((canal_luminosidad_mejorado, canal_a, canal_b))
        imagen_mejorada = cv2.cvtColor(lab_fusionado, cv2.COLOR_LAB2BGR)
        return imagen_mejorada

    @staticmethod
    def aplicar_relleno_y_redimensionar(
        imagen: np.ndarray,
        cajas_delimitadoras: Optional[List[List[float]]] = None,
        tamano_objetivo: int = 640
    ) -> Tuple[np.ndarray, List[List[float]]]:
        """
        Añade bordes negros (padding simétrico) para hacer la imagen cuadrada sin distorsionar la relación de aspecto,
        la redimensiona a la resolución objetivo (640x640) y recalcula con precisión matemática las coordenadas YOLO.

        :param imagen: Imagen original en formato BGR.
        :param cajas_delimitadoras: Lista de cajas en formato YOLO [[x_centro, y_centro, ancho, alto], ...].
        :param tamano_objetivo: Dimensión de resolución cuadrada (por defecto 640).
        :return: Tupla con (imagen_procesada_640x640, cajas_recalculadas).
        """
        if imagen is None:
            raise ValueError("La imagen proporcionada es nula o inválida.")

        alto_original, ancho_original = imagen.shape[:2]
        dimension_maxima = max(alto_original, ancho_original)

        # Cálculo del relleno simétrico
        relleno_superior = (dimension_maxima - alto_original) // 2
        relleno_inferior = dimension_maxima - alto_original - relleno_superior
        relleno_izquierdo = (dimension_maxima - ancho_original) // 2
        relleno_derecho = dimension_maxima - ancho_original - relleno_izquierdo

        # Rellenar con negro (borde constante con valor [0, 0, 0])
        imagen_cuadrada = cv2.copyMakeBorder(
            imagen,
            relleno_superior,
            relleno_inferior,
            relleno_izquierdo,
            relleno_derecho,
            cv2.BORDER_CONSTANT,
            value=[0, 0, 0]
        )

        # Redimensionar al tamaño objetivo de YOLO
        imagen_redimensionada = cv2.resize(
            imagen_cuadrada,
            (tamano_objetivo, tamano_objetivo),
            interpolation=cv2.INTER_LINEAR
        )

        # Recalcular las coordenadas de las cajas delimitadoras de YOLO si existen
        cajas_recalculadas: List[List[float]] = []
        if cajas_delimitadoras:
            for caja in cajas_delimitadoras:
                x_centro_norm, y_centro_norm, ancho_norm, alto_norm = caja

                # Convertir a píxeles absolutos originales
                x_centro_abs = x_centro_norm * ancho_original
                y_centro_abs = y_centro_norm * alto_original
                ancho_abs = ancho_norm * ancho_original
                alto_abs = alto_norm * alto_original

                # Ajustar según el padding en la imagen cuadrada
                x_centro_cuadrada = x_centro_abs + relleno_izquierdo
                y_centro_cuadrada = y_centro_abs + relleno_superior

                # Normalizar respecto a la nueva dimensión cuadrada
                nuevo_x_centro = float(np.clip(x_centro_cuadrada / dimension_maxima, 0.0, 1.0))
                nuevo_y_centro = float(np.clip(y_centro_cuadrada / dimension_maxima, 0.0, 1.0))
                nuevo_ancho = float(np.clip(ancho_abs / dimension_maxima, 0.0, 1.0))
                nuevo_alto = float(np.clip(alto_abs / dimension_maxima, 0.0, 1.0))

                cajas_recalculadas.append([nuevo_x_centro, nuevo_y_centro, nuevo_ancho, nuevo_alto])

        return imagen_redimensionada, cajas_recalculadas
