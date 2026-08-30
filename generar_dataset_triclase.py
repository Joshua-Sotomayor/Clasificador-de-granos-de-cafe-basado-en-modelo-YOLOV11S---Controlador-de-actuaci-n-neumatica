"""
Generador de Dataset Tri-Clase (Arabica_Bueno, Robusta_Bueno, Grano_Defecto)
Finca Alvizua - Universidad Tecnológica La Salle (ULSA León)
"""

import os
import random
import re
import cv2
import zipfile
from typing import Dict, List, Tuple
from src.procesador_imagen import ProcesadorImagen
from src.aumentador_datos import AumentadorDatos

# Mapeo de IDs de 13 clases a 3 clases:
# 0: Arabica_Bueno
# 1: Robusta_Bueno
# 2: Grano_Defecto
MAPEO_TRICLASE = {
    0: 2,   # Arabica_Agrio -> Grano_Defecto
    1: 2,   # Arabica_Brocado -> Grano_Defecto
    2: 0,   # Arabica_Bueno -> Arabica_Bueno ⭐
    3: 2,   # Arabica_Cereza -> Grano_Defecto
    4: 2,   # Arabica_Concha -> Grano_Defecto
    5: 2,   # Arabica_Inmaduro -> Grano_Defecto
    6: 2,   # Arabica_Negro -> Grano_Defecto
    7: 2,   # Arabica_Quebrado -> Grano_Defecto
    8: 2,   # Robusta_Brocado -> Grano_Defecto
    9: 1,   # Robusta_Bueno -> Robusta_Bueno ⭐
    10: 2,  # Robusta_Cereza -> Grano_Defecto
    11: 2,  # Robusta_Negro -> Grano_Defecto
    12: 2,  # Robusta_Quebrado -> Grano_Defecto
}


def leer_etiquetas_yolo_triclase(ruta_etiqueta: str) -> Tuple[List[List[float]], List[int]]:
    cajas = []
    clases = []
    if not ruta_etiqueta or not os.path.exists(ruta_etiqueta):
        return cajas, clases

    with open(ruta_etiqueta, "r", encoding="utf-8") as f:
        for linea in f:
            partes = linea.strip().split()
            if len(partes) >= 5:
                try:
                    clase_original = int(partes[0])
                    coords = [float(p) for p in partes[1:5]]
                    clase_triclase = MAPEO_TRICLASE.get(clase_original, 2)
                    cajas.append(coords)
                    clases.append(clase_triclase)
                except ValueError:
                    continue
    return cajas, clases


def guardar_etiquetas(ruta_archivo: str, cajas: List[List[float]], clases: List[int]):
    os.makedirs(os.path.dirname(ruta_archivo), exist_ok=True)
    with open(ruta_archivo, "w", encoding="utf-8") as f:
        for c, caja in zip(clases, cajas):
            f.write(f"{c} {caja[0]:.6f} {caja[1]:.6f} {caja[2]:.6f} {caja[3]:.6f}\n")


