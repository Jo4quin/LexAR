"""Chatbot RAG (Fase 6): caso en lenguaje natural → leyes aplicables + fallos CSJN relevantes.

Pipeline: (1) query rewriting — un LLM reescribe el caso coloquial en consultas en lenguaje
juridico, mitigando el mismatch coloquial↔formal sin re-embeber el corpus (los embeddings de
Fase 2 son SEMANTIC_SIMILARITY, un espacio simetrico donde la query se embebe igual);
(2) retrieval FAISS sobre fragmentos de leyes y de fallos; (3) respuesta con citas obligatorias
validadas automaticamente contra el texto fuente.
"""
from __future__ import annotations

import re
from typing import Callable

from google.genai import types

from .config import ANSWER_MODEL, REWRITE_MODEL
from .embeddings import embed_texts
from .llm import generate_json
from .rate_limiter import AdaptiveRateLimiter
from .retrieval import CorpusIndex, aggregate_hits_by_document
from .segmentation import normalize_text

DISCLAIMER = (
    "Esta respuesta es asistencia a la investigacion juridica sobre un corpus acotado "
    "(leyes y decreto-leyes nacionales; fallos CSJN publicados en SAIJ desde 2020). "
    "No constituye asesoramiento legal."
)

REWRITE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "consultas": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
        "materia": types.Schema(type=types.Type.STRING),
    },
    required=["consultas", "materia"],
)

ANSWER_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "respuesta_markdown": types.Schema(type=types.Type.STRING),
        "citas": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "fuente_id": types.Schema(type=types.Type.STRING),
                    "cita_textual": types.Schema(type=types.Type.STRING),
                },
                required=["fuente_id", "cita_textual"],
            ),
        ),
    },
    required=["respuesta_markdown", "citas"],
)


# Ids de fuente citables ([frag:00012345] leyes, [cfrag:00001234] fallos). El LLM a veces mete
# varios en un mismo corchete ("[cfrag:X, cfrag:Y]") — se parsean todas las ocurrencias en vez
# de tratar el corchete como un unico id (bug conocido que penalizaba la trazabilidad).
CITATION_ID_PATTERN = re.compile(r"c?frag:\d+")

MAX_HISTORY_TURNS = 4
MAX_HISTORY_CHARS = 1_500


def _history_section(history: list[dict] | None) -> str:
    """Bloque 'Conversacion previa' para los prompts. history = [{'role','content'}, ...]."""
    if not history:
        return ""
    lines = []
    for turn in history[-MAX_HISTORY_TURNS:]:
        content = str(turn.get("content", "")).strip()
        if not content:
            continue
        role = "Abogado" if turn.get("role") == "user" else "Asistente"
        lines.append(f"{role}: {content[:MAX_HISTORY_CHARS]}")
    if not lines:
        return ""
    return "\nConversacion previa (contexto de esta consulta):\n" + "\n".join(lines) + "\n"


def rewrite_query(
    case_text: str,
    limiter: AdaptiveRateLimiter | None = None,
    history: list[dict] | None = None,
) -> dict:
    history_block = _history_section(history)
    followup_note = (
        "\nSi el caso es una repregunta o ampliacion sobre la conversacion previa, reescribilo\n"
        "incorporando ese contexto (la consulta reescrita debe entenderse sola)."
        if history_block
        else ""
    )
    prompt = f"""Un abogado describe un caso en lenguaje coloquial. Reescribilo como 1 a 3 consultas
breves en lenguaje juridico formal argentino, aptas para buscar normativa aplicable por
similitud semantica (ej.: "me chocaron el auto" → "responsabilidad civil por accidente de
transito", "obligacion de resarcir danos causados por vehiculos"). Indica tambien la materia
juridica principal.{followup_note}
{history_block}
Caso: {case_text}

Devolve un unico JSON con: consultas (lista de 1 a 3 strings), materia (string breve)."""
    return generate_json(REWRITE_MODEL, prompt, REWRITE_SCHEMA, limiter)


def _vigencia_nota(info: dict | None, score: float) -> str:
    """Nota de vigencia/relevancia para la linea de la ley en el prompt. `info` viene de
    vigencia_fn: {'estado', 'detalle', 'n_mods'}. Siempre incluye la relevancia (similitud del
    mejor fragmento) para que el modelo pese matches debiles (caso C)."""
    partes = [f"relevancia {score:.2f}"]
    if info:
        estado, detalle, n_mods = info.get("estado"), info.get("detalle"), info.get("n_mods", 0)
        if estado:
            partes.append(f"{estado.upper()}" + (f" — {detalle}" if detalle else ""))
        if n_mods:
            partes.append(f"{n_mods} modificaciones posteriores (el texto puede ser la version original)")
    return " · ".join(partes)


