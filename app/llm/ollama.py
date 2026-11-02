"""LLMClient поверх Ollama /api/chat со structured output (`format` = JSON-схема ответа)."""
from __future__ import annotations

import json
from typing import Any

import httpx

from . import LLMError, LLMUnavailable


class OllamaClient:
    def __init__(self, base_url: str, model: str, *, timeout: float = 240.0,
                 temperature: float = 0.3, keep_alive: str = "30m", num_ctx: int = 4096):
        self.model = model
        self._options = {"temperature": temperature, "num_ctx": num_ctx}
        self._keep_alive = keep_alive
        # trust_env=False: системные HTTP(S)_PROXY не должны перехватывать запросы к модели.
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, trust_env=False)

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "think": False,  # «думающим» моделям рассуждения не нужны: шаги задаёт схема
            "keep_alive": self._keep_alive,
            "options": self._options,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        resp = self._post(payload)
        if resp.status_code == 400 and "think" in resp.text:  # модель без поддержки think
            payload.pop("think")
            resp = self._post(payload)
        if resp.status_code == 404:
            raise LLMUnavailable(f"модель {self.model} не найдена в Ollama (ollama pull {self.model})")
        if resp.status_code >= 500:  # например, разовый сбой CUDA при загрузке модели
            raise LLMError(f"Ollama вернула {resp.status_code}", retryable=True)
        if resp.status_code >= 400:
            raise LLMError(f"Ollama вернула {resp.status_code}: {resp.text[:200]}")
        try:
            data = json.loads(resp.json()["message"]["content"])
        except (ValueError, KeyError, TypeError) as e:
            raise LLMError("модель вернула невалидный JSON", retryable=True) from e
        if not isinstance(data, dict):
            raise LLMError("модель вернула не JSON-объект", retryable=True)
        return data

    def is_up(self) -> bool:
        try:
            return self._http.get("/api/version", timeout=2.0).status_code == 200
        except httpx.HTTPError:
            return False

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        try:
            return self._http.post("/api/chat", json=payload)
        except httpx.TimeoutException as e:
            raise LLMError("модель не ответила вовремя") from e  # повтор занял бы столько же
        except httpx.TransportError as e:
            raise LLMUnavailable("LLM недоступна (на демо-сервере: не открыт туннель к Ollama)") from e
