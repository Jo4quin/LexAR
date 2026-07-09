"""LexAR — Asistente Jurídico. Home: descripción del producto + estado de los datos."""
from __future__ import annotations

import sys
from pathlib import Path

for _base in [Path(__file__).resolve().parent, *Path(__file__).resolve().parents]:
    if (_base / "src" / "lexar").exists():
        sys.path.insert(0, str(_base / "src"))
        sys.path.insert(0, str(_base / "app"))
        break

import pyarrow.parquet as pq
import streamlit as st

from lexar import config
from style import badge, disclaimer_banner, inject_css

st.set_page_config(page_title="LexAR — Asistente Jurídico", page_icon="⚖️", layout="wide")
inject_css()

st.title("⚖️ LexAR — Asistente Jurídico")
st.markdown(
    """
Plataforma de asistencia a la investigación jurídica sobre **legislación nacional argentina**
(leyes y decreto-leyes, Infoleg + SAIJ) y **fallos de la Corte Suprema publicados en SAIJ desde 2020**.

- **📚 Explorador**: seleccioná una ley y mirá sus normas vinculadas (oficiales y semánticas),
  con un resumen generado por IA que explica cada relación, y los fallos CSJN relacionados.
- **💬 Chatbot**: planteá un caso en lenguaje natural ("me chocaron el auto") y recibí las
  leyes aplicables, normativa relacionada y fallos relevantes, con citas textuales verificadas.
"""
)
disclaimer_banner(
    "Esta herramienta asiste la investigación jurídica sobre un corpus acotado. "
    "No constituye asesoramiento legal."
)

st.subheader("Estado de los datos")


def _artifact_status(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "—"
    try:
        rows = f"{pq.read_metadata(path).num_rows:,}"
    except Exception:
        rows = "—"
    return True, rows


artifacts = [
    ("Fragmentos de leyes", config.EMBEDDING_FRAGMENTS_PATH, "Fase 2"),
    ("Pares candidatos", config.CANDIDATES_PATH, "Fase 2"),
    ("Clasificaciones", config.CLASSIFICATIONS_PATH, "Fase 3"),
    ("Fallos CSJN ≥2020", config.FALLOS_PATH, "Fase 4"),
    ("Fragmentos de fallos", config.CASE_FRAGMENTS_PATH, "Fase 4"),
    ("Vínculos ley↔fallo", config.LAW_CASE_LINKS_PATH, "Fase 4"),
    ("Vínculos entre normas", config.NORM_LINKS_PATH, "Fase 5"),
    ("Caché de resúmenes IA", config.LINK_SUMMARIES_PATH, "Fase 5 / app"),
]

grid_cols = st.columns(4)
for i, (label, path, phase) in enumerate(artifacts):
    ok, rows = _artifact_status(path)
    status_badge = badge("✅ listo", "good") if ok else badge("❌ falta", "bad")
    with grid_cols[i % 4]:
        st.markdown(
            f'<div class="lexar-card">'
            f'<div class="lexar-eyebrow">{phase}</div>'
            f'<div class="lexar-card__title">{label}</div>'
            f'<div class="lexar-card__meta lexar-num">{rows} filas</div>'
            f'<div style="margin-top:0.35rem">{status_badge}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

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
