"""Rutas y constantes del proyecto.

ROOT se resuelve buscando el directorio que contiene `data/lexar_datos_infoleg_saij` hacia
arriba desde el cwd y desde este archivo — funciona lanzando desde la raiz del repo, desde
notebooks/ o desde un worktree en .claude/worktrees/ (los datos y outputs viven en el checkout
principal y se comparten). Override explicito via la variable de entorno LEXAR_ROOT.
"""
from __future__ import annotations

import os
from pathlib import Path


def _find_root() -> Path:
    env = os.environ.get("LEXAR_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    candidates = [Path.cwd(), *Path.cwd().parents, here.parent, *here.parents]
    for base in candidates:
        if (base / "data" / "lexar_datos_infoleg_saij").exists():
            return base
    for base in candidates:
        if (base / "outputs").exists():
            return base
    return Path.cwd()


ROOT = _find_root()

DATASET_DIR = ROOT / "data" / "lexar_datos_infoleg_saij"
TEXT_VERSIONS_PATH = DATASET_DIR / "corpus_unificado" / "text_versions.parquet"
DOCUMENTS_PATH = DATASET_DIR / "infoleg" / "procesado" / "documents.csv"
RELATIONS_PATH = DATASET_DIR / "infoleg" / "procesado" / "relations.csv"

OUTPUT_DIR = ROOT / "outputs"
EMBEDDINGS_NPY_PATH = OUTPUT_DIR / "embeddings.npy"
EMBEDDING_FRAGMENTS_PATH = OUTPUT_DIR / "embedding_fragments.parquet"
CANDIDATES_PATH = OUTPUT_DIR / "analysis_candidates.parquet"

# Criterio de clasificacion de conflictos servido por la app. "v1" = verificacion original de la
# Fase 3 (candidate_classifications.parquet); "v2" = re-verificacion con contexto de norma completa
# y test de "instrumentos paralelos" (candidate_classifications_v2.parquet) — ver
# notebooks/Reverificacion_Conflictos.ipynb. v1 nunca se sobreescribe: volver a "v1" alcanza para
# revertir sin re-correr nada.
CLASSIFICATIONS_VERSION = os.environ.get("LEXAR_CLASSIFICATIONS_VERSION", "v2")
_CLASSIFICATIONS_SUFFIX = "" if CLASSIFICATIONS_VERSION == "v1" else f"_{CLASSIFICATIONS_VERSION}"
CLASSIFICATIONS_PATH = OUTPUT_DIR / f"candidate_classifications{_CLASSIFICATIONS_SUFFIX}.parquet"

# Fase 4 — jurisprudencia CSJN.
JURIS_DATA_DIR = ROOT / "data" / "jurisprudencia_csjn"
FALLOS_PATH = JURIS_DATA_DIR / "fallos_csjn.parquet"
JURIS_OUTPUT_DIR = OUTPUT_DIR / "jurisprudencia"
CASE_FRAGMENTS_PATH = JURIS_OUTPUT_DIR / "case_fragments.parquet"
CASE_EMBEDDINGS_NPY_PATH = JURIS_OUTPUT_DIR / "case_embeddings.npy"
LAW_CASE_LINKS_PATH = JURIS_OUTPUT_DIR / "law_case_links.parquet"

# Fase 5 — vinculos entre normas. Sigue a CLASSIFICATIONS_VERSION (dominant_label depende de
# candidate_classifications).
NORM_LINKS_PATH = OUTPUT_DIR / f"norm_links{_CLASSIFICATIONS_SUFFIX}.parquet"
LINK_SUMMARIES_PATH = OUTPUT_DIR / "link_summaries.parquet"

# Feedback de la app (👍/👎 por respuesta del chatbot).
FEEDBACK_PATH = OUTPUT_DIR / "feedback_chatbot.parquet"

# Fase 6/8 — chatbot y evaluacion.
# REPO_DIR es la raiz del checkout que contiene este codigo (worktree incluido) — para archivos
# versionados en git, a diferencia de ROOT que apunta a donde viven data/ y outputs/ compartidos.
REPO_DIR = Path(__file__).resolve().parents[2]
CASOS_PRUEBA_PATH = REPO_DIR / "eval" / "casos_prueba.csv"
EVAL_DIR = OUTPUT_DIR / "eval"

# Vertex AI: mismo proyecto y auth ADC configurados en la Fase 2 (ver CLAUDE.md).
GCP_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "lexar-501717")
GCP_LOCATION = "us-central1"
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768  # truncado via Matryoshka Representation Learning (maximo nativo: 3072)
SUMMARY_MODEL = "gemini-2.5-flash-lite"
CHAT_MODEL = "gemini-2.5-flash"

# Segmentacion (mismos valores que la Fase 1).
MIN_FRAGMENT_CHARS = 80
MAX_FRAGMENT_CHARS = 2_500
CHUNK_OVERLAP_CHARS = 250

# Umbral de similitud heredado de la Fase 2 (percentil 90 sobre 679.720 pares).
SIMILARITY_THRESHOLD = 0.957

RANDOM_SEED = 42
