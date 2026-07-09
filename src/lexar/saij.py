"""Scraper de fallos CSJN contra la API JSON de SAIJ (Fase 4).

API descubierta el 2026-07-08 (misma familia de endpoints que produjo saij_texts.csv):
- Busqueda: https://www.saij.gob.ar/busqueda?o=<offset>&p=<page>&f=<facets>&s=fecha-rango|DESC
  Gotcha: el facet de tribunal es `Tribunal/...` — `Organismo/...` devuelve 0 resultados.
- Documento: https://www.saij.gob.ar/view-document?guid=<uuid> → JSON con metadata del fallo;
  el texto completo NO viene en el JSON sino como PDF referenciado en content['texto-doc'].
- PDF: https://www.saij.gob.ar/descarga-archivo?guid=<pdf-uuid>&name=<file-name>
  Los fallos >=2020 son PDFs digitales; el texto se extrae con pypdf. Si un PDF no tiene capa
  de texto (escaneado), el fallo queda con fetch_status='pdf_no_text' en vez de romper la corrida.
"""
from __future__ import annotations

import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

FACETS_FALLOS_CSJN = (
    "Total"
    "|Tipo de Documento/Jurisprudencia/Fallo"
    "|Tribunal/CORTE SUPREMA DE JUSTICIA DE LA NACION"
)
BASE_URL = "https://www.saij.gob.ar"
USER_AGENT = "LexAR-academico/1.0 (proyecto NLP UdeSA)"
REQUEST_SLEEP_SECONDS = 0.4


