"""Indices FAISS sobre los embeddings de leyes (Fase 2) y de fallos CSJN (Fase 4)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np
import pandas as pd

from .config import (
    CASE_EMBEDDINGS_NPY_PATH,
    CASE_FRAGMENTS_PATH,
    EMBEDDING_FRAGMENTS_PATH,
    EMBEDDINGS_NPY_PATH,
)


@dataclass
class CorpusIndex:
    """Embeddings L2-normalizados + metadata alineada 1:1 + indice FAISS de coseno exacto."""

    fragments: pd.DataFrame
    embeddings: np.ndarray
    index: faiss.IndexFlatIP

    def search(self, query_vectors: np.ndarray, top_k: int = 20) -> pd.DataFrame:
        """Vecinos por query. Devuelve la metadata de los fragmentos con `score` y `query_index`."""
        query_vectors = np.ascontiguousarray(query_vectors.astype(np.float32))
        if query_vectors.ndim == 1:
            query_vectors = query_vectors[None, :]
        scores, indices = self.index.search(query_vectors, min(top_k, len(self.fragments)))

        frames = []
        for qi in range(len(query_vectors)):
            valid = indices[qi] != -1
            hits = self.fragments.iloc[indices[qi][valid]].copy()
            hits["score"] = scores[qi][valid]
            hits["query_index"] = qi
            frames.append(hits)
        return pd.concat(frames, ignore_index=True) if frames else self.fragments.iloc[0:0].copy()


def build_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    embeddings = np.ascontiguousarray(embeddings.astype(np.float32))
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    return index


def _load_corpus(npy_path: Path, fragments_path: Path, columns: list[str] | None = None) -> CorpusIndex:
    assert npy_path.exists(), f"No existe {npy_path} — correr la fase que lo genera primero."
    assert fragments_path.exists(), f"No existe {fragments_path} — correr la fase que lo genera primero."
    embeddings = np.load(npy_path)
    fragments = pd.read_parquet(fragments_path, columns=columns)
    assert len(fragments) == len(embeddings), (
        f"Desalineados: {len(fragments):,} fragmentos vs {len(embeddings):,} embeddings"
    )
    return CorpusIndex(fragments=fragments, embeddings=embeddings, index=build_index(embeddings))


def load_law_index() -> CorpusIndex:
    """Indice sobre los 112k fragmentos de leyes de la Fase 2."""
    return _load_corpus(
        EMBEDDINGS_NPY_PATH,
        EMBEDDING_FRAGMENTS_PATH,
        columns=["fragment_id", "document_id", "label", "titulo_resumido", "tipo_norma", "fecha_sancion", "text"],
    )


def load_case_index() -> CorpusIndex:
    """Indice sobre los fragmentos de fallos CSJN de la Fase 4."""
    return _load_corpus(CASE_EMBEDDINGS_NPY_PATH, CASE_FRAGMENTS_PATH)


def aggregate_hits_by_document(hits: pd.DataFrame, id_col: str = "document_id") -> pd.DataFrame:
    """Colapsa hits a nivel documento: score maximo, cantidad de fragmentos y mejor fragmento."""
    if hits.empty:
        return hits
    best = hits.sort_values("score", ascending=False).drop_duplicates(id_col)
    counts = hits.groupby(id_col).size().rename("n_hits")
    return best.merge(counts, on=id_col).sort_values("score", ascending=False).reset_index(drop=True)
