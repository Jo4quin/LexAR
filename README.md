# LexAR — Asistente Jurídico para Abogados

LexAR es un proyecto académico para la materia **Procesamiento de Lenguaje Natural** (Universidad de
San Andrés). Construye una base de conocimiento sobre normativa nacional argentina —embeddings
semánticos, grafo de vínculos entre normas y clasificación de relaciones— más jurisprudencia de la
Corte Suprema (CSJN), y la pone al servicio de un **asistente jurídico orientado a la investigación**:
un explorador de leyes con normas vinculadas y resúmenes generados por IA, y un chatbot que responde
casos planteados en lenguaje natural con citas normativas verificadas contra la fuente.

> **Historia del proyecto (pivot, 2026-07-08).** LexAR arrancó como un detector de **redundancias y
> contradicciones** entre leyes (Fases 1-3) y luego viró hacia un producto de asistencia jurídica
> (Fases 4-8). Las Fases 1-3 no se descartaron: son el motor de retrieval del producto (embeddings +
> grafo de vínculos) y una de sus señales de análisis. El detalle de implementación del pivot está en
> [`PLAN.md`](PLAN.md).

## Qué hace

El producto tiene tres piezas, todas navegables desde la app web:

- **Explorador de leyes.** Búsqueda por título/número o **por tema** (semántica, sobre el índice de
  embeddings). Cada norma tiene su ficha con: texto completo (cuando el corpus lo tiene),
  **advertencia de vigencia** (cuántas modificaciones posteriores registra Infoleg), **normas
  vinculadas** (oficiales y semánticas) con un resumen IA on-demand de cada relación, un **mapa de
  vínculos** interactivo, y los **fallos de la CSJN** relacionados.
- **Hallazgos.** Los pares de fragmentos que el análisis de las Fases 1-3 marcó como **posible
  conflicto normativo** (4 confirmados tras la re-verificación de la Fase 3.5), con el escenario
  concreto de colisión — la conexión visible del producto con la misión original del proyecto.
- **Chatbot RAG.** Se le plantea un caso en lenguaje coloquial y devuelve el marco legal aplicable
  —leyes, normativa relacionada y fallos— con **citas textuales verificadas** automáticamente contra
  la fuente. Multi-turno, con progreso en vivo y feedback 👍/👎.

Para el uso detallado de la app, ver [`TUTORIAL.md`](TUTORIAL.md).

## Cómo correr

### Requisitos

- **Python 3.11+**.
- **Credenciales de Google Cloud** con Vertex AI habilitado (la app genera resúmenes y respuestas del
  chatbot con modelos `gemini-*`):
  ```bash
  gcloud auth application-default login
  ```
