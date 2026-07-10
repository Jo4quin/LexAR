"""Singletons del corpus, cargados lazy (reemplazan a los @st.cache_resource de Streamlit).

Cada recurso se carga en el primer request que lo necesita, no en el startup: la maquina de
desarrollo anda justa de RAM (ver CLAUDE.md) y asi la Home responde sin cargar FAISS ni el
texto completo del corpus. Un unico lock global serializa las cargas a proposito — dos cargas
pesadas concurrentes son justamente el pico de memoria que queremos evitar.
"""
from __future__ import annotations

import threading
from typing import Callable

import pandas as pd

from lexar import config
from lexar.links import load_norm_links
from lexar.retrieval import CorpusIndex, load_case_index, load_law_index
from lexar.summaries import LinkSummarizer

# RLock, no Lock: algunos loaders llaman a otros getters (get_titles -> get_documents) y un
# lock no reentrante deadlockea cuando el recurso interno todavia no esta cacheado.
_lock = threading.RLock()
_cache: dict[str, object] = {}


def _get(key: str, loader: Callable[[], object]):
    if key not in _cache:
        with _lock:
            if key not in _cache:
                _cache[key] = loader()
    return _cache[key]


def get_documents() -> pd.DataFrame:
    """documents.csv completo, indexado por document_id (30k filas, liviano)."""
    return _get(
        "documents",
        lambda: pd.read_csv(config.DOCUMENTS_PATH, dtype=str, keep_default_na=False).set_index(
            "document_id", drop=False
        ),
    )


def get_titles() -> pd.Series:
    return _get("titles", lambda: get_documents()["titulo_resumido"])


def get_norm_links() -> pd.DataFrame:
    return _get("norm_links", load_norm_links)


def get_texts() -> pd.Series:
    """document_id -> full_text (misma carga que hacia el explorador de Streamlit)."""
    return _get(
        "texts",
        lambda: pd.read_parquet(config.TEXT_VERSIONS_PATH, columns=["document_id", "full_text"])
        .drop_duplicates("document_id")
        .set_index("document_id")["full_text"],
    )


def get_law_case_links() -> pd.DataFrame | None:
    """None si la Fase 4 no corrio — la UI degrada con un aviso, no crashea."""
    return _get(
        "law_case_links",
        lambda: pd.read_parquet(config.LAW_CASE_LINKS_PATH)
        if config.LAW_CASE_LINKS_PATH.exists()
        else None,
    )


def get_fallos() -> pd.DataFrame | None:
    return _get(
        "fallos",
        lambda: pd.read_parquet(config.FALLOS_PATH).set_index("case_id", drop=False)
        if config.FALLOS_PATH.exists()
        else None,
    )


def get_law_index() -> CorpusIndex:
    return _get("law_index", load_law_index)


def get_case_index() -> CorpusIndex | None:
    return _get(
        "case_index",
        lambda: load_case_index() if config.CASE_EMBEDDINGS_NPY_PATH.exists() else None,
    )


def get_summarizer() -> LinkSummarizer:
    return _get("summarizer", LinkSummarizer)


def _load_conflictos() -> pd.DataFrame:
    """Los pares possible_conflict confirmados por la re-verificacion de la Fase 3
    (criterio v2 por default — ver config.CLASSIFICATIONS_VERSION), con el texto de ambos
    fragmentos. Los textos se leen con un filtro isin sobre pyarrow.dataset — NUNCA cargar la
    columna `text` completa de embedding_fragments (regla de memoria del CLAUDE.md)."""
    import pyarrow.dataset as ds

    import pyarrow.parquet as pq

    base_cols = [
        "fragment_a_id", "fragment_b_id", "document_a_id", "document_b_id",
        "similarity_score", "final_label", "final_confidence", "final_explanation",
    ]
    schema_cols = set(pq.read_schema(config.CLASSIFICATIONS_PATH).names)
    cols = base_cols + (["escenario_conflicto"] if "escenario_conflicto" in schema_cols else [])
    cls = pd.read_parquet(config.CLASSIFICATIONS_PATH, columns=cols)
    if "escenario_conflicto" not in cls.columns:
        cls["escenario_conflicto"] = ""
    conflictos = cls[cls["final_label"] == "possible_conflict"].copy()
    frag_ids = list(set(conflictos["fragment_a_id"]) | set(conflictos["fragment_b_id"]))
    dataset = ds.dataset(config.EMBEDDING_FRAGMENTS_PATH)
    tabla = dataset.to_table(
        columns=["fragment_id", "text"], filter=ds.field("fragment_id").isin(frag_ids)
    )
    textos = dict(zip(tabla.column("fragment_id").to_pylist(), tabla.column("text").to_pylist()))
    conflictos["text_a"] = conflictos["fragment_a_id"].map(textos)
    conflictos["text_b"] = conflictos["fragment_b_id"].map(textos)
    return conflictos.sort_values("final_confidence", ascending=False)


def get_conflictos() -> pd.DataFrame:
    return _get("conflictos", _load_conflictos)


def append_feedback(row: dict) -> None:
    """Feedback 👍/👎 del chatbot: leer-concatenar-escribir bajo el lock global (mismo patron
    que el cache de LinkSummarizer). Volumen esperado: decenas de filas."""
    with _lock:
        if config.FEEDBACK_PATH.exists():
            df = pd.concat([pd.read_parquet(config.FEEDBACK_PATH), pd.DataFrame([row])], ignore_index=True)
        else:
            df = pd.DataFrame([row])
        config.FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(config.FEEDBACK_PATH, index=False)
