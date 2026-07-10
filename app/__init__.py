"""Capa web de LexAR (FastAPI + HTMX + Tailwind).

Resuelve `src/` en sys.path al importar el paquete, igual que lo hacian las paginas de
Streamlit y los notebooks: se camina hacia arriba desde este archivo hasta encontrar
`src/lexar`, asi `uvicorn app.main:app` funciona desde la raiz del repo o de un worktree.
"""
from __future__ import annotations

import sys
from pathlib import Path

for _base in [Path(__file__).resolve().parent, *Path(__file__).resolve().parents]:
    if (_base / "src" / "lexar").exists():
        _src = str(_base / "src")
        if _src not in sys.path:
            sys.path.insert(0, _src)
        break
