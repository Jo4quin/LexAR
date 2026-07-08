"""Resumenes IA de vinculos entre normas, generados on-demand con cache en parquet (Fase 5).

Decision de equipo (2026-07-08): no se precomputan en batch — el resumen se genera la primera
vez que alguien abre ese vinculo en la app y queda cacheado por (doc_pair_key, prompt_version).
El costo LLM es proporcional al uso real; los ejemplos de la demo se precalientan aparte.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
from google.genai import types

from .config import (
    CANDIDATES_PATH,
    DOCUMENTS_PATH,
    EMBEDDING_FRAGMENTS_PATH,
    LINK_SUMMARIES_PATH,
    SIMILARITY_THRESHOLD,
    SUMMARY_MODEL,
)
from .llm import generate_json
from .rate_limiter import AdaptiveRateLimiter

SUMMARY_PROMPT_VERSION = "resumen-v1"

SUMMARY_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "relacion": types.Schema(type=types.Type.STRING),
        "relevancia_juridica": types.Schema(type=types.Type.STRING),
        "evidencia_a": types.Schema(type=types.Type.STRING),
        "evidencia_b": types.Schema(type=types.Type.STRING),
    },
    required=["relacion", "relevancia_juridica", "evidencia_a", "evidencia_b"],
)


class LinkSummarizer:
    """Carga una vez las tablas que necesita el prompt; `summarize()` es cache-first."""

    def __init__(self):
        self.documents = pd.read_csv(
            DOCUMENTS_PATH, dtype=str, keep_default_na=False
        ).set_index("document_id")
        candidates = pd.read_parquet(
            CANDIDATES_PATH,
            columns=["document_a_id", "document_b_id", "fragment_a_id", "fragment_b_id", "similarity_score"],
        )
        self.scoped = candidates[candidates["similarity_score"] >= SIMILARITY_THRESHOLD]
        self.fragment_texts = pd.read_parquet(
            EMBEDDING_FRAGMENTS_PATH, columns=["fragment_id", "text"]
        ).set_index("fragment_id")["text"]
        self.limiter = AdaptiveRateLimiter()

    def _load_cache(self) -> pd.DataFrame:
        if LINK_SUMMARIES_PATH.exists():
            return pd.read_parquet(LINK_SUMMARIES_PATH)
        return pd.DataFrame(columns=[
            "doc_pair_key", "prompt_version", "relacion", "relevancia_juridica",
            "evidencia_a", "evidencia_b", "model", "created_at",
        ])

    def _doc_line(self, document_id: str) -> str:
        if document_id not in self.documents.index:
            return document_id
        doc = self.documents.loc[document_id]
        return (
            f"{doc.get('titulo_resumido', '')} ({doc.get('tipo_norma', '')}, "
            f"sancionada {doc.get('fecha_sancion', '')}, id {document_id})"
        )

    def _top_fragment_pairs(self, doc_a: str, doc_b: str, top_n: int = 3) -> list[tuple[str, str, float]]:
        mask = (
            ((self.scoped["document_a_id"] == doc_a) & (self.scoped["document_b_id"] == doc_b))
            | ((self.scoped["document_a_id"] == doc_b) & (self.scoped["document_b_id"] == doc_a))
        )
        pairs = self.scoped[mask].sort_values("similarity_score", ascending=False).head(top_n)
        out = []
        for _, row in pairs.iterrows():
            frag_a, frag_b = row["fragment_a_id"], row["fragment_b_id"]
            if row["document_a_id"] != doc_a:
                frag_a, frag_b = frag_b, frag_a
            out.append((
                str(self.fragment_texts.get(frag_a, ""))[:1500],
                str(self.fragment_texts.get(frag_b, ""))[:1500],
                float(row["similarity_score"]),
            ))
        return out

    def _build_prompt(self, doc_a: str, doc_b: str, link_row: pd.Series | None) -> str:
        fragment_section = ""
        for i, (text_a, text_b, score) in enumerate(self._top_fragment_pairs(doc_a, doc_b), start=1):
            fragment_section += (
                f"\n--- Par de fragmentos {i} (similitud {score:.3f}) ---\n"
                f"De la Norma A: {text_a}\n"
                f"De la Norma B: {text_b}\n"
            )
        hints = []
        if link_row is not None:
            if link_row.get("link_source") in ("official", "both"):
                hints.append(
                    "Infoleg registra oficialmente que una de estas normas modifica a la otra "
                    f"({link_row.get('direccion_oficial') or link_row.get('official_direction', '')})."
                )
            label = link_row.get("dominant_label")
            if isinstance(label, str) and label:
                hints.append(f"Una clasificacion automatica previa etiqueto la relacion como '{label}'.")
        hint_section = ("\nContexto adicional: " + " ".join(hints)) if hints else ""
        if not fragment_section:
            fragment_section = "\n(No hay pares de fragmentos semanticamente similares; el vinculo es solo oficial.)"

        return f"""Sos un asistente de investigacion juridica para abogados argentinos. Explica de manera
clara y sintetica por que estas dos normas nacionales estan relacionadas y cual es la
relevancia juridica practica de ese vinculo para un profesional. No des asesoramiento legal;
describi la relacion. Cita evidencia textual literal de los fragmentos provistos; no inventes
contenido que no este en el texto.

Norma A: {self._doc_line(doc_a)}
Norma B: {self._doc_line(doc_b)}
{fragment_section}{hint_section}

Devolve un unico JSON con: relacion (2-3 oraciones explicando por que se vinculan),
relevancia_juridica (1-2 oraciones sobre que implica en la practica), evidencia_a (cita
textual breve de la Norma A, o cadena vacia si no hay fragmentos), evidencia_b (idem Norma B)."""

    def summarize(self, document_id_a: str, document_id_b: str, link_row: pd.Series | None = None) -> dict:
        doc_a, doc_b = sorted([document_id_a, document_id_b])
        key = f"{doc_a}|{doc_b}"
        cache = self._load_cache()
        hit = cache[(cache["doc_pair_key"] == key) & (cache["prompt_version"] == SUMMARY_PROMPT_VERSION)]
        if not hit.empty:
            row = hit.iloc[-1].to_dict()
            row["from_cache"] = True
            return row

        result = generate_json(SUMMARY_MODEL, self._build_prompt(doc_a, doc_b, link_row), SUMMARY_SCHEMA, self.limiter)
        row = {
            "doc_pair_key": key,
            "prompt_version": SUMMARY_PROMPT_VERSION,
            "relacion": result["relacion"],
            "relevancia_juridica": result["relevancia_juridica"],
            "evidencia_a": result["evidencia_a"],
            "evidencia_b": result["evidencia_b"],
            "model": SUMMARY_MODEL,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        updated = pd.concat([cache, pd.DataFrame([row])], ignore_index=True)
        LINK_SUMMARIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        updated.to_parquet(LINK_SUMMARIES_PATH, index=False)
        row["from_cache"] = False
        return row
