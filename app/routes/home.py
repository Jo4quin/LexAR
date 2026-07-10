"""Home: descripcion del producto + estado de los datos (una fila por artefacto del pipeline)."""
from __future__ import annotations

import pyarrow.parquet as pq
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from lexar import config

from ..templating import templates

router = APIRouter()

ARTIFACTS = [
    ("Fase 2", "Fragmentos de leyes", config.EMBEDDING_FRAGMENTS_PATH),
    ("Fase 2", "Pares candidatos", config.CANDIDATES_PATH),
    ("Fase 3", "Clasificaciones", config.CLASSIFICATIONS_PATH),
    ("Fase 4", "Fallos CSJN ≥2020", config.FALLOS_PATH),
    ("Fase 4", "Fragmentos de fallos", config.CASE_FRAGMENTS_PATH),
    ("Fase 4", "Vínculos ley↔fallo", config.LAW_CASE_LINKS_PATH),
    ("Fase 5", "Vínculos entre normas", config.NORM_LINKS_PATH),
    ("Fase 5 / app", "Caché de resúmenes IA", config.LINK_SUMMARIES_PATH),
]


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    artifacts = list(ARTIFACTS)
    # El feedback lo genera la propia app al usarla — se lista solo si existe, para que no
    # aparezca como "falta" (no hay ningun notebook que correr para generarlo).
    if config.FEEDBACK_PATH.exists():
        artifacts.append(("App", "Feedback del chatbot", config.FEEDBACK_PATH))
    rows = []
    for fase, label, path in artifacts:
        exists = path.exists()
        num_rows = None
        if exists:
            try:
                num_rows = pq.read_metadata(path).num_rows
            except Exception:
                num_rows = None
        rows.append({"fase": fase, "label": label, "exists": exists, "rows": num_rows})

    missing_npy = [
        p.name
        for p in (config.EMBEDDINGS_NPY_PATH, config.CASE_EMBEDDINGS_NPY_PATH)
        if not p.exists()
    ]
    # Modelos por tarea (nombres reales desde config, para no desincronizar la explicacion).
    modelos = [
        ("Embeddings semánticos", config.EMBEDDING_MODEL,
         "Vectoriza leyes, fallos y consultas en un mismo espacio (768d) para el retrieval FAISS."),
        ("Reescritura de consulta", config.REWRITE_MODEL,
         "Traduce el caso coloquial del chatbot a consultas en lenguaje jurídico formal."),
        ("Respuesta del chatbot", config.ANSWER_MODEL,
         "Redacta el marco legal con citas verificadas y prioriza la norma vigente."),
        ("Resúmenes de vínculos («Explicar IA»)", config.SUMMARY_MODEL,
         "Explica por qué dos normas se relacionan y su relevancia jurídica, on-demand y cacheado."),
        ("Clasificación de pares (Fase 3, batch)", "gemini-2.5-flash-lite → flash → pro",
         "Triage masivo, verificación y confirmación de conflictos en cascada de menor a mayor costo."),
    ]
    return templates.TemplateResponse(
        request, "home.html", {"artifacts": rows, "missing_npy": missing_npy, "modelos": modelos}
    )