def _law_context(
    hits, top_docs: int, vigencia_fn=None, frags_per_doc: int = 3
) -> tuple[str, dict[str, str], dict[str, dict]]:
    """Contexto normativo agrupado por ley. Para cada una de las top_docs leyes se incluyen sus
    mejores `frags_per_doc` fragmentos (no solo el de mayor similitud): una ley suele tener el
    articulo sustantivo en un fragmento distinto al que mejor matchea la consulta, y con uno solo
    ese criterio queda afuera (p.ej. la regla de edad de un regimen penal)."""
    if hits.empty:
        return "", {}, {}
    ranked = aggregate_hits_by_document(hits, "document_id").head(top_docs)
    hits_sorted = hits.sort_values("score", ascending=False)
    section, sources, fuentes = "", {}, {}
    for _, drow in ranked.iterrows():
        document_id = drow["document_id"]
        info = vigencia_fn(document_id) if vigencia_fn else None
        section += (
            f"\n{drow['tipo_norma']} — {drow['titulo_resumido']} ({drow['fecha_sancion']}, "
            f"{drow['label']}, id {document_id}) [VIGENCIA: {_vigencia_nota(info, float(drow['score']))}]:\n"
        )
        doc_frags = hits_sorted[hits_sorted["document_id"] == document_id].head(frags_per_doc)
        for _, frow in doc_frags.iterrows():
            source_id = frow["fragment_id"]
            sources[source_id] = frow["text"]
            fuentes[source_id] = {
                "tipo": "ley",
                "document_id": document_id,
                "titulo": str(drow["titulo_resumido"]),
                "estado": (info or {}).get("estado", ""),
                "detalle": (info or {}).get("detalle", ""),
            }
            section += f"  [{source_id}]: {str(frow['text'])[:1200]}\n"
    return section, sources, fuentes


def _case_context(hits, top_cases: int) -> tuple[str, dict[str, str], dict[str, dict]]:
    if hits is None or hits.empty:
        return "", {}, {}
    cases = aggregate_hits_by_document(hits, "case_id").head(top_cases)
    section, sources, fuentes = "", {}, {}
    for _, row in cases.iterrows():
        source_id = row["fragment_id"]
        sources[source_id] = row["text"]
        fuentes[source_id] = {
            "tipo": "fallo",
            "case_id": row["case_id"],
            "url": str(row["url"]) if row.get("url") else "",
            "titulo": f"{row['actor']} c/ {row['demandado']} s/ {row['sobre']}",
        }
        section += (
            f"\n[{source_id}] Fallo CSJN {row['fecha']}: {row['actor']} c/ {row['demandado']} "
            f"s/ {row['sobre']} (id {row['case_id']}):\n{str(row['text'])[:1500]}\n"
        )
    return section, sources, fuentes


def validate_citations(citas: list[dict], sources: dict[str, str]) -> list[dict]:
    """Valida cada cita contra sus fuentes. Un corchete puede traer varios ids — la cita es
    valida si la quote normalizada aparece en alguna de las fuentes listadas."""
    citations = []
    for citation in citas:
        raw_id = str(citation.get("fuente_id", ""))
        ids = CITATION_ID_PATTERN.findall(raw_id) or [raw_id.strip().strip("[]")]
        quote = citation.get("cita_textual", "")
        quote_norm = normalize_text(quote)
        valid = bool(quote_norm) and any(
            source_id in sources and quote_norm in normalize_text(sources[source_id])
            for source_id in ids
        )
        citations.append({
            "fuente_id": ", ".join(ids),
            "fuente_ids": ids,
            "cita_textual": quote,
            "cita_valida": valid,
        })
    return citations


