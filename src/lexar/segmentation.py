"""Chunking de texto (extraido de la Fase 1). Los fallos no tienen estructura `ARTICULO n`,
asi que la Fase 4 usa chunk_text directo, igual que el fallback de leyes sin articulos."""
from __future__ import annotations

import hashlib
import re
import unicodedata

from .config import CHUNK_OVERLAP_CHARS, MAX_FRAGMENT_CHARS, MIN_FRAGMENT_CHARS


def normalize_text(text: str) -> str:
    """Normalizacion para comparar texto (extraida de la Fase 3): sin acentos, minusculas,
    espacios colapsados. La usa la validacion de citas del chatbot."""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def clean_fragment_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def chunk_text(text: str, max_chars: int = MAX_FRAGMENT_CHARS, overlap: int = CHUNK_OVERLAP_CHARS):
    text = str(text)
    if len(text) <= max_chars:
        yield 0, len(text), clean_fragment_text(text)
        return

    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind("\n", start, end))
            if boundary > start + max_chars * 0.5:
                end = boundary + 1
        chunk = clean_fragment_text(text[start:end])
        if len(chunk) >= MIN_FRAGMENT_CHARS:
            yield start, end, chunk
        if end >= len(text):
            break
        start = max(0, end - overlap)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
