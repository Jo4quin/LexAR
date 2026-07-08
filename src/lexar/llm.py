"""Llamadas LLM con salida JSON estructurada (mismo patron types.Schema + retry de la Fase 3)."""
from __future__ import annotations

import json
import time

from google.genai import types

from .embeddings import get_client
from .rate_limiter import AdaptiveRateLimiter


def generate_json(
    model: str,
    prompt: str,
    schema: types.Schema,
    limiter: AdaptiveRateLimiter | None = None,
    temperature: float = 0.0,
    max_retries: int = 6,
    base_delay: float = 5.0,
) -> dict:
    client = get_client()
    limiter = limiter or AdaptiveRateLimiter()
    for attempt in range(max_retries):
        limiter.wait_turn()
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=temperature,
                ),
            )
            limiter.report_success()
            return json.loads(response.text)
        except Exception as exc:
            if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc):
                limiter.report_rate_limited()
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"Reintentando ({attempt + 1}/{max_retries}) tras error: {exc}. Espero {delay:.1f}s")
            time.sleep(delay)
