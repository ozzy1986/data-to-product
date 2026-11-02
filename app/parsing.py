"""Разбор тела запроса → ProductInput с понятными сообщениями об ошибках (общий для API и CLI)."""
from __future__ import annotations

import json

from pydantic import ValidationError

from .models import ProductInput

# Сообщения pydantic → человеческие, по типу ошибки.
_ERRORS = {
    "missing": "обязательное поле",
    "string_type": "должно быть строкой",
    "dict_type": "должно быть объектом",
    "string_too_short": "не может быть пустым",
    "string_too_long": "слишком длинное значение",
    "too_long": "слишком много элементов",
    "extra_forbidden": "неизвестное поле (допустимы: name, manufacturer, specs, description)",
}


class ApiError(Exception):
    """Ошибка с HTTP-статусом и понятным текстом для пользователя."""

    def __init__(self, status: int, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.status, self.message, self.details = status, message, details or []


def _details(exc: ValidationError) -> list[str]:
    out = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"]) or "тело запроса"
        msg = _ERRORS.get(err["type"]) or str(err["msg"]).removeprefix("Value error, ")
        out.append(f"{field}: {msg}")
    return out


def parse_product(body: bytes) -> ProductInput:
    if not body.strip():
        raise ApiError(400, "Пустой запрос: пришлите JSON с данными о товаре.")
    try:
        data = json.loads(body)
    except UnicodeDecodeError:
        raise ApiError(400, "Тело запроса должно быть в UTF-8.")
    except json.JSONDecodeError as e:
        raise ApiError(400, f"Некорректный JSON: {e.msg} (строка {e.lineno}, столбец {e.colno}).")
    if not isinstance(data, dict):
        raise ApiError(400, "Ожидается JSON-объект {\"name\": …, \"manufacturer\": …, \"specs\": {…}, \"description\": …}.")
    try:
        return ProductInput.model_validate(data)
    except ValidationError as e:
        raise ApiError(422, "Данные о товаре не прошли проверку.", _details(e))
