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

_lock = threading.Lock()
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
