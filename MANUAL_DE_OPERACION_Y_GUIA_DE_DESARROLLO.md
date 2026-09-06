# MANUAL DE OPERACIÓN, ARQUITECTURA Y GUÍA DE DESARROLLO
## Sistema de Visión Artificial y Clasificación Óptica de Café Oro (Finca Alvizua)
**Institución**: Universidad Tecnológica La Salle (ULSA León, Nicaragua)  
**Proyecto**: Automatización Agroindustrial - Clasificador Basado en YOLO11s y Controlador Neumático  
**Fecha de Publicación**: Septiembre 2026  

---

## 1. INTRODUCCIÓN Y PROPÓSITO DEL DOCUMENTO

Este documento constituye la guía canónica de referencia técnica, arquitectura de software, patrones de diseño, estándares de codificación y flujo de trabajo para el desarrollo del clasificador inteligente de café oro de la Finca Alvizua.

Todos los desarrolladores, investigadores y agentes de IA que colaboren en este repositorio deben acatar estas directrices para asegurar la modularidad, estabilidad en tiempo real, mantenibilidad del código y reproducibilidad científica de los modelos de inteligencia artificial.

---

## 2. ESTÁNDARES DE CODIFICACIÓN Y NOMENCLATURA DE VARIABLES

El proyecto combina precisión matemática y agronómica con estándares de ingeniería de software para sistemas de visión por computadora embebidos e industriales.

### 2.1. Reglas de Nomenclatura

| Elemento | Convención | Idioma | Ejemplo en el Código | Justificación |
| :--- | :--- | :--- | :--- | :--- |
| **Lógica de Dominio y Datos** | `snake_case` | Español | `directorio_imagenes_entrada`, `cajas_delimitadoras`, `extraer_id_grano` | Claridad con la terminología agroindustrial de Finca Alvizua. |
| **Clases y Tipos** | `PascalCase` | Español / Bilingüe | `GestorDataset`, `ProcesadorImagen`, `AumentadorDatos`, `YOLODetector`, `GestorMetricas`, `MongoManager` | Estándar PEP 8 y distinción inequívoca de entidades. |
| **Funciones y Métodos** | `snake_case` (verbos) | Español | `aplicar_autocontraste()`, `guardar_resumen_lote()`, `iniciar_sesion()` | Denotan acciones concretas y directas sobre el estado. |
| **Constantes Globales** | `UPPER_SNAKE_CASE` | Español / Técnico | `COLOR_VERDE_ULSA`, `MAPEO_TRICLASE`, `NOMBRES_CLASES_DEFECTO`, `DIRECTORIO_SALIDA` | Inmutables y fácilmente identificables a nivel de módulo. |
| **Atributos Privados / Hilos** | `_snake_case` (prefijo `_`) | Español / Técnico | `self._lock`, `self._ejecutando`, `self._frame_reciente`, `self._conectado` | Encapsulamiento y protección de estados compartidos concurrentes. |
| **Colas y Sincronización** | `snake_case` | Bilingüe | `cola_salida`, `cola_frames`, `_lock = threading.RLock()` | Facilidad de rastreo en flujos multihilo. |

### 2.2. Tipado Estático y Robustez (Type Hinting)
Todo módulo debe emplear anotaciones del módulo `typing` de Python para facilitar la introspección y validación estática:
```python
from typing import Dict, List, Tuple, Optional, Union, Any
import numpy as np

def aplicar_relleno_y_redimensionar(
    imagen: np.ndarray,
    cajas_delimitadoras: Optional[List[List[float]]] = None,
    tamano_objetivo: int = 640
) -> Tuple[np.ndarray, List[List[float]]]:
    ...
```

### 2.3. Estructura de Docstrings
Cada clase y método público debe incluir un docstring explicativo en español:
1. **Descripción concisa** del propósito y algoritmo utilizado.
2. **`:param nombre:`** Tipo y rol del parámetro.
3. **`:return:`** Estructura y significado del valor retornado.
4. **Excepciones** documentadas si aplica (`ValueError`, `FileNotFoundError`).

---

## 3. ARQUITECTURA DEL SISTEMA Y PATRONES DE DISEÑO

