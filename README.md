# LexAR

LexAR es un proyecto academico para la materia **Procesamiento de Lenguaje Natural**. Construye una
base de conocimiento sobre normativa nacional argentina (embeddings semanticos, grafo de vinculos,
clasificacion de relaciones entre normas) y la usa como motor de un **Asistente Juridico para
Abogados**: explorador de leyes con normas vinculadas y resumenes generados por IA, jurisprudencia de
la Corte Suprema (SAIJ, desde 2020), y un chatbot que responde casos en lenguaje natural con citas
normativas verificadas.

> **Pivot (2026-07-08):** el proyecto arranco con un enfoque de deteccion de redundancias y
> contradicciones (Fases 1-3, completas, descriptas mas abajo) y a partir de ahi se redirecciono hacia
> el producto para abogados. Las Fases 1-3 **no se descartan** — son la base del producto: los
> embeddings y el grafo de vinculos son el motor de retrieval, y el motor LLM de clasificacion se
> reusa para generar los resumenes de vinculos. El plan de implementacion completo del pivot
> (Fases 4-8) esta en `PLAN.md`.

## Objetivo general

Construir un pipeline de PLN que transforme textos legales argentinos y fallos de la Corte Suprema en
una base consultable por fragmentos, detecte normas semanticamente cercanas y vinculadas oficialmente,
y ponga ese conocimiento al servicio de un asistente juridico para abogados.

El producto (demo) debe mostrar:

- un explorador de leyes con sus normas vinculadas (oficiales y semanticas) y jurisprudencia relevante
  de la CSJN desde 2020;
- un resumen generado por IA que explica por que dos normas estan relacionadas y su relevancia
  juridica;
- un chatbot que, dado un caso en lenguaje natural, devuelve las leyes aplicables, la normativa
  relacionada y los fallos relevantes, con citas textuales verificadas contra la fuente.

## Ideas principales

### 1. Deteccion de redundancias y contradicciones normativas (Fases 1-3, completas)

La primera linea del proyecto analizo leyes nacionales argentinas para encontrar relaciones
problematicas entre fragmentos normativos.

Se consideraron relevantes, entre otros, estos casos:

- contradicciones directas entre obligaciones, prohibiciones, permisos o procedimientos;
- normas viejas no derogadas que entren en tension con normas posteriores;
- definiciones legales incompatibles o parcialmente divergentes;
- plazos o requisitos procedimentales distintos para situaciones similares;
- excepciones que vuelven ambigua una regla general;
- normas que regulan lo mismo o son funcionalmente equivalentes aunque esten redactadas de manera distinta.

El sistema no parte de la idea de afirmar automaticamente que existe una contradiccion juridica
definitiva — el resultado se entiende como una **hipotesis priorizada para revision humana**. Esta
clasificacion (`possible_conflict`, `possible_overlap`, etc.) sigue viva como una de las senales que
alimentan los vinculos entre normas del producto (Fase 5), ya no como el objetivo final del proyecto.

### 2. Asistente juridico para abogados (Fases 4-8, el pivot actual)

La segunda linea reutiliza el corpus, los embeddings y la clasificacion de la primera para construir
un asistente juridico orientado a la investigacion, no a la redaccion. El asistente permite:

- explorar una ley y ver sus normas vinculadas, con un resumen IA de cada relacion;
- consultar la jurisprudencia de la Corte Suprema (SAIJ, desde 2020) asociada a una norma;
- plantear un caso en lenguaje natural y recibir el marco legal aplicable, con fuentes citadas.

Ver `PLAN.md` para el detalle de implementacion de cada fase.

Para el alcance inicial, esta idea queda como extension natural del trabajo principal. El foco inmediato es construir una buena base de conocimiento y una demo de deteccion + propuesta de redaccion alternativa.

## Datos disponibles

El proyecto ya incluye datasets recolectados desde fuentes oficiales y documentacion asociada.

### Fuentes

- **Infoleg**: metadatos de normativa nacional, relaciones entre normas modificatorias y modificadas, y textos completos cuando la fuente los provee.
- **SAIJ**: textos normativos obtenidos mediante API, usados para complementar normas sin texto en Infoleg.

### Alcance juridico actual

El corpus apunta a **leyes y decreto-leyes nacionales argentinas**. No incluye, como objetivo inicial:

