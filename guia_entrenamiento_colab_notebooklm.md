# GUÍA TÉCNICA DE ENTRENAMIENTO EN GOOGLE COLAB Y EVOLUCIÓN HISTÓRICA DE HIPERPARÁMETROS
**Proyecto**: Sistema de Visión Computacional para Detección de Defectos y Clasificación Varietal en Café Verde (*Coffea arabica* y *Coffea canephora*)  
**Institución**: Universidad Tecnológica La Salle (ULSA León, Nicaragua)  
**Entorno de Cómputo**: Google Colab (GPU NVIDIA Tesla T4 15GB VRAM / CUDA 12.8 / PyTorch 2.x)  
**Framework**: Ultralytics YOLO (v8.x y v11.x)  
**Fecha de Documentación**: Septiembre 2026  

---

## 1. INTRODUCCIÓN Y ENTORNO EXPERIMENTAL EN GOOGLE COLAB

El desarrollo de este sistema de visión artificial se llevó a cabo utilizando la infraestructura en la nube de **Google Colab**, aprovechando aceleradores gráficos **NVIDIA Tesla T4 (14,913 MiB VRAM)**. Esta plataforma permitió iterar rápidamente mediante arquitecturas convolucionales y de atención espacial, evaluando el impacto del ajuste de hiperparámetros, la resolución espacial, la ingeniería de datos (*Data-Centric AI*) y la abstracción taxonómica de clases.

### Pipeline Estándar de Ejecución en Colab
Cada sesión experimental en Google Colab siguió un protocolo estricto de 5 fases:
1. **Instalación y Configuración del Entorno**: Importación de librerías especializadas (`ultralytics`, `torch`, `opencv-python`, `albumentations`).
2. **Higiene de Memoria GPU**: Limpieza de memoria residual mediante `gc.collect()` y `torch.cuda.empty_cache()` para prevenir errores de tipo *CUDA Out-of-Memory (OOM)*.
3. **Descompresión y Verificación Determinística**: Extracción silenciosa del archivo `.zip` del dataset estructurado con `data.yaml`.
4. **Entrenamiento y Validación Integrada**: Ejecución del motor YOLO con trazabilidad de pérdidas (`box_loss`, `cls_loss`, `dfl_loss`) y métricas de desempeño ($P$, $R$, $mAP_{50}$, $mAP_{50-95}$).
5. **Persistencia y Empaquetado de Artefactos**: Compresión y descarga automatizada de la carpeta de salida conteniendo curvas PR, matrices de confusión y los pesos optimizados (`best.pt` y `last.pt`).

---

## 2. REFERENCIAS TEÓRICAS Y JUSTIFICACIÓN DE HIPERPARÁMETROS

Para la configuración de cada hiperparámetro se tomaron como base estándares científicos de la literatura internacional:

1. **Optimizador AdamW (`optimizer='AdamW'`)**:
   - *Referencia*: Loshchilov & Hutter (2019) - *"Decoupled Weight Decay Regularization"*.
   - *Justificación*: Desacopla el decaimiento de peso (*weight decay*) del gradiente acumulado, evitando que los pesos de las capas convolucionales crezcan desproporcionadamente en datasets pequeños o medianos, asegurando una convergencia más estable que el SGD clásico.
2. **Decaimiento Cosenoidal de la Tasa de Aprendizaje (`cos_lr=True`)**:
   - *Referencia*: Loshchilov & Hutter (2017) - *"SGDR: Stochastic Gradient Descent with Warm Restarts"*.
   - *Justificación*: Reduce la tasa de aprendizaje suavemente siguiendo una curva de coseno desde $\eta_{max} = 0.001$ hasta $\eta_{min} \approx 10^{-5}$, permitiendo que la red explore el espacio de parámetros al inicio y afine detalles milimétricos (como orificios de broca o fisuras de quebrados) en las épocas finales.
