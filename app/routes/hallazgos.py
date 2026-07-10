"""Hallazgos: los pares possible_conflict confirmados por la verificacion de la Fase 3 —
la conexion visible del producto con la mision original del proyecto (detectar redundancias
y contradicciones en la legislacion)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from lexar.textfix import fix_display_text

from .. import state
from ..templating import templates

router = APIRouter()


@router.get("/hallazgos", response_class=HTMLResponse)
def hallazgos(request: Request):
    conflictos = state.get_conflictos()
    titles = state.get_titles()

    grupos: dict[tuple[str, str], dict] = {}
    for _, r in conflictos.iterrows():
        clave = (r["document_a_id"], r["document_b_id"])
        if clave not in grupos:
            grupos[clave] = {
                "doc_a": r["document_a_id"],
                "doc_b": r["document_b_id"],
                "titulo_a": fix_display_text(str(titles.get(r["document_a_id"], r["document_a_id"]))),
                "titulo_b": fix_display_text(str(titles.get(r["document_b_id"], r["document_b_id"]))),
                "pares": [],
            }
        grupos[clave]["pares"].append({
            "similitud": f"{r['similarity_score']:.3f}",
            "confianza": f"{r['final_confidence']:.2f}" if r["final_confidence"] == r["final_confidence"] else "—",
            "explicacion": fix_display_text(str(r["final_explanation"] or "")),
            "text_a": fix_display_text(str(r["text_a"] or ""))[:2000],
            "text_b": fix_display_text(str(r["text_b"] or ""))[:2000],
        })

    lista = sorted(grupos.values(), key=lambda g: len(g["pares"]), reverse=True)
    return templates.TemplateResponse(request, "hallazgos.html", {
        "grupos": lista,
        "n_pares": len(conflictos),
        "n_grupos": len(lista),
    })
