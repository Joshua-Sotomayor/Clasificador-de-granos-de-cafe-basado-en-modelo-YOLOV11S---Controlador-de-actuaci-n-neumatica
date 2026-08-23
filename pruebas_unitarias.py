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
    assert "cascara_cereza" in config.objetivos_aumento
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
    assert gestor.extraer_id_grano("grano_001_frontal.jpg") == "grano_001"
    assert gestor.extraer_id_grano("grano_001_reverso.png") == "grano_001"
    assert gestor.extraer_id_grano("muestra_45_caraA.jpeg") == "muestra_45"
    assert gestor.extraer_id_grano("muestra_45_caraB.jpeg") == "muestra_45"
    assert gestor.extraer_id_grano("cafe_88_f.jpg") == "cafe_88"
    assert gestor.extraer_id_grano("cafe_88_r.jpg") == "cafe_88"

    # Simular grupos por ID
    grupos_simulados = {
        f"grano_{i:03d}": [
            {"nombre_base": f"grano_{i:03d}_frontal", "id_grano": f"grano_{i:03d}"},
            {"nombre_base": f"grano_{i:03d}_reverso", "id_grano": f"grano_{i:03d}"}
        ]
        for i in range(100)
    }

    divisiones = gestor.dividir_dataset(grupos_simulados)
    train_ids = {m["id_grano"] for m in divisiones["train"]}
    val_ids = {m["id_grano"] for m in divisiones["val"]}
    test_ids = {m["id_grano"] for m in divisiones["test"]}

    # Verificar que no hay solapamiento de IDs (Zero Data Leakage)
    assert len(train_ids.intersection(val_ids)) == 0, "Fuga de datos entre Train y Val!"
    assert len(train_ids.intersection(test_ids)) == 0, "Fuga de datos entre Train y Test!"
    assert len(val_ids.intersection(test_ids)) == 0, "Fuga de datos entre Val y Test!"
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