3. **Desactivación de Mosaico (`mosaic=0.0`)**:
   - *Referencia*: Bochkovskiy et al. (2020) - YOLOv4; Ultralytics Research Guidelines.
   - *Justificación*: El aumento por mosaico une 4 imágenes recortadas aleatoriamente. En granos de café sobre bandejas, el mosaico corta los granos a la mitad creando "falsos quebrados" artificiales y distorsionando la relación de aspecto ovalada. Desactivarlo preserva la textura natural al $100\%$.
4. **Calentamiento Gradual (`warmup_epochs=3.0`)**:
   - *Justificación*: Evita la inestabilidad numérica en las primeras épocas cuando los pesos preentrenados en COCO se adaptan a las texturas específicas del café oro.
5. **Parada Temprana (*Early Stopping*) (`patience=25` / `patience=35`)**:
   - *Referencia*: Prechelt (1998) - *"Early Stopping - but when?"*.
   - *Justificación*: Monitorea la métrica compuesta de validación (*fitness*) y congela los pesos en el punto exacto de máxima generalización, previniendo el sobreajuste (*overfitting*).

---

## 3. EVOLUCIÓN CRONOLÓGICA DE LAS VERSIONES DE ENTRENAMIENTO

A continuación se detalla la evolución completa de los experimentos, con sus códigos ejecutables en Google Colab, justificaciones técnicas y resultados obtenidos.

---

### VERSIÓN 1 (V1): Baseline Inicial con YOLOv8 Nano (13 Clases, 640px)
- **Motivación**: Establecer una línea base (*baseline*) de referencia con el modelo más ligero de la generación anterior (YOLOv8n).
- **Código Ejecutado en Colab**:
```python
# =====================================================================
# VERSIÓN 1: BASELINE YOLOV8 NANO (13 CLASES)
# =====================================================================
!pip install -q ultralytics
import gc, torch
from ultralytics import YOLO

gc.collect()
if torch.cuda.is_available(): torch.cuda.empty_cache()
!unzip -q -o dataset_yolo_13clases.zip -d .

modelo_v1 = YOLO("yolov8n.pt")
modelo_v1.train(
    data="dataset_yolo/data.yaml",
    epochs=100,
    batch=16,
    imgsz=640,
    optimizer="SGD",
    lr0=0.01,
    patience=20,
    device=0,
    project="entrenamientos_alvizua",
    name="v1_yolov8n_baseline"
)
```
- **Resultados**: $mAP@0.50 = 41.20\%$, $mAP@0.50:0.95 = 31.50\%$, Latencia: $3.2\text{ ms}$ ($312\text{ FPS}$).
- **Lección Aprendida**: Demostró viabilidad técnica, pero el optimizador SGD y la baja capacidad del modelo nano provocaron un Recall muy pobre en defectos sutiles (Brocados y Conchas $< 20\%$).

---

### VERSIÓN 2 (V2): Transición a YOLO11 Nano con Optimizador AdamW (13 Clases)
- **Motivación**: Migrar a la arquitectura YOLO11, incorporando bloques convolucionales `C3k2` y módulos de atención espacial `C2PSA`, cambiando a optimizador `AdamW`.
- **Código Ejecutado en Colab**:
```python
# =====================================================================
# VERSIÓN 2: YOLO11 NANO CON ADAMW
# =====================================================================
modelo_v2 = YOLO("yolo11n.pt")
modelo_v2.train(
    data="dataset_yolo/data.yaml",
    epochs=120,
    batch=16,
    imgsz=640,
    optimizer="AdamW",
    lr0=0.001,
    weight_decay=0.0005,
    patience=25,
    device=0,
    project="entrenamientos_alvizua",
    name="v2_yolo11n_adamw"
)
```
- **Resultados**: $mAP@0.50 = 46.80\%$, $mAP@0.50:0.95 = 37.40\%$, Latencia: $3.5\text{ ms}$ ($285\text{ FPS}$).
- **Lección Aprendida**: El mecanismo de atención de YOLO11 mejoró el reconocimiento de bordes (+5.6% en $mAP$), pero las distorsiones de aumento por mosaico seguían confundiendo la hendidura natural del grano con fisuras.

