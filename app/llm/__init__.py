"""Порт LLM: сервис зависит только от этого протокола, адаптер конкретной модели подставляется снаружи."""
from typing import Any, Protocol


class LLMError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class LLMUnavailable(LLMError):
    """Модель недоступна (нет туннеля, не запущена) — повтор бессмыслен, клиенту 503."""


class LLMClient(Protocol):
    model: str

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...

    def is_up(self) -> bool: ...