El software sigue una **Arquitectura en Capas Desacopladas (Layered Clean Architecture)** que aísla la adquisición de hardware, la inferencia de inteligencia artificial, la persistencia en base de datos y la interfaz de usuario.

```
┌────────────────────────────────────────────────────────────────────────┐
│                   CAPA DE PRESENTACIÓN (ui/)                           │
│     Dashboard Nativo CustomTkinter (30-60 FPS) / Alternativa Flet      │
│          Componentes: StatCards, Gráficos Reactivos, Temas             │
└───────────────────▲───────────────────────────────▲────────────────────┘
                    │ (Callbacks UI / Queues)       │ (Lectura de Telemetría)
┌───────────────────┴───────────────────────────────┴────────────────────┐
│                    CAPA DEL NÚCLEO (core/)                             │
│  • YOLODetector: Productor Asíncrono de Video (Doble Hilo Desacoplado) │
│  • GestorMetricas: Monitor de Sesión, Contadores y Consumo (kWh)       │
└───────────────────▲───────────────────────────────▲────────────────────┘
                    │                               │
┌───────────────────┴────────────────┐  ┌───────────┴────────────────────┐
│   CAPA DE PREPROCESAMIENTO (src/)  │  │   CAPA DE PERSISTENCIA         │
│  • Configuracion                   │  │   (storage/)                   │
│  • ProcesadorImagen (CLAHE + Pad)  │  │  • MongoManager: MongoDB Atlas │
│  • AumentadorDatos (Albumentations)│  │    + Búfer Offline JSON        │
│  • GestorDataset (Anti-Leakage)    │  │    Tolerancia a fallos de red  │
└────────────────────────────────────┘  └────────────────────────────────┘
```

### 3.1. Patrón Productor-Consumidor Desacoplado (Producer-Consumer)
- **Problema**: La captura continua de la cámara web (30 FPS) y la inferencia de YOLO (que toma entre 4.9 ms y 15 ms por frame) no deben compartir el ciclo de refresco de la interfaz gráfica para evitar caídas de cuadros o congelamientos (*GUI freezing*).
- **Solución implementada**:
  - `Hilo de Captura`: Lee fotogramas ininterrumpidamente desde OpenCV / DirectShow.
  - `Hilo de Inferencia`: Extrae el último fotograma disponible, corre el modelo YOLO11s y deposita el payload con detecciones en una cola `queue.Queue(maxsize=3)`.
  - `Consumidor (GUI CustomTkinter)`: Consume de la cola a intervalos fijos de 15 ms con `.after()`, logrando un streaming fluido a 30-60 FPS sin carga excesiva en el procesador.

### 3.2. Patrón Repository / DAO con Resiliencia Offline (Offline-First)
- Implementado en `storage/database.py` con la clase `MongoManager`.
- **Estrategia**:
  1. Conexión asíncrona a **MongoDB Atlas** en un hilo `daemon`.
  2. Si no hay conexión o no existe variable de entorno `MONGO_URI`, el sistema **no se bloquea ni arroja excepciones**: guarda automáticamente cada resumen de lote en `storage/offline_logs.json`.
  3. Al restablecer la conectividad, sincroniza y vacía los registros pendientes hacia la nube de manera transparente.

### 3.3. Patrón Data-Centric AI y Prevención de Fuga de Datos (Anti-Data Leakage)
- Implementado en `src/gestor_dataset.py` mediante el método `extraer_id_grano()`.
- **Problema de Visión en Granos**: Cada grano o bandeja física fue fotografiada en dos orientaciones: anverso (`_frontal_`) y reverso (`_reverso_`). Si una cara cae en entrenamiento y la otra en validación, se produce **Data Leakage** (la red memoriza el grano).
- **Solución**: Se normaliza el identificador del grano mediante expresiones regulares eliminando sufijos de cara (`_frontal_`, `_reverso_`, `_anverso_`). Toda división estratificada (`train`, `val`, `test`) se realiza agrupando por **ID físico**, garantizando que ambas caras permanezcan en la misma partición.