- jurisprudencia;
- doctrina;
- normativa provincial;
- resoluciones administrativas;
- decretos comunes fuera del recorte disponible.

El alcance real depende de la cobertura efectiva de los datos ya recolectados.

### Paquete presente en el repositorio

Los datos **no se versionan en git** (son cientos de MB y superan el limite de GitHub); se comparten por
fuera del repo y viven localmente en `data/`, que esta en `.gitignore`. Ver `CLAUDE.md` para instrucciones
de donde colocarlos.

- `data/lexar_datos_infoleg_saij/`: paquete con datos Infoleg + SAIJ combinados. Su `LEEME.md` describe
  30.061 documentos totales, de los cuales 8.887 (29,6 %) tienen texto completo (8.684 de Infoleg, 203 de
  SAIJ) tras deduplicar y descartar registros sin texto util.

Para el desarrollo inicial conviene tomar como punto de partida el archivo:

```text
data/lexar_datos_infoleg_saij/corpus_unificado/text_versions.parquet
```

Este archivo contiene los 9.518 textos limpios y unificados (Infoleg + SAIJ, con `quality_flag`), listos
para segmentacion. Un paquete anterior mas amplio (`lexar_dataset_2026-06-25/`) fue mencionado en una
version previa de este documento pero nunca llego a incorporarse al proyecto; si aparece en el futuro,
documentar la diferencia de cobertura contra este paquete antes de fijar resultados experimentales.

## Unidad de analisis

La unidad ideal de comparacion es el **articulo legal**.

Propuesta de jerarquia:

1. Articulo, cuando el texto tenga marcadores confiables.
2. Inciso o parrafo, si la segmentacion puede extraerlos con precision.
3. Chunk textual con solapamiento, como fallback para textos largos o codigos extensos.
4. Documento completo o resumen, solo para exploracion temprana.

El MVP deberia implementar primero segmentacion por articulo y usar chunking especial para codigos o compilaciones muy extensas.

## Pipeline propuesto

### 1. Preparacion del corpus

- Cargar `text_versions.parquet`.
- Unir cada texto con metadatos desde `documents.csv`.
- Conservar trazabilidad: `document_id`, fuente, version, URL o referencia original.
- Normalizar texto para procesamiento: espacios, encabezados, marcas de articulo y caracteres residuales.
- Segmentar cada texto en articulos o fragmentos.

Salida esperada:

```text
legal_fragments
```

con campos como `fragment_id`, `document_id`, `text_version_id`, `fragment_type`, `label`, `text`, `char_start`, `char_end` y `content_hash`.

### 2. Representacion semantica

- Generar embeddings para cada fragmento.
- Evaluar modelos de embeddings en espanol o multilingues.
- Guardar vectores en un indice consultable.
- Explorar reduccion de dimensionalidad para visualizacion y clustering.

Opciones posibles:

- API comercial de embeddings, aprovechando los creditos disponibles;
- modelo open source multilingue como alternativa reproducible;
- combinacion de ambas para comparar calidad/costo.

### 3. Recuperacion de candidatos

La busqueda de contradicciones no debe hacerse contra todos los pares posibles, porque el numero de combinaciones seria demasiado grande.

Primero se generan candidatos mediante:

- similitud coseno entre embeddings;
- busqueda por vecinos cercanos;
- clustering por subespacios semanticos;
- filtros por metadatos: tema, fecha, tipo de norma, fuente, vigencia si estuviera disponible;
- grafo de modificaciones Infoleg, para priorizar normas que ya tienen relacion historica.

Salida esperada:

```text
analysis_candidates
```

con pares de fragmentos semanticamente cercanos y evidencia de recuperacion.

### 4. Clasificacion de relacion normativa

Cada par candidato se clasifica con un modelo de lenguaje o con una combinacion de reglas + LLM.

Etiquetas iniciales:

- `possible_conflict`: posible contradiccion o incompatibilidad.
- `possible_overlap`: posible redundancia o regulacion equivalente.
- `possible_modification`: una norma parece modificar, limitar o actualizar a otra.
- `different_scope`: los textos se parecen, pero aplican a sujetos, situaciones o ambitos distintos.
- `neutral`: no se detecta tension relevante.
- `needs_review`: el caso requiere revision humana.