def agrupar_por_id_grano(dir_imgs: str, dir_lbls: str) -> Dict[str, List[Dict[str, str]]]:
    grupos = {}
    patron_id = re.compile(r"(grano[_\s]*\d+|id[_\s]*\d+)", re.IGNORECASE)
    patron_val = re.compile(r"(val|validaci[oó]n|test)", re.IGNORECASE)

    archivos = [f for f in os.listdir(dir_imgs) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    for arch in sorted(archivos):
        nombre_base, ext = os.path.splitext(arch)
        ruta_img = os.path.join(dir_imgs, arch)
        ruta_lbl = os.path.join(dir_lbls, f"{nombre_base}.txt")

        if not os.path.exists(ruta_lbl):
            continue

        match_id = patron_id.search(nombre_base)
        id_grano = match_id.group(1).lower().replace(" ", "_") if match_id else nombre_base

        muestra = {
            "ruta_imagen": ruta_img,
            "ruta_etiqueta": ruta_lbl,
            "nombre_base": nombre_base,
            "extension": ext,
            "es_validacion": bool(patron_val.search(nombre_base)),
        }
        grupos.setdefault(id_grano, []).append(muestra)

    return grupos


def generar_dataset_triclase():
    print("=" * 60)
    print("  GENERANDO DATASET YOLO TRI-CLASE")
    print("  (Arabica_Bueno, Robusta_Bueno, Grano_Defecto)")
    print("  Finca Alvizua - Universidad Tecnológica La Salle")
    print("=" * 60)

    dir_imgs_in = "dataset_bruto/images"
    dir_lbls_in = "dataset_bruto/labels"
    dir_salida = "dataset_yolo_triclase"
    tamano_objetivo = 640

    procesador = ProcesadorImagen()
    aumentador = AumentadorDatos()

    # 1. Crear directorios de salida
    for part in ("train", "val"):
        os.makedirs(os.path.join(dir_salida, "images", part), exist_ok=True)
        os.makedirs(os.path.join(dir_salida, "labels", part), exist_ok=True)

    # 2. Agrupar por grano
    grupos = agrupar_por_id_grano(dir_imgs_in, dir_lbls_in)
    print(f"[*] Total granos físicos identificados: {len(grupos)}")

    # 3. Separar particiones respetando validación
    divisiones = {"train": [], "val": []}
    for id_grano, muestras in grupos.items():
        if any(m["es_validacion"] for m in muestras):
            divisiones["val"].extend(muestras)
        else:
            divisiones["train"].extend(muestras)

    print(f"[*] Imágenes base: Train={len(divisiones['train'])}, Val={len(divisiones['val'])}")

    estadisticas = {
        "train_base": 0, "val_base": 0, "train_aum": 0,
        "arabica_bueno_val": 0, "robusta_bueno_val": 0, "defectos_val": 0
    }

    # 4. Procesar y guardar imágenes
    for part, muestras in divisiones.items():
        print(f"\n[*] Procesando partición '{part}' ({len(muestras)} imágenes base)...")
        for m in muestras:
            img = cv2.imread(m["ruta_imagen"])
            if img is None:
                continue

            cajas_orig, clases_orig = leer_etiquetas_yolo_triclase(m["ruta_etiqueta"])
            if part == "val":
                estadisticas["arabica_bueno_val"] += sum(1 for c in clases_orig if c == 0)
                estadisticas["robusta_bueno_val"] += sum(1 for c in clases_orig if c == 1)
                estadisticas["defectos_val"] += sum(1 for c in clases_orig if c == 2)

            # CLAHE + Letterbox
            img_clahe = procesador.aplicar_autocontraste(img)
            img_final, cajas_finales = procesador.aplicar_relleno_y_redimensionar(
                imagen=img_clahe,
                cajas_delimitadoras=cajas_orig,
                tamano_objetivo=tamano_objetivo
            )

            # Guardar base
            ruta_img_out = os.path.join(dir_salida, "images", part, f"{m['nombre_base']}.jpg")
            ruta_lbl_out = os.path.join(dir_salida, "labels", part, f"{m['nombre_base']}.txt")
            cv2.imwrite(ruta_img_out, img_final)
            guardar_etiquetas(ruta_lbl_out, cajas_finales, clases_orig)
            estadisticas[f"{part}_base"] += 1

            # Aumento enriquecido en train (8 variaciones ricas por imagen base)
            if part == "train" and len(cajas_finales) > 0:
                variaciones = aumentador.aumentar_muestra(
                    imagen=img_final,
                    cajas_delimitadoras=cajas_finales,
                    etiquetas_clases=clases_orig,
                    multiplicador=8
                )
                for idx, v in enumerate(variaciones, 1):
                    nom_aum = f"{m['nombre_base']}_aum_{idx}"
                    r_img_aum = os.path.join(dir_salida, "images", part, f"{nom_aum}.jpg")
                    r_lbl_aum = os.path.join(dir_salida, "labels", part, f"{nom_aum}.txt")
                    cv2.imwrite(r_img_aum, v["imagen"])
                    guardar_etiquetas(r_lbl_aum, v["cajas"], v["etiquetas"])
                    estadisticas["train_aum"] += 1

    # 5. Generar data.yaml tri-clase
    ruta_yaml = os.path.join(dir_salida, "data.yaml")
    with open(ruta_yaml, "w", encoding="utf-8") as f:
        f.write("# Configuración del Dataset Tri-Clase YOLO (Finca Alvizua)\n")
        f.write(f"path: {dir_salida}\n")
        f.write("train: images/train\n")
        f.write("val: images/val\n\n")
        f.write("nc: 3\n\n")
        f.write("names:\n")
        f.write("  0: Arabica_Bueno\n")
        f.write("  1: Robusta_Bueno\n")
        f.write("  2: Grano_Defecto\n")

    print(f"\n[*] Archivo '{ruta_yaml}' generado con éxito (3 clases).")

    # 6. Comprimir a zip
    zip_salida = "dataset_yolo_triclase.zip"
    print(f"[*] Comprimiendo en '{zip_salida}'...")
    with zipfile.ZipFile(zip_salida, "w", zipfile.ZIP_DEFLATED) as zipf:
        for raiz, _, archivos in os.walk(dir_salida):
            for archivo in archivos:
                ruta_c = os.path.join(raiz, archivo)
                ruta_r = os.path.relpath(ruta_c, os.path.dirname(dir_salida))
                zipf.write(ruta_c, ruta_r)

    tamano_mb = os.path.getsize(zip_salida) / (1024 * 1024)
    print(f"\n[OK] Dataset Tri-Clase generado con éxito: '{zip_salida}' ({tamano_mb:.2f} MB)")
    print(f"     - Train: {estadisticas['train_base']} base + {estadisticas['train_aum']} aumentadas = {estadisticas['train_base'] + estadisticas['train_aum']} imágenes")
    print(f"     - Val: {estadisticas['val_base']} imágenes:")
    print(f"            • Arabica_Bueno: {estadisticas['arabica_bueno_val']} granos")
    print(f"            • Robusta_Bueno: {estadisticas['robusta_bueno_val']} granos")
    print(f"            • Grano_Defecto: {estadisticas['defectos_val']} granos")
    print("=" * 60)


if __name__ == "__main__":
    generar_dataset_triclase()
