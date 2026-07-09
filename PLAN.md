# Plan de implementación: pivot a Asistente Jurídico para Abogados (Fases 4–8)

> Documento de planificación del equipo — 8 de julio de 2026. Actualizado el 9 de julio de 2026
> con los resultados finales de la implementación.
> Complementa al `README.md` (que describe las Fases 1–3, ya completas) y lo reemplazará como
> plan de trabajo vigente una vez validado por el equipo.

## Resultado final (2026-07-09) — Fases 4-8 completas

Todas las fases del pivot se implementaron y verificaron contra datos reales en la branch
`pivot-asistente-juridico`:

| Fase | Resultado |
|---|---|
| 6.1 — Core `src/lexar/` | 11 módulos extraídos/nuevos, importados por notebooks y app |
| 4 — Jurisprudencia CSJN | 1.234 fallos (2020-2026), 8.702 fragmentos, 8.702/8.702 embeddings, 28.930 vínculos ley↔fallo |
| 5 — Vínculos + resúmenes | 48.276 `norm_links` (38.552 semánticos, 8.297 oficiales, 1.427 ambos); resúmenes on-demand verificados con caché |
| 6 — Chatbot RAG | Verificado end-to-end con ambos índices; 8/10 citas válidas en el ejemplo de referencia |
| 7 — App Streamlit | Las 3 páginas arrancan sin errores (`streamlit run app/Home.py`, HTTP 200) |
| 8 — Evaluación | Recall@10 73,5 % (con query rewriting) vs. 70,6 % (sin); trazabilidad de citas 93,7 % sobre 143 citas |

Un hallazgo no anticipado en el plan original: un bug real de colisión de índices de checkpoint
en `embeddings.py` (ver sección Fase 4 y `CLAUDE.md`), encontrado y corregido durante la
implementación — no un problema de recursos de la máquina como parecía al principio.

## Contexto

El equipo decidió redireccionar LexAR hacia un producto para abogados: explorador de leyes con normas
vinculadas, fallos CSJN relevantes (SAIJ, ≥2020), resúmenes IA por vínculo, y un chatbot que recibe casos
en lenguaje natural. La evaluación de viabilidad (2026-07-08) concluyó que las Fases 1–3 existentes son
la base del producto: los 112.582 embeddings + FAISS son el motor de retrieval, el grafo `relations.csv`
+ los 679.720 pares semánticos son los vínculos, y el motor LLM de Fase 3 (`run_classification_stage()`)
se reusa para los resúmenes. El único dato nuevo es la jurisprudencia: **~1.261 fallos CSJN ≥2020**
(de 16.977 en SAIJ), verificado contra la API.

Este plan reemplaza las viejas Fases 4 (redacción alternativa) y 5 (informe) del README por las nuevas
Fases 4–8 del producto. Se mantiene la numeración continua y el patrón de trabajo existente: una fase =
un notebook pipeline con constantes `MAX_*` para smoke tests, checkpointing reanudable y outputs en
`outputs/`.

**Decisiones ya tomadas:**

- Interfaz: **app Streamlit** (explorador + chatbot).
- Resúmenes IA de vínculos: **on-demand + caché parquet** (no batch masivo); se precalientan los
  ejemplos de la demo.
- Alcance jurisprudencia: **solo Fallos CSJN 2020→hoy** vía SAIJ.
- Chatbot: **query rewriting** (caso coloquial → consulta jurídica) en lugar de re-embeber el corpus
  con task type RETRIEVAL.
- Todo en la branch `Lucaspini01`.

## Activos existentes a reutilizar (no reimplementar)

| Activo | Dónde vive |
|---|---|
| `chunk_text()`, `segment_text_version()` | `notebooks/Redundancias&Contradicciones.ipynb` |
| `AdaptiveRateLimiter` (AIMD) + `embed_batch_with_retry()` | mismo notebook — embeddings con `task_type="SEMANTIC_SIMILARITY"`, 768d |
| `top_neighbors_faiss()` | mismo notebook |
| `run_classification_stage()` + `normalize_text()` + patrón `types.Schema`/JSON estructurado | `notebooks/Clasificacion_Candidatos.ipynb` |
| `outputs/embeddings.npy` + `embedding_fragments.parquet` (112.582 × 768, L2-norm) | ya generados |
| `outputs/analysis_candidates.parquet` (679.720 pares), `candidate_classifications.parquet` (68.050 clasificados) | ya generados |
| `data/.../infoleg/procesado/relations.csv` (126.447 aristas), `documents.csv` (30.061 normas) | paquete de datos |
| GCP: proyecto `lexar-501717`, ADC ya configurado, modelos `gemini-embedding-001`, `gemini-2.5-flash-lite`, `gemini-2.5-flash` | config existente |

