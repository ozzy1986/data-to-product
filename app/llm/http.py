"""Общее для HTTP-клиентов LLM: отправка запроса и единое толкование ошибок."""
from __future__ import annotations

import json
from typing import Any

import httpx

from . import LLMError, LLMUnavailable


def post(http: httpx.Client, path: str, payload: dict[str, Any], *, unreachable: str) -> httpx.Response:
    try:
        return http.post(path, json=payload)
    except httpx.TimeoutException as e:
        raise LLMError("модель не ответила вовремя") from e  # повтор занял бы столько же
    except httpx.TransportError as e:
        raise LLMUnavailable(unreachable) from e


def check(resp: httpx.Response, model: str) -> None:
    status = resp.status_code
    if status in (401, 403):
        raise LLMUnavailable("API LLM отклонил ключ: проверьте LLM_API_KEY")
    if status == 404:
        raise LLMUnavailable(f"модель {model} не найдена: проверьте LLM_MODEL и LLM_URL")
    if status == 429 or status >= 500:  # лимит запросов или разовый сбой провайдера
        raise LLMError(f"API LLM вернул {status}", retryable=True)
    if status >= 400:
        raise LLMError(f"API LLM вернул {status}: {resp.text[:200]}")


def json_object(content: Any) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except (TypeError, ValueError) as e:
        raise LLMError("модель вернула невалидный JSON", retryable=True) from e
    if not isinstance(data, dict):
        raise LLMError("модель вернула не JSON-объект", retryable=True)
    return data
