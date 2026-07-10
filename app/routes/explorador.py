"""Explorador de leyes: busqueda con HTMX, ficha de norma con URL compartible,
normas vinculadas con resumen IA on-demand y fallos CSJN relacionados."""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from lexar.links import count_later_modifications, links_for_document
from lexar.textfix import fix_display_text

from .. import state
from ..templating import templates

router = APIRouter()

MAX_RESULTADOS = 50
MAX_VINCULOS = 100
MAX_FALLOS = 10
MAX_TEXTO_CHARS = 50_000

LINK_SOURCE_LABEL = {
    "official": "Oficial",
    "semantic": "Semántico",
    "both": "Oficial + semántico",
}
DOMINANT_LABEL = {
    "possible_modification": ("Modificación", "tinta"),
    "possible_overlap": ("Superposición", "tinta"),
    "possible_conflict": ("Posible conflicto", "rojo"),
    "different_scope": ("Alcance distinto", "neutro"),
    "neutral": ("Neutral", "neutro"),
    "needs_review": ("A revisar", "rojo"),
}


def _buscar(q: str) -> list[dict]:
    documents = state.get_documents()
    q = q.strip()
    if not q:
        return []
    mask = (
        documents["titulo_resumido"].str.contains(q, case=False, na=False, regex=False)
        | documents["titulo_sumario"].str.contains(q, case=False, na=False, regex=False)
        | documents["texto_resumido"].str.contains(q, case=False, na=False, regex=False)
        | (documents["document_id"] == q)
    )
    matches = documents[mask].head(MAX_RESULTADOS)
    return [
        {
            "document_id": row["document_id"],
            "titulo": fix_display_text(row["titulo_resumido"]),
            "tipo": row["tipo_norma"],
            "fecha": row["fecha_sancion"] or "s/d",
        }
        for _, row in matches.iterrows()
    ]


def _buscar_semantica(q: str, top_docs: int = 20) -> list[dict]:
    """Busqueda por tema: embebe la consulta (1 llamada a Vertex) y busca en el FAISS de leyes.
    Mismos campos que _buscar() + score y snippet del mejor fragmento."""
    from lexar.embeddings import embed_texts
    from lexar.retrieval import aggregate_hits_by_document

    law = state.get_law_index()
    hits = law.search(embed_texts([q.strip()]), top_k=40)
    docs = aggregate_hits_by_document(hits, "document_id").head(top_docs)
    return [
        {
            "document_id": row["document_id"],
            "titulo": fix_display_text(str(row["titulo_resumido"])),
            "tipo": row["tipo_norma"],
            "fecha": row["fecha_sancion"] or "s/d",
            "score": f"{row['score']:.3f}",
            "snippet": fix_display_text(str(row["text"])[:220]),
        }
        for _, row in docs.iterrows()
    ]


@router.get("/explorador", response_class=HTMLResponse)
def explorador(request: Request, q: str = "", modo: str = "titulo"):
    """Pagina de busqueda. El form HTMX pega a esta misma ruta (asi hx-push-url deja una URL
    compartible /explorador?q=...&modo=...): si el request viene de HTMX se devuelve solo el
    partial de resultados; si es una carga completa (o un link compartido), la pagina entera."""
    contexto = {"q": q, "modo": modo, "resultados": None}
    if q.strip():
        if modo == "tema":
            try:
                contexto["resultados"] = _buscar_semantica(q)
            except Exception as exc:
                contexto["error"] = f"No se pudo hacer la búsqueda semántica: {exc}"
                contexto["resultados"] = []
        else:
            contexto["resultados"] = _buscar(q)
    if request.headers.get("hx-request"):
        return templates.TemplateResponse(request, "partials/resultados_busqueda.html", contexto)
    return templates.TemplateResponse(request, "explorador.html", contexto)


