"""
Script de Pruebas Unitarias y de Integración para el Pipeline de Preprocesamiento y Aumento.
Valida todas las capas: Configuración, Procesador de Imagen, Aumentador y Gestor de Dataset.
"""

import os
import shutil
import tempfile
import numpy as np
import cv2

from src.configuracion import Configuracion
from src.procesador_imagen import ProcesadorImagen
from src.aumentador_datos import AumentadorDatos
from src.gestor_dataset import GestorDataset


def probar_configuracion():
    print("[1/5] Probando Capa de Configuración...")
    config = Configuracion()
    assert config.tamano_objetivo == 640
    assert config.proporcion_division == (0.8, 0.1, 0.1)
    assert "Arabica_Cereza" in config.objetivos_aumento
    assert "Robusta_Negro" in config.objetivos_aumento
    assert config.objetivos_aumento["Arabica_Cereza"] == 17
    assert config.objetivos_aumento["Robusta_Negro"] == 7
    print("  -> Capa de Configuración OK.")


def probar_procesador_imagen():
    print("[2/5] Probando Capa de Procesamiento de Imagen...")
    # Crear imagen sintética rectangular (400 alto x 800 ancho)
    imagen_sintetica = np.zeros((400, 800, 3), dtype=np.uint8)
    imagen_sintetica[100:300, 200:600] = [120, 80, 200]

    # 1. Probar Autocontraste CLAHE
    img_contraste = ProcesadorImagen.aplicar_autocontraste(imagen_sintetica)
    assert img_contraste.shape == imagen_sintetica.shape

    # 2. Probar Padding y Redimensionamiento a 640x640 con recálculo de cajas YOLO
    # Caja original en el centro: x_c=0.5, y_c=0.5, w=0.5 (400px), h=0.5 (200px)
    cajas_originales = [[0.5, 0.5, 0.5, 0.5]]
    img_640, cajas_recalc = ProcesadorImagen.aplicar_relleno_y_redimensionar(
        imagen=img_contraste,
        cajas_delimitadoras=cajas_originales,
        tamano_objetivo=640
    )

    assert img_640.shape == (640, 640, 3), f"Forma incorrecta: {img_640.shape}"
    assert len(cajas_recalc) == 1
    # En imagen 800x800 pad: dimension_maxima=800.
    # Original alto=400, relleno_superior=(800-400)//2 = 200
    # x_c=0.5*800=400 / 800 = 0.5
    # y_c=(0.5*400 + 200)/800 = 400/800 = 0.5
    # w=(0.5*800)/800 = 0.5
    # h=(0.5*400)/800 = 200/800 = 0.25
    caja = cajas_recalc[0]
    assert abs(caja[0] - 0.5) < 1e-4, f"x_centro incorrecto: {caja[0]}"
    assert abs(caja[1] - 0.5) < 1e-4, f"y_centro incorrecto: {caja[1]}"
    assert abs(caja[2] - 0.5) < 1e-4, f"ancho incorrecto: {caja[2]}"
    assert abs(caja[3] - 0.25) < 1e-4, f"alto incorrecto: {caja[3]}"
    print("  -> Capa de Procesamiento OK (Autocontraste y Recálculo exacto de BBoxes).")


def probar_aumentador_datos():
    print("[3/5] Probando Capa de Aumento de Datos...")
    aumentador = AumentadorDatos()
    img_test = np.full((640, 640, 3), 128, dtype=np.uint8)
    cajas_test = [[0.5, 0.5, 0.2, 0.2]]
    etiquetas_test = [2]  # cáscara de cereza

    variaciones = aumentador.aumentar_muestra(
        imagen=img_test,
        cajas_delimitadoras=cajas_test,
        etiquetas_clases=etiquetas_test,
        multiplicador=6
    )

    assert len(variaciones) == 6, f"Se esperaban 6 variaciones, se obtuvieron {len(variaciones)}"
    for var in variaciones:
        assert var["imagen"].shape == (640, 640, 3)
        assert len(var["cajas"]) == 1
        assert var["etiquetas"] == [2]
    print("  -> Capa de Aumento de Datos OK (Albumentations con YOLO BBoxes).")


