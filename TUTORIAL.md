# Tutorial: usar el Asistente Jurídico LexAR

Guía práctica para poner en marcha la app (Explorador + Chatbot) y usarla. Para el detalle técnico
de cómo se construyó cada pieza, ver `PLAN.md` y `CLAUDE.md`; este documento es solo "cómo la uso".

## 1. Requisitos previos

- Python 3.11+ instalado.
- El paquete de datos `data/lexar_datos_infoleg_saij/` ya colocado en la raíz del repo (ver
  `CLAUDE.md` → "Local data" si todavía no lo tenés).
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

Abrí `http://127.0.0.1:8000` en el navegador.

**Primer uso**: la primera vez que entrás a cada sección (Explorador, Chatbot), el servidor carga y
cachea los archivos parquet grandes y el índice FAISS — puede tardar varios segundos (la primera
consulta al chatbot es la más lenta). Las veces siguientes es instantáneo mientras el servidor siga
corriendo.

## 4. Home — estado de los datos

Lo primero que ves es un panel con una fila por artefacto (fragmentos de leyes, candidatos,
clasificaciones, fallos CSJN, vínculos entre normas, etc.) y su cantidad de filas actual. Sirve
para confirmar de un vistazo que todo lo que la app necesita ya está generado antes de usarla — si
falta algo, aparece marcado y te dice de qué fase viene.

## 5. Explorador — buscar una ley y ver sus vínculos

1. Andá a **Explorador** en la barra de navegación superior.
2. Escribí parte del título o el id de una norma en el buscador (ej. `defensa del consumidor`,
   `24.240`, o directamente `infoleg:638`) — los resultados aparecen a medida que escribís, y la
   URL queda compartible (`/explorador?q=...`).
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

## 6. Chatbot — plantear un caso en lenguaje natural

1. Andá a **Chatbot** en la barra de navegación superior.
2. Escribí un caso como se lo contarías a un colega — no hace falta usar lenguaje jurídico. Ejemplos
   que funcionan bien:
   - *"Me chocaron el auto y el otro conductor no tiene seguro, qué puedo reclamar"*
   - *"Compré una heladera que vino fallada y el vendedor no se hace cargo"*
   - *"Me despidieron sin causa después de 10 años de trabajo"*
3. El chatbot muestra su progreso ("Reescribiendo la consulta, buscando normativa y fallos…") y
   tarda entre 15 y 25 segundos en responder — internamente hace varias llamadas al modelo en
   cadena (reescritura de la consulta, búsqueda y generación de la respuesta).
4. La respuesta viene en markdown, organizada por tema, con cada afirmación normativa citando su
   fuente entre corchetes (`[frag:...]` para leyes, `[cfrag:...]` para fallos).
5. Debajo de la respuesta hay tres desplegables:
   - **Citas textuales**: cada cita con un sello **VERIFICADA** o **NO VERIFICADA** según se haya
     comprobado automáticamente que es texto literal de la fuente citada — así podés confiar (o
     desconfiar puntualmente) en cada afirmación sin tener que ir a buscar el texto original vos
     mismo.
   - **Leyes recuperadas**: la lista completa de normas que encontró el buscador, con su similitud.
   - **Fallos CSJN recuperados**: idem para jurisprudencia.
6. Al pie, un recordatorio fijo: esto es asistencia a la investigación jurídica sobre un corpus
   acotado, **no asesoramiento legal**.

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
