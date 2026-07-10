"""Estado de vigencia de una norma a partir del campo `observaciones` de documents.csv.

InfoLeg anota la derogacion/abrogacion en texto libre dentro de `observaciones`, p.ej.:
    "<b>ABROGADA</b> POR EL ARTICULO 48 DE LA LEY 27801"
    "ABROGADA POR ART. 11 DE LA LEY Nº 23966. RESTABLECIDA VIGENCIA POR ART. 1º ..."  -> en vigor
    "DEROGADA, CON EXCEPCION DEL ARTICULO 10, POR EL ARTICULO 9° ..."                 -> parcial

Es la unica senal de vigencia disponible: `relation_type` en relations.csv es siempre "modifies"
(no distingue derogacion). Se usa para (1) marcar la ley derogada en la UI y (2) avisarle al
chatbot que no use el criterio de una ley que ya no rige (ver src/lexar/chatbot.py).
"""
from __future__ import annotations

import re

from lexar.textfix import fix_display_text

_TAG_RE = re.compile(r"<[^>]+>")          # <b>, <a href=...>, etc.
_WS_RE = re.compile(r"\s+")
_DETALLE_MAX = 180


def _limpiar(observaciones: str) -> str:
    """Quita HTML y normaliza espacios; des-mojibakea para mostrar."""
    txt = _TAG_RE.sub(" ", observaciones or "")
    txt = fix_display_text(txt)
    return _WS_RE.sub(" ", txt).strip()


def estado_vigencia(observaciones: object) -> dict:
    """{'estado': 'derogada' | 'parcialmente derogada' | '', 'detalle': str}.

    `estado == ''` = sin senal de derogacion (NO afirmamos vigencia positiva: `observaciones`
    vacio no la garantiza). El sello/aviso solo aparece cuando hay derogacion detectada."""
    texto = _limpiar(str(observaciones or ""))
    up = texto.upper()
    derogada = "ABROG" in up or "DEROG" in up
    # "RESTABLECIDA VIGENCIA" revierte una derogacion previa: la norma esta en vigor.
    restablecida = "RESTABLEC" in up
    if not derogada or restablecida:
        return {"estado": "", "detalle": ""}
    parcial = "EXCEP" in up  # "DEROGADA, CON EXCEPCION DEL ARTICULO ..."
    return {
        "estado": "parcialmente derogada" if parcial else "derogada",
        "detalle": texto[:_DETALLE_MAX],
    }