def probar_extraccion_id_y_particionado():
    print("[4/5] Probando Agrupación por ID y Prevención de Data Leakage...")
    config = Configuracion()
    gestor = GestorDataset(config)

    # Pruebas de extracción de ID de grano
    assert gestor.extraer_id_grano("agrios_frontal_arabica.jpg") == "agrios_arabica"
    assert gestor.extraer_id_grano("agrios_reverso_arabica.png") == "agrios_arabica"
    assert gestor.extraer_id_grano("brocado_validacion_frontal_robusta.jpg") == "brocado_validacion_robusta"
    assert gestor.extraer_id_grano("brocado_validacion_reverso_robusta.jpg") == "brocado_validacion_robusta"
    assert gestor.extraer_id_grano("buenos_frontal_1_arabica.jpeg") == "buenos_1_arabica"
    assert gestor.extraer_id_grano("buenos_reverso_1_arabica.jpeg") == "buenos_1_arabica"

    # Simular grupos por ID con partición de validación explícita
    grupos_simulados = {
        "agrios_arabica": [
            {"nombre_base": "agrios_frontal_arabica", "id_grano": "agrios_arabica", "es_validacion": False},
            {"nombre_base": "agrios_reverso_arabica", "id_grano": "agrios_arabica", "es_validacion": False}
        ],
        "agrios_val_arabica": [
            {"nombre_base": "agrios_validacion_frontal_arabica", "id_grano": "agrios_val_arabica", "es_validacion": True},
            {"nombre_base": "agrios_validacion_reverso_arabica", "id_grano": "agrios_val_arabica", "es_validacion": True}
        ],
    }

    divisiones = gestor.dividir_dataset(grupos_simulados)
    assert len(divisiones["train"]) == 2
    assert len(divisiones["val"]) == 2
    assert divisiones["train"][0]["nombre_base"] == "agrios_frontal_arabica"
    assert divisiones["val"][0]["nombre_base"] == "agrios_validacion_frontal_arabica"
    print("  -> Agrupación por ID y Particionado sin Data Leakage OK.")


def probar_pipeline_completo():
    print("[5/5] Probando Ejecución Completa del Pipeline End-to-End...")
    dir_temporal = tempfile.mkdtemp(prefix="test_moppi_")
    try:
        dir_imgs = os.path.join(dir_temporal, "images_in")
        dir_lbls = os.path.join(dir_temporal, "labels_in")
        dir_out = os.path.join(dir_temporal, "dataset_yolo")
        os.makedirs(dir_imgs, exist_ok=True)
        os.makedirs(dir_lbls, exist_ok=True)

        # Crear 10 granos sintéticos (20 fotos: frontal y reverso)
        for i in range(10):
            id_grano = f"grano_{i:03d}"
            # Asignar clase 2 (cáscara de cereza, aumento=4 para test) a algunos granos
            clase = 2 if i < 3 else 0

            for cara in ("frontal", "reverso"):
                nombre = f"{id_grano}_{cara}"
                # Crear imagen sintética
                img = np.random.randint(50, 200, (480, 640, 3), dtype=np.uint8)
                cv2.imwrite(os.path.join(dir_imgs, f"{nombre}.jpg"), img)
                # Crear etiqueta YOLO
                with open(os.path.join(dir_lbls, f"{nombre}.txt"), "w") as f:
                    f.write(f"{clase} 0.5 0.5 0.3 0.3\n")

        config = Configuracion(
            directorio_imagenes_entrada=dir_imgs,
            directorio_etiquetas_entrada=dir_lbls,
            directorio_salida=dir_out,
            tamano_objetivo=640,
            proporcion_division=(0.8, 0.1, 0.1),
            objetivos_aumento={2: 4},  # Multiplicador 4 para clase 2
            mapeo_nombres_a_ids={"bueno": 0, "cascara_cereza": 2},
            semilla_aleatoria=42,
        )

        gestor = GestorDataset(config)
        estadisticas = gestor.ejecutar_pipeline()

        assert estadisticas["total_granos_unicos"] == 10
        assert estadisticas["total_imagenes_originales"] == 20
        assert estadisticas["muestras_aumentadas_generadas"] > 0

        # Verificar que existen los archivos generados en train/val/test
        for particion in ("train", "val", "test"):
            imgs_generadas = os.listdir(os.path.join(dir_out, "images", particion))
            lbls_generadas = os.listdir(os.path.join(dir_out, "labels", particion))
            assert len(imgs_generadas) == len(lbls_generadas)

        print("  -> Pipeline End-to-End OK.")
    finally:
        shutil.rmtree(dir_temporal, ignore_errors=True)


if __name__ == "__main__":
    probar_configuracion()
    probar_procesador_imagen()
    probar_aumentador_datos()
    probar_extraccion_id_y_particionado()
    probar_pipeline_completo()
    print("\n TODOS LOS TESTS PASARON EXITOSAMENTE.")