Para cada resultado, el sistema debe guardar:

- etiqueta;
- confianza;
- explicacion breve;
- citas de los fragmentos comparados;
- modelo usado;
- version del prompt o regla;
- timestamp.

### 5. Generacion de propuesta de redaccion

Para los casos clasificados como contradiccion, redundancia o solapamiento fuerte, el modelo debe generar una propuesta de mejora.

La salida puede tener esta forma:

- problema detectado;
- articulos o fragmentos afectados;
- razonamiento resumido;
- propuesta de texto alternativo;
- advertencias sobre ambitos, fechas o supuestos no resueltos.

Esta parte es clave para la demo: no alcanza con detectar similitud, hay que mostrar como el sistema podria ayudar a corregir o armonizar la normativa.

## Arquitectura conceptual

```text
Datos oficiales
  -> corpus unificado
  -> segmentacion en fragmentos
  -> embeddings
  -> indice vectorial
  -> clustering / vecinos cercanos
  -> candidatos de analisis
  -> clasificacion con LLM
  -> explicacion + propuesta de redaccion
  -> revision humana / metricas
```

## MVP recomendado

Para la materia, el MVP deberia ser acotado pero demostrable.

### Incluido

- Carga del corpus procesado existente.
- Segmentacion inicial por articulos.
- Generacion de embeddings para una muestra o subconjunto manejable.
- Busqueda de vecinos cercanos.
- Seleccion de pares candidatos.
- Clasificacion de pares con un LLM.
- Generacion de explicacion y texto alternativo.
- Notebook o script reproducible con resultados.
- Informe tecnico con metodologia, limitaciones y ejemplos.

### No incluido en el MVP

- Fine-tuning propio.
- Cobertura perfecta de toda la normativa argentina.
- Resolucion juridica definitiva de conflictos.
- Interfaz completa de asistente legal.
- Ingesta nueva desde cero si los datos actuales alcanzan para experimentar.

## Estrategia de evaluacion

Como no hay ejemplos semilla de contradicciones conocidas, conviene evaluar el sistema como un ranking de candidatos para revision humana.

Metricas sugeridas:

- **Precision@K**: proporcion de casos utiles entre los primeros K resultados.
- **Tasa de hallazgos relevantes**: cantidad de redundancias/contradicciones plausibles encontradas en una muestra.
- **Calidad de explicacion**: evaluacion humana de si la justificacion cita evidencia correcta.
- **Utilidad de propuesta de redaccion**: evaluacion humana de si el texto alternativo reduce ambiguedad o duplicacion.
- **Trazabilidad**: porcentaje de respuestas con fragmentos y fuentes correctamente identificadas.

Si se consigue revision de abogados o docentes, se puede construir un pequeno conjunto etiquetado para medir precision y ajustar prompts.

## Riesgos principales

- La similitud semantica no implica contradiccion juridica.
- Dos articulos pueden parecer equivalentes pero aplicar a sujetos, epocas o ambitos distintos.
- La vigencia normativa puede no estar completamente resuelta.
- La cobertura de texto no es total y varia entre snapshots.
- Algunos textos largos requieren segmentacion especial.
- El grafo de modificaciones indica relacion entre normas, pero no necesariamente el articulo exacto modificado.
- Un LLM puede sobreinterpretar si no se le exige citar evidencia textual.

## Plan de trabajo

### Fase 1: Consolidacion de datos — completa

- Elegir el snapshot principal: `lexar_datos_infoleg_saij`.
- Confirmar conteos de documentos, textos y fuentes.
- Definir esquema de `legal_fragments`.
- Implementar o ajustar segmentacion por articulo.

### Fase 2: Embeddings y busqueda — completa

- Generar embeddings sobre el corpus completo (no solo una muestra): 113.895 fragmentos, 112.582
  embeddings unicos via Vertex AI (`gemini-embedding-001`).
- Construir indice vectorial (FAISS, similitud coseno exacta).
- Recuperar vecinos cercanos por fragmento: 679.720 pares candidatos.
- Inspeccionar clusters y subespacios: 8.942 clusters exploratorios; visualizacion PCA/t-SNE.

Detalle tecnico completo en `CLAUDE.md` (seccion "Notebook architecture").

