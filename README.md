# LexAR

LexAR es un proyecto academico para la materia **Procesamiento de Lenguaje Natural**. El objetivo es construir una base de conocimiento sobre normativa nacional argentina y usarla para detectar posibles redundancias, contradicciones o solapamientos entre normas. A partir de ese trabajo, el proyecto tambien explora un asistente legal capaz de ayudar a redactar, revisar y desafiar escritos legales usando evidencia normativa recuperada del corpus.

## Objetivo general

Construir un pipeline de PLN que transforme textos legales argentinos en una base consultable por fragmentos, detecte normas semanticamente cercanas y clasifique pares candidatos segun el tipo de relacion juridico-linguistica que presentan.

La demo esperada debe mostrar:

- ejemplos de posibles contradicciones, redundancias o solapamientos encontrados;
- evidencia textual de los articulos o fragmentos involucrados;
- una explicacion generada por modelo;
- una propuesta de redaccion alternativa o texto de reemplazo que reduzca la ambiguedad o duplicacion detectada.

## Ideas principales

### 1. Deteccion de redundancias y contradicciones normativas

La primera linea del proyecto busca analizar leyes nacionales argentinas para encontrar relaciones problematicas entre fragmentos normativos.

Se consideran relevantes, entre otros, estos casos:

- contradicciones directas entre obligaciones, prohibiciones, permisos o procedimientos;
- normas viejas no derogadas que entren en tension con normas posteriores;
- definiciones legales incompatibles o parcialmente divergentes;
- plazos o requisitos procedimentales distintos para situaciones similares;
- excepciones que vuelven ambigua una regla general;
- normas que regulan lo mismo o son funcionalmente equivalentes aunque esten redactadas de manera distinta.

El sistema no parte de la idea de afirmar automaticamente que existe una contradiccion juridica definitiva. En el MVP, el resultado debe entenderse como una **hipotesis priorizada para revision humana**.

### 2. Asistente legal sobre la base de conocimiento

La segunda linea reutiliza el corpus, los embeddings, los clusters y los analisis previos para crear un asistente legal. El asistente deberia poder ayudar a:

- redactar una primera version de un escrito legal;
- revisar un escrito existente;
- encontrar fundamentos normativos;
- detectar argumentos debiles o normas potencialmente conflictivas;
- sugerir contraargumentos;
- proponer mejoras de redaccion con citas al corpus usado.

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

### Fase 3: Analisis de candidatos

- Disenar prompt de clasificacion.
- Clasificar pares candidatos.
- Guardar etiquetas, explicaciones y evidencia.
- Ajustar filtros para reducir falsos positivos.

### Fase 4: Redaccion alternativa

- Para casos relevantes, pedir al modelo una propuesta de armonizacion o reemplazo.
- Exigir que la propuesta cite los fragmentos usados.
- Comparar resultados manualmente.

### Fase 5: Informe y demo

- Preparar ejemplos representativos.
- Mostrar metodologia de punta a punta.
- Incluir limitaciones.
- Presentar metricas simples de evaluacion.

## Entregables

- Base de fragmentos legales segmentados.
- Indice de embeddings.
- Tabla de candidatos recuperados.
- Tabla de analisis clasificados.
- Ejemplos curados de contradiccion, redundancia o solapamiento.
- Propuestas de redaccion alternativa.
- Informe academico-tecnico.
- Demo reproducible en notebook o aplicacion minima.

## Proxima decision

La decision tecnica mas importante es fijar el **snapshot principal** y el **subconjunto inicial**.

Recomendacion:

1. Usar `lexar_dataset_2026-06-25/data/processed/text_corpus/text_versions.parquet` como base inicial por su mayor cobertura documentada.
2. Empezar con una muestra tematica o temporal para reducir ruido.
3. Validar manualmente los primeros 20 a 50 pares recuperados antes de escalar.