def answer_case(
    case_text: str,
    law_index: CorpusIndex,
    case_index: CorpusIndex | None = None,
    top_k_fragments: int = 40,
    top_docs: int = 6,
    top_cases: int = 4,
    frags_per_doc: int = 3,
    limiter: AdaptiveRateLimiter | None = None,
    history: list[dict] | None = None,
    on_stage: Callable[[str], None] | None = None,
    vigencia_fn: Callable[[str], dict] | None = None,
    answer_model: str | None = None,
) -> dict:
    limiter = limiter or AdaptiveRateLimiter()
    notify = on_stage or (lambda stage: None)

    notify("reescribiendo")
    rewrite = rewrite_query(case_text, limiter, history)
    consultas = [q for q in rewrite.get("consultas", []) if q.strip()] or [case_text]

    notify("buscando")
    query_vectors = embed_texts(consultas, limiter)
    law_hits = law_index.search(query_vectors, top_k=top_k_fragments)
    case_hits = case_index.search(query_vectors, top_k=top_k_fragments) if case_index is not None else None

    law_section, law_sources, law_fuentes = _law_context(law_hits, top_docs, vigencia_fn, frags_per_doc)
    case_section, case_sources, case_fuentes = _case_context(case_hits, top_cases)
    sources = {**law_sources, **case_sources}
    fuentes = {**law_fuentes, **case_fuentes}

    notify("redactando")
    history_block = _history_section(history)
    fallos_block = f"\nFallos CSJN recuperados (desde 2020):\n{case_section}" if case_section else ""
    prompt = f"""Sos un asistente de investigacion juridica para abogados argentinos. Un abogado plantea
un caso; en base UNICAMENTE a los fragmentos normativos y fallos recuperados abajo, indica el
marco legal aplicable: que leyes aplican, que dicen, y que fallos recientes son relevantes.
Reglas estrictas:
- Cada afirmacion normativa debe citar su fuente con el identificador entre corchetes
  (ej. [frag:00012345]) y las citas textuales deben ser copias literales del texto provisto.
- Si los fragmentos recuperados no cubren el caso, decilo explicitamente en vez de inventar.
- Responde en espanol, en markdown, ordenado por relevancia.

VIGENCIA Y JERARQUIA (cada ley trae una nota [VIGENCIA: ...] con su estado y relevancia):
- Si una ley figura DEROGADA o ABROGADA (o solo modifica una ley derogada), su criterio ya NO
  rige: responde con el de la ley EN VIGOR y menciona la derogada solo como antecedente.
- El flag de derogacion es la senal dura. Una ley NO derogada sigue vigente aunque sea antigua
  (puede ser ley especial que prevalece sobre una general posterior): no la descartes por vieja.
  La posterioridad solo desempata entre dos normas EN VIGOR incompatibles cuando ninguna es
  claramente especial. AcLara siempre cual es la norma vigente.
- Si una ley vigente tiene "modificaciones posteriores", adverti que el texto citado puede ser la
  version original y no reflejar la ultima reforma.
- ATENCION vacatio legis: una nota puede decir que una ley sera abrogada/reemplazada por otra que
  aun NO entro en vigor (p.ej. "vigencia a los 180 dias de la publicacion"). En ese caso indica el
  criterio ACTUALMENTE vigente Y TAMBIEN el cambio que viene, con su fecha de entrada en vigor, para
  que el abogado sepa que la regla esta por cambiar.

ALCANCE: el corpus es solo leyes y decreto-leyes NACIONALES (sin decretos comunes, resoluciones ni
normativa provincial/municipal) y solo el 29,6% tiene texto completo. Si los fragmentos son de baja
relevancia o el tema es tipicamente provincial/local (ej. transito, habilitaciones municipales),
aclaralo: puede haber normativa aplicable fuera de este corpus. No fuerces una respuesta con normas
que no encajan.
{history_block}
Caso planteado: {case_text}
Consultas juridicas derivadas: {"; ".join(consultas)} (materia: {rewrite.get("materia", "")})

Fragmentos normativos recuperados:
{law_section}{fallos_block}

Devolve un unico JSON con: respuesta_markdown (la respuesta completa) y citas (lista de
objetos con fuente_id — el identificador entre corchetes — y cita_textual — copia literal
del fragmento que sostiene cada afirmacion central)."""

    result = generate_json(answer_model or ANSWER_MODEL, prompt, ANSWER_SCHEMA, limiter)

    return {
        "caso": case_text,
        "consultas": consultas,
        "materia": rewrite.get("materia", ""),
        "respuesta_markdown": result["respuesta_markdown"],
        "citas": validate_citations(result.get("citas", []), sources),
        "fuentes": fuentes,
        "disclaimer": DISCLAIMER,
        "leyes": aggregate_hits_by_document(law_hits, "document_id").head(top_docs),
        "fallos": (
            aggregate_hits_by_document(case_hits, "case_id").head(top_cases)
            if case_hits is not None and not case_hits.empty
            else None
        ),
    }