### Fase 3: Analisis de candidatos — completa

- Disenar prompt de clasificacion: guia de las 6 etiquetas, exige citar evidencia textual de ambos
  fragmentos, usa el grafo de modificaciones de Infoleg como pista (no como etiqueta automatica).
- Reglas deterministas antes del LLM (near_identical, boilerplate): resolvieron 23.889 de 68.050 pares
  (35%) sin costo de LLM.
- Clasificar pares candidatos en dos niveles: triage con `gemini-2.5-flash-lite` sobre 44.161 pares,
  verificacion con `gemini-2.5-flash` sobre los 440 marcados `possible_conflict` — confirmo solo 84 (19%),
  bajando el resto a `different_scope`/`possible_modification`/`possible_overlap`.
- Guardar etiquetas, confianza, explicacion y evidencia citada en `candidate_classifications.parquet`.
- Golden set estratificado (80 pares) para evaluacion humana, con guia de etiquetado incluida en el
  notebook.

Distribucion final: 25.017 `possible_overlap`, 24.868 `neutral`, 14.077 `possible_modification`, 3.607
`different_scope`, 397 `needs_review`, 84 `possible_conflict`. Detalle tecnico completo en `CLAUDE.md`
(seccion "Notebook architecture (Fase 3)").

### Fase 4 (vieja) y Fase 5 (vieja): reemplazadas por el pivot

Las fases "Redaccion alternativa" e "Informe y demo" que originalmente seguian a la deteccion de
contradicciones quedan **reemplazadas** por las Fases 4-8 del pivot (abajo). El detalle completo de
implementacion esta en `PLAN.md`.

### Fase 4: Jurisprudencia CSJN (SAIJ) — completa

- Scraping de fallos de la Corte Suprema publicados en SAIJ, 2020 en adelante (via la API JSON de
  SAIJ; el texto completo viene como PDF, extraido con `pypdf`).
- Segmentacion con el mismo `chunk_text()` de la Fase 1 (los fallos no tienen estructura de articulos).
- Embeddings con el mismo pipeline de la Fase 2 (`gemini-embedding-001`, checkpointing reanudable).
- Vinculo ley↔fallo por similitud semantica contra el indice FAISS de leyes de la Fase 2.

Resultado (2026-07-09): **1.234 fallos** CSJN 2020-2026, **8.702 fragmentos** unicos, **8.702/8.702
embeddings**, **28.930 vinculos** ley↔fallo entre 1.225 fallos y 2.743 normas. Dos hallazgos tecnicos no
anticipados: un limite de profundidad de paginacion en el backend de SAIJ (resuelto paginando por año
calendario via el facet `Fecha/<año>`) y un bug de colision de indices de checkpoint en el pipeline de
embeddings (corregido). Detalle completo en `CLAUDE.md` y en `notebooks/Jurisprudencia_CSJN.ipynb`.

### Fase 5: Vinculos entre normas + resumenes IA — completa

- Consolidacion de `analysis_candidates` (Fase 2) y `candidate_classifications` (Fase 3) a nivel
  documento, unida con el grafo oficial de modificaciones de Infoleg → `norm_links.parquet`.
- Resumenes de cada vinculo generados por IA **on-demand con cache** (no batch masivo): se generan la
  primera vez que se consultan y quedan cacheados en `link_summaries.parquet`.

Resultado: **48.276 vinculos** (38.552 semanticos, 8.297 oficiales, 1.427 ambos). Sanity check contra la
Ley 24.240 (Defensa del Consumidor): 20 vinculos, 18 modificaciones posteriores detectadas
correctamente. Cache de resumenes verificado (la segunda consulta al mismo par no vuelve a llamar al
LLM). Detalle tecnico en `notebooks/Vinculos_Normas.ipynb` y `src/lexar/summaries.py`.

### Fase 6: Chatbot RAG — completa

- Extraccion del core compartido (rate limiter, embeddings, retrieval FAISS) a `src/lexar/`, reusado
  tanto por los notebooks nuevos como por la app.
- Pipeline del chatbot: *query rewriting* (caso coloquial → consultas en lenguaje juridico) →
  retrieval sobre leyes y fallos → respuesta con citas obligatorias → validacion automatica de que
  cada cita es texto literal de la fuente.