**Gotcha de API descubierto en la evaluación:** el facet de tribunal en la API de búsqueda de SAIJ es
`Tribunal/CORTE SUPREMA DE JUSTICIA DE LA NACION` — `Organismo/...` devuelve 0 resultados.

## Nueva estructura del repo

```
src/lexar/            # NUEVO — código compartido entre notebooks nuevos y la app
  __init__.py
  config.py           # ROOT/paths/GCP_PROJECT (misma lógica de resolución que el config cell actual)
  rate_limiter.py     # AdaptiveRateLimiter extraído tal cual
  embeddings.py       # cliente Vertex embed (SEMANTIC_SIMILARITY, 768d) + embed_batch_with_retry
  retrieval.py        # carga de embeddings.npy/FAISS (leyes y fallos), búsqueda top-k, agregación por documento
  links.py            # carga/joins de norm_links, law_case_links, relations
  summaries.py        # resumen on-demand de vínculo con caché parquet
  chatbot.py          # pipeline query rewriting → retrieval → respuesta con citas
  textfix.py          # corrección best-effort de mojibake para display (ftfy)
notebooks/
  Jurisprudencia_CSJN.ipynb    # Fase 4
  Vinculos_Normas.ipynb        # Fase 5
  Evaluacion_Producto.ipynb    # Fase 8
app/
  Home.py                      # landing + estado de datos
  pages/1_Explorador.py        # Fase 7
  pages/2_Chatbot.py           # Fase 7
```

Los notebooks de Fases 1–3 **no se tocan** (siguen siendo la documentación ejecutable de esas fases).
Los notebooks nuevos importan desde `src/lexar/` en lugar de copiar código. `requirements.txt` suma
`streamlit`, `ftfy`, `requests`.

---

## Fase 4 — Jurisprudencia CSJN (notebook `Jurisprudencia_CSJN.ipynb`) — completa

**Resultado real:** 1.234 fallos CSJN 2020-2026 (100 % `fetch_status=ok`), 8.702 fragmentos
únicos, 8.702/8.702 embeddings, 28.930 vínculos ley↔fallo entre 1.225 fallos y 2.743 normas.

**Dos hallazgos que no estaban en el plan original:**
- *Límite de paginación de SAIJ*: paginar sobre los ~17.000 fallos con `o=`/`p=` devuelve HTTP
  500 determinístico pasado offset ~1.000 (techo del backend, no un documento corrupto). Se
  resolvió paginando por año calendario vía el facet `Fecha/<año>` (verificado exacto:
  `Fecha/2020` → 248 resultados), manteniendo cada consulta muy por debajo del techo. Detalle
  completo en `CLAUDE.md`.
- *Bug de colisión de índices de checkpoint*: al borrar manualmente un checkpoint de embeddings
  corrupto (por una escritura truncada durante un momento de disco lleno), la siguiente corrida
  reutilizó ese número de archivo — `next_part_index = len(list(glob(...)))` cuenta archivos, no
  calcula el máximo índice existente, así que un hueco en la numeración hace que el próximo
  `to_parquet` pise un checkpoint válido en silencio. Corregido en `src/lexar/embeddings.py`
  (`_next_part_index()` usa máximo+1). Ver `CLAUDE.md` para el detalle de diagnóstico.

**4.1 Scraping SAIJ.** Contra `https://www.saij.gob.ar/busqueda` (JSON): facets
`Tipo de Documento/Jurisprudencia/Fallo` + `Tribunal/CORTE SUPREMA DE JUSTICIA DE LA NACION`, paginando
con `o` (offset) y `p` (page size), orden `fecha-rango|DESC`, cortando en fecha < 2020-01-01. Por cada
resultado, bajar el documento completo por `uuid` (mismo patrón de API que produjo `saij_texts.csv`).
Rate limiting cortés (sleep ~0.5 s entre requests; son ~1,3k docs, minutos). Checkpointing simple:
guardar por lotes y saltar uuids ya bajados al reanudar.

