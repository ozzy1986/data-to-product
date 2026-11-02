"""LLMClient поверх OpenAI-совместимого Chat Completions API.

Один адаптер на всех, кто говорит на этом протоколе: OpenAI, Google Gemini, DeepSeek, OpenRouter
(в том числе модели Claude), Groq, LM Studio, vLLM и сама Ollama (`/v1`).
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from .http import check, json_object, post


class OpenAIClient:
    def __init__(self, base_url: str, model: str, api_key: str = "", *, timeout: float = 240.0,
                 temperature: float = 0.3, transport: httpx.BaseTransport | None = None):
        self.model = model
        self._temperature = temperature
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        # trust_env оставлен включённым: облачному API может понадобиться системный прокси.
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, headers=headers,
                                  transport=transport)
        self._unreachable = f"нет связи с API LLM ({base_url})"

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        # json_object поддерживают почти все совместимые API, а json_schema — не все. Схему модель
        # получает текстом; отклонения от неё всё равно выправляет normalize() в генераторе.
        system += "\n\nОтвет — один JSON-объект по этой JSON-схеме:\n" + json.dumps(schema, ensure_ascii=False)
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self._temperature,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        resp = self._post(payload)
        if resp.status_code == 400 and "temperature" in resp.text:  # reasoning-модели её не принимают
            payload.pop("temperature")
            resp = self._post(payload)
        check(resp, self.model)
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            content = None
        return json_object(content)

    def is_up(self) -> bool:
        try:
            return self._http.get("/models", timeout=3.0).status_code == 200
        except httpx.HTTPError:
            return False

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        return post(self._http, "/chat/completions", payload, unreachable=self._unreachable)
