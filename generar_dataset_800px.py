"""
Script para generar el dataset YOLO en resolución nativa de 800x800 píxeles.
Finca Alvizua - Detección de Defectos en Café
"""

import os
import shutil
import zipfile
from src.configuracion import Configuracion
from src.gestor_dataset import GestorDataset


def generar_dataset_800():
    print("Iniciando generación de dataset nativo a 800x800 px...")
    
    # 1. Configurar salida a dataset_yolo_800px con 800px nativo
    config = Configuracion(
        directorio_imagenes_entrada="dataset_bruto/images",
        directorio_etiquetas_entrada="dataset_bruto/labels",
        directorio_salida="dataset_yolo_800px",
        tamano_objetivo=800,
        proporcion_division=(0.8, 0.1, 0.1),
        semilla_aleatoria=42,
    )
    
    # 2. Ejecutar pipeline
    gestor = GestorDataset(config)
    estadisticas = gestor.ejecutar_pipeline()
    
    # 3. Comprimir a dataset_yolo_800px.zip
    archivo_zip = "dataset_yolo_800px.zip"
    print(f"\n[*] Comprimiendo '{config.directorio_salida}' en '{archivo_zip}'...")
    
    with zipfile.ZipFile(archivo_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for raiz, _, archivos in os.walk(config.directorio_salida):
            for archivo in archivos:
                ruta_completa = os.path.join(raiz, archivo)
                ruta_relativa = os.path.relpath(ruta_completa, os.path.dirname(config.directorio_salida))
                zipf.write(ruta_completa, ruta_relativa)
                
    tamano_mb = os.path.getsize(archivo_zip) / (1024 * 1024)
    print(f"[OK] Archivo '{archivo_zip}' generado con exito ({tamano_mb:.2f} MB).")
    return estadisticas


if __name__ == "__main__":
    generar_dataset_800()