def _get(url: str, timeout: int = 60, max_retries: int = 4) -> bytes:
    """SAIJ devuelve 500 esporadicos bajo uso normal (no rate limiting); un retry corto
    alcanza. Se usa tanto para la paginacion de busqueda como para documentos individuales —
    si la paginacion misma falla persistentemente, se deja propagar para no perder progreso
    en silencio (el caller reanuda desde checkpoints en la proxima corrida)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(max_retries):
        time.sleep(REQUEST_SLEEP_SECONDS)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == max_retries - 1:
                raise
            time.sleep(2.0 * (attempt + 1))


def _get_json(url: str) -> dict:
    return json.loads(_get(url).decode("utf-8", errors="replace"))


def _search_page(offset: int, page_size: int) -> list[str]:
    params = {
        "o": offset,
        "p": page_size,
        "f": FACETS_FALLOS_CSJN,
        "s": "fecha-rango|DESC",
        "v": "colapsada",
    }
    url = f"{BASE_URL}/busqueda?" + urllib.parse.urlencode(params)
    results = _get_json(url)["searchResults"]
    return [doc["uuid"] for doc in (results.get("documentResultList") or [])]


def _search_page_resilient(offset: int, page_size: int) -> list[str]:
    """SAIJ devuelve 500 de forma deterministica para ciertos rangos de offset/page_size
    (probablemente un documento puntual con datos corruptos en el indice de busqueda), no solo
    como fallo transitorio: reintentar con el mismo page_size no alcanza. Ante un 500
    persistente, se subdivide el rango a la mitad hasta encontrar el/los uuids problematicos, y
    esos offsets individuales se saltean (logueados) en vez de abortar todo el scraping."""
    try:
        return _search_page(offset, page_size)
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            raise
        if page_size == 1:
            print(f"  aviso: offset {offset} devuelve 500 persistente, se saltea 1 resultado")
            return []
        left_size = page_size // 2
        left = _search_page_resilient(offset, left_size)
        right = _search_page_resilient(offset + left_size, page_size - left_size)
        return left + right


def search_fallo_uuids(page_size: int = 100, max_pages: int = 500):
    """Genera UUIDs de fallos CSJN en orden fecha DESC, pidiendo paginas de a una (lazy:
    quien consume corta cuando llega a fallos anteriores al rango buscado, sin listar los
    ~17k uuids historicos). La fecha real se lee despues del view-document de cada fallo,
    porque el resultado de busqueda colapsado no la incluye."""
    for page in range(max_pages):
        docs = _search_page_resilient(page * page_size, page_size)
        if not docs:
            return
        yield from docs


def extract_pdf_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _s(value) -> str:
    """SAIJ mezcla tipos entre documentos (numero-interno viene como int o como string segun
    el fallo); todo campo escalar se castea a str para que los batches parquet no rompan."""
    return "" if value is None else str(value)


def fetch_fallo(uuid: str) -> dict:
    """Baja metadata + texto (PDF) de un fallo. Nunca lanza: los errores quedan en fetch_status."""
    row = {"case_id": f"saij:{uuid}", "saij_uuid": uuid, "fetch_status": "ok", "full_text": ""}
    try:
        raw = _get_json(f"{BASE_URL}/view-document?guid={uuid}")
        document = json.loads(raw["data"])["document"]
        content = document.get("content", {})
        friendly = (document.get("metadata", {}).get("friendly-url") or {}).get("description", "")
        row.update({
            "fecha": _s(content.get("fecha")),
            "tipo_fallo": _s(content.get("tipo-fallo")),
            "tribunal": _s(content.get("tribunal")),
            "actor": _s(content.get("actor")),
            "demandado": _s(content.get("demandado")),
            "sobre": _s(content.get("sobre")),
            "magistrados": _s(content.get("magistrados")),
            "numero_interno": _s(content.get("numero-interno")),
            "id_infojus": _s(content.get("id-infojus")),
            "sumarios_relacionados": json.dumps(content.get("sumarios-relacionados", {}), ensure_ascii=False),
            "url": f"{BASE_URL}/{friendly}" if friendly else "",
        })
        texto_doc = content.get("texto-doc") or {}
        if not texto_doc.get("uuid"):
            row["fetch_status"] = "no_pdf"
            return row
        pdf_url = f"{BASE_URL}/descarga-archivo?" + urllib.parse.urlencode(
            {"guid": texto_doc["uuid"], "name": texto_doc.get("file-name", "doc.pdf")}
        )
        text = extract_pdf_text(_get(pdf_url))
        if len(text.strip()) < 200:
            row["fetch_status"] = "pdf_no_text"
        row["full_text"] = text
    except Exception as exc:
        row["fetch_status"] = f"error: {type(exc).__name__}: {exc}"[:300]
    return row


def _load_fetched_uuids(parts_dir: Path) -> set[str]:
    done: set[str] = set()
    for part in sorted(parts_dir.glob("part_*.parquet")):
        done.update(pd.read_parquet(part, columns=["saij_uuid"])["saij_uuid"])
    return done


def scrape_fallos_csjn(
    parts_dir: Path,
    since: str = "2020-01-01",
    max_fallos: int | None = None,
    checkpoint_every: int = 50,
) -> None:
    """Corrida completa reanudable: lista uuids, saltea los ya bajados, corta en `since`.

    Como la busqueda viene en fecha DESC, el corte por fecha se aplica al consolidar; aca se
    dejan de pedir documentos nuevos cuando una racha de `checkpoint_every` fallos consecutivos
    quedo antes de `since` (margen para fechas levemente desordenadas en el indice de SAIJ).
    """
    parts_dir.mkdir(parents=True, exist_ok=True)
    already = _load_fetched_uuids(parts_dir)
    print(f"Ya bajados en checkpoints previos: {len(already):,}")

    buffer: list[dict] = []
    next_part = len(list(parts_dir.glob("part_*.parquet")))
    fetched = 0
    consecutive_old = 0

    for uuid in search_fallo_uuids():
        if uuid in already:
            continue
        row = fetch_fallo(uuid)
        buffer.append(row)
        fetched += 1

        fecha = row.get("fecha") or ""
        if fecha and fecha < since:
            consecutive_old += 1
        else:
            consecutive_old = 0

        if len(buffer) >= checkpoint_every:
            pd.DataFrame(buffer).to_parquet(parts_dir / f"part_{next_part:06d}.parquet", index=False)
            next_part += 1
            buffer = []
            print(f"  checkpoint: {fetched:,} fallos bajados en esta corrida (ultima fecha: {fecha})")

        if consecutive_old >= checkpoint_every:
            print(f"Corte: {consecutive_old} fallos consecutivos anteriores a {since}.")
            break
        if max_fallos is not None and fetched >= max_fallos:
            print(f"Corte: MAX_FALLOS={max_fallos} alcanzado (smoke test).")
            break

    if buffer:
        pd.DataFrame(buffer).to_parquet(parts_dir / f"part_{next_part:06d}.parquet", index=False)
    print(f"Scraping terminado: {fetched:,} fallos bajados en esta corrida.")


def build_case_fragments(fallos: pd.DataFrame) -> pd.DataFrame:
    """Chunkea el texto de cada fallo (los fallos no tienen estructura `ARTICULO n`; se usa
    chunk_text directo, igual que el fallback de leyes sin articulos). Mismo esquema que
    legal_fragments, con namespace `cfrag:` en fragment_id."""
    from .segmentation import chunk_text, content_hash

    rows: list[dict] = []
    for _, fallo in fallos.iterrows():
        for ordinal, (start, end, chunk) in enumerate(chunk_text(fallo["full_text"]), start=1):
            rows.append({
                "case_id": fallo["case_id"],
                "fragment_type": "chunk",
                "ordinal": ordinal,
                "label": f"CHUNK {ordinal}",
                "char_start": start,
                "char_end": end,
                "text": chunk,
                "content_hash": content_hash(chunk),
                "text_len": len(chunk),
                "fecha": fallo["fecha"],
                "tipo_fallo": fallo["tipo_fallo"],
                "actor": fallo["actor"],
                "demandado": fallo["demandado"],
                "sobre": fallo["sobre"],
                "id_infojus": fallo["id_infojus"],
                "url": fallo["url"],
            })
    fragments = pd.DataFrame(rows)
    if not fragments.empty:
        fragments.insert(0, "fragment_id", [f"cfrag:{i:08d}" for i in range(len(fragments))])
    return fragments


def consolidate_fallos(parts_dir: Path, output_path: Path, since: str = "2020-01-01") -> pd.DataFrame:
    """Une los part files, filtra a fecha >= since y fetch_status ok, deduplica por uuid."""
    parts = sorted(parts_dir.glob("part_*.parquet"))
    assert parts, f"No hay checkpoints en {parts_dir} — correr scrape_fallos_csjn primero."
    fallos = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    fallos = fallos.drop_duplicates("saij_uuid", keep="last")
    in_scope = fallos[(fallos["fecha"] >= since) & (fallos["fetch_status"] == "ok")].copy()
    dropped = len(fallos) - len(in_scope)
    print(f"Fallos consolidados: {len(in_scope):,} en alcance (>= {since}, status ok); {dropped:,} descartados/fuera de rango")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    in_scope.reset_index(drop=True).to_parquet(output_path, index=False)
    return in_scope