def _vinculos_para_template(links: pd.DataFrame) -> list[dict]:
    titles = state.get_titles()
    rows = []
    for _, r in links.head(MAX_VINCULOS).iterrows():
        label, label_kind = DOMINANT_LABEL.get(r.get("dominant_label"), (r.get("dominant_label") or "—", "neutro"))
        sim = r.get("max_similarity")
        rows.append({
            "other_id": r["other_document_id"],
            "titulo": fix_display_text(str(titles.get(r["other_document_id"], r["other_document_id"]))),
            "source": LINK_SOURCE_LABEL.get(r.get("link_source"), r.get("link_source") or "—"),
            "source_kind": r.get("link_source"),
            "label": label,
            "label_kind": label_kind,
            "direccion": r.get("direccion_oficial") or "",
            "similitud": f"{sim:.3f}" if pd.notna(sim) else "—",
        })
    return rows


def _fallos_para_template(document_id: str) -> list[dict] | None:
    """None = Fase 4 sin correr (aviso en la UI); lista vacia = sin fallos sobre el umbral."""
    law_case_links, fallos = state.get_law_case_links(), state.get_fallos()
    if law_case_links is None or fallos is None:
        return None
    related = law_case_links[law_case_links["document_id"] == document_id].head(MAX_FALLOS)
    cards = []
    for _, r in related.iterrows():
        if r["case_id"] not in fallos.index:
            continue
        f = fallos.loc[r["case_id"]]
        cards.append({
            "caratula": fix_display_text(f"{f['actor']} c/ {f['demandado']} s/ {f['sobre']}")[:160],
            "tipo": str(f["tipo_fallo"]),
            "fecha": str(f["fecha"]),
            "url": str(f["url"]) if f.get("url") else "",
            "similitud": f"{r['max_similarity']:.3f}",
        })
    return cards


@router.get("/explorador/norma/{document_id}", response_class=HTMLResponse)
def norma(request: Request, document_id: str):
    documents = state.get_documents()
    if document_id not in documents.index:
        return templates.TemplateResponse(
            request,
            "explorador.html",
            {"q": document_id, "resultados": [], "error": f"No existe la norma «{document_id}» en el corpus."},
            status_code=404,
        )
    doc = documents.loc[document_id]
    norm_links = state.get_norm_links()
    links = links_for_document(norm_links, document_id)

    full_text = state.get_texts().get(document_id)
    if not (isinstance(full_text, str) and full_text.strip()):
        full_text = None

    return templates.TemplateResponse(request, "norma.html", {
        "doc": {
            "document_id": document_id,
            "titulo": fix_display_text(doc["titulo_resumido"]),
            "tipo": doc["tipo_norma"],
            "sancion": doc["fecha_sancion"] or "s/d",
            "boletin": doc["fecha_boletin"] or "s/d",
            "resumen": fix_display_text(doc["texto_resumido"]) if doc.get("texto_resumido") else "",
        },
        "n_mods": count_later_modifications(norm_links, document_id),
        "texto_completo": fix_display_text(full_text[:MAX_TEXTO_CHARS]) if full_text else None,
        "texto_chars": len(full_text) if full_text else 0,
        "vinculos": _vinculos_para_template(links),
        "n_vinculos": len(links),
        "fallos": _fallos_para_template(document_id),
    })


GRAFO_MAX_VECINOS = 20
# Colores de arista por etiqueta dominante (tokens de base.html). El resto de etiquetas
# (neutral, different_scope, needs_review) cae al gris de linea.
GRAFO_EDGE_COLORS = {
    "possible_conflict": "#A93D32",
    "possible_modification": "#4A3C8C",
    "possible_overlap": "#A99BE3",
}