### 3.4. Patrón Fallback / Degradación Elegante (Graceful Degradation)
- Si los pesos `models/best.pt` no existen en disco, `YOLODetector` activa automáticamente el **Modo Demostrativo / Simulado** generando detecciones sintéticas con coordenadas dinámicas.
- Si no hay cámara física conectada, genera un fondo sintético con gradiente institucional ULSA para que los desarrolladores puedan probar la interfaz sin hardware adicional.

---

## 4. CATÁLOGO Y FUNCIÓN DE CADA MÓDULO DEL REPOSITORIO

### 4.1. Módulos Principales de la Aplicación

| Ruta del Módulo | Clase Principal | Rol y Funcionalidad Específica |
| :--- | :--- | :--- |
| `core/detector.py` | `YOLODetector` | Productor multihilo de visión por computadora. Administra la cámara (DirectShow en Windows), inferencia con Ultralytics YOLOv11s, filtrado por confianza mínima, renderizado de bounding boxes con colores institucionales y telemetría de latencia. |
| `core/metricas.py` | `GestorMetricas` | Gestor centralizado de telemetría y cálculos analíticos en tiempo real. Cronometraje activo (con pausas), conteo de granos sanos vs. defectuosos, cálculo del consumo eléctrico acumulado en kilovatios-hora ($kWh$), tasa de FPS y generación de resúmenes de lote estructurados. |
| `src/configuracion.py` | `Configuracion` | Centraliza constantes de ruta, resoluciones cuadradas (640x640, 800x800), división porcentual (`train`, `val`, `test`), multiplicadores de aumento por clase minoritaria y mapeos de nombres de clase a IDs YOLO. |
| `src/procesador_imagen.py` | `ProcesadorImagen` | Lógica de normalización fotométrica y espacial con OpenCV: aplicación de **CLAHE** (ecualización adaptativa de histograma) en el canal de luminosidad ($L$) del espacio de color $LAB$ para realzar broca y texturas, y padding simétrico con recalculo trigonométrico de coordenadas YOLO. |
| `src/aumentador_datos.py` | `AumentadorDatos` | Enriquecimiento de muestras minoritarias con **Albumentations**. Rotaciones aleatorias, volteos horizontales/verticales, ajustes de brillo y contraste preservando exactamente las cajas delimitadoras normalizadas. |
| `src/gestor_dataset.py` | `GestorDataset` | Orquestador integral de datos: lectura del directorio bruto, agrupación por grano físico anti-fuga, división estratificada, aplicación de procesamiento, aumento balanceado y generación automática del archivo `data.yaml`. |
| `storage/database.py` | `MongoManager` | Gestión de persistencia en MongoDB Atlas para almacenamiento de lotes analizados. Incluye búfer local JSON de contingencia (`offline_logs.json`) y sincronización automática. |
| `ui/dashboard_ctk.py` | `DashboardCustomTkinter` | Interfaz gráfica nativa de alto rendimiento construida con CustomTkinter. Visualizador de video en tiempo real, selector de fuentes de cámara, control de sesiones, métricas de calidad y gráficas integradas. |
| `ui/dashboard.py` | `InterfazClasificadora` | Interfaz alternativa construida sobre Flet (Flutter para Python). Se puede activar pasando el argumento `--flet`. |
| `ui/theme.py` | Constantes de Tema | Define las constantes de color corporativas de ULSA León para botones, tarjetas y estados. |
| `ui/components/stat_card.py`| `StatCard` | Componente reutilizable para tarjetas métricas (KPIs de granos sanos, defectuosos, energía, FPS). |
| `ui/components/charts.py` | Componentes Gráficos | Gráficas analíticas de distribución de defectos y evolución temporal. |
| `main_dashboard.py` | `main()` | Punto de entrada único del sistema. Carga variables de `.env`, instancia los módulos desacoplados y arranca el dashboard. |

### 4.2. Scripts de Generación de Datasets y Experimentación

