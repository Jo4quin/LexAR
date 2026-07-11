# Tutorial: usar el Asistente Jurídico LexAR

Guía práctica para poner en marcha la app (Explorador + Chatbot) y usarla. Para el detalle técnico
de cómo se construyó cada pieza, ver los notebooks de `notebooks/` y el `README.md`; este documento
es solo "cómo la uso".

## 1. Requisitos previos

- Python 3.11+ instalado.
- El paquete de datos `data/lexar_datos_infoleg_saij/` ya colocado en la raíz del repo (ver
  `README.md` → "Datos y artefactos" si todavía no lo tenés — se descargan del Drive).
- Los outputs de las Fases 1-4 ya generados en `outputs/` — es decir, haber corrido al menos una
  vez `notebooks/Redundancias&Contradicciones.ipynb`, `Clasificacion_Candidatos.ipynb`,
  `Jurisprudencia_CSJN.ipynb` y `Vinculos_Normas.ipynb`. Si no los corriste todavía, la página
  **Home** de la app te va a mostrar exactamente qué falta.
- Credenciales de Google Cloud activas — la app llama a Vertex AI para generar resúmenes de
  vínculos y respuestas del chatbot (las mismas credenciales que ya usaste en las Fases 2-3):

  ```bash
  gcloud auth application-default login
  ```

## 2. Instalación

Desde la raíz del repo:

```bash
pip install -r requirements.txt
```

Esto instala, entre otras cosas, `fastapi`, `uvicorn`, `ftfy` y `pypdf`, que son específicas del
pivot y no se usaban en las Fases 1-3.

## 3. Arrancar la app

```bash
python -m uvicorn app.main:app
```

Abrí `http://127.0.0.1:8000` en el navegador. Si el puerto 8000 está ocupado, agregá
`--port 8080` (o el que quieras) y ajustá la URL.

**Primer uso**: la primera vez que entrás a cada sección (Explorador, Chatbot), el servidor carga y
cachea los archivos parquet grandes y el índice FAISS — puede tardar varios segundos. La más lenta
es la **primera consulta al chatbot** (~40-60 segundos: construye el índice de 112k fragmentos y
recién después llama al modelo); las siguientes tardan solo lo que tardan las llamadas al LLM. La
terminal donde lanzaste `uvicorn` muestra el log de cada request, útil si algo no responde.

## 4. Home — estado de los datos

Lo primero que ves es un panel con una fila por artefacto (fragmentos de leyes, candidatos,
clasificaciones, fallos CSJN, vínculos entre normas, etc.) y su cantidad de filas actual. Sirve
para confirmar de un vistazo que todo lo que la app necesita ya está generado antes de usarla — si
falta algo, aparece marcado y te dice de qué fase viene.

## 5. Explorador — buscar una ley y ver sus vínculos

1. Andá a **Explorador** en la barra de navegación superior.
2. Elegí el modo de búsqueda:
   - **Por título** (default): escribí parte del título o el id de una norma (ej. `defensa del
     consumidor`, `24.240`, o directamente `infoleg:638`) — los resultados aparecen a medida que
     escribís.
   - **Por tema (semántica)**: escribí un tema o situación («protección de datos personales»,
     «contratos de alquiler») y apretá Enter o **Buscar** — encuentra normas por contenido aunque
     el título no coincida, usando el índice de embeddings del proyecto. Cada resultado muestra
     su score de similitud y un fragmento del texto que matcheó. La primera búsqueda por tema
     carga el índice (~30-60 s); las siguientes son casi instantáneas.
   En ambos modos la URL queda compartible (`/explorador?q=...&modo=...`).
3. Hacé clic en el resultado correcto. Cada norma tiene su propia URL
   (`/explorador/norma/infoleg:638`), así que podés compartirla o guardarla como favorito.
4. Vas a ver:
   - **Ficha de la norma**: tipo, fecha de sanción, boletín, id.
   - **Advertencia de vigencia**, si corresponde: cuántas modificaciones posteriores tiene
     registradas en Infoleg. Es una señal de que el texto mostrado puede no ser la versión vigente.
   - **Texto completo**, si el corpus lo tiene (recordá: solo el 29,6&nbsp;% de las leyes tienen
     texto completo — el resto son metadatos).
   - **Tabla de normas vinculadas**, con:
     - `vínculo`: si la relación es oficial (del grafo de modificaciones de Infoleg), semántica
       (por similitud de contenido) o ambas.
     - `relación`: la etiqueta que le puso el clasificador de la Fase 3 (modificación,
       superposición, alcance distinto, etc.).
     - `simil.`: qué tan parecido es el contenido, cuando aplica.
   - **Fallos CSJN relacionados** (2020 en adelante), con carátula, fecha y link directo a SAIJ.