- Salida: `data/jurisprudencia_csjn/fallos_csjn.parquet` (gitignored, documentar en `CLAUDE.md`).
- Esquema: `case_id` (`saij:<uuid>`), `fecha`, `titulo`, `tipo_fallo` (sentencia/interlocutorio),
  `descriptores` (tesauro), `full_text`, `url`, `fetch_status`. Mantener la convención de claves del
  proyecto (prefijo de namespace como `infoleg:<id>`).

**4.2 Segmentación.** `chunk_text()` reutilizado (los fallos no tienen estructura `ARTICULO n`; chunking
directo con overlap). Salida: `outputs/jurisprudencia/case_fragments.parquet` con los mismos campos que
`legal_fragments` (`fragment_id` con prefijo `cfrag:`, `content_hash` sha256). Volumen estimado: ~15–40k
fragmentos.

**4.3 Embeddings.** Mismo pipeline de Fase 2 (limiter + retry + checkpoints en
`outputs/jurisprudencia/embeddings/part_*.parquet`, keyed por `content_hash`), consolidado a
`outputs/jurisprudencia/case_embeddings.npy` + parquet alineado 1:1. Costo: centavos.

**4.4 Vínculo ley↔fallo.** FAISS sobre los embeddings de leyes existentes; buscar cada fragmento de
fallo → top-k fragmentos de ley; agregar a nivel `(document_id, case_id)` con `max_sim`, `mean_sim`,
`n_fragment_pairs`. Salida: `outputs/jurisprudencia/law_case_links.parquet`. Respetar la regla de memoria
del proyecto: **sin** `text_a`/`text_b` en la tabla bulk; texto solo en exports chicos de inspección.

**Smoke test:** constante `MAX_FALLOS` (None = todo) en el config cell, mismo patrón que
`MAX_TEXT_VERSIONS`.

## Fase 5 — Grafo de vínculos entre normas + resúmenes IA (notebook `Vinculos_Normas.ipynb`) — completa

**Resultado real:** 48.276 vínculos (38.552 solo semánticos, 8.297 solo oficiales, 1.427 ambos).
Distribución de `dominant_label`: 23.357 `neutral`, 11.575 `possible_modification`, 10.865
`possible_overlap`, 2.277 `different_scope`, 192 `needs_review`, 10 `possible_conflict`. Sanity
check contra la Ley 24.240 (Defensa del Consumidor): 20 vínculos, 18 modificaciones posteriores
detectadas correctamente. Resúmenes on-demand precalentados sobre 8 pares de demo y verificados:
la segunda llamada al mismo par sale del caché sin volver a llamar al LLM.

**5.1 Consolidación a nivel documento.** Desde `analysis_candidates.parquet` (filtrado a similitud
≥0.957) agregar pares de fragmentos → pares de documentos (`n_fragment_pairs`, `max_sim`, `mean_sim`).
Join con `relations.csv` → `link_source ∈ {official, semantic, both}`. Join con
`candidate_classifications.parquet` → `dominant_label` (moda de `final_label` del par de documentos) y
hasta 3 `final_explanation` existentes como evidencia. Excluir pares donde la etiqueta dominante es
`neutral` por boilerplate. Salida: `outputs/norm_links.parquet` (clave: `doc_pair_key` = ids ordenados).

**5.2 Resúmenes on-demand.** Implementar en `src/lexar/summaries.py` (no en el notebook, para que la app
lo importe): función que recibe `doc_pair_key`, arma el prompt con metadatos de ambas normas
(`titulo_resumido`, `tipo_norma`, `fecha_sancion`), los top pares de fragmentos con texto,
`has_infoleg_relation` y `dominant_label`, y pide a `gemini-2.5-flash-lite` un JSON estructurado
(`relation_summary`, `legal_relevance`, `evidence_quotes`) — reusar el patrón `types.Schema` de Fase 3.
Caché en `outputs/link_summaries.parquet` (append, keyed por `doc_pair_key` + versión de prompt): si ya
existe, no llama al LLM. El notebook precalienta los resúmenes de los ejemplos de la demo (~20–30 pares).

## Fase 6 — Chatbot RAG (módulo `src/lexar/chatbot.py`) — completa