---

### VERSIÓN 5 (V5): Escalamiento a YOLO11s con Decaimiento Cosenoidal y Sin Mosaico
- **Motivación**: Escalar a `YOLO11s` (Small, 9.4M parámetros) para dotar a la red de mayor capacidad representacional, desactivando mosaico (`mosaic=0.0`) y activando `cos_lr=True`.
- **Código Ejecutado en Colab**:
```python
# =====================================================================
# VERSIÓN 5: MODELO MULTICLASE CAMPEÓN INICIAL (YOLO11s)
# =====================================================================
modelo_v5 = YOLO("yolo11s.pt")
modelo_v5.train(
    data="dataset_yolo/data.yaml",
    epochs=120,
    batch=16,
    imgsz=640,
    optimizer="AdamW",
    lr0=0.001,
    weight_decay=0.0005,
    cos_lr=True,
    mosaic=0.0,
    warmup_epochs=3.0,
    patience=35,
    device=0,
    project="entrenamientos_alvizua",
    name="v5_yolo11s_multiclase_original"
)
```
- **Resultados**: $mAP@0.50 = \mathbf{50.49\%}$, $mAP@0.50:0.95 = 44.57\%$, Latencia: $6.1\text{ ms}$ ($164\text{ FPS}$).
- **Lección Aprendida**: Se coronó como el mejor modelo multiclase inicial. Rescató 92 granos sanos y logró $0\%$ de fuga en granos negros y cerezas. Sin embargo, se descubrió una anomalía en la métrica de granos buenos en validación.

---

### VERSIÓN 6 (V6): Auditoría Data-Centric AI y Corrección de Anotaciones en Label Studio
- **Motivación**: Diagnóstico de error en el dataset. La imagen `buenos_validacion_frontal_arabica.jpg` tenía 55 granos reales pero solo 18 estaban etiquetados. Los 37 granos restantes eran penalizados falsamente como fondo (*background*).
- **Acción**: Se exportó el JSON corregido con las 55 anotaciones y se re-ejecutó el pipeline de preprocesamiento, expandiendo el conjunto de validación de **373 a 410 instancias reales**.

---

### VERSIÓN 7 (V7): Experimento de Alta Resolución Nativa a 800px (13 Clases)
- **Motivación**: Entrenar a $800\times 800\text{ px}$ para darle a la red un $+56\%$ de píxeles por grano.
- **Código Ejecutado en Colab**:
```python
# =====================================================================
# VERSIÓN 7: EXPERIMENTO A 800PX NATIVO
# =====================================================================
modelo_v7 = YOLO("yolo11s.pt")
modelo_v7.train(
    data="dataset_yolo_800px/data.yaml",
    epochs=120,
    batch=8,
    imgsz=800,
    optimizer="AdamW",
    lr0=0.001,
    weight_decay=0.0005,
    cos_lr=True,
    mosaic=0.0,
    patience=20,
    device=0,
    project="entrenamientos_alvizua",
    name="v7_yolo11s_800px"
)
```
- **Resultados**: $mAP@0.50 = 26.50\%$, Latencia: $8.2\text{ ms}$ ($122\text{ FPS}$).
- **Lección Aprendida**: El Early Stopping se activó prematuramente en la época 14 debido a un pico de gradiente durante el reescalado de anclas de COCO (preentrenado a 640px). La resolución de 640px demostró ser óptima y más rápida.

---