5. Para pedir una explicación en lenguaje natural de por qué dos normas están vinculadas: apretá
   **"Explicar IA"** en la fila de ese vínculo. La primera vez que pedís ese par específico, llama
   al modelo (tarda unos segundos); si ya lo habías pedido antes, sale al instante desde el caché.
6. **Mapa de vínculos**: el botón "Ver mapa" dibuja el vecindario de la norma como un grafo
   interactivo — la norma al centro, sus vecinas alrededor, y también los vínculos *entre* las
   vecinas (así los clusters de normas que se modifican entre sí se ven a simple vista). Línea
   sólida = vínculo oficial, punteada = semántico; el color codifica la relación (rojo =
   conflicto, violeta = modificación). Click en cualquier nodo abre esa norma.

## 5 bis. Hallazgos — posibles conflictos normativos

La sección **Hallazgos** muestra el resultado estrella del análisis de las Fases 1-3: los pares de
fragmentos confirmados como *posible conflicto normativo*. El clasificador de dos niveles marcó 84
sobre 679.720 pares analizados, pero al revisarlos se vio que la mayoría eran *instrumentos
paralelos* (tratados con contrapartes distintas, regímenes para beneficiarios distintos), no
contradicciones; una re-verificación con criterio más estricto (Fase 3.5) los dejó en **4 conflictos
confirmados**, cada uno con su escenario concreto de colisión. Cada card muestra las dos normas (con
link a sus fichas), la explicación del modelo verificador, la similitud y confianza, y los dos
fragmentos enfrentados.
El botón "Explicar IA" genera un resumen más elaborado del vínculo (mismo caché que el
Explorador). Ojo: «posible conflicto» es una señal para revisión profesional, no un dictamen.

## 6. Chatbot — plantear un caso en lenguaje natural

1. Andá a **Chatbot** en la barra de navegación superior.
2. Escribí un caso como se lo contarías a un colega — no hace falta usar lenguaje jurídico. Ejemplos
   que funcionan bien:
   - *"Me chocaron el auto y el otro conductor no tiene seguro, qué puedo reclamar"*
   - *"Compré una heladera que vino fallada y el vendedor no se hace cargo"*
   - *"Me despidieron sin causa después de 10 años de trabajo"*
3. El chatbot muestra el progreso real de cada etapa mientras trabaja («Reescribiendo la
   consulta…» → «Buscando normativa y fallos…» → «Redactando la respuesta…») y tarda entre 15 y
   25 segundos en responder — internamente hace varias llamadas al modelo en cadena.
4. La respuesta viene en markdown, organizada por tema, con cada afirmación normativa citando su
   fuente entre corchetes (`[frag:...]` para leyes, `[cfrag:...]` para fallos). **Las citas son
   clickeables**: un `frag` te lleva a la ficha de esa norma en el Explorador y un `cfrag` abre
   el fallo en SAIJ.
5. **Podés repreguntar**: la conversación tiene memoria («¿y si el conductor era menor de
   edad?» se entiende en el contexto del caso anterior). "Nueva conversación" arranca de cero.
6. Debajo de la respuesta hay tres desplegables:
   - **Citas textuales**: cada cita con un sello **VERIFICADA** o **NO VERIFICADA** según se haya
     comprobado automáticamente que es texto literal de la fuente citada — así podés confiar (o
     desconfiar puntualmente) en cada afirmación sin tener que ir a buscar el texto original vos
     mismo.
   - **Leyes recuperadas**: la lista completa de normas que encontró el buscador, con su similitud.
   - **Fallos CSJN recuperados**: idem para jurisprudencia.
7. Al pie de cada respuesta hay botones **👍/👎** — el voto se guarda en
   `outputs/feedback_chatbot.parquet` y alimenta la evaluación del proyecto. Usalos: es un dato
   más para el informe.
8. También al pie, un recordatorio fijo: esto es asistencia a la investigación jurídica sobre un
   corpus acotado, **no asesoramiento legal**.

## 7. Limitaciones a tener presentes mientras la usás

- **Cobertura de texto**: 8.887 de 30.061 leyes (29,6&nbsp;%) tienen texto completo. Las demás solo
  tienen metadatos — no van a aparecer citadas por el chatbot ni tener texto en el Explorador.
- **Alcance del corpus**: solo Leyes y Decreto-Leyes nacionales. No hay decretos comunes,
  resoluciones ni normativa provincial — para temas muy locales (tránsito, por ejemplo) el chatbot
  va a traer lo que hay a nivel nacional, que puede ser parcial.
- **Jurisprudencia**: solo fallos de la Corte Suprema publicados en SAIJ desde 2020, y no el
  universo completo que maneja el buscador oficial de la Corte — es una selección.
- **Vigencia**: la advertencia de modificaciones posteriores te avisa que puede haber cambios, pero
  no reemplaza la verificación de la versión vigente en una fuente oficial.

## 8. Detener la app

`Ctrl+C` en la terminal donde la lanzaste.
