# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Branch policy

All work happens on the `Lucaspini01` branch. Do not commit or push to `main` unless the user explicitly
asks for it in that specific instance — a prior approval does not carry over to later requests. Before
committing, confirm the current branch is `Lucaspini01` (or another branch the user explicitly named);
if you're on `main`, switch to `Lucaspini01` first (creating it from `main` if it doesn't exist yet)
rather than committing there.

## What this is

LexAR is an academic NLP project (Procesamiento de Lenguaje Natural coursework) that builds a searchable
knowledge base from Argentine national legislation and uses it to surface likely redundancies,
contradictions, or overlaps between laws. A planned second phase layers a legal-assistant use case
(drafting/reviewing legal writing with citations) on top of the same corpus — not yet started.

The full project brief, data sources, phased plan, and evaluation strategy live in `README.md` — read it
before making architectural changes; it is the source of truth for scope and is written in Spanish.

## Repository state

This repo currently contains only two tracked files:

- `README.md` — project description, data sources, pipeline design, phased plan (Fases 1-5).
- `Redundancias&Contradicciones.ipynb` — the only code, implementing Fases 1 and 2 of the plan.

There is no package manifest (`requirements.txt`/`pyproject.toml`), no test suite, and no lint config.
Dependencies are installed ad hoc from within the notebook.

## Required local data (not tracked in git)

The notebook expects a dataset snapshot directory at the repo root that is **not committed**:

```
lexar_dataset_2026-06-25/data/processed/text_corpus/text_versions.parquet
lexar_dataset_2026-06-25/data/processed/infoleg_laws/documents.csv
lexar_dataset_2026-06-25/data/processed/infoleg_laws/relations.csv
```

The config cell asserts `TEXT_VERSIONS_PATH` and `DOCUMENTS_PATH` exist and will raise if this snapshot
isn't present alongside the notebook. Per the README, `text_versions.parquet` is the preferred starting
point over the alternate `lexar_datos_infoleg_saij/` package (better full-text coverage).

## Running the notebook

```bash
pip install pandas pyarrow numpy
jupyter notebook "Redundancias&Contradicciones.ipynb"
```

`pyarrow` is required to read the `.parquet` corpus file; the notebook raises a clear `RuntimeError` at
import time if it's missing. Optional API-based embeddings (commented out by default, to avoid accidental
cost) additionally need `pip install openai` and an `OPENAI_API_KEY`.

Outputs are written to `outputs/` (created automatically):
- `outputs/legal_fragments_sample.csv` — segmented fragments from Fase 1.
- `outputs/analysis_candidates_sample.csv` — nearest-neighbor candidate pairs from Fase 2.

## Notebook architecture (Fases 1 & 2)

The notebook is a linear pipeline, driven by constants in the config cell near the top
(`MAX_TEXT_VERSIONS`, `MAX_FRAGMENTS_FOR_EMBEDDINGS`, segmentation size thresholds, `N_HASH_FEATURES`,
`TOP_K_NEIGHBORS`, `SIMILARITY_THRESHOLD_FOR_CLUSTERS`, `RANDOM_SEED`). Raise the `MAX_*` sample sizes
gradually to scale from a quick smoke test to the full corpus.

1. **Fase 1 — Consolidacion de datos**: loads `text_versions.parquet`, joins it with `documents.csv`
   metadata on `document_id`, optionally samples down to `MAX_TEXT_VERSIONS` rows.
2. **Segmentacion**: `segment_text_version()` looks for `ARTICULO <n>` headers via `ARTICLE_PATTERN`
   (a normalized, accent-stripped regex match). If 2+ article headers are found, the text is split by
   article, with long articles (> `MAX_FRAGMENT_CHARS`) further split into overlapping chunks via
   `chunk_text()`. If fewer than 2 article headers are found, the whole text falls back to
   `chunk_text()` directly. Every fragment gets a `content_hash` (sha256) and a `fragment_id`
   (`frag:%08d`). This is the `legal_fragments` table from the README's schema.
3. **Fase 2 — Embeddings**: `hashing_embeddings()` is a from-scratch, dependency-free TF-IDF-like
   baseline (token hashing into `N_HASH_FEATURES` buckets + IDF weighting + L2 normalization) — chosen
   for offline reproducibility, not quality. A commented-out OpenAI `text-embedding-3-small` alternative
   (`openai_embeddings()`) is left in place as a drop-in replacement.
4. **Retrieval**: `top_neighbors()` computes blockwise cosine similarity (embeddings are pre-normalized,
   so it's a plain dot product), explicitly excludes self-matches and same-`document_id` pairs (to avoid
   trivial intra-document hits), and keeps the top-`TOP_K_NEIGHBORS` per fragment. Pairs are deduplicated
   via a sorted `pair_key`. This produces the `analysis_candidates` table from the README's schema.
5. **Clusters exploratorios**: `connected_components_from_candidates()` does a simple BFS over an
   adjacency graph built from candidate pairs above `SIMILARITY_THRESHOLD_FOR_CLUSTERS` — a rough,
   non-final grouping meant only for manual inspection of related fragments.

## Where this is headed (not yet implemented)

Per the README's phased plan, the next phases build on `outputs/analysis_candidates_sample.csv`:

- **Fase 3**: classify each candidate pair with an LLM/rules into one of
  `possible_conflict | possible_overlap | possible_modification | different_scope | neutral | needs_review`,
  storing label, confidence, explanation, cited fragments, model, and prompt version.
- **Fase 4**: for conflict/overlap cases, generate an alternative redaction proposal that cites the
  fragments it's based on.
- **Fase 5**: report and demo.

When implementing these, follow the field/table names already specified in the README rather than
inventing new ones, since Fases 1-2 already establish `fragment_id`, `document_id`, `candidate_id`,
`pair_key`, etc. as the shared keys new code should join against.