### VERSIÓN 8 (V8): YOLO11s 13 Clases con Dataset Corregido (120 Épocas Completas)
- **Motivación**: Re-entrenar el modelo de 13 clases sobre las 410 instancias limpias con `patience=0` para permitir convergencia total.
- **Código Ejecutado en Colab**:
```python
# =====================================================================
# VERSIÓN 8: 13 CLASES CON DATASET 100% CORREGIDO (120 ÉPOCAS)
# =====================================================================
modelo_v8 = YOLO("yolo11s.pt")
modelo_v8.train(
    data="dataset_yolo/data.yaml",
    epochs=120,
    batch=16,
    imgsz=640,
    optimizer="AdamW",
    lr0=0.001,
    weight_decay=0.0005,
    cos_lr=True,
    mosaic=0.0,
    warmup_epochs=3.0,
    patience=0,
    device=0,
    project="entrenamientos_alvizua",
    name="v8_yolo11s_13clases_corregido"
)
```
- **Resultados**: $mAP@0.50 = 32.35\%$, $mAP@0.50:0.95 = 27.60\%$, Latencia: $4.9\text{ ms}$ ($204\text{ FPS}$).
- **Impacto Clave**: El rescate de `Arabica_Bueno` subió de 27 a **60 granos reales ($+122.2\%$)** con Recall de $70.7\%$ y `Arabica_Negro` alcanzó $89.1\%$ de Recall.  
  *Diagnóstico*: El $mAP$ promedio bajó a $32.4\%$ porque la red confundía subdefectos entre sí (un brocado clasificado como quebrado), demostrando la necesidad de una abstracción taxonómica superior.

---

### VERSIÓN 9 (V9): Paradigma Binario Industrial (2 Clases: Grano_Bueno vs Grano_Defecto)
- **Motivación**: Eliminar la matriz de confusión inter-defecto agrupando todos los defectos en una sola clase binaria de descarte.
- **Código Ejecutado en Colab**:
```python
# =====================================================================
# VERSIÓN 9: MODELO BINARIO INDUSTRIAL (2 CLASES)
# =====================================================================
modelo_v9 = YOLO("yolo11s.pt")
modelo_v9.train(
    data="dataset_yolo_binario/data.yaml",
    epochs=100,
    batch=16,
    imgsz=640,
    optimizer="AdamW",
    lr0=0.001,
    weight_decay=0.0005,
    cos_lr=True,
    mosaic=0.0,
    warmup_epochs=3.0,
    patience=25,
    device=0,
    project="entrenamientos_alvizua",
    name="v9_yolo11s_binario"
)
```
- **Resultados**: $mAP@0.50 = \mathbf{81.80\%}$, $mAP@0.50:0.95 = 70.37\%$, Pureza: **$97.3\%$** (solo 1 defecto colado de 215).
- **Lección Aprendida**: El $mAP$ dio un salto histórico ($+152\%$), pero la red se volvió excesivamente "desconfiada", clasificando granos sanos con sombras normales como defectos (solo rescató 36 granos buenos).

---

### VERSIÓN 10 (V10): Paradigma Tri-Clase (CAMPEÓN ABSOLUTO 👑)
- **Motivación**: Diseñar la arquitectura óptima para la Finca Alvizua: separar las dos variedades comerciales sanas (`Arabica_Bueno` y `Robusta_Bueno`) y unificar el canal de descarte (`Grano_Defecto`).
- **Código Ejecutado en Colab**:
```python
# =====================================================================
# VERSIÓN 10: MODELO TRI-CLASE CAMPEÓN (YOLO11s)
# =====================================================================
modelo_v10 = YOLO("yolo11s.pt")
modelo_v10.train(
    data="dataset_yolo_triclase/data.yaml",
    epochs=100,
    batch=16,
    imgsz=640,
    optimizer="AdamW",
    lr0=0.001,
    weight_decay=0.0005,
    cos_lr=True,
    mosaic=0.0,
    warmup_epochs=3.0,
    patience=25,
    device=0,
    project="entrenamientos_alvizua",
    name="v10_yolo11s_triclase_campeon"
)
```
- **Resultados Históricos**:
  - **$mAP@0.50$ Global**: **$\mathbf{87.41\%}$ (Récord Máximo)**
  - **$mAP@0.50:0.95$**: **$\mathbf{75.61\%}$**
  - **Precisión Global ($P$)**: **$86.10\%$**
  - **Sensibilidad Global ($R$)**: **$80.30\%$**
  - **Precisión en Arabica Bueno**: **$\mathbf{94.80\%}$**
  - **$mAP@50$ en Robusta Bueno**: **$\mathbf{95.60\%}$** ($Recall = 93.7\%$)
  - **$mAP@50$ en Grano Defecto**: **$87.70\%$**
  - **Granos Sanos Rescatados**: **$\mathbf{127\text{ granos}}$** ($57$ Arábica + $70$ Robusta)
  - **Pureza en Saco de Arábica**: **$\mathbf{100.0\%}$ (Cero defectos y cero Robusta colados)**
  - **Latencia de Inferencia**: **$4.9\text{ ms}$ ($\mathbf{204\text{ FPS}}$)**
