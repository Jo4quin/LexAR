"""Chatbot RAG: caso en lenguaje natural -> respuesta con citas verificadas.

El historial vive solo en el DOM (HTMX agrega mensajes): answer_case() es stateless, igual
que en la version Streamlit donde el historial era puramente visual.
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from lexar import config
from lexar.chatbot import DISCLAIMER, answer_case

from .. import state
from ..templating import templates

router = APIRouter()

LEY_COLS = ["document_id", "titulo_resumido", "tipo_norma", "fecha_sancion", "score"]
FALLO_COLS = ["case_id", "fecha", "actor", "demandado", "sobre", "score"]


@router.get("/chatbot", response_class=HTMLResponse)
def chatbot(request: Request):
    return templates.TemplateResponse(request, "chatbot.html", {
        "disclaimer": DISCLAIMER,
        # Chequeo barato (sin cargar FAISS): si falta la Fase 4, avisar que responde solo con leyes.
        "sin_fallos": not config.CASE_EMBEDDINGS_NPY_PATH.exists(),
    })


@router.post("/chatbot/mensaje", response_class=HTMLResponse)
def mensaje(request: Request, caso: str = Form(...)):
    try:
        result = answer_case(caso, state.get_law_index(), state.get_case_index())
    except Exception as exc:
        return templates.TemplateResponse(
            request, "partials/mensaje_asistente.html", {"error": str(exc)}
        )

    leyes = result["leyes"][LEY_COLS].to_dict("records") if result["leyes"] is not None else []
    fallos = (
        result["fallos"][FALLO_COLS].to_dict("records") if result["fallos"] is not None else None
    )
    citas_validas = sum(c["cita_valida"] for c in result["citas"])
    return templates.TemplateResponse(request, "partials/mensaje_asistente.html", {
        "consultas": result["consultas"],
        "materia": result["materia"],
        "respuesta_markdown": result["respuesta_markdown"],
        "citas": result["citas"],
        "citas_validas": citas_validas,
        "leyes": leyes,
        "fallos": fallos,
        "disclaimer": DISCLAIMER,
    })
