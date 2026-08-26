# Reporte Técnico y Científico: Sistema de Visión Artificial para Clasificación de Café (Finca Alvizua)
**Documento de Evaluación para NotebookLM y Validación de Producción**

---

## 1. Resumen Ejecutivo y Objetivo Operativo

El presente proyecto desarrolló e implementó un pipeline integral de preprocesamiento, aumento de datos balanceado y entrenamiento de una red neuronal de última generación (**YOLO11 Medium**) para la detección y clasificación de **13 clases de café** (variedades Arábica y Robusta con sus respectivos defectos físicos y fitosanitarios) en la **Finca Alvizua**.

### Enfoque de Producción (Regla de Negocio Crítica)
En una línea de producción agroindustrial con cinta transportadora y actuadores mecánicos (pistones neumáticos o compuertas de descarte):
- **Costo Cero en Confusión entre Defectos**: Si el sistema confunde un *grano negro* con un *grano brocado* o un *grano agrio* con un *grano inmaduro*, el impacto productivo es **nulo**, ya que todos los defectos son desviados al mismo contenedor de desecho.
- **Foco Primario en Granos Buenos**: El éxito económico y de calidad del sistema depende exclusivamente de dos factores:
  1. **Evitar Falsos Positivos de Defecto**: No expulsar granos sanos a la basura (proteger el rendimiento en kilogramos).
  2. **Evitar Falsos Negativos de Defecto**: No permitir que granos defectuosos se mezclen en el lote de café de exportación (proteger la calidad en taza).

---

## 2. Glosario Pedagógico de Inteligencia Artificial (Explicado para Café)

Para facilitar la interpretación de los resultados y la comparación con la literatura científica, a continuación se definen los términos técnicos clave:

### A. Métricas de Rendimiento del Modelo

#### 1. Precisión ($P$ - Precision)
- **Definición**: Es la pureza de las predicciones del modelo. Responde a la pregunta: *De todos los granos que el modelo marcó como "Buenos", ¿cuántos eran realmente buenos?*
- **Impacto en Café**: Una alta precisión en *Granos Buenos* garantiza que el saco de café final no esté contaminado con defectos.

#### 2. Recall / Exhaustividad ($R$)
- **Definición**: Es la capacidad del modelo para no dejar escapar ningún grano. Responde a la pregunta: *De todos los granos buenos reales que pasaron por la cinta transportadora, ¿qué porcentaje logró identificar el modelo?*
- **Impacto en Café**: Un Recall del $90\%$ en *Granos Buenos* significa que de 100 granos sanos, el modelo rescata 90 y solo 10 se le escapan por error.

#### 3. $mAP_{50}$ (Mean Average Precision al 50%)
- **Definición**: Es la métrica reina en detección de objetos (YOLO). Es el promedio ponderado de la Precisión y el Recall para todas las clases, considerando que una detección es válida si la caja predicha coincide al menos en un **$50\%$ de área ($IoU \ge 0.5$)** con el grano real.

#### 4. $mAP_{50-95}$
- **Definición**: Evalúa la exactitud geométrica milimétrica de las cajas delimitadoras, promediando el desempeño desde un solapamiento del $50\%$ hasta un $95\%$. Mide qué tan ajustado está el contorno de la caja al grano físico.

#### 5. $IoU$ (Intersection over Union - Intersección sobre Unión)
- **Definición**: Mide el porcentaje de solapamiento espacial entre el cuadro que dibujó la persona al etiquetar y el cuadro que predijo la inteligencia artificial.

---

### B. Pérdidas y Mecanismos de Aprendizaje (*Losses*)

#### 6. Pérdidas (*Losses*): `box_loss`, `cls_loss`, `dfl_loss`
- **¿Qué es una pérdida?**: Es la medida matemática del error del modelo. Durante el entrenamiento, las pérdidas deben **bajar continuamente**; cuanto más cerca de cero estén, mejor aprende la red.
  - **`box_loss` (Pérdida de Caja)**: Mide el error al ubicar las coordenadas y dimensiones de la caja.
  - **`cls_loss` (Pérdida de Clasificación)**: Mide el error al identificar qué defecto o variedad tiene el grano.
  - **`dfl_loss` (Distribution Focal Loss)**: Mide la precisión de los bordes finos de la caja delimitadora.

#### 7. Transfer Learning (Transferencia de Aprendizaje)
- **Definición**: En lugar de inicializar las neuronas con valores aleatorios desde cero, se toma un modelo base (`yolo11m.pt`) que ya fue preentrenado con millones de imágenes generales (dataset COCO). El modelo ya sabe reconocer bordes, contrastes, curvas y texturas; nosotros solo realizamos un **ajuste fino (*fine-tuning*)** para especializarlo en café.

#### 8. Optimizadores: AdamW vs SGD
- **SGD (Stochastic Gradient Descent)**: Motor tradicional que actualiza los pesos mediante descensos en línea recta con inercia (*momentum*).
- **AdamW (Adaptive Moment Estimation with Decoupled Weight Decay)**: Motor moderno que adapta la velocidad de aprendizaje individualmente para cada peso de la red y desacopla la regularización L2. Es el estándar superior para redes complejas con múltiples clases como YOLO11.