| Script | Propósito y Salida Generada |
| :--- | :--- |
| `generar_dataset_triclase.py` | Genera el dataset del **Modelo Campeón (3 Clases)**: `0: Arabica_Bueno`, `1: Robusta_Bueno`, `2: Grano_Defecto`. Genera `dataset_yolo_triclase/` y empaqueta en `dataset_yolo_triclase.zip`. |
| `generar_dataset_binario.py` | Genera el dataset binario industrial: `0: Grano_Bueno`, `1: Grano_Defecto` en `dataset_yolo_binario/` y `.zip`. |
| `generar_dataset_800px.py` | Genera el dataset nativo en alta resolución a 800x800 píxeles para análisis comparativo de detalle fino. |
| `actualizar_etiqueta_y_reprocesar.py` | Script de sincronización con Label Studio para re-procesar y corregir etiquetas omitidas en imágenes de validación. |
| `entrenar_yolo11s.py` / `.ipynb` | Scripts de entrenamiento local o en Google Colab con YOLO11s (Ultralytics), hiperparámetros de convergencia y guardado en `models/best.pt`. |
| `generar_graficos_ulsa.py` | Generador de figuras vectoriales de 300 DPI con paleta institucional ULSA León para publicaciones e informes. |
| `reporte_tecnico_notebooklm.md` | Informe técnico-científico con la tabla maestra de experimentos, matrices de confusión y análisis operativo. |

### 4.3. Batería de Pruebas Unitarias (`tests/`)

- `tests/test_detector.py`: Valida el arranque del detector, la emisión de payloads válidos a la cola y el fallback a modo simulado.
- `tests/test_metricas.py`: Valida el cálculo de $kWh$, cronómetro de sesión con pausas, conteo de defectos y resúmenes de lote.
- `tests/test_database.py`: Valida el comportamiento offline y la lectura/escritura en el búfer JSON de respaldo.
- `tests/test_ui_build.py`: Valida la construcción correcta de los componentes visuales de la interfaz sin errores de sintaxis.
- `tests/run_all_tests.py`: Suite ejecutora general con verificación de 100% de éxito.

---

## 5. FLUJO DE TRABAJO (GIT WORKFLOW) Y CONVENCIONES DE EQUIPO

Para mantener el historial limpio y facilitar la integración continua, se sigue la siguiente metodología de ramificación y control de versiones:

```
[main / master]  ───────●────────────────────────────────────────● (Producción Estable)
                         ▲                                        ▲
                         │ (Merge Hito Aprobado)                 │ (Merge Hito Aprobado)
[dev]            ────────●────────────────────────────────────────● (Integración Continua)
                          \                                      /
                           \───●───────●────────●───────●───────/
                                (feat/modelo-triclase-...)
```

### 5.1. Jerarquía de Ramas
1. **`main` / `master`**: Rama de producción estable. Contiene únicamente código probado, con pruebas unitarias pasando al 100% y modelos campeones validados.
2. **`dev`**: Rama de integración y desarrollo activo. Aquí convergen las características terminadas antes de ser promovidas a `main`.
3. **`feat/<nombre-funcionalidad>`**: Ramas de trabajo para características individuales.
   - Nombres descriptivos en kebab-case: `feat/modelo-triclase-arabica-robusta-defecto`, `feat/desarrollo-interfaz`, `feat/inference-dashboard`.
   - Deben partir de `dev` (o `main`) y reintegrarse mediante merge limpio.

### 5.2. Convención de Mensajes de Commit
Los commits deben seguir el formato semántico convencional:
- `feat: <descripción>` para nuevas funcionalidades o scripts (ej. `feat: generador de dataset tri-clase`).
- `fix: <descripción>` para correcciones de bugs (ej. `fix(video): desacoplar hilos para fluidez a 30 FPS`).
- `docs: <descripción>` para documentación, informes o gráficos científicos (ej. `docs: informe técnico para NotebookLM`).
- `perf: <descripción>` para optimizaciones de rendimiento y latencia.
- `test: <descripción>` para incorporación o ajuste de pruebas unitarias.

### 5.3. Gestión de Datos Grandes y Modelos
- Los archivos `.pt` (pesos de YOLO) se colocan en `models/best.pt`.
- Las carpetas con miles de imágenes descomprimidas (`dataset_yolo/`, `dataset_yolo_triclase/`) están registradas en `.gitignore` para no saturar Git.
- Los datasets preparados se empaquetan en archivos `.zip` (`dataset_yolo_triclase.zip`) para su fácil transferencia a plataformas de GPU en la nube.

