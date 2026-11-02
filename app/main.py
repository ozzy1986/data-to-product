"""HTTP-слой. POST /api/generate — карточка; GET /api/examples — сохранённые примеры; GET /api/health.

Локально отдаёт и веб-форму из public/; на сервере статику отдаёт Apache, сюда идёт только /api.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings, settings as default_settings
from .factory import build_generator
from .generator import CardGenerator
from .llm import LLMError, LLMUnavailable
from .parsing import ApiError, parse_product

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

ROOT = Path(__file__).resolve().parent.parent
_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def _json(data, status: int = 200) -> Response:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return Response(body, status_code=status, media_type="application/json; charset=utf-8", headers=_HEADERS)


def load_examples(directory: Path) -> list[dict]:
    """Сохранённые результаты для демо — видны и без LLM. Формат: examples/output/<имя>.json."""
    out = []
    for path in sorted(directory.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            log.warning("bad example file %s", path)
    return out


def create_app(generator: CardGenerator | None = None, settings: Settings = default_settings) -> FastAPI:
    generator = generator or build_generator(settings)
    examples = load_examples(ROOT / "examples" / "output")
    slots = asyncio.Semaphore(settings.llm_concurrency)
    waiting = 0

    # Документация и схема снаружи не нужны — меньше поверхности.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    async def read_body(request: Request) -> bytes:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > settings.max_body_bytes:
            raise ApiError(413, f"Запрос больше {settings.max_body_bytes // 1000} КБ.")
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > settings.max_body_bytes:
                raise ApiError(413, f"Запрос больше {settings.max_body_bytes // 1000} КБ.")
        return bytes(body)

    @app.post("/api/generate")
    async def generate(request: Request):
        nonlocal waiting
        product = parse_product(await read_body(request))
        cached = generator.cached(product)  # готовая карточка — мимо очереди к модели
        if cached:
            return _json(cached.model_dump())
        if waiting >= settings.queue_limit:
            raise ApiError(503, "Модель занята другими запросами, повторите через минуту.")
        waiting += 1
        try:
            async with slots:
                result = await run_in_threadpool(generator.generate, product)
        except LLMUnavailable as e:
            raise ApiError(503, f"{e}. Сохранённые примеры доступны на странице.")
        except LLMError as e:
            raise ApiError(502, f"Ошибка модели: {e}. Повторите запрос.")
        finally:
            waiting -= 1
        return _json(result.model_dump())

    @app.get("/api/examples")
    async def get_examples():
        return _json(examples)

    @app.api_route("/api/health", methods=["GET", "HEAD"])
    async def health():
        up = await run_in_threadpool(generator.llm.is_up)
        return _json({"status": "ok", "llm": "up" if up else "down", "model": generator.llm.model})

    @app.exception_handler(ApiError)
    async def api_error(_request: Request, exc: ApiError):
        return _json({"error": exc.message, "details": exc.details}, exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException):
        return _json({"error": exc.detail if isinstance(exc.detail, str) else "error"}, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        return _json({"error": "bad request"}, 400)

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, _exc: Exception):
        log.exception("unhandled error")
        return _json({"error": "Внутренняя ошибка сервиса."}, 500)

    # Последним: статика ловит всё, что не /api.
    app.mount("/", StaticFiles(directory=ROOT / "public", html=True), name="public")
    return app


app = create_app()
