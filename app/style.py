"""Identidad visual compartida por las 3 paginas (Fase 7 + 2 rondas de retoque UX 2026-07-09).

Primera ronda: paleta navy/vino "papel legal" — el feedback fue que se veia demasiado
conservadora/institucional, con mucho espacio en blanco y botones chicos. Segunda ronda (esta):
paleta azul profundo + acento turquesa mas "producto SaaS", mas densidad (menos padding
vertical default de Streamlit) y controles mas grandes. El tema base (colores de los widgets
nativos) vive en `.streamlit/config.toml`; este modulo agrega tipografia, densidad y componentes
chicos (badges, cards) que Streamlit no soporta de fabrica. `inject_css()` se llama una vez al
principio de cada pagina.
"""
from __future__ import annotations

import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@600;700;800&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
    --lx-paper: #f6f9fb;
    --lx-ink: #0f1b2d;
    --lx-primary: #0e7490;
    --lx-primary-soft: #e0f2f7;
    --lx-accent: #06b6d4;
    --lx-accent-soft: #e3f8fb;
    --lx-muted: #64748b;
    --lx-good: #15803d;
    --lx-good-soft: #e2f4e8;
    --lx-bad: #b91c1c;
    --lx-bad-soft: #fbe7e7;
    --lx-border: #dbe4ea;
}

/* Ojo: NO usar selectores tipo [class*="st-"] aca — los emotion-classnames internos de Streamlit
(incluidos los de los iconos Material) contienen "st-" y un font-family generico les rompe el icono
(termina mostrando el nombre del icono como texto plano en vez del glifo). Alcanza con heredar desde
html/body/.stApp. */
html, body, .stApp {
    font-family: 'Inter', -apple-system, sans-serif;
}

h1, h2, h3, h4, .stApp [data-testid="stHeading"] h1, .stApp [data-testid="stHeading"] h2 {
    font-family: 'Manrope', -apple-system, sans-serif !important;
    font-weight: 800 !important;
    color: var(--lx-ink);
    letter-spacing: -0.02em;
}

[data-testid="stMetricValue"], code, .lexar-num {
    font-family: 'IBM Plex Mono', 'Courier New', monospace;
    font-variant-numeric: tabular-nums;
}

/* Menos aire arriba/abajo y un ancho de lectura mas razonable: el padding default de Streamlit
(~6rem verticales sumando header+block-container) era la principal fuente del "mucho espacio en
blanco" reportado. */
.block-container {
    padding-top: 2.25rem;
    padding-bottom: 3rem;
    max-width: 1180px;
}
[data-testid="stVerticalBlock"] {
    gap: 0.6rem;
}

/* Encabezado de pagina: filete de acento arriba de todo, como un membrete de producto. */
[data-testid="stAppViewContainer"] > .main {
    border-top: 4px solid var(--lx-primary);
}

/* Botones mas grandes y con mas presencia — el feedback fue "botones chicos". */
.stButton > button {
    border-radius: 8px;
    font-weight: 600;
    padding: 0.55rem 1.35rem;
    font-size: 0.95rem;
    transition: transform 0.05s ease, box-shadow 0.15s ease;
}
.stButton > button[kind="primary"], .stButton > button:not([kind]) {
    background-color: var(--lx-primary);
    border-color: var(--lx-primary);
}
.stButton > button:hover {
    box-shadow: 0 2px 10px rgba(14, 116, 144, 0.25);
    transform: translateY(-1px);
}

.stTextInput input, .stSelectbox [data-baseweb="select"] {
    border-radius: 8px;
}
.stTextInput input {
    padding-top: 0.6rem;
    padding-bottom: 0.6rem;
}

.lexar-eyebrow {
    font-family: 'Inter', sans-serif;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--lx-accent);
    margin-bottom: 0.15rem;
}

/* Badges: pills chicas para link_source / dominant_label / estado, en vez de emoji+texto plano. */
.lexar-badge {
    display: inline-block;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    line-height: 1.5;
    white-space: nowrap;
}
.lexar-badge--primary { background: var(--lx-primary-soft); color: var(--lx-primary); }
.lexar-badge--accent { background: var(--lx-accent-soft); color: #0c7c93; }
.lexar-badge--good { background: var(--lx-good-soft); color: var(--lx-good); }
.lexar-badge--bad { background: var(--lx-bad-soft); color: var(--lx-bad); }
.lexar-badge--muted { background: #eef2f5; color: var(--lx-muted); }

/* Cards: fondo blanco con sombra suave en vez de un container liso — mas "producto", menos hoja
de papel. Rail de color a la izquierda para diferenciar de un card generico. */
.lexar-card {
    background: #ffffff;
    border: 1px solid var(--lx-border);
    border-left: 4px solid var(--lx-accent);
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin-bottom: 0.6rem;
    box-shadow: 0 1px 3px rgba(15, 27, 45, 0.06);
}
.lexar-card__title {
    font-weight: 700;
    color: var(--lx-ink);
    margin-bottom: 0.15rem;
}
.lexar-card__meta {
    color: var(--lx-muted);
    font-size: 0.86rem;
}
.lexar-card__meta a {
    color: var(--lx-primary);
    font-weight: 600;
}

.lexar-disclaimer {
    background: var(--lx-primary-soft);
    border-left: 4px solid var(--lx-primary);
    border-radius: 8px;
    padding: 0.6rem 0.9rem;
    color: var(--lx-ink);
    font-size: 0.88rem;
}

/* Nuestro <style> se inyecta via st.markdown y aterriza mas tarde en el DOM que el stylesheet
propio de Streamlit; con selectores de igual especificidad (una sola clase) el orden en el DOM
desempata, asi que sin esto nuestra fuente sans-serif termina pisando la de los iconos nativos
(el glifo de Material Symbols) y se ve el nombre del icono como texto plano en vez del glifo. */
[data-testid="stIconMaterial"] {
    font-family: "Material Symbols Rounded" !important;
}
</style>
"""

_BADGE_KIND_CLASS = {
    "primary": "lexar-badge--primary",
    "accent": "lexar-badge--accent",
    "good": "lexar-badge--good",
    "bad": "lexar-badge--bad",
    "muted": "lexar-badge--muted",
}


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def badge(text: str, kind: str = "muted") -> str:
    """HTML de una pill coloreada. `kind` in {primary, accent, good, bad, muted}."""
    css_class = _BADGE_KIND_CLASS.get(kind, "lexar-badge--muted")
    return f'<span class="lexar-badge {css_class}">{text}</span>'


def disclaimer_banner(text: str) -> None:
    st.markdown(f'<div class="lexar-disclaimer">⚖️ {text}</div>', unsafe_allow_html=True)
