# =============================================================================
# 🔬 ENTRENAMIENTO YOLO11s — Versión 5 (Small)
# Réplica de hiperparámetros V4 Campeona (YOLO11m) con arquitectura Small
# Para ejecutar en Google Colab con GPU
# =============================================================================

# ─── CELDA 1: Instalar Ultralytics ───────────────────────────────────
# !pip install ultralytics -q

# ─── CELDA 2: Montar Google Drive ────────────────────────────────────
# from google.colab import drive
# drive.mount('/content/drive')

# ─── CELDA 3: Verificar GPU disponible ──────────────────────────────
# !nvidia-smi

# ─── CELDA 4: Subir o copiar el dataset_yolo desde Drive ────────────
# Opción A: Si el dataset_yolo.zip ya está en Drive
# !cp /content/drive/MyDrive/MOPPI/dataset_yolo.zip /content/
# !unzip -q /content/dataset_yolo.zip -d /content/

# Opción B: Si subes el dataset_yolo.zip manualmente a Colab
# (usar el panel de archivos de Colab para subir dataset_yolo.zip)
# !unzip -q /content/dataset_yolo.zip -d /content/

# ─── CELDA 5: Verificar estructura del dataset ──────────────────────
# !cat /content/dataset_yolo/data.yaml
# !echo "---"
# !echo "Imágenes de entrenamiento:"
# !ls /content/dataset_yolo/images/train/ | wc -l
# !echo "Imágenes de validación:"
# !ls /content/dataset_yolo/images/val/ | wc -l

# ─── CELDA 6: Actualizar rutas en data.yaml para Colab ──────────────
import yaml

data_yaml_path = "/content/dataset_yolo/data.yaml"

with open(data_yaml_path, "r") as f:
    data_config = yaml.safe_load(f)

# Actualizar path raíz para Colab
data_config["path"] = "/content/dataset_yolo"
data_config["train"] = "images/train"
data_config["val"] = "images/val"

with open(data_yaml_path, "w") as f:
    yaml.dump(data_config, f, default_flow_style=False)

print("✅ data.yaml actualizado para Colab:")
print(yaml.dump(data_config, default_flow_style=False))

# ─── CELDA 7: ENTRENAMIENTO YOLO11s ─────────────────────────────────
from ultralytics import YOLO

# Cargar modelo preentrenado YOLO11s (Small ~9.4M params)
modelo = YOLO("yolo11s.pt")

# Entrenar con hiperparámetros de la Versión 4 Campeona
resultados = modelo.train(
    # === Dataset ===
    data=data_yaml_path,
    imgsz=640,

    # === Duración y Early Stopping ===
    epochs=150,          # Techo alto; early stopping cortará antes
    patience=35,         # Misma paciencia que V4 campeona

    # === Optimizador: AdamW + Cosine Annealing (clave del éxito V4) ===
    optimizer="AdamW",
    lr0=0.001,           # Learning rate inicial
    lrf=0.01,            # Factor final del LR
    cos_lr=True,         # Decaimiento cosenoidal suave

    # === Regularización ===
    weight_decay=0.0005,
    dropout=0.0,

    # === Pesos de pérdida ===
    box=7.5,             # box_loss
    cls=0.5,             # cls_loss
    dfl=1.5,             # dfl_loss

    # === Aumento de datos ===
    hsv_h=0.015,
    hsv_s=0.7,
    hsv_v=0.4,
    degrees=0.0,
    translate=0.1,
    scale=0.5,
    fliplr=0.5,
    flipud=0.0,
    mosaic=1.0,
    mixup=0.0,

    # === Hardware (Colab GPU) ===
    batch=-1,            # Auto-batch según VRAM de Colab
    workers=2,           # Colab funciona mejor con 2 workers
    device=0,            # GPU de Colab

    # === Proyecto y logging ===
    project="/content/runs",
    name="yolo11s_cafe_v5",
    exist_ok=True,
    verbose=True,
    save=True,
    save_period=25,
    plots=True,

    # === Reproducibilidad ===
    seed=42,
)

# ─── CELDA 8: Ver resultados del entrenamiento ──────────────────────
from IPython.display import Image, display
import os

ruta_resultados = "/content/runs/yolo11s_cafe_v5"

# Mostrar curvas de entrenamiento
if os.path.exists(f"{ruta_resultados}/results.png"):
    display(Image(filename=f"{ruta_resultados}/results.png", width=900))

# Mostrar matriz de confusión
if os.path.exists(f"{ruta_resultados}/confusion_matrix_normalized.png"):
    display(Image(filename=f"{ruta_resultados}/confusion_matrix_normalized.png", width=700))

# Mostrar predicciones de validación
if os.path.exists(f"{ruta_resultados}/val_batch0_pred.png"):
    display(Image(filename=f"{ruta_resultados}/val_batch0_pred.png", width=700))

print("\n" + "=" * 60)
print("   ENTRENAMIENTO YOLO11s COMPLETADO")
print("=" * 60)
print(f"   Mejor modelo: {ruta_resultados}/weights/best.pt")
print("=" * 60)

# ─── CELDA 9: Copiar best.pt a Google Drive ─────────────────────────
# !mkdir -p /content/drive/MyDrive/MOPPI/modelos_entrenados/
# !cp /content/runs/yolo11s_cafe_v5/weights/best.pt /content/drive/MyDrive/MOPPI/modelos_entrenados/yolo11s_best.pt
# print("✅ Modelo guardado en Google Drive")

# ─── CELDA 10: Validar el modelo entrenado ───────────────────────────
# modelo_entrenado = YOLO("/content/runs/yolo11s_cafe_v5/weights/best.pt")
# metricas = modelo_entrenado.val(data=data_yaml_path, imgsz=640, conf=0.30)
# print(f"\nmAP50:    {metricas.box.map50:.4f}")
# print(f"mAP50-95: {metricas.box.map:.4f}")
# print(f"Precisión: {metricas.box.mp:.4f}")
# print(f"Recall:    {metricas.box.mr:.4f}")
