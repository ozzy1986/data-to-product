"""LLMClient поверх Anthropic Messages API (официальный SDK) со structured outputs."""
from __future__ import annotations

from typing import Any

import anthropic

from . import LLMError, LLMUnavailable
from .http import json_object

# Structured outputs не принимают ограничения длины и числа элементов: их всё равно проверяет код.
_UNSUPPORTED = {"minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum"}


def strict_schema(schema: Any) -> Any:
    """Схема в форме, которую требует API: у каждого объекта additionalProperties=false."""
    if isinstance(schema, list):
        return [strict_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    out = {k: strict_schema(v) for k, v in schema.items() if k not in _UNSUPPORTED}
    if out.get("type") == "object":
        out["additionalProperties"] = False
    return out


class ClaudeClient:
    def __init__(self, model: str, api_key: str = "", *, base_url: str = "", timeout: float = 240.0,
                 http_client: Any = None):
        self.model = model
        # Без ключа SDK сам ищет ANTHROPIC_API_KEY и профиль `ant auth login`.
        # Повторы при 429/5xx и сетевых сбоях — внутри SDK (с учётом retry-after), поэтому наши
        # ошибки ниже не помечаются retryable: иначе повторы умножились бы.
        self._client = anthropic.Anthropic(api_key=api_key or None, base_url=base_url or None,
                                           timeout=timeout, max_retries=2, http_client=http_client)

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        try:
            # temperature не передаём: текущие модели Claude её не принимают.
            response = self._client.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": strict_schema(schema)}},
            )
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise LLMUnavailable("API Anthropic отклонил ключ: проверьте LLM_API_KEY") from e
        except anthropic.NotFoundError as e:
            raise LLMUnavailable(f"модель {self.model} не найдена: проверьте LLM_MODEL") from e
        except anthropic.APITimeoutError as e:  # подкласс APIConnectionError — ловим раньше
            raise LLMError("модель не ответила вовремя") from e
        except anthropic.APIConnectionError as e:
            raise LLMUnavailable("нет связи с API Anthropic") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"API Anthropic вернул {e.status_code}: {e.message[:200]}") from e
        if response.stop_reason == "refusal":
            raise LLMError("модель отказалась отвечать на запрос")
        if response.stop_reason == "max_tokens":
            raise LLMError("ответ модели обрезан по max_tokens", retryable=True)
        return json_object(next((b.text for b in response.content if b.type == "text"), None))

    def is_up(self) -> bool:
        try:
            self._client.with_options(timeout=3.0, max_retries=0).models.list(limit=1)
            return True
        except anthropic.APIError:
            return False