- Set de casos de prueba anotado a mano (`eval/casos_prueba.csv`) como ground truth de la Fase 8.

Resultado: verificado end-to-end contra ambos indices FAISS (leyes + fallos). Sobre los 17 casos de
prueba: **143 citas** generadas, **93,7% trazables** (verificadas textualmente contra la fuente
citada). Detalle tecnico en `src/lexar/chatbot.py`.

### Fase 7: App web (FastAPI + HTMX + Tailwind) — completa

Originalmente construida en Streamlit; reconstruida el 2026-07-10 como app FastAPI con templates
Jinja2, HTMX para la interactividad y Tailwind CSS (CDN v4), con identidad visual propia.

- **Explorador** (`app/routes/explorador.py`): busqueda por titulo (en vivo) o **por tema**
  (semantica, sobre el indice FAISS de la Fase 2, con score y snippet por resultado), URL
  compartible (`/explorador?q=...&modo=...`), ficha de norma con URL propia
  (`/explorador/norma/infoleg:638`), advertencia de vigencia, tabla de normas vinculadas con
  boton "Explicar IA" por fila (resumen on-demand con cache), **mapa de vinculos** (grafo
  interactivo del vecindario normativo, con vinculos entre vecinos, via vis-network) y fallos
  CSJN relacionados.
- **Hallazgos** (`app/routes/hallazgos.py`): los 84 pares *possible_conflict* confirmados por la
  verificacion de la Fase 3, agrupados por par de normas, con explicacion del verificador,
  ambos fragmentos y boton "Explicar IA" — la conexion visible del producto con la mision
  original del proyecto.
- **Chatbot** (`app/routes/chatbot.py`): chat **multi-turno** (las repreguntas se entienden en
  contexto) sobre el pipeline de la Fase 6, con **progreso en vivo por etapa** (reescritura →
  busqueda → redaccion, via polling HTMX), **citas clickeables** (frag → ficha de la norma,
  cfrag → fallo en SAIJ), sello de verificacion por cita y **feedback 👍/👎** persistido en
  `outputs/feedback_chatbot.parquet`.
- **Home** (`app/routes/home.py`): estado de los datos generados por cada fase.

Correr con `python -m uvicorn app.main:app` desde la raiz del repo (por defecto en
`http://127.0.0.1:8000`). Verificado (2026-07-10) con click-through completo en navegador: busqueda,
ficha de la Ley 24.240 (advertencia de vigencia + 20 vinculos), resumen IA desde cache, y consulta
al chatbot con citas verificadas.

### Fase 8: Evaluacion e informe — completa

- Precision@K / Recall del chatbot sobre `casos_prueba.csv`, con y sin *query rewriting*.
- Trazabilidad: porcentaje de citas del chatbot verificadas automaticamente contra la fuente.
- Muestra estratificada para rubrica humana de calidad de los resumenes de vinculos.
- Informe final con metodologia, limitaciones y ejemplos.

Resultado (2026-07-09), sobre los 17 casos de `eval/casos_prueba.csv`: **Recall@10 73,5%** con query
rewriting vs. **70,6%** sin — la mejora que justifica la decision de diseño. Precision@10 practicamente
plana (10,0% vs. 9,4%), esperable dado que cada caso tiene solo 1-2 leyes esperadas frente a 10
posiciones evaluadas. Trazabilidad de citas: **93,7%** (134/143) en la corrida original;
**re-medida el 2026-07-10 tras corregir el parseo de citas con multiples ids en un corchete:
96,3% (157/163)** (`outputs/eval/citation_traceability_v2.csv`). La rubrica humana de resumenes de
vinculos (`outputs/eval/rubrica_resumenes.csv`) quedo generada pero sin completar — requiere revision
manual del equipo. Detalle tecnico en `notebooks/Evaluacion_Producto.ipynb`.

## Entregables

- Base de fragmentos legales segmentados (leyes y fallos CSJN).
- Indices de embeddings (leyes y jurisprudencia).
- Grafo de vinculos entre normas, con resumenes generados por IA.
- Chatbot juridico con citas verificadas.
- App web FastAPI + HTMX (explorador + chatbot).
- Metricas de evaluacion (precision/recall de retrieval, trazabilidad de citas).
- Informe academico-tecnico.