---

## 6. PAUTAS INSTITUCIONALES DE DISEÑO VISUAL (ULSA LEÓN)

En toda interfaz gráfica (`ui/`), presentación o gráfica científica (`generar_graficos_ulsa.py`), es obligatorio respetar la identidad de marca de la Universidad Tecnológica La Salle:

### 6.1. Paleta de Colores Corporativa

```
┌──────────────────────────────┬─────────────┬────────────────────────────────────┐
│ Color Institucional          │ Código HEX  │ Aplicación Primaria                │
├──────────────────────────────┼─────────────┼────────────────────────────────────┤
│ Verde La Salle Principal     │ #006837     │ Botones primarios, barras de éxito │
│ Verde ULSA Dashboard         │ #197B30     │ Grano sano, estados activos        │
│ Verde Acento                 │ #2BB673     │ Líneas de tendencia, bordes activos│
│ Verde Fondo Suave            │ #E8F5E9     │ Fondos de tarjetas y contenedores  │
│ Gris Pizarra Corporativo     │ #2D3748     │ Textos principales y encabezados   │
│ Gris Rejilla / Bordes        │ #E2E8F0     │ Separadores y líneas de gráficos   │
│ Rojo Alerta / Defecto        │ #C62828     │ Detección de grano defectuoso      │
│ Dorado de Distinción         │ #D4AF37     │ Resaltado de Modelo Campeón        │
└──────────────────────────────┴─────────────┴────────────────────────────────────┘
```

### 6.2. Gráficos Científicos de Alto Impacto
- Resolución mínima: **300 DPI** para impresión y publicación académica.
- Estilo: Rejilla suave discontinua (`--`, alfa 0.7), tipografía limpia sin serifa (`DejaVu Sans`), etiquetas con porcentajes explícitos y recuadros explicativos en puntos clave (ej. Frontera de Pareto y Matriz de Producción).

---

## 7. MATRIZ DE PARADIGMAS EXPERIMENTALES Y MODELO CAMPEÓN

El sistema ha sido probado a través de tres grandes enfoques:

1. **Paradigma 13 Clases (Multiclase Exhaustivo)**:
   - Diagnostica cada tipo de defecto individualmente (Broca, Concha, Quebrado, Agrio, etc.).
   - *Resultado*: Adecuado para auditoría de laboratorio, pero sufre de confusión morfológica inter-clase en bandas rápidas ($mAP@50 \approx 50.5\%$).
2. **Paradigma Binario (2 Clases)**:
   - Separa en `Grano_Bueno` vs. `Grano_Defecto`.
   - *Resultado*: Eleva el $mAP@50$ a $81.8\%$, pero descarta granos sanos por sombras leves.
3. **Paradigma Tri-Clase Comercial (CAMPEÓN 👑)**:
   - Separa en:
     - `0: Arabica_Bueno` (Pureza 100.0% para exportación)
     - `1: Robusta_Bueno` (Recuperación 88.6% para consumo local)
     - `2: Grano_Defecto` (Descarte automático con actuador neumático)
   - *Resultado*: **$mAP@0.50$ histórico del $87.41\%$**, latencia de **$4.9\text{ ms}$ ($204\text{ FPS}$)**, cero fuga de defectos a exportación y rescate de 127 granos sanos.

---

## 8. HOJA DE RUTA Y CONTINUACIÓN DEL DESARROLLO (RAMA DE INTERFAZ)

Para la siguiente etapa en la nueva rama `feat/desarrollo-interfaz`:
1. **Control de Actuación Neumática**:
   - Integración del controlador de electroválvulas / actuadores neumáticos para expulsión sincronizada de granos con base en la coordenada $Y$ del grano detectado.
2. **Panel de Ajuste Dinámico de Umbrales**:
   - Sliders en tiempo real para calibrar la confianza de detección sin reiniciar el clasificador.
3. **Estadísticas Avanzadas de Producción**:
   - Desglose instantáneo en pantalla del porcentaje de pureza para exportación vs. lote comercial.