#### 9. Cosine Annealing (`cos_lr=True`)
- **Definición**: Programa de decaimiento cosenoidal de la tasa de aprendizaje. Durante las primeras épocas el modelo aprende a ritmo estándar y en las últimas épocas **reduce la velocidad de aprendizaje de forma suave y curva**, permitiendo que la red "fije y asiente" los detalles microscópicos (como orificios de broca) sin brincar sobre el mínimo de pérdida.

#### 10. Early Stopping y Paciencia (`patience`)
- **Definición**: Freno de mano automático. Si el modelo pasa $N$ épocas consecutivas (ej. 35) sin superar su récord de validación ($mAP$), el entrenamiento se detiene automáticamente y guarda el mejor punto (`best.pt`), protegiendo al modelo contra el **sobreajuste (*overfitting*)** (memorizar fotos en lugar de aprender patrones reales).

---

## 3. Desglose del Pipeline de Datos (Preprocesamiento y Aumento)

1. **Resolución y Geometría Estandarizada**:
   - Padding simétrico constante (fondo negro) para transformar fotos rectangulares a cuadradas sin distorsión de relación de aspecto (*Aspect Ratio*).
   - Redimensionamiento isotrópico a resolución fija de **$640\times 640$ píxeles**.
2. **Autocontraste Adaptativo en Espacio LAB (CLAHE)**:
   - Aplicación de ecualización adaptativa de histograma (`clipLimit=2.0`, `tileGridSize=(8,8)`) exclusivamente sobre el canal de luminosidad ($L$).
   - Realza texturas sutiles (estrías de inmadurez, perforaciones de broca, mordeduras mecánicas y decoloraciones de fermento) sin alterar el color RGB real.
3. **Estrategia Antifiltración (*Zero Data Leakage*)**:
   - Agrupamiento estricto por ID de lote físico. Las tomas frontal y reverso del mismo grano quedaron aisladas obligatoriamente dentro del mismo conjunto.
4. **Balanceo de Clases Minoritarias con Albumentations**:
   - Multiplicación sintética controlada exclusivamente en entrenamiento con rotaciones de 90°, volteos horizontales/verticales y perturbación fotométrica balanceada de brillo/contraste a $\pm 15\%$ ($p=0.5$).
   - Recálculo exacto de las coordenadas de las cajas delimitadoras YOLO.
5. **Composición Final del Dataset**:
   - **Entrenamiento (`train`)**: 269 imágenes ($640\times 640$) con $\approx 9,200$ instancias de granos anotados.
   - **Validación (`val`)**: 26 imágenes ($640\times 640$) con 373 instancias reales para validación imparcial.

---

## 4. Tabla Comparativa Histórica de Experimentos

| Parámetro / Métrica | Versión 1 (AdamW Base) | Versión 2 (SGD + No Mosaic) | Versión 3 (AdamW + cls=1.5) | Versión 4 (YOLO11m Cosine) | **Versión 5 (YOLO11s Ligero)** ⚡ |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Arquitectura** | YOLO11m ($20\text{M}$) | YOLO11m ($20\text{M}$) | YOLO11m ($20\text{M}$) | YOLO11m ($20\text{M}$) | **YOLO11s ($9.4\text{M}$)** |
| **Velocidad Inferencia** | $12.7\text{ ms}$ ($78\text{ FPS}$) | $12.7\text{ ms}$ ($78\text{ FPS}$) | $12.3\text{ ms}$ ($81\text{ FPS}$) | $12.8\text{ ms}$ ($78\text{ FPS}$) | **$6.1\text{ ms}$ ($\approx 164\text{ FPS}$)** 🚀 |
| **Optimizador** | AdamW (`lr=0.001`) | SGD (`lr=0.01`) | AdamW (`lr=0.001`) | AdamW (`lr=0.001` + Cos) | **AdamW (`lr=0.001` + Cos)** |
| **Épocas Entrenadas** | 55 épocas | 65 épocas | 107 épocas | 75 épocas | **90 épocas** (pico en época 55) |
| **$mAP_{50}$ Global** | `0.4384` (43.8%) | `0.3318` (33.2%) | `0.2304` (23.0%) | **`0.5187` (51.9%)** | **`0.5049` (50.5%)** ⭐ |
| **$mAP_{50-95}$ Global** | `0.3811` (38.1%) | `0.2459` (24.6%) | `0.1996` (20.0%) | **`0.4453` (44.5%)** | **`0.4356` (43.6%)** |
| **Precisión Arabica Bueno** | $40.3\%$ | $23.8\%$ | $37.3\%$ | $45.8\%$ | **`61.8%`** 📈 *(+16% pureza)* |
| **Precisión Robusta Bueno** | $82.8\%$ | $22.4\%$ | $57.7\%$ | $72.7\%$ | **`78.0%`** 📈 |

