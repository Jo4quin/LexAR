"""Chatbot RAG (Fase 6): caso en lenguaje natural → leyes aplicables + fallos CSJN relevantes.

Pipeline: (1) query rewriting — un LLM reescribe el caso coloquial en consultas en lenguaje
juridico, mitigando el mismatch coloquial↔formal sin re-embeber el corpus (los embeddings de
Fase 2 son SEMANTIC_SIMILARITY, un espacio simetrico donde la query se embebe igual);
(2) retrieval FAISS sobre fragmentos de leyes y de fallos; (3) respuesta con citas obligatorias
validadas automaticamente contra el texto fuente.
"""
from __future__ import annotations

from google.genai import types

from .config import CHAT_MODEL
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


def rewrite_query(case_text: str, limiter: AdaptiveRateLimiter | None = None) -> dict:
    prompt = f"""Un abogado describe un caso en lenguaje coloquial. Reescribilo como 1 a 3 consultas
breves en lenguaje juridico formal argentino, aptas para buscar normativa aplicable por
similitud semantica (ej.: "me chocaron el auto" → "responsabilidad civil por accidente de
transito", "obligacion de resarcir danos causados por vehiculos"). Indica tambien la materia
juridica principal.

Caso: {case_text}

Devolve un unico JSON con: consultas (lista de 1 a 3 strings), materia (string breve)."""
    return generate_json(CHAT_MODEL, prompt, REWRITE_SCHEMA, limiter)


def _law_context(hits, top_docs: int) -> tuple[str, dict[str, str]]:
    docs = aggregate_hits_by_document(hits, "document_id").head(top_docs)
    section, sources = "", {}
    for _, row in docs.iterrows():
        source_id = row["fragment_id"]
        sources[source_id] = row["text"]
        section += (
            f"\n[{source_id}] {row['titulo_resumido']} ({row['tipo_norma']}, {row['fecha_sancion']}, "
            f"{row['label']}, id {row['document_id']}):\n{str(row['text'])[:1500]}\n"
        )
    return section, sources


def _case_context(hits, top_cases: int) -> tuple[str, dict[str, str]]:
    if hits is None or hits.empty:
        return "", {}
    cases = aggregate_hits_by_document(hits, "case_id").head(top_cases)
    section, sources = "", {}
    for _, row in cases.iterrows():
        source_id = row["fragment_id"]
        sources[source_id] = row["text"]
        section += (
            f"\n[{source_id}] Fallo CSJN {row['fecha']}: {row['actor']} c/ {row['demandado']} "
            f"s/ {row['sobre']} (id {row['case_id']}):\n{str(row['text'])[:1500]}\n"
        )
    return section, sources


def answer_case(
    case_text: str,
    law_index: CorpusIndex,
    case_index: CorpusIndex | None = None,
    top_k_fragments: int = 24,
    top_docs: int = 6,
    top_cases: int = 4,
    limiter: AdaptiveRateLimiter | None = None,
) -> dict:
    limiter = limiter or AdaptiveRateLimiter()

    rewrite = rewrite_query(case_text, limiter)
    consultas = [q for q in rewrite.get("consultas", []) if q.strip()] or [case_text]

    query_vectors = embed_texts(consultas, limiter)
    law_hits = law_index.search(query_vectors, top_k=top_k_fragments)
    case_hits = case_index.search(query_vectors, top_k=top_k_fragments) if case_index is not None else None

    law_section, law_sources = _law_context(law_hits, top_docs)
    case_section, case_sources = _case_context(case_hits, top_cases)
    sources = {**law_sources, **case_sources}

    fallos_block = f"\nFallos CSJN recuperados (desde 2020):\n{case_section}" if case_section else ""
    prompt = f"""Sos un asistente de investigacion juridica para abogados argentinos. Un abogado plantea
un caso; en base UNICAMENTE a los fragmentos normativos y fallos recuperados abajo, indica el
marco legal aplicable: que leyes aplican, que dicen, y que fallos recientes son relevantes.
Reglas estrictas:
- Cada afirmacion normativa debe citar su fuente con el identificador entre corchetes
  (ej. [frag:00012345]) y las citas textuales deben ser copias literales del texto provisto.
- Si los fragmentos recuperados no cubren el caso, decilo explicitamente en vez de inventar.
- Responde en espanol, en markdown, ordenado por relevancia.

Caso planteado: {case_text}
Consultas juridicas derivadas: {"; ".join(consultas)} (materia: {rewrite.get("materia", "")})

Fragmentos normativos recuperados:
{law_section}{fallos_block}

Devolve un unico JSON con: respuesta_markdown (la respuesta completa) y citas (lista de
objetos con fuente_id — el identificador entre corchetes — y cita_textual — copia literal
del fragmento que sostiene cada afirmacion central)."""

    result = generate_json(CHAT_MODEL, prompt, ANSWER_SCHEMA, limiter)

    citations = []
    for citation in result.get("citas", []):
        source_id = citation.get("fuente_id", "").strip().strip("[]")
        quote = citation.get("cita_textual", "")
        source_text = sources.get(source_id, "")
        citations.append({
            "fuente_id": source_id,
            "cita_textual": quote,
            "cita_valida": bool(source_text) and normalize_text(quote) in normalize_text(source_text),
        })

    return {
        "caso": case_text,
        "consultas": consultas,
        "materia": rewrite.get("materia", ""),
        "respuesta_markdown": result["respuesta_markdown"],
        "citas": citations,
        "disclaimer": DISCLAIMER,
        "leyes": aggregate_hits_by_document(law_hits, "document_id").head(top_docs),
        "fallos": (
            aggregate_hits_by_document(case_hits, "case_id").head(top_cases)
            if case_hits is not None and not case_hits.empty
            else None
        ),
    }
