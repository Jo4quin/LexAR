"""Identidad visual compartida por las 3 paginas (Fase 7 + retoque UX 2026-07-09).

Antes de esto la app usaba el tema default de Streamlit sin ninguna paleta/tipografia propia
("se ve muy generica" fue el feedback). El tema base (colores) vive en `.streamlit/config.toml`;
este modulo agrega tipografia y componentes chicos (badges, cards) que Streamlit no soporta de
fabrica. `inject_css()` se llama una vez al principio de cada pagina.
"""
from __future__ import annotations

import streamlit as st

# Paleta: navy institucional + vino para jurisprudencia/alertas, sobre un fondo papel calido
# (coherente con .streamlit/config.toml). Un solo tema (no hay variante oscura): la app corre
# localmente y el toggle de tema de Streamlit queda deshabilitado al fijar [theme] en config.toml,
# asi que conviene comprometerse a un unico look bien resuelto en vez de uno a medias.
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
    --lx-paper: #f8f6f0;
    --lx-ink: #1c2536;
    --lx-primary: #1f3a5f;
    --lx-primary-soft: #e4ebf3;
    --lx-accent: #8a2332;
    --lx-accent-soft: #f4e3e6;
    --lx-muted: #6b7280;
    --lx-good: #1f6f4a;
    --lx-good-soft: #e1f0e8;
    --lx-bad: #9b2c2c;
    --lx-bad-soft: #fbe6e6;
    --lx-border: #ddd5c2;
}

/* Ojo: NO usar selectores tipo [class*="st-"] aca — los emotion-classnames internos de Streamlit
(incluidos los de los iconos Material) contienen "st-" y un font-family generico les rompe el icono
(termina mostrando el nombre del icono como texto plano en vez del glifo). Alcanza con heredar desde
html/body/.stApp. */
html, body, .stApp {
    font-family: 'IBM Plex Sans', -apple-system, sans-serif;
}

h1, h2, h3, h4, .stApp [data-testid="stHeading"] h1, .stApp [data-testid="stHeading"] h2 {
    font-family: 'Source Serif 4', Georgia, serif !important;
    color: var(--lx-ink);
    letter-spacing: -0.01em;
}

[data-testid="stMetricValue"], code, .lexar-num {
    font-family: 'IBM Plex Mono', 'Courier New', monospace;
    font-variant-numeric: tabular-nums;
}

/* Encabezado de pagina: un filete navy fino arriba de todo, como un membrete. */
[data-testid="stAppViewContainer"] > .main {
    border-top: 4px solid var(--lx-primary);
}

.stButton > button {
    border-radius: 6px;
    font-weight: 500;
}
.stButton > button[kind="primary"], .stButton > button:not([kind]) {
    background-color: var(--lx-primary);
    border-color: var(--lx-primary);
}

.stTextInput input, .stSelectbox [data-baseweb="select"] {
    border-radius: 6px;
}

.lexar-eyebrow {
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--lx-muted);
    margin-bottom: 0.15rem;
}

/* Badges: pills chicas para link_source / dominant_label / estado, en vez de emoji+texto plano. */
.lexar-badge {
    display: inline-block;
    padding: 0.12rem 0.55rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 500;
    line-height: 1.5;
    white-space: nowrap;
}
.lexar-badge--primary { background: var(--lx-primary-soft); color: var(--lx-primary); }
.lexar-badge--accent { background: var(--lx-accent-soft); color: var(--lx-accent); }
.lexar-badge--good { background: var(--lx-good-soft); color: var(--lx-good); }
.lexar-badge--bad { background: var(--lx-bad-soft); color: var(--lx-bad); }
.lexar-badge--muted { background: #eee9dc; color: var(--lx-muted); }

/* Cards de fallos CSJN: rail de color a la izquierda en vez de un container liso. */
.lexar-card {
    background: #fffdf8;
    border: 1px solid var(--lx-border);
    border-left: 4px solid var(--lx-accent);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.6rem;
}
.lexar-card__title {
    font-weight: 600;
    color: var(--lx-ink);
    margin-bottom: 0.15rem;
}
.lexar-card__meta {
    color: var(--lx-muted);
    font-size: 0.86rem;
}
.lexar-card__meta a {
    color: var(--lx-primary);
    font-weight: 500;
}

.lexar-disclaimer {
    background: var(--lx-primary-soft);
    border-left: 4px solid var(--lx-primary);
    border-radius: 6px;
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
