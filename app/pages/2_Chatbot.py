"""Chatbot jurídico: caso en lenguaje natural → leyes aplicables + fallos CSJN, con citas."""
from __future__ import annotations

import sys
from pathlib import Path

for _base in [Path(__file__).resolve().parent, *Path(__file__).resolve().parents]:
    if (_base / "src" / "lexar").exists():
        sys.path.insert(0, str(_base / "src"))
        break

import streamlit as st

from lexar import config
from lexar.chatbot import DISCLAIMER, answer_case
from lexar.retrieval import load_case_index, load_law_index
from lexar.textfix import fix_display_text

st.set_page_config(page_title="LexAR — Chatbot", page_icon="💬", layout="wide")
st.title("💬 Chatbot jurídico")
st.caption(DISCLAIMER)


@st.cache_resource(show_spinner="Cargando índices de búsqueda (una sola vez)…")
def load_indexes():
    law = load_law_index()
    case = load_case_index() if config.CASE_EMBEDDINGS_NPY_PATH.exists() else None
    return law, case


law_index, case_index = load_indexes()
if case_index is None:
    st.warning("Índice de fallos no disponible (correr la Fase 4). El chatbot responderá solo con leyes.")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for turn in st.session_state.chat_history:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])

case_text = st.chat_input("Planteá un caso, ej.: me chocaron el auto y el seguro no quiere pagar")
if case_text:
    st.session_state.chat_history.append({"role": "user", "content": case_text})
    with st.chat_message("user"):
        st.markdown(case_text)

    with st.chat_message("assistant"):
        with st.spinner("Reescribiendo la consulta, buscando normativa y fallos…"):
            try:
                result = answer_case(case_text, law_index, case_index)
            except Exception as exc:
                st.error(f"Error consultando el modelo: {exc}")
                st.stop()

        st.caption("Consultas jurídicas derivadas: " + " · ".join(result["consultas"]) + f" (materia: {result['materia']})")
        st.markdown(fix_display_text(result["respuesta_markdown"]))

        valid = sum(c["cita_valida"] for c in result["citas"])
        with st.expander(f"Citas textuales ({valid}/{len(result['citas'])} verificadas contra la fuente)"):
            for citation in result["citas"]:
                icon = "✅" if citation["cita_valida"] else "❌"
                st.markdown(f"{icon} `[{citation['fuente_id']}]` “{fix_display_text(citation['cita_textual'])}”")

        with st.expander("Leyes recuperadas"):
            st.dataframe(
                result["leyes"][["document_id", "titulo_resumido", "tipo_norma", "fecha_sancion", "score"]],
                use_container_width=True, hide_index=True,
            )
        if result["fallos"] is not None:
            with st.expander("Fallos CSJN recuperados"):
                st.dataframe(
                    result["fallos"][["case_id", "fecha", "actor", "demandado", "sobre", "score"]],
                    use_container_width=True, hide_index=True,
                )
        st.caption(result["disclaimer"])

    st.session_state.chat_history.append({"role": "assistant", "content": result["respuesta_markdown"]})