- **Datos y artefactos** descargados del Drive (ver [Datos y artefactos](#datos-y-artefactos)) — no se
  versionan en git.

### Pasos

```bash
# 1. Descargar del Drive el paquete de datos y los artefactos generados y descomprimirlos
#    en la raíz del repo, de modo de tener  ./data/  y  ./outputs/
#    (link en la sección "Datos y artefactos").

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Levantar la app
python -m uvicorn app.main:app
```

Abrir `http://127.0.0.1:8000`. Si el puerto 8000 está ocupado, agregar `--port 8080` (o el que se
prefiera) y ajustar la URL.

> **Primer uso.** La primera vez que se entra a cada sección, el servidor carga los parquet grandes y
> el índice FAISS (varios segundos). La consulta más lenta es la **primera al chatbot** (~40-60 s:
> construye el índice de 112k fragmentos y recién después llama al modelo); las siguientes tardan solo
> lo que tardan las llamadas al LLM. Detalle en [`TUTORIAL.md`](TUTORIAL.md).

Los notebooks de `notebooks/` regeneran los artefactos desde cero si hiciera falta; requieren las
mismas credenciales de GCP. No es necesario correrlos para usar la app si se descargan los `outputs/`
del Drive.

## Datos y artefactos

Los datos de entrada y los artefactos generados **no se versionan en git** (cientos de MB, con archivos
que superan el límite de GitHub). Se comparten por Drive:

**📁 Drive del proyecto:**
**https://drive.google.com/drive/folders/1mougJFdcUnriCWW6elfy3vNtzl68iXW7?usp=sharing**

Contiene:

- **`data/`** — el paquete de datos de entrada:
  - `lexar_datos_infoleg_saij/` — Infoleg + SAIJ combinados y deduplicados (fuente de las Fases 1-3).
    Su `LEEME.md` documenta 30.061 documentos, de los cuales 8.887 (29,6 %) tienen texto completo
    (8.684 de Infoleg, 203 de SAIJ). Punto de partida:
    `corpus_unificado/text_versions.parquet` (9.518 textos limpios y unificados, listos para
    segmentar).
  - `jurisprudencia_csjn/` — fallos de la CSJN scrapeados de SAIJ (Fase 4).
- **`outputs/`** — los artefactos generados por los notebooks (fragmentos segmentados, embeddings,
  clasificaciones, grafo de vínculos, evaluación). Descargarlos evita tener que regenerarlos, que
  implica varias horas de cómputo y costo de Vertex AI.

Colocar ambas carpetas en la raíz del repo (`./data/` y `./outputs/`). La configuración resuelve la
raíz a la carpeta que contenga `data/`, así que la app y los notebooks funcionan tanto desde la raíz
del repo como desde `notebooks/`.

### Fuentes

- **Infoleg** — metadatos de normativa nacional, grafo de relaciones modificatorias, y textos completos
  cuando la fuente los provee.
- **SAIJ** — textos normativos que complementan a Infoleg, y **fallos de la Corte Suprema (2020 en
  adelante)**, vía su API JSON (el texto completo de los fallos viene como PDF, extraído con `pypdf`).

### Alcance jurídico

El corpus apunta a **leyes y decreto-leyes nacionales argentinos**, más jurisprudencia de la CSJN
desde 2020. No incluye normativa provincial, resoluciones administrativas, doctrina ni decretos comunes
fuera del recorte disponible.

## Estructura del repo

```
README.md            # este archivo
TUTORIAL.md          # cómo usar la app (Explorador + Chatbot), paso a paso
PLAN.md              # plan de implementación del pivot (Fases 4-8)
CLAUDE.md            # documentación técnica interna detallada (arquitectura, gotchas, decisiones)
requirements.txt
notebooks/           # el pipeline, un notebook por fase
  Redundancias&Contradicciones.ipynb   # Fases 1-2: corpus, segmentación, embeddings, retrieval
  Clasificacion_Candidatos.ipynb        # Fase 3: reglas + LLM de dos niveles
  Reverificacion_Conflictos.ipynb       # Fase 3.5: re-criterio "instrumentos paralelos"
  Jurisprudencia_CSJN.ipynb             # Fase 4: scraping + embeddings de fallos CSJN
  Vinculos_Normas.ipynb                 # Fase 5: grafo de vínculos + resúmenes IA
  Evaluacion_Producto.ipynb             # Fase 8: métricas de retrieval y trazabilidad
src/lexar/           # core compartido (importado por los notebooks nuevos y la app)
app/                 # app web: FastAPI + Jinja2 + HTMX + Tailwind
eval/                # casos_prueba.csv: ground truth anotado a mano (Fase 8)
data/ , outputs/     # gitignored — se descargan del Drive (ver arriba)
```

El detalle técnico de cada módulo, los gotchas y las decisiones de diseño están en [`CLAUDE.md`](CLAUDE.md).

## Fases y resultados

### Fase 1 — Consolidación del corpus ✓
Carga de `text_versions.parquet`, join con metadatos, una versión de texto por documento, y
segmentación por **artículo** (con fallback a chunks solapados para textos sin estructura de
artículos). Resultado: **113.895 fragmentos** legales.

### Fase 2 — Embeddings y búsqueda ✓
Embeddings semánticos con Vertex AI (`gemini-embedding-001`, 768d) sobre el corpus completo, con
checkpointing reanudable y un rate limiter adaptativo (AIMD, converge al cupo real sin conocerlo de
antemano). Índice FAISS (similitud coseno exacta) y recuperación de vecinos cercanos. Resultado:
**112.582 embeddings únicos**, **679.720 pares candidatos**, 8.942 clusters exploratorios.

### Fase 3 — Clasificación de relaciones ✓
Reglas deterministas (near-identical, boilerplate) resolvieron el 35 % de los pares sin costo de LLM;
el resto pasó por triage (`gemini-2.5-flash-lite`) + verificación de los conflictos
(`gemini-2.5-flash`). Cada par queda con etiqueta, confianza, explicación y evidencia citada.
Distribución final: 25.017 `possible_overlap`, 24.868 `neutral`, 14.077 `possible_modification`,
3.607 `different_scope`, 397 `needs_review`, 84 `possible_conflict`.

### Fase 3.5 — Re-verificación de conflictos ✓
Al usar la app se detectó que la mayoría de los 84 `possible_conflict` no eran contradicciones sino
**instrumentos paralelos** (tratados bilaterales con contrapartes distintas, regímenes para
beneficiarios distintos, etc.). Un prompt v2 que agrega el resumen oficial de cada norma y exige
describir el escenario concreto de colisión, confirmado con `gemini-2.5-pro`, bajó el resultado a
**4 conflictos confirmados** (84 → 4), todos con una tensión legal concreta y bien formada. El
criterio se cambia con una sola constante (`config.CLASSIFICATIONS_VERSION`), sin recomputar.

### Fase 4 — Jurisprudencia CSJN ✓
Scraping de fallos de la Corte Suprema en SAIJ (2020 en adelante), segmentación y embeddings con el
mismo pipeline de la Fase 2, y vínculo ley↔fallo por similitud. Resultado: **1.234 fallos**,
**8.702 fragmentos**, **28.930 vínculos** ley↔fallo entre 1.225 fallos y 2.743 normas.

### Fase 5 — Grafo de vínculos + resúmenes IA ✓
Consolidación de los candidatos (Fase 2) y las clasificaciones (Fase 3) a nivel documento, unida con
el grafo oficial de modificaciones de Infoleg. Resúmenes de cada vínculo generados por IA **on-demand
con caché**. Resultado: **48.276 vínculos** (38.552 semánticos, 8.297 oficiales, 1.427 ambos).

### Fase 6 — Chatbot RAG ✓
Pipeline: *query rewriting* (caso coloquial → consultas en lenguaje jurídico) → retrieval sobre leyes
y fallos → respuesta con citas obligatorias → validación automática de que cada cita es texto literal
de la fuente citada.

### Fase 7 — App web ✓
FastAPI + Jinja2 + HTMX + Tailwind, con identidad visual propia. Explorador, Hallazgos y Chatbot
(ver [Qué hace](#qué-hace)). Se corre con `python -m uvicorn app.main:app`.

### Fase 8 — Evaluación ✓
Sobre los 17 casos anotados a mano de `eval/casos_prueba.csv`:
- **Recall@10: 73,5 %** con query rewriting vs. **70,6 %** sin — la mejora que justifica esa decisión
  de diseño (para un asistente de investigación, que la ley correcta aparezca en la lista importa más
  que la precisión).
- Precision@10 prácticamente plana (10,0 % vs. 9,4 %), esperable dado que cada caso tiene solo 1-2
  leyes esperadas frente a 10 posiciones evaluadas.
- **Trazabilidad de citas: 96,3 %** (157/163) verificadas textualmente contra la fuente.

## Limitaciones

- **Cobertura de texto**: solo 8.887 de 30.061 leyes (29,6 %) tienen texto completo; el resto son
  metadatos y no aparecen citadas por el chatbot ni con texto en el Explorador.
- **Alcance del corpus**: Leyes y Decreto-Leyes nacionales. No incluye decretos comunes, resoluciones
  ni normativa provincial.
- **Jurisprudencia**: solo fallos de la CSJN publicados en SAIJ desde 2020 — una selección, no el
  universo completo.
- **Similitud ≠ contradicción**: la cercanía semántica no implica conflicto jurídico; los
  `possible_conflict` son hipótesis priorizadas para **revisión profesional**, no dictámenes.
- **Vigencia**: la advertencia de modificaciones posteriores señala que puede haber cambios, pero no
  reemplaza la verificación de la versión vigente en una fuente oficial.

## Entregables

- Base de fragmentos legales segmentados (leyes y fallos CSJN).
- Índices de embeddings (leyes y jurisprudencia).
- Grafo de vínculos entre normas, con resúmenes generados por IA.
- Chatbot jurídico con citas verificadas.
- App web (FastAPI + HTMX): explorador + hallazgos + chatbot.
- Métricas de evaluación (precision/recall de retrieval, trazabilidad de citas).
- Informe académico-técnico.
