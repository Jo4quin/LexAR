"""Correccion best-effort del mojibake heredado del scrape de Infoleg/SAIJ, solo para display.

El texto fuente tiene acentos rotos (p. ej. "Decl?rase") que no afectan embeddings ni
clasificacion, pero son inaceptables en una interfaz para abogados. ftfy corrige lo corregible;
si no esta instalado, el texto pasa sin tocar (la app no debe romperse por esto).
"""
from __future__ import annotations

try:
    from ftfy import fix_text as _fix_text

    def fix_display_text(text: str) -> str:
        return _fix_text(str(text))
except ImportError:  # pragma: no cover
    def fix_display_text(text: str) -> str:
        return str(text)
