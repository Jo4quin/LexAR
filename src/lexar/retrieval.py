"""Indices FAISS sobre los embeddings de leyes (Fase 2) y de fallos CSJN (Fase 4).

Disenado para una maquina justa de RAM (este repo ya tuvo MemoryErrors, ver CLAUDE.md):
- la matriz .npy se abre con mmap y se agrega al indice por chunks;
- la columna `text` (la mas pesada del parquet de fragmentos) NO se carga en memoria — se lee
  por indice posicional via pyarrow.dataset.take() solo para los hits de cada busqueda.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import faiss
import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from .config import (
    CASE_EMBEDDINGS_NPY_PATH,
    CASE_FRAGMENTS_PATH,
    EMBEDDING_FRAGMENTS_PATH,
    EMBEDDINGS_NPY_PATH,
)

LAW_METADATA_COLUMNS = ["fragment_id", "document_id", "label", "titulo_resumido", "tipo_norma", "fecha_sancion"]
CASE_METADATA_COLUMNS = [
    "fragment_id", "case_id", "label", "fecha", "tipo_fallo", "actor", "demandado", "sobre", "url",
]


@dataclass
class CorpusIndex:
    """Metadata liviana en memoria + indice FAISS; el texto se lee de disco por busqueda."""

    fragments: pd.DataFrame
    index: faiss.IndexFlatIP
    fragments_path: Path
    _text_dataset: ds.Dataset = field(init=False, repr=False)

    def __post_init__(self):
        self._text_dataset = ds.dataset(self.fragments_path)

    def search(self, query_vectors: np.ndarray, top_k: int = 20) -> pd.DataFrame:
        """Vecinos por query. Devuelve metadata + `text` (leido de disco solo para los hits),
        `score` y `query_index`."""
        query_vectors = np.ascontiguousarray(query_vectors.astype(np.float32))
        if query_vectors.ndim == 1:
            query_vectors = query_vectors[None, :]
        scores, indices = self.index.search(query_vectors, min(top_k, len(self.fragments)))

        frames = []
        for qi in range(len(query_vectors)):
            valid = indices[qi] != -1
            hits = self.fragments.iloc[indices[qi][valid]].copy()
            hits["_row"] = indices[qi][valid]
            hits["score"] = scores[qi][valid]
            hits["query_index"] = qi
            frames.append(hits)
        if not frames:
            return self.fragments.iloc[0:0].copy()
        result = pd.concat(frames, ignore_index=True)

        rows = sorted(set(result["_row"].tolist()))
        texts = self._text_dataset.take(rows, columns=["text"]).column("text").to_pylist()
        text_by_row = dict(zip(rows, texts))
        result["text"] = result["_row"].map(text_by_row)
        return result.drop(columns="_row")


def build_index(embeddings: np.ndarray, chunk_rows: int = 20_000) -> faiss.IndexFlatIP:
    """Intenta un unico add() con toda la matriz (evita el costo de realloc+copy repetido que
    hace `IndexFlatCodes` al crecer su buffer interno en cada add()). Si la maquina esta
    demasiado justa de RAM para ese pico — este repo ya documenta MemoryErrors recurrentes en
    desarrollo, ver CLAUDE.md — cae a agregar de a chunks con gc.collect() entre medio; agregar
    de a partes no reduce el trabajo total de reallocacion pero sí el tamano de cada paso, lo
    que puede alcanzar cuando no hay un bloque contiguo grande libre por fragmentacion."""
    import gc

    embeddings = np.ascontiguousarray(embeddings, dtype=np.float32)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    try:
        index.add(embeddings)
        return index
    except MemoryError:
        pass

    index.reset()
    gc.collect()
    for start in range(0, len(embeddings), chunk_rows):
        index.add(embeddings[start:start + chunk_rows])
        gc.collect()
    return index


def _load_corpus(npy_path: Path, fragments_path: Path, columns: list[str]) -> CorpusIndex:
    assert npy_path.exists(), f"No existe {npy_path} — correr la fase que lo genera primero."
    assert fragments_path.exists(), f"No existe {fragments_path} — correr la fase que lo genera primero."
    embeddings = np.load(npy_path, mmap_mode="r")
    fragments = pd.read_parquet(fragments_path, columns=columns)
    assert len(fragments) == len(embeddings), (
        f"Desalineados: {len(fragments):,} fragmentos vs {len(embeddings):,} embeddings"
    )
    return CorpusIndex(fragments=fragments, index=build_index(embeddings), fragments_path=fragments_path)


def load_law_index() -> CorpusIndex:
    """Indice sobre los 112k fragmentos de leyes de la Fase 2."""
    return _load_corpus(EMBEDDINGS_NPY_PATH, EMBEDDING_FRAGMENTS_PATH, LAW_METADATA_COLUMNS)


def load_case_index() -> CorpusIndex:
    """Indice sobre los fragmentos de fallos CSJN de la Fase 4."""
    return _load_corpus(CASE_EMBEDDINGS_NPY_PATH, CASE_FRAGMENTS_PATH, CASE_METADATA_COLUMNS)


def aggregate_hits_by_document(hits: pd.DataFrame, id_col: str = "document_id") -> pd.DataFrame:
    """Colapsa hits a nivel documento: score maximo, cantidad de fragmentos y mejor fragmento."""
    if hits.empty:
        return hits
    best = hits.sort_values("score", ascending=False).drop_duplicates(id_col)
    counts = hits.groupby(id_col).size().rename("n_hits")
    return best.merge(counts, on=id_col).sort_values("score", ascending=False).reset_index(drop=True)
