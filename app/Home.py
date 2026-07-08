"""LexAR — Asistente Jurídico. Home: descripción del producto + estado de los datos."""
from __future__ import annotations

import sys
from pathlib import Path

for _base in [Path(__file__).resolve().parent, *Path(__file__).resolve().parents]:
    if (_base / "src" / "lexar").exists():
        sys.path.insert(0, str(_base / "src"))
        break

import pyarrow.parquet as pq
import streamlit as st

from lexar import config

st.set_page_config(page_title="LexAR — Asistente Jurídico", page_icon="⚖️", layout="wide")

st.title("⚖️ LexAR — Asistente Jurídico")
st.markdown(
    """
Plataforma de asistencia a la investigación jurídica sobre **legislación nacional argentina**
(leyes y decreto-leyes, Infoleg + SAIJ) y **fallos de la Corte Suprema publicados en SAIJ desde 2020**.

- **📚 Explorador**: seleccioná una ley y mirá sus normas vinculadas (oficiales y semánticas),
  con un resumen generado por IA que explica cada relación, y los fallos CSJN relacionados.
- **💬 Chatbot**: planteá un caso en lenguaje natural ("me chocaron el auto") y recibí las
  leyes aplicables, normativa relacionada y fallos relevantes, con citas textuales verificadas.

> ⚠️ Esta herramienta asiste la investigación jurídica sobre un corpus acotado.
> **No constituye asesoramiento legal.**
"""
)

st.subheader("Estado de los datos")


def _artifact_row(label: str, path: Path) -> dict:
    if not path.exists():
        return {"Artefacto": label, "Estado": "❌ falta", "Filas": "—", "Generado por": ""}
    try:
        rows = f"{pq.read_metadata(path).num_rows:,}"
    except Exception:
        rows = "—"
    return {"Artefacto": label, "Estado": "✅", "Filas": rows, "Generado por": ""}


rows = [
    _artifact_row("Fragmentos de leyes (embedding_fragments)", config.EMBEDDING_FRAGMENTS_PATH) | {"Generado por": "Fase 2"},
    _artifact_row("Pares candidatos (analysis_candidates)", config.CANDIDATES_PATH) | {"Generado por": "Fase 2"},
    _artifact_row("Clasificaciones (candidate_classifications)", config.CLASSIFICATIONS_PATH) | {"Generado por": "Fase 3"},
    _artifact_row("Fallos CSJN ≥2020 (fallos_csjn)", config.FALLOS_PATH) | {"Generado por": "Fase 4"},
    _artifact_row("Fragmentos de fallos (case_fragments)", config.CASE_FRAGMENTS_PATH) | {"Generado por": "Fase 4"},
    _artifact_row("Vínculos ley↔fallo (law_case_links)", config.LAW_CASE_LINKS_PATH) | {"Generado por": "Fase 4"},
    _artifact_row("Vínculos entre normas (norm_links)", config.NORM_LINKS_PATH) | {"Generado por": "Fase 5"},
    _artifact_row("Caché de resúmenes IA (link_summaries)", config.LINK_SUMMARIES_PATH) | {"Generado por": "Fase 5 / app"},
]
st.dataframe(rows, use_container_width=True, hide_index=True)

missing_npy = [p for p in (config.EMBEDDINGS_NPY_PATH, config.CASE_EMBEDDINGS_NPY_PATH) if not p.exists()]
if missing_npy:
    st.warning("Faltan matrices de embeddings: " + ", ".join(str(p) for p in missing_npy))
else:
    st.success("Embeddings de leyes y de fallos disponibles — el chatbot puede buscar en ambos corpus.")

st.caption(
    "Cobertura: 8.887 de 30.061 leyes con texto completo (29,6%); fallos limitados a la selección "
    "que SAIJ publica de la CSJN (~100–250 por año). Corpus solo nacional: sin decretos comunes, "
    "resoluciones ni normativa provincial."
)
