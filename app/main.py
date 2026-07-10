"""App FastAPI de LexAR. Correr desde la raiz del repo:

    python -m uvicorn app.main:app --reload

Los endpoints pesados (pandas/FAISS/LLM) son `def` sincronicos a proposito: FastAPI los corre
en su threadpool y el servidor sigue respondiendo mientras una consulta espera al modelo.
"""
from __future__ import annotations

from fastapi import FastAPI

from .routes import chatbot, explorador, home

app = FastAPI(title="LexAR — Asistente Jurídico", docs_url=None, redoc_url=None)
app.include_router(home.router)
app.include_router(explorador.router)
app.include_router(chatbot.router)
