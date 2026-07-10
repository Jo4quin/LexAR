"""Embeddings via Vertex AI (extraido de la Fase 2): batches concurrentes con rate limiting
adaptativo y checkpointing reanudable por content_hash."""
from __future__ import annotations

import gc
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from google import genai
from google.genai import types

from .config import EMBEDDING_DIM, EMBEDDING_MODEL, GCP_LOCATION, GCP_PROJECT
from .rate_limiter import AdaptiveRateLimiter

_client = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)
    return _client


def embed_batch_with_retry(
    texts: list[str],
    limiter: AdaptiveRateLimiter,
    max_retries: int = 6,
    base_delay: float = 5.0,
) -> list[np.ndarray]:
    client = get_client()
    for attempt in range(max_retries):
        limiter.wait_turn()
        try:
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type="SEMANTIC_SIMILARITY",
                    output_dimensionality=EMBEDDING_DIM,
                ),
            )
            limiter.report_success()
            return [np.array(e.values, dtype=np.float32) for e in response.embeddings]
        except Exception as exc:
            if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc):
                limiter.report_rate_limited()
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"Reintentando batch ({attempt + 1}/{max_retries}) tras error: {exc}. Espero {delay:.1f}s")
            time.sleep(delay)


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return matrix / norms


def embed_texts(texts: list[str], limiter: AdaptiveRateLimiter | None = None) -> np.ndarray:
    """Embeddings sincronicos para listas chicas (queries del chatbot). L2-normalizados,
    en el mismo espacio SEMANTIC_SIMILARITY que el corpus."""
    limiter = limiter or AdaptiveRateLimiter()
    vectors = embed_batch_with_retry(list(texts), limiter)
    return l2_normalize(np.vstack(vectors))


def load_embedding_checkpoint(checkpoint_dir: Path) -> set[str]:
    done: set[str] = set()
    for part_path in sorted(checkpoint_dir.glob("part_*.parquet")):
        done.update(pd.read_parquet(part_path, columns=["content_hash"])["content_hash"])
    return done


def _next_part_index(checkpoint_dir: Path) -> int:
    """Maximo indice existente + 1, no la CANTIDAD de archivos: si un checkpoint corrupto se
    borra a mano (deja un hueco en la numeracion), `len(glob(...))` reutiliza un numero ya usado
    y el siguiente `to_parquet` pisa un part file valido en silencio, perdiendo esos hashes sin
    ningun error. Con el maximo, un hueco nunca colisiona con un archivo existente."""
    indices = [int(p.stem.split("_")[1]) for p in checkpoint_dir.glob("part_*.parquet")]
    return max(indices, default=-1) + 1


def embed_corpus_checkpointed(
    fragments: pd.DataFrame,
    checkpoint_dir: Path,
    batch_size: int = 32,
    max_workers: int = 5,
    checkpoint_every: int = 20,
) -> int:
    """Embebe fragments (columnas content_hash + text, unicos por content_hash) reanudando
    desde checkpoints previos. Devuelve la cantidad de batches descartados tras agotar
    reintentos (0 = corrida completa)."""
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    limiter = AdaptiveRateLimiter()

    already = load_embedding_checkpoint(checkpoint_dir)
    pending = fragments[~fragments["content_hash"].isin(already)]
    print(f"{checkpoint_dir.name}: ya embebidos {len(already):,}, pendientes {len(pending):,}")
    if pending.empty:
        return 0

    batches = [pending.iloc[i:i + batch_size] for i in range(0, len(pending), batch_size)]
    next_part_index = _next_part_index(checkpoint_dir)
    buffer_hashes: list[str] = []
    buffer_vectors: list[np.ndarray] = []
    completed = failed = processed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(embed_batch_with_retry, b["text"].tolist(), limiter): b for b in batches}
        for future in as_completed(futures):
            batch = futures[future]
            try:
                vectors = future.result()
            except Exception as exc:
                failed += 1
                print(f"Batch descartado tras agotar reintentos ({failed} descartados). Error: {exc}")
                continue

            buffer_hashes.extend(batch["content_hash"].tolist())
            buffer_vectors.extend(vectors)
            completed += 1
            processed += len(batch)

            if completed % checkpoint_every == 0 or completed + failed == len(batches):
                if buffer_hashes:
                    part = pd.DataFrame({
                        "content_hash": buffer_hashes,
                        "embedding": [v.tolist() for v in buffer_vectors],
                    })
                    part.to_parquet(checkpoint_dir / f"part_{next_part_index:06d}.parquet", index=False)
                    next_part_index += 1
                    print(f"Checkpoint: {processed:,}/{len(pending):,} pendientes procesados, {failed} descartados")
                buffer_hashes, buffer_vectors = [], []

    if failed:
        print(f"{failed} batches quedaron pendientes. Volver a correr para reintentarlos.")
    return failed


def consolidate_embeddings(fragments: pd.DataFrame, checkpoint_dir: Path) -> np.ndarray:
    """Reconstruye la matriz de embeddings alineada 1:1 con fragments, leyendo los part files
    de a uno para acotar la memoria pico (mismo patron que la Fase 2). Devuelve la matriz
    L2-normalizada; falla si falta algun content_hash."""
    hash_to_index = {h: i for i, h in enumerate(fragments["content_hash"])}
    matrix = np.zeros((len(fragments), EMBEDDING_DIM), dtype=np.float32)
    filled = np.zeros(len(fragments), dtype=bool)

    for part_index, part_path in enumerate(sorted(checkpoint_dir.glob("part_*.parquet"))):
        part = pd.read_parquet(part_path)
        for h, vec in zip(part["content_hash"], part["embedding"]):
            idx = hash_to_index.get(h)
            if idx is not None and not filled[idx]:
                matrix[idx] = vec
                filled[idx] = True
        del part
        if part_index % 40 == 0:
            gc.collect()

    missing = int((~filled).sum())
    assert missing == 0, f"Faltan {missing} embeddings. Volver a correr embed_corpus_checkpointed."
    return l2_normalize(matrix)
