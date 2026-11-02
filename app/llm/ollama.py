"""LLMClient поверх Ollama /api/chat со structured output (`format` = JSON-схема ответа)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .http import check, json_object, post

log = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str, model: str, *, timeout: float = 240.0, temperature: float = 0.3,
                 keep_alive: str = "30m", num_ctx: int = 4096, transport: httpx.BaseTransport | None = None):
        self.model = model
        self._options = {"temperature": temperature, "num_ctx": num_ctx}
        self._keep_alive = keep_alive
        # trust_env=False: системные HTTP(S)_PROXY не должны перехватывать запросы к локальной модели.
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, trust_env=False,
                                  transport=transport)

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,  # Ollama строит из схемы грамматику: ответ другой формы невозможен
            "think": False,  # «думающим» моделям рассуждения не нужны: шаги задаёт схема
            "keep_alive": self._keep_alive,
            "options": self._options,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        resp = self._post(payload)
        if resp.status_code == 400 and "think" in resp.text:  # модель без поддержки think
            payload.pop("think")
            resp = self._post(payload)
        check(resp, self.model)
        try:
            body = resp.json()
            content = body["message"]["content"]
        except (ValueError, KeyError, TypeError):
            body, content = {}, None
        if body.get("prompt_eval_count", 0) + body.get("eval_count", 0) >= self._options["num_ctx"]:
            log.warning("ответ упёрся в num_ctx=%s: Ollama могла обрезать промпт", self._options["num_ctx"])
        return json_object(content)

    def is_up(self) -> bool:
        try:
            return self._http.get("/api/version", timeout=2.0).status_code == 200
        except httpx.HTTPError:
            return False

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        return post(self._http, "/api/chat", payload,
                    unreachable="LLM недоступна (на демо-сервере: не открыт туннель к Ollama)")
