"""Entorno Jinja2 compartido por todas las rutas, con los filtros propios de LexAR."""
from __future__ import annotations

from pathlib import Path

import markdown as _markdown
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from lexar.textfix import fix_display_text

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _fix(text: object) -> str:
    """Mojibake del corpus (ver textfix.py) — aplicar a todo texto que venga de los datos."""
    return fix_display_text(text) if isinstance(text, str) else ("" if text is None else str(text))


def _md(text: object) -> Markup:
    """respuesta_markdown del chatbot -> HTML. Markup para que el autoescape no lo re-escape;
    el contenido viene de nuestro propio LLM con schema estructurado, no de terceros."""
    return Markup(_markdown.markdown(_fix(text), extensions=["extra"]))


def _miles(n: object) -> str:
    """Separador de miles en convencion es-AR: 112.582, no 112,582."""
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


templates.env.filters["fix"] = _fix
templates.env.filters["md"] = _md
templates.env.filters["miles"] = _miles
