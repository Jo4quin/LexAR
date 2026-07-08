"""Explorador de leyes: ficha de la norma, normas vinculadas con resumen IA, fallos CSJN."""
from __future__ import annotations

import json
import sys
from pathlib import Path

for _base in [Path(__file__).resolve().parent, *Path(__file__).resolve().parents]:
    if (_base / "src" / "lexar").exists():
        sys.path.insert(0, str(_base / "src"))
        break

import pandas as pd
import streamlit as st

from lexar import config
from lexar.links import count_later_modifications, links_for_document, load_norm_links
from lexar.summaries import LinkSummarizer
from lexar.textfix import fix_display_text

st.set_page_config(page_title="LexAR — Explorador", page_icon="📚", layout="wide")
st.title("📚 Explorador de leyes")


@st.cache_resource(show_spinner="Cargando corpus…")
def load_data():
    documents = pd.read_csv(config.DOCUMENTS_PATH, dtype=str, keep_default_na=False)
    norm_links = load_norm_links()
    texts = pd.read_parquet(
        config.TEXT_VERSIONS_PATH, columns=["document_id", "full_text"]
    ).drop_duplicates("document_id").set_index("document_id")["full_text"]
    law_case_links = (
        pd.read_parquet(config.LAW_CASE_LINKS_PATH) if config.LAW_CASE_LINKS_PATH.exists() else None
    )
    fallos = pd.read_parquet(config.FALLOS_PATH) if config.FALLOS_PATH.exists() else None
    return documents, norm_links, texts, law_case_links, fallos


@st.cache_resource(show_spinner="Preparando generador de resúmenes…")
def load_summarizer() -> LinkSummarizer:
    return LinkSummarizer()


documents, norm_links, texts, law_case_links, fallos = load_data()
titles = documents.set_index("document_id")["titulo_resumido"]

query = st.text_input("Buscar norma por título o id (ej: defensa del consumidor, infoleg:638)")
if not query:
    st.info("Escribí parte del título de una norma para empezar.")
    st.stop()

mask = (
    documents["titulo_resumido"].str.contains(query, case=False, na=False)
    | documents["titulo_sumario"].str.contains(query, case=False, na=False)
    | documents["texto_resumido"].str.contains(query, case=False, na=False)
    | (documents["document_id"] == query.strip())
)
matches = documents[mask].head(50)
if matches.empty:
    st.warning("No se encontraron normas para esa búsqueda.")
    st.stop()

options = {
    f"{row['titulo_resumido'][:90]} — {row['tipo_norma']} ({row['fecha_sancion']}) [{row['document_id']}]": row["document_id"]
    for _, row in matches.iterrows()
}
selected = st.selectbox(f"Resultados ({len(matches)}):", list(options))
document_id = options[selected]
doc = documents.set_index("document_id").loc[document_id]

st.divider()
st.header(fix_display_text(doc["titulo_resumido"]))
meta_cols = st.columns(4)
meta_cols[0].metric("Tipo", doc["tipo_norma"])
meta_cols[1].metric("Sanción", doc["fecha_sancion"] or "s/d")
meta_cols[2].metric("Boletín", doc["fecha_boletin"] or "s/d")
meta_cols[3].metric("Id", document_id)

n_mods = count_later_modifications(norm_links, document_id)
if n_mods:
    st.warning(
        f"⚠️ Esta norma tiene **{n_mods} modificaciones posteriores** registradas en Infoleg. "
        "El texto mostrado puede no reflejar la versión vigente."
    )

if doc.get("texto_resumido"):
    st.markdown(f"*{fix_display_text(doc['texto_resumido'])}*")

full_text = texts.get(document_id)
if isinstance(full_text, str) and full_text.strip():
    with st.expander(f"Texto completo ({len(full_text):,} caracteres)"):
        st.text(fix_display_text(full_text[:50_000]))
else:
    st.caption("Sin texto completo disponible en el corpus (cobertura: 29,6% de las normas).")

# --- Normas vinculadas -------------------------------------------------------------------
st.subheader("Normas vinculadas")
links = links_for_document(norm_links, document_id)
if links.empty:
    st.info("Sin vínculos registrados para esta norma.")
else:
    SOURCE_BADGE = {"official": "🏛️ oficial", "semantic": "🧠 semántico", "both": "🏛️🧠 ambos"}
    table = links.copy()
    table["titulo"] = table["other_document_id"].map(titles).map(fix_display_text)
    table["vinculo"] = table["link_source"].map(SOURCE_BADGE)
    st.dataframe(
        table[["other_document_id", "titulo", "vinculo", "dominant_label", "direccion_oficial", "max_similarity"]]
        .rename(columns={
            "other_document_id": "norma", "dominant_label": "relación (Fase 3)",
            "direccion_oficial": "dirección oficial", "max_similarity": "similitud",
        }),
        use_container_width=True, hide_index=True,
    )

    link_options = {
        f"{fix_display_text(str(titles.get(r['other_document_id'], r['other_document_id'])))[:80]} "
        f"[{r['other_document_id']}]": r
        for _, r in links.head(30).iterrows()
    }
    chosen = st.selectbox("Elegí un vínculo para explicarlo con IA:", list(link_options))
    if st.button("🧾 Explicar relación (IA)"):
        link_row = link_options[chosen]
        with st.spinner("Generando resumen (la primera vez llama al modelo; después sale del caché)…"):
            summary = load_summarizer().summarize(document_id, link_row["other_document_id"], link_row)
        cache_note = "desde caché" if summary["from_cache"] else "recién generado"
        st.success(f"Resumen ({cache_note}, modelo {summary.get('model', '')})")
        st.markdown(f"**Relación:** {summary['relacion']}")
        st.markdown(f"**Relevancia jurídica:** {summary['relevancia_juridica']}")
        if summary.get("evidencia_a"):
            st.markdown(f"> Norma A: “{fix_display_text(summary['evidencia_a'])}”")
        if summary.get("evidencia_b"):
            st.markdown(f"> Norma B: “{fix_display_text(summary['evidencia_b'])}”")

# --- Fallos CSJN relacionados ------------------------------------------------------------
st.subheader("Fallos CSJN relacionados (SAIJ, 2020 → hoy)")
if law_case_links is None or fallos is None:
    st.info("Todavía no se corrió la Fase 4 (jurisprudencia). Ver `notebooks/Jurisprudencia_CSJN.ipynb`.")
else:
    related = law_case_links[law_case_links["document_id"] == document_id].head(10)
    if related.empty:
        st.info("Sin fallos relacionados por encima del umbral de similitud.")
    else:
        fallos_meta = fallos.set_index("case_id")
        for _, r in related.iterrows():
            f = fallos_meta.loc[r["case_id"]]
            caratula = fix_display_text(f"{f['actor']} c/ {f['demandado']} s/ {f['sobre']}")
            with st.container(border=True):
                st.markdown(
                    f"**{caratula[:160]}**  \n"
                    f"{f['tipo_fallo']} · {f['fecha']} · similitud {r['max_similarity']:.3f}"
                    + (f" · [ver en SAIJ]({f['url']})" if f.get("url") else "")
                )