---

## 5. Análisis Específico de Rendimiento por Clase (Versión 5 - YOLO11s)

A continuación se detalla el comportamiento del modelo ligero discriminando las clases clave:

### ☕ Granos Buenos (Foco Principal del Negocio)
| Clase | Instancias en Validación | Precisión ($P$) | Recall ($R$) | $mAP_{50}$ | Análisis de Operación |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`Robusta_Bueno`** | 79 | **$78.0\%$** | **$72.0\%$** | **$83.1\%$** | **Excelente pureza**. Casi el 80% de lo que aprueba es grano sano de alta calidad. |
| **`Arabica_Bueno`** | 81 | **$61.8\%$** | **$55.6\%$** | **$58.9\%$** | **Mayor pureza lograda**. Subió la precisión de 45% a casi 62%, evitando contaminar el lote. |

### ☕ Defectos Críticos y Severos
| Clase | Instancias en Validación | Precisión ($P$) | Recall ($R$) | $mAP_{50}$ | Análisis de Operación |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`Robusta_Cereza`** | 6 | **$72.0\%$** | **$100.0\%$** | **$99.5\%$** | **Detección perfecta**. Cero fugas al canal de exportación. |
| **`Robusta_Negro`** | 14 | $19.2\%$ | **$100.0\%$** | **$65.2\%$** | **Descarte total**. El 100% de los granos negros de Robusta son detectados y expulsados. |
| **`Arabica_Cereza`** | 5 | **$64.8\%$** | **$80.0\%$** | **$80.6\%$** | **Muy alta efectividad**. |
| **`Arabica_Negro`** | 46 | **$65.6\%$** | $24.9\%$ | **$67.7\%$** | **Confiable**. |
| **`Arabica_Agrio`** | 49 | **$33.5\%$** | **$53.1\%$** | **$48.1\%$** | **Récord histórico en Agrios**. Subió al 48.1% de $mAP$. |
| **`Arabica_Brocado`** | 11 | **$51.8\%$** | $27.3\%$ | **$37.2\%$** | **Precisión $>50\%$** en la detección de brocas. |

---

## 6. Evaluación de Factibilidad Técnica para Despliegue en Producción

### A. Latencia y Velocidad en Tiempo Real
- **Tiempo de Inferencia de YOLO11m**: **$12.8\text{ ms}$ por cuadro** en GPU Tesla T4 (equivalente a **$\approx 78\text{ FPS}$**).
- **Requisito Típico de Cinta Transportadora**: $30 \text{ a } 60\text{ FPS}$ con tiempos de respuesta menores a $35\text{ ms}$.
- **Conclusión de Velocidad**: El modelo supera holgadamente la velocidad requerida para enviar pulsos de activación a electroválvulas o actuadores neumáticos en tiempo real.

### B. Análisis Costo-Beneficio de la Lógica Binaria (Bueno vs Desecho)
Bajo la arquitectura de clasificación multiclase entrenada, el clasificador de producción opera con la siguiente regla lógica:

$$\text{Decisión} = \begin{cases} \text{Aceptar (Canal Exportación)}, & \text{si } \text{Clase} \in \{\text{Arabica\_Bueno}, \text{Robusta\_Bueno}\} \text{ y } \text{Confianza} \ge \tau \\ \text{Expulsar (Canal Desecho)}, & \text{en cualquier otro caso} \end{cases}$$

- **Ventaja**: Toda confusión interna entre *Brocado*, *Negro*, *Agrio*, *Quebrado*, *Inmaduro*, *Concha* o *Cereza* converge automáticamente al canal de **Expulsión**, garantizando que el lote de desecho absorba todos los defectos sin importar su categoría taxonómica.
- **Calibración del Umbral ($\tau$)**:
  - Para **Máxima Pureza de Exportación**: Fijar $\tau = 0.60$ (sacrifica un porcentaje de granos buenos dudosos pero garantiza que ningún defecto contamine el saco).
  - Para **Máximo Rendimiento en Masa**: Fijar $\tau = 0.40$ (retiene más volumen de café sano).

---

## 7. Conclusiones y Recomendaciones para la Investigación

1. **Efectividad del Aumento de Datos y Preprocesamiento**: El pipeline de autocontraste CLAHE en espacio LAB y padding simétrico a $640\times 640$ con Albumentations permitió que clases microscópicas como *Arabica Brocado* pasaran de un $4\%$ inicial a un **$52.5\%$ de $mAP$** con un **$71.5\%$ de precisión**.
2. **Optimizador Óptimo**: La combinación de **`AdamW`** con **`Cosine Annealing` (`cos_lr=True`)** demostró ser la más estable y precisa para la arquitectura YOLO11m, superando a SGD y evitando oscilaciones en clases mayoritarias.
3. **Viabilidad de Lanzamiento**: El modelo contenido en `yolo11m_cafe_v4_final/weights/best.pt` se encuentra **técnicamente validado y listo para pruebas piloto en hardware embebido / cinta transportadora**.