- **Conclusión**: **El modelo cumbre de la investigación**. Congeló los pesos en el punto dulce (*sweet spot*) de la época 47 mediante Early Stopping.

---

### VERSIÓN 11 (V11): Tri-Clase Forzado a 120 Épocas (`patience=0`)
- **Motivación**: Verificar experimentalmente si forzar 120 épocas continuas sin parada temprana podía mejorar el Recall de Arábica.
- **Código Ejecutado en Colab**:
```python
# =====================================================================
# VERSIÓN 11: TRI-CLASE FORZADO A 120 ÉPOCAS (SIN PARADA TEMPRANA)
# =====================================================================
modelo_v11 = YOLO("yolo11s.pt")
modelo_v11.train(
    data="dataset_yolo_triclase/data.yaml",
    epochs=120,
    batch=16,
    imgsz=640,
    optimizer="AdamW",
    lr0=0.001,
    weight_decay=0.0005,
    cos_lr=True,
    mosaic=0.0,
    warmup_epochs=3.0,
    patience=0,
    device=0,
    project="entrenamientos_alvizua",
    name="v11_yolo11s_triclase_120ep"
)
```
- **Resultados**: $mAP@0.50 = 74.82\%$, $mAP@0.50:0.95 = 65.46\%$, Granos Rescatados: $2\text{ granos}$.
- **Hallazgo Científico**: Demostró el fenómeno de **Sobre-ajuste por Sesgo de Superclase (*Superclass Bias Overfitting*)**. Al entrenar en exceso, la red aprendió a clasificar casi todo como `Grano_Defecto`, degradando el rescate de café sano. Esto justificó empíricamente la supremacía de la **Versión 10 (Época 47)**.

---

## 4. MATRIZ DE DECISIÓN PARA INFERENCIA EN TIEMPO REAL

Para la puesta en marcha del modelo campeón (`v10_yolo11s_triclase_campeon/weights/best.pt`) en el microcontrolador o sistema embebido de la clasificadora física, se define la siguiente regla de software:

```python
from ultralytics import YOLO

# Carga del modelo campeón
modelo_alvizua = YOLO("modelo_campeon_triclase_alvizua.pt")

# Inferencia en tiempo real calibrada
resultados = modelo_alvizua.predict(
    source="camara_bandeja.jpg",
    conf=0.40,          # Umbral de confianza calibrado para pureza > 98%
    iou=0.45,           # Non-Maximum Suppression para cajas superpuestas
    imgsz=640,
    device=0            # GPU / TensorRT
)
```

---

## 5. RESUMEN DE IMPACTO PARA NOTEBOOKLM Y DEFENSA DE TESIS

1. **Eficiencia Algorítmica**: La transición de 13 clases a 3 clases incrementó el $mAP$ del $32.4\%$ al **$87.41\%$** ($+170\%$ de mejora relativa).
2. **Data-Centric AI**: La corrección de las 55 etiquetas duplicó la tasa de detección de granos sanos ($+122\%$).
3. **Factibilidad Tecnológica**: Con $4.9\text{ ms}$ de latencia ($204\text{ FPS}$), el sistema supera los requerimientos de bandas transportadoras comerciales ($166\text{ FPS}$).
4. **Impacto Económico Directo**: Garantiza **$100\%$ de pureza en café Arábica de exportación** y recupera el $88.6\%$ del café Robusta para comercio nacional.
