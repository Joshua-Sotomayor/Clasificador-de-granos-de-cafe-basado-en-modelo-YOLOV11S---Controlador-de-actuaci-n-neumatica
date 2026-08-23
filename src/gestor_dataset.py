"""
Capa de Gestión de Datos (Orquestador)
Coordina la lectura de archivos, agrupación por ID de grano para prevenir Data Leakage,
división en train/val/test, preprocesamiento, aumento y almacenamiento estructurado.
"""

import os
import re
import glob
import random
from typing import Dict, List, Tuple, Any, Union, Optional
import cv2
import numpy as np

from .configuracion import Configuracion
from .procesador_imagen import ProcesadorImagen
from .aumentador_datos import AumentadorDatos


class GestorDataset:
    """
    Orquestador principal que integra las capas de configuración, procesamiento y aumento.
    """

    def __init__(self, configuracion: Configuracion):
        """
        Inicializa el gestor con su configuración y componentes dependientes.

        :param configuracion: Instancia de la clase Configuracion.
        """
        self.configuracion = configuracion
        self.procesador = ProcesadorImagen()
        self.aumentador = AumentadorDatos()

    def extraer_id_grano(self, nombre_archivo: str) -> str:
        """
        Extrae el identificador raíz del grano físico a partir del nombre del archivo,
        removiendo sufijos que diferencian caras (ej. _frontal, _reverso, _f, _r, etc.)
        para evitar que ambas caras del mismo grano queden en particiones distintas (Data Leakage).

        :param nombre_archivo: Nombre del archivo de imagen (con o sin extensión).
        :return: Identificador único del grano físico.
        """
        nombre_base = os.path.splitext(os.path.basename(nombre_archivo))[0]
        # Expresión regular para remover sufijos comunes de orientación/cara
        patron_orientacion = r"([_\-\s]+(frontal|reverso|front|back|anverso|cara_?[ab]|cara|lado_?[12]|[frab]))$"
        id_limpio = re.sub(patron_orientacion, "", nombre_base, flags=re.IGNORECASE)
        return id_limpio if id_limpio else nombre_base

    def agrupar_por_id_grano(self) -> Dict[str, List[Dict[str, str]]]:
        """
        Escanea las imágenes del directorio de entrada y las asocia con su archivo de etiquetas .txt,
        agrupándolas por el ID único del grano.

        :return: Diccionario {id_grano: [{'ruta_imagen': ..., 'ruta_etiqueta': ..., 'nombre_base': ...}, ...]}
        """
        extensiones_validas = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        rutas_imagenes: List[str] = []

        if os.path.exists(self.configuracion.directorio_imagenes_entrada):
            for entrada in os.listdir(self.configuracion.directorio_imagenes_entrada):
                ruta_completa = os.path.join(self.configuracion.directorio_imagenes_entrada, entrada)
                if os.path.isfile(ruta_completa):
                    _, extension = os.path.splitext(entrada)
                    if extension.lower() in extensiones_validas:
                        rutas_imagenes.append(ruta_completa)

        # Ordenar para garantizar determinismo
        rutas_imagenes.sort()

        grupos_por_id: Dict[str, List[Dict[str, str]]] = {}

        for ruta_img in rutas_imagenes:
            nombre_base = os.path.splitext(os.path.basename(ruta_img))[0]
            id_grano = self.extraer_id_grano(nombre_base)

            # Buscar archivo de etiquetas correspondiente (.txt)
            ruta_etiqueta = os.path.join(
                self.configuracion.directorio_etiquetas_entrada,
                f"{nombre_base}.txt"
            )

            elemento = {
                "ruta_imagen": ruta_img,
                "ruta_etiqueta": ruta_etiqueta if os.path.exists(ruta_etiqueta) else "",
                "nombre_base": nombre_base,
                "id_grano": id_grano,
            }

            if id_grano not in grupos_por_id:
                grupos_por_id[id_grano] = []
            grupos_por_id[id_grano].append(elemento)

        return grupos_por_id

    def dividir_dataset(
        self, grupos_por_id: Dict[str, List[Dict[str, str]]]
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Divide el conjunto de granos en entrenamiento, validación y prueba a nivel de ID único,
        garantizando que ninguna cara del mismo grano quede dividida entre splits.

        :param grupos_por_id: Diccionario de imágenes agrupadas por ID de grano.
        :return: Diccionario con listas de muestras para 'train', 'val' y 'test'.
        """
        ids_granos = list(grupos_por_id.keys())
        # Semilla para partición reproducible
        random.seed(self.configuracion.semilla_aleatoria)
        random.shuffle(ids_granos)

        total_ids = len(ids_granos)
        prop_train, prop_val, prop_test = self.configuracion.proporcion_division

        corte_train = int(total_ids * prop_train)
        corte_val = corte_train + int(total_ids * prop_val)

        ids_train = set(ids_granos[:corte_train])
        ids_val = set(ids_granos[corte_train:corte_val])
        ids_test = set(ids_granos[corte_val:])

        divisiones: Dict[str, List[Dict[str, str]]] = {
            "train": [],
            "val": [],
            "test": []
        }

        for id_grano, muestras in grupos_por_id.items():
            if id_grano in ids_train:
                divisiones["train"].extend(muestras)
            elif id_grano in ids_val:
                divisiones["val"].extend(muestras)
            else:
                divisiones["test"].extend(muestras)

        return divisiones

    @staticmethod
    def leer_etiquetas_yolo(ruta_etiqueta: str) -> Tuple[List[List[float]], List[Union[int, str]]]:
        """
        Lee un archivo .txt en formato YOLO (<clase> <x_centro> <y_centro> <ancho> <alto>).

        :param ruta_etiqueta: Ruta absoluta o relativa al archivo .txt.
        :return: Tupla con (cajas_delimitadoras, etiquetas_clases).
        """
        cajas: List[List[float]] = []
        clases: List[Union[int, str]] = []

        if not ruta_etiqueta or not os.path.exists(ruta_etiqueta):
            return cajas, clases

        with open(ruta_etiqueta, "r", encoding="utf-8") as archivo:
            for linea in archivo:
                partes = linea.strip().split()
                if len(partes) >= 5:
                    clase_str = partes[0]
                    # Intentar convertir clase a entero si es numérico
                    try:
                        clase = int(clase_str)
                    except ValueError:
                        clase = clase_str

                    try:
                        coords = [float(p) for p in partes[1:5]]
                        cajas.append(coords)
                        clases.append(clase)
                    except ValueError:
                        continue

        return cajas, clases

    @staticmethod
    def guardar_etiquetas_yolo(
        ruta_archivo: str,
        cajas_delimitadoras: List[List[float]],
        etiquetas_clases: List[Union[int, str]]
    ) -> None:
        """
        Guarda las cajas delimitadoras y sus clases en un archivo de texto en formato YOLO.

        :param ruta_archivo: Ruta de destino del archivo .txt.
        :param cajas_delimitadoras: Lista de cajas [x, y, w, h].
        :param etiquetas_clases: Lista de clases correspondientes.
        """
        os.makedirs(os.path.dirname(ruta_archivo), exist_ok=True)
        with open(ruta_archivo, "w", encoding="utf-8") as archivo:
            for clase, caja in zip(etiquetas_clases, cajas_delimitadoras):
                archivo.write(f"{clase} {caja[0]:.6f} {caja[1]:.6f} {caja[2]:.6f} {caja[3]:.6f}\n")

    def obtener_multiplicador_aumento(self, etiquetas_clases: List[Union[int, str]]) -> int:
        """
        Determina si una imagen contiene clases minoritarias objetivo y devuelve el multiplicador correspondiente.

        :param etiquetas_clases: Lista de clases presentes en la imagen.
        :return: Multiplicador máximo aplicable (0 si no requiere aumento).
        """
        multiplicador_maximo = 0

        # Crear un mapa inverso si las etiquetas son numéricas
        id_a_nombre = {v: k for k, v in self.configuracion.mapeo_nombres_a_ids.items()}

        for etiqueta in etiquetas_clases:
            # 1. Verificar coincidencia directa en objetivos_aumento (por ID numérico o string)
            if etiqueta in self.configuracion.objetivos_aumento:
                multiplicador_maximo = max(
                    multiplicador_maximo,
                    self.configuracion.objetivos_aumento[etiqueta]
                )

            # 2. Si la etiqueta es numérica, verificar por nombre traducido
            nombre_clase = id_a_nombre.get(etiqueta)
            if nombre_clase and nombre_clase in self.configuracion.objetivos_aumento:
                multiplicador_maximo = max(
                    multiplicador_maximo,
                    self.configuracion.objetivos_aumento[nombre_clase]
                )

        return multiplicador_maximo

    def crear_directorios_salida(self) -> None:
        """
        Crea la estructura de carpetas estándar requerida para entrenar con YOLO.
        """
        for particion in ("train", "val", "test"):
            os.makedirs(os.path.join(self.configuracion.directorio_salida, "images", particion), exist_ok=True)
            os.makedirs(os.path.join(self.configuracion.directorio_salida, "labels", particion), exist_ok=True)

    def ejecutar_pipeline(self) -> Dict[str, Any]:
        """
        Ejecuta el pipeline completo de preprocesamiento, particionado y aumento de datos balanceado.

        :return: Diccionario con resumen estadístico del procesamiento.
        """
        print("=" * 60)
        print("  INICIANDO PIPELINE DE PROCESAMIENTO Y AUMENTO DE DATOS")
        print("  Finca Alvizua - Detección de Defectos en Granos de Café")
        print("=" * 60)

        # 1. Validar directorio de entrada
        if not os.path.exists(self.configuracion.directorio_imagenes_entrada):
            print(f"[Aviso] Directorio de imágenes de entrada no encontrado: '{self.configuracion.directorio_imagenes_entrada}'")
            print("Creando directorios base de ejemplo...")
            os.makedirs(self.configuracion.directorio_imagenes_entrada, exist_ok=True)
            os.makedirs(self.configuracion.directorio_etiquetas_entrada, exist_ok=True)

        # 2. Crear estructura de salida
        self.crear_directorios_salida()

        # 3. Agrupar por ID de grano
        grupos_por_id = self.agrupar_por_id_grano()
        total_granos_unicos = len(grupos_por_id)
        total_imagenes_originales = sum(len(lista) for lista in grupos_por_id.values())

        print(f"[*] Granos físicos únicos identificados: {total_granos_unicos}")
        print(f"[*] Total de imágenes originales detectadas: {total_imagenes_originales}")

        if total_imagenes_originales == 0:
            print("[Información] No se encontraron imágenes en el directorio de entrada. Pipeline preparado y a la espera de datos.")
            return {
                "total_granos_unicos": 0,
                "total_imagenes_originales": 0,
                "imagenes_procesadas_por_particion": {"train": 0, "val": 0, "test": 0},
                "muestras_aumentadas_generadas": 0,
            }

        # 4. Dividir dataset evitando Data Leakage
        divisiones = self.dividir_dataset(grupos_por_id)

        estadisticas = {
            "total_granos_unicos": total_granos_unicos,
            "total_imagenes_originales": total_imagenes_originales,
            "imagenes_procesadas_por_particion": {"train": 0, "val": 0, "test": 0},
            "muestras_aumentadas_generadas": 0,
        }

        # 5. Procesar cada partición
        for particion, muestras in divisiones.items():
            print(f"\n[*] Procesando partición '{particion}' ({len(muestras)} imágenes originales)...")

            for muestra in muestras:
                ruta_img = muestra["ruta_imagen"]
                ruta_lbl = muestra["ruta_etiqueta"]
                nombre_base = muestra["nombre_base"]

                # a) Cargar imagen
                imagen_bgr = cv2.imread(ruta_img)
                if imagen_bgr is None:
                    print(f"[Error] No se pudo leer la imagen: {ruta_img}")
                    continue

                # b) Cargar etiquetas
                cajas_originales, clases_originales = self.leer_etiquetas_yolo(ruta_lbl)

                # c) Aplicar autocontraste CLAHE
                imagen_contrastada = self.procesador.aplicar_autocontraste(imagen_bgr)

                # d) Aplicar padding simétrico y redimensionar a 640x640 recalculando cajas YOLO
                imagen_final, cajas_finales = self.procesador.aplicar_relleno_y_redimensionar(
                    imagen=imagen_contrastada,
                    cajas_delimitadoras=cajas_originales,
                    tamano_objetivo=self.configuracion.tamano_objetivo
                )

                # e) Guardar imagen y etiquetas base procesadas
                ruta_destino_img = os.path.join(
                    self.configuracion.directorio_salida,
                    "images",
                    particion,
                    f"{nombre_base}.jpg"
                )
                ruta_destino_lbl = os.path.join(
                    self.configuracion.directorio_salida,
                    "labels",
                    particion,
                    f"{nombre_base}.txt"
                )

                cv2.imwrite(ruta_destino_img, imagen_final)
                self.guardar_etiquetas_yolo(ruta_destino_lbl, cajas_finales, clases_originales)
                estadisticas["imagenes_procesadas_por_particion"][particion] += 1

                # f) Si es conjunto de entrenamiento (train), aplicar aumento a clases minoritarias
                if particion == "train" and len(clases_originales) > 0 and len(cajas_finales) > 0:
                    multiplicador = self.obtener_multiplicador_aumento(clases_originales)

                    if multiplicador > 0:
                        variaciones = self.aumentador.aumentar_muestra(
                            imagen=imagen_final,
                            cajas_delimitadoras=cajas_finales,
                            etiquetas_clases=clases_originales,
                            multiplicador=multiplicador
                        )

                        for indice_aum, var in enumerate(variaciones, start=1):
                            nombre_aumentado = f"{nombre_base}_aum_{indice_aum}"
                            ruta_aum_img = os.path.join(
                                self.configuracion.directorio_salida,
                                "images",
                                particion,
                                f"{nombre_aumentado}.jpg"
                            )
                            ruta_aum_lbl = os.path.join(
                                self.configuracion.directorio_salida,
                                "labels",
                                particion,
                                f"{nombre_aumentado}.txt"
                            )

                            cv2.imwrite(ruta_aum_img, var["imagen"])
                            self.guardar_etiquetas_yolo(ruta_aum_lbl, var["cajas"], var["etiquetas"])
                            estadisticas["muestras_aumentadas_generadas"] += 1

        print("\n" + "=" * 60)
        print("  PIPELINE COMPLETADO CON ÉXITO")
        print("=" * 60)
        print(f"  - Imágenes base procesadas (Train): {estadisticas['imagenes_procesadas_por_particion']['train']}")
        print(f"  - Imágenes base procesadas (Val):   {estadisticas['imagenes_procesadas_por_particion']['val']}")
        print(f"  - Imágenes base procesadas (Test):  {estadisticas['imagenes_procesadas_por_particion']['test']}")
        print(f"  - Variaciones sintéticas aumentadas (Train): {estadisticas['muestras_aumentadas_generadas']}")
        total_final = (
            sum(estadisticas["imagenes_procesadas_por_particion"].values())
            + estadisticas["muestras_aumentadas_generadas"]
        )
        print(f"  - Total general de imágenes en dataset_yolo: {total_final}")
        print("=" * 60)

        return estadisticas
