"""Componedor unico de titulos de norma para toda la app.

El dato crudo de InfoLeg reparte la identidad de una ley en varios campos y ninguno sirve
solo como titulo:
  - `titulo_resumido`: etiqueta generica del subtipo/accion ("REGIMEN LEGAL", "DISPOSICIONES",
    "LEY Nº 24240 - MODIFICACION"); vacia en ~14% de las normas.
  - `titulo_sumario`:  el tema real ("DEFENSA DEL CONSUMIDOR", "REGIMEN PENAL JUVENIL");
    vacio en ~6%.
  - `texto_resumido`:  resumen largo del contenido (casi nunca vacio).
  - `numero_norma`:    el numero real de la ley (24240), en document_identifiers.csv.

`componer_titulo()` los combina en un unico string legible:
    "Ley 24.240 — Defensa del Consumidor"
    "Ley 27.250 — Defensa del Consumidor · modificación"   (para distinguir de la original)
    "Ley 27.801 — Régimen Penal Juvenil"

Todo se usa via `state.get_titles()`, asi que cambiar esto propaga el titulo nuevo a busqueda,
ficha, normas vinculadas, grafo, resumen IA y Hallazgos sin tocar cada call site.
"""
from __future__ import annotations

from lexar.textfix import fix_display_text

# Conectores que van en minuscula en un titulo es-AR (salvo como primera palabra).
_MINUSCULAS = {
    "de", "del", "la", "el", "los", "las", "y", "e", "o", "u",
    "en", "a", "por", "para", "con", "al", "un", "una",
}
# Siglas que deben quedar en mayuscula. No se pueden detectar por el case del origen: TODO el
# texto de InfoLeg viene en mayuscula, asi que sin whitelist "AGUA" pareceria una sigla.
_SIGLAS = {
    "PEN", "IVA", "AFIP", "ANSES", "IGJ", "CSJN", "BCRA", "INSSJP", "IOSFA",
    "PYME", "PYMES", "IPS", "SA", "SRL", "ART", "IOMA", "UBA", "YPF", "DNI", "CABA",
}
_TEMA_MAX = 90


def formato_numero(numero: object) -> str:
    """'24240' -> '24.240' (separador de miles es-AR). 'S/N'/vacio/no-numerico -> 'S/N'."""
    s = str(numero or "").strip()
    if not s or not s.isdigit():
        return "S/N"
    return f"{int(s):,}".replace(",", ".")


def title_case_es(texto: str) -> str:
    """Title case legible: capitaliza cada palabra salvo los conectores, deja intactos los
    tokens con digitos o siglas (ya en mayuscula, <=4 letras: PEN, IVA, AFIP, ANSES)."""
    palabras = texto.split()
    out = []
    for i, w in enumerate(palabras):
        low = w.lower()
        if any(c.isdigit() for c in w):
            out.append(w)                       # numeros, "24240", "art.4"
        elif w.upper() in _SIGLAS:
            out.append(w.upper())               # siglas conocidas: PEN, IVA, AFIP
        elif i != 0 and low in _MINUSCULAS:
            out.append(low)                      # conectores (salvo primera palabra)
        else:
            out.append(low.capitalize())
    return " ".join(out)


def _es_modificacion(row) -> bool:
    campos = f"{row.get('titulo_resumido', '')} {row.get('texto_resumido', '')}".upper()
    return "MODIFICAC" in campos


def _tema(row) -> str:
    """El descriptor mas informativo disponible, ya des-mojibakeado."""
    for campo in ("titulo_sumario", "titulo_resumido", "texto_resumido"):
        val = fix_display_text(str(row.get(campo, "") or "")).strip()
        if val:
            return title_case_es(val[:_TEMA_MAX])
    return ""


def componer_titulo(row) -> str:
    """Titulo unificado a partir de una fila de documents (con numero_norma mergeado).

    `row` puede ser una Series de pandas o un dict; se accede via .get()."""
    tipo = str(row.get("tipo_norma", "") or "Norma").strip() or "Norma"
    numero = formato_numero(row.get("numero_norma"))
    tema = _tema(row)

    cabecera = f"{tipo} {numero}" if numero != "S/N" else tipo
    titulo = f"{cabecera} — {tema}" if tema else cabecera
    if _es_modificacion(row):
        titulo += " · modificación"
    return titulo
