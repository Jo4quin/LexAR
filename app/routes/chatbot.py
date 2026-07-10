"""Chatbot RAG: caso en lenguaje natural -> respuesta con citas verificadas y clickeables.

- El historial vive solo en el cliente (JS manda un JSON con los turnos previos); el server es
  stateless salvo por los jobs en vuelo.
- Progreso en vivo: POST /chatbot/mensaje encola la consulta en un thread y devuelve una burbuja
  que hace polling a /chatbot/estado/{job_id}; answer_case reporta etapas via on_stage. La
  respuesta final (o el error) se devuelve con HTTP 286, que le indica a htmx cortar el polling.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from markupsafe import Markup, escape

from lexar import config
from lexar.chatbot import DISCLAIMER, answer_case

from .. import state
from ..templating import _md, templates

router = APIRouter()

LEY_COLS = ["document_id", "titulo_resumido", "tipo_norma", "fecha_sancion", "score"]
FALLO_COLS = ["case_id", "fecha", "actor", "demandado", "sobre", "score"]

JOB_TTL_SECONDS = 900
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

STAGE_TEXT = {
    "preparando": "Preparando la consulta…",
    "reescribiendo": "Reescribiendo la consulta en lenguaje jurídico…",
    "buscando": "Buscando normativa y fallos en los índices…",
    "redactando": "Redactando la respuesta con citas…",
}

CITATION_RE = re.compile(r"\[((?:c?frag:\d+)(?:\s*,\s*c?frag:\d+)*)\]")
ID_RE = re.compile(r"c?frag:\d+")


def _link_fuente(fragment_id: str, fuentes: dict) -> str:
    """<a> hacia la ficha de la norma (frag) o el fallo en SAIJ (cfrag); texto plano si el id
    no esta entre las fuentes recuperadas."""
    fuente = fuentes.get(fragment_id)
    attrs = 'class="text-tinta hover:underline"'
    if fuente and fuente.get("tipo") == "ley":
        return (
            f'<a href="/explorador/norma/{escape(fuente["document_id"])}" {attrs} '
            f'title="{escape(fuente.get("titulo", ""))}">{fragment_id}</a>'
        )
    if fuente and fuente.get("url"):
        return (
            f'<a href="{escape(fuente["url"])}" target="_blank" rel="noopener" {attrs} '
            f'title="{escape(fuente.get("titulo", ""))}">{fragment_id}</a>'
        )
    return fragment_id


def _linkify(html: str, fuentes: dict) -> Markup:
    """Convierte los [frag:...]/[cfrag:...] de la respuesta ya renderizada en links."""
    def _reemplazo(m: re.Match) -> str:
        ids = ID_RE.findall(m.group(1))
        return '<span class="font-mono text-[0.82em]">[' + ", ".join(
            _link_fuente(i, fuentes) for i in ids
        ) + "]</span>"

    return Markup(CITATION_RE.sub(_reemplazo, html))


def _contexto_respuesta(result: dict) -> dict:
    fuentes = result.get("fuentes", {})
    citas = [
        {**c, "ids_html": Markup(", ".join(_link_fuente(i, fuentes) for i in c["fuente_ids"]))}
        for c in result["citas"]
    ]
    return {
        "caso": result["caso"],
        "consultas": result["consultas"],
        "materia": result["materia"],
        "respuesta_html": _linkify(str(_md(result["respuesta_markdown"])), fuentes),
        "respuesta_markdown": result["respuesta_markdown"],
        "citas": citas,
        "citas_validas": sum(c["cita_valida"] for c in result["citas"]),
        "leyes": result["leyes"][LEY_COLS].to_dict("records") if result["leyes"] is not None else [],
        "fallos": result["fallos"][FALLO_COLS].to_dict("records") if result["fallos"] is not None else None,
        "disclaimer": DISCLAIMER,
    }


def _parse_historial(raw: str) -> list[dict] | None:
    """Historial que manda el cliente; defensivo — si no parsea, se ignora sin romper."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(parsed, list):
        return None
    turnos = [
        {"role": str(t.get("role", "")), "content": str(t.get("content", ""))}
        for t in parsed
        if isinstance(t, dict) and str(t.get("content", "")).strip()
    ]
    return turnos or None


def _limpiar_jobs() -> None:
    limite = time.time() - JOB_TTL_SECONDS
    with _jobs_lock:
        for job_id in [j for j, v in _jobs.items() if v["created"] < limite]:
            del _jobs[job_id]


@router.get("/chatbot", response_class=HTMLResponse)
def chatbot(request: Request):
    return templates.TemplateResponse(request, "chatbot.html", {
        "disclaimer": DISCLAIMER,
        # Chequeo barato (sin cargar FAISS): si falta la Fase 4, avisar que responde solo con leyes.
        "sin_fallos": not config.CASE_EMBEDDINGS_NPY_PATH.exists(),
    })


@router.post("/chatbot/mensaje", response_class=HTMLResponse)
def mensaje(request: Request, caso: str = Form(...), historial: str = Form("")):
    history = _parse_historial(historial)
    _limpiar_jobs()
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {"created": time.time(), "stage": "preparando", "result": None, "error": None}

    def _correr():
        def on_stage(stage: str) -> None:
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["stage"] = stage

        try:
            result = answer_case(
                caso, state.get_law_index(), state.get_case_index(),
                history=history, on_stage=on_stage,
            )
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["result"] = result
        except Exception as exc:
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["error"] = str(exc)

    threading.Thread(target=_correr, daemon=True).start()
    return templates.TemplateResponse(
        request, "partials/chat_progreso.html",
        {"job_id": job_id, "etapa": STAGE_TEXT["preparando"]},
    )


@router.get("/chatbot/estado/{job_id}", response_class=HTMLResponse)
def estado(request: Request, job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        snapshot = dict(job) if job else None

    if snapshot is None:
        return templates.TemplateResponse(
            request, "partials/mensaje_asistente.html",
            {"error": "la consulta expiró en el servidor — mandala de nuevo"}, status_code=286,
        )
    if snapshot["error"]:
        with _jobs_lock:
            _jobs.pop(job_id, None)
        return templates.TemplateResponse(
            request, "partials/mensaje_asistente.html", {"error": snapshot["error"]}, status_code=286,
        )
    if snapshot["result"] is None:
        return templates.TemplateResponse(
            request, "partials/chat_progreso.html",
            {"job_id": job_id, "etapa": STAGE_TEXT.get(snapshot["stage"], "Procesando…")},
        )

    with _jobs_lock:
        _jobs.pop(job_id, None)
    return templates.TemplateResponse(
        request, "partials/mensaje_asistente.html",
        _contexto_respuesta(snapshot["result"]), status_code=286,
    )


@router.post("/chatbot/feedback", response_class=HTMLResponse)
def feedback(
    request: Request,
    voto: str = Form(...),
    caso: str = Form(""),
    materia: str = Form(""),
    citas_validas: int = Form(0),
    citas_total: int = Form(0),
):
    state.append_feedback({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "caso": caso,
        "materia": materia,
        "voto": "util" if voto == "up" else "no_util",
        "citas_validas": int(citas_validas),
        "citas_total": int(citas_total),
    })
    return HTMLResponse(
        '<p class="font-mono text-[10.5px] uppercase tracking-[0.12em] text-verde py-1">'
        "Feedback registrado ✓ — gracias</p>"
    )