**Resultado real:** verificado end-to-end con `answer_case()` sobre los dos índices FAISS
(112.582 fragmentos de leyes + 8.702 de fallos). Ejemplo de referencia ("me chocaron el auto y
el otro conductor no tiene seguro"): reescritura a 2 consultas jurídicas, recuperó 6 leyes y 4
fallos CSJN relevantes, generó respuesta citada con 8/10 citas válidas contra el texto fuente.
Sobre los 17 casos de prueba completos (Fase 8): 143 citas totales, 93,7 % de trazabilidad.

**6.1 Extracción del core a `src/lexar/`.** Copiar (no mover) `AdaptiveRateLimiter`,
`embed_batch_with_retry`, la carga FAISS y `normalize_text` desde los notebooks a los módulos listados
arriba. Los notebooks viejos quedan intactos; código nuevo importa de `src`.

**6.2 Pipeline del chatbot** (una función `answer_case(query) -> Answer`):

1. *Query rewriting*: `gemini-2.5-flash` reescribe el caso coloquial ("me chocaron el auto") en 1–3
   consultas en lenguaje jurídico + materia estimada. Mitiga el mismatch coloquial↔formal sin re-embeber
   el corpus (los embeddings existentes son `SEMANTIC_SIMILARITY`; la query se embebe igual, quedando en
   el mismo espacio simétrico).
2. *Retrieval*: embed de las consultas reescritas → FAISS top-k sobre fragmentos de leyes **y** de fallos
   → agregación por `document_id`/`case_id` (score máx por documento), traer normas vinculadas de
   `norm_links` para los top documentos.
3. *Generación*: `gemini-2.5-flash` redacta la respuesta con citas obligatorias — cada afirmación
   normativa referencia `document_id`/`case_id` + quote textual (salida JSON estructurada:
   `answer_markdown`, `citations[]`). Disclaimer fijo de "no es asesoramiento legal".
4. *Validación de citas*: check automático de que cada quote ∈ texto del fragmento citado (esto alimenta
   la métrica de trazabilidad de Fase 8).

**6.3 Set de casos de prueba.** `outputs/eval/casos_prueba.csv`: ~15–20 casos coloquiales (choque de
auto, despido, alquiler, defensa del consumidor, etc.) con las leyes esperadas anotadas a mano por el
equipo (columnas `caso`, `leyes_esperadas`, `notas`). Es el ground truth de la evaluación de Fase 8.

## Fase 7 — App Streamlit (`app/`) — completa

**Resultado real:** las 3 páginas (`Home`, `Explorador`, `Chatbot`) arrancan sin errores —
`streamlit run app/Home.py` responde HTTP 200 en las tres rutas, sin traceback en el log del
servidor. Verificación a nivel de arranque/smoke test; queda pendiente una pasada manual de
interacción en navegador (buscar una ley, pedir un resumen, hacer una consulta al chatbot) para
quien continúe el trabajo.

**Explorador (`pages/1_Explorador.py`):**

- Búsqueda/selección de ley por número o título (sobre `documents.csv`).
- Ficha de la norma: metadatos, texto si existe (pasado por `textfix.py`/ftfy para el mojibake),
  advertencia de vigencia ("esta norma tiene N modificaciones posteriores" desde `relations.csv`).
- Tabla de normas vinculadas desde `norm_links.parquet`: badge de `link_source`
  (oficial/semántico/ambos), `dominant_label`, similitud. Botón "Explicar relación" → resumen on-demand
  (`summaries.py`, spinner la primera vez, instantáneo desde caché después).
- Sección "Fallos CSJN relacionados (2020→hoy)" desde `law_case_links.parquet`, ordenados por
  similitud/fecha, con link a SAIJ.

**Chatbot (`pages/2_Chatbot.py`):** UI de chat (`st.chat_message`) sobre `chatbot.answer_case()`, con
citas expandibles que muestran el fragmento fuente completo. Disclaimer visible.

**Home (`Home.py`):** descripción del producto + panel de estado de datos (conteos de cada parquet, para
detectar de un vistazo si falta correr una fase).

Carga de datos con `@st.cache_resource` (FAISS + parquets se cargan una vez). Correr con
`streamlit run app/Home.py` desde el repo root; reusar la lógica de resolución de `ROOT` de `config.py`.

## Fase 8 — Evaluación e informe (notebook `Evaluacion_Producto.ipynb`) — completa

**Resultado real** (sobre los 17 casos de `eval/casos_prueba.csv`, guardado en
`outputs/eval/ablation_query_rewrite.csv` y `outputs/eval/citation_traceability.csv`):

- **Precision@10**: 10,0 % sin query rewriting vs. 9,4 % con — prácticamente sin diferencia. Es
  un número bajo esperable: el conjunto de leyes esperadas por caso es chico (1-2 normas) frente
  a las 10 posiciones evaluadas, así que precision@10 castiga estructuralmente incluso a un
  retrieval que encuentra todo lo relevante.
- **Recall@10**: 70,6 % sin rewriting vs. **73,5 % con rewriting** — la mejora real que justifica
  la decisión de diseño: reescribir el caso coloquial a lenguaje jurídico ayuda a que las leyes
  esperadas aparezcan en algún lugar del top-10, que es la métrica que más importa para un
  chatbot de investigación (el usuario ve la lista completa, no solo el primer resultado).
- **Trazabilidad de citas**: 93,7 % (134 de 143 citas) son texto literal verificable contra el
  fragmento fuente citado.
- La rúbrica humana de resúmenes de vínculos (`outputs/eval/rubrica_resumenes.csv`) quedó armada
  por el notebook pero sin completar — requiere revisión manual del equipo, no es automatizable.

- **Actualización de documentación**: `README.md` y `CLAUDE.md` reescritos con el pivot completo,
  la nueva estructura `src/`/`app/`/`eval/`, y los gotchas técnicos encontrados (facet `Tribunal`,
  límite de paginación de SAIJ, bug de colisión de índices de checkpoint).

## Orden de ejecución y dependencias

```
Fase 4 (jurisprudencia) ──┐
                          ├→ Fase 7 (app) → Fase 8 (evaluación + informe)
Fase 5 (vínculos) ────────┤
Fase 6 (chatbot core) ────┘
```

Fases 4, 5 y 6.1 son independientes entre sí (4 y 5 solo dependen de outputs ya generados). El orden
recomendado de implementación: 6.1 (`src/`) primero — 4 y 5 ya nacen importando de ahí — luego 4, 5,
6.2–6.3, 7, 8.

## Costos estimados (créditos UDESA)

- Fase 4: embeddings de ~15–40k chunks → centavos. Scraping: gratis, minutos.
- Fase 5: on-demand; precalentamiento de demo ~30 llamadas flash-lite → despreciable.
- Fase 6/7: por consulta del chatbot (~3 llamadas LLM + 1 embed) → centavos por sesión de demo.
- Total esperado: **< 5 USD**, muy por debajo de lo que costó Fase 2–3.

## Verificación por fase

1. **Fase 4 smoke**: `MAX_FALLOS=20` → scraping + chunking + embeddings + links corren end-to-end;
   verificar que los 20 fallos son CSJN y ≥2020, y que `law_case_links` tiene pares con similitud >0.6.
2. **Fase 4 full**: conteo final ≈1.261 fallos (± los que agregue SAIJ); spot-check de 5 fallos contra
   la web de SAIJ.
3. **Fase 5**: `norm_links` — verificar contra 3 leyes conocidas (p. ej. una ley con modificatorias
   famosas) que los vínculos oficiales aparecen con `link_source=official`; generar 2 resúmenes on-demand
   y confirmar que la segunda llamada sale del caché (sin latencia LLM).
4. **Fase 6**: correr `answer_case("me chocaron el auto")` → debe citar Ley 24.449 (tránsito) y/o CCyC;
   validación de quotes en verde.
5. **Fase 7**: `streamlit run app/Home.py` → flujo completo manual: buscar "24.240" (defensa del
   consumidor) → ver vínculos → explicar una relación → ver fallos; luego una consulta al chatbot.
6. **Fase 8**: notebook corre con `casos_prueba.csv` completo y produce las 3 métricas.

## Riesgos conocidos (heredados de la evaluación de viabilidad)

- **Cobertura de texto: 29,6 %** (8.887/30.061 leyes) — comunicar el alcance en la app.
- **Corpus solo nacional** (Leyes y Decreto-Leyes) — sin decretos, resoluciones ni normativa provincial.
- **SAIJ publica una selección de fallos CSJN** (~100–250/año), no el universo completo del buscador
  oficial de la Corte.
- **Vigencia**: solo 803 normas tienen versión actualizada — mitigado con la advertencia de
  modificaciones posteriores en el explorador.
- **Mojibake** en el texto fuente — mitigado en display con ftfy; el fix real en origen queda fuera de
  alcance.
