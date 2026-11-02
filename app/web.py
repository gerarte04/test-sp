"""Минимальный веб-интерфейс: форма + JSON API."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from .config import ConfigError, Settings
from .input_validation import InputError, load_json, parse_product
from .llm import LLMClient, LLMError, make_client
from .render import card_to_markdown
from .service import generate_card

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"

app = FastAPI(title="AI-помощник для товарных описаний", version="0.1.0")


def get_client() -> tuple[LLMClient, Settings]:
    settings = Settings.from_env()
    return make_client(settings), settings


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/generate")
async def generate(request: Request) -> JSONResponse:
    # Тело читаем вручную, чтобы на битый JSON отдать понятную ошибку, а не 422 от FastAPI.
    try:
        product, report = parse_product(load_json(await request.body()))
    except InputError as exc:
        return JSONResponse(status_code=400, content=exc.to_dict())

    try:
        client, settings = get_client()
    except ConfigError as exc:
        return JSONResponse(status_code=500, content={"error": f"Ошибка конфигурации: {exc}", "details": []})

    try:
        # Клиент LLM синхронный — выполняем в пуле потоков, чтобы не блокировать event loop.
        card = await run_in_threadpool(
            generate_card, product, report, client, max_attempts=settings.max_attempts
        )
    except LLMError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc), "details": []})
    except Exception:  # noqa: BLE001 — не отдаём трейсбек пользователю
        log.exception("unexpected error")
        return JSONResponse(status_code=500, content={"error": "Внутренняя ошибка сервиса.", "details": []})

    return JSONResponse(content={"card": card.model_dump(), "markdown": card_to_markdown(card)})