def _grafo_edge(desde: str, hasta: str, source: str, label: str, sim: float) -> dict:
    width = 1.2
    if pd.notna(sim):
        width = 1 + max(0.0, min(1.0, (float(sim) - 0.95) / 0.05)) * 3
    etiqueta = DOMINANT_LABEL.get(label, (label or "—", ""))[0]
    return {
        "from": desde,
        "to": hasta,
        "dashes": source == "semantic",
        "color": {"color": GRAFO_EDGE_COLORS.get(label, "#C9C4B8"), "opacity": 0.85},
        "width": round(width, 2),
        "title": f"{etiqueta} · {LINK_SOURCE_LABEL.get(source, source)}",
    }


@router.get("/explorador/norma/{document_id}/grafo.json")
def grafo_json(document_id: str):
    """Datos para vis-network: la norma central, sus top vecinos y — clave para que se vea un
    cluster real y no una estrella — los vinculos entre los propios vecinos."""
    norm_links = state.get_norm_links()
    links = links_for_document(norm_links, document_id)
    vecinos = links.sort_values("max_similarity", ascending=False, na_position="last").head(GRAFO_MAX_VECINOS)
    titles = state.get_titles()
    node_ids = {document_id, *vecinos["other_document_id"]}

    def _label(doc_id: str) -> str:
        titulo = fix_display_text(str(titles.get(doc_id, doc_id)))
        return titulo[:32] + ("…" if len(titulo) > 32 else "")

    nodes = [{
        "id": document_id, "label": _label(document_id), "size": 26,
        "color": {"background": "#4A3C8C", "border": "#372D6E"},
        "title": f"{fix_display_text(str(titles.get(document_id, document_id)))} ({document_id})",
    }]
    edges = []
    for _, r in vecinos.iterrows():
        other = r["other_document_id"]
        nodes.append({
            "id": other, "label": _label(other), "size": 14,
            "color": {"background": "#EDEAF7", "border": "#A99BE3"},
            "title": f"{fix_display_text(str(titles.get(other, other)))} ({other})",
        })
        edges.append(_grafo_edge(document_id, other, r["link_source"], r.get("dominant_label"), r.get("max_similarity")))

    entre_vecinos = norm_links[
        norm_links["document_id_a"].isin(node_ids)
        & norm_links["document_id_b"].isin(node_ids)
        & (norm_links["document_id_a"] != document_id)
        & (norm_links["document_id_b"] != document_id)
    ]
    for _, r in entre_vecinos.iterrows():
        edges.append(_grafo_edge(
            r["document_id_a"], r["document_id_b"], r["link_source"],
            r.get("dominant_label"), r.get("max_similarity"),
        ))

    return {"nodes": nodes, "edges": edges}


@router.post("/explorador/norma/{document_id}/resumen", response_class=HTMLResponse)
def resumen(request: Request, document_id: str, other_document_id: str = Form(...)):
    """Resumen IA de un vinculo (partial HTMX). Cache-first via LinkSummarizer — el costo LLM
    se paga una sola vez por par de normas."""
    titles = state.get_titles()
    contexto = {
        "titulo_a": fix_display_text(str(titles.get(document_id, document_id))),
        "titulo_b": fix_display_text(str(titles.get(other_document_id, other_document_id))),
        "other_id": other_document_id,
    }
    links = links_for_document(state.get_norm_links(), document_id)
    match = links[links["other_document_id"] == other_document_id]
    link_row = match.iloc[0] if not match.empty else None
    try:
        summary = state.get_summarizer().summarize(document_id, other_document_id, link_row)
    except Exception as exc:
        return templates.TemplateResponse(
            request, "partials/resumen_vinculo.html", {**contexto, "error": str(exc)}
        )
    return templates.TemplateResponse(request, "partials/resumen_vinculo.html", {
        **contexto,
        "resumen": {
            "relacion": summary["relacion"],
            "relevancia": summary["relevancia_juridica"],
            "evidencia_a": fix_display_text(summary.get("evidencia_a") or ""),
            "evidencia_b": fix_display_text(summary.get("evidencia_b") or ""),
            "modelo": summary.get("model", ""),
            "from_cache": summary["from_cache"],
        },
    })
