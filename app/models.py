"""Входные данные о приборе и готовая карточка товара."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

NO_DATA = "данных нет"


def _clean(value: Any) -> str:
    """Значение характеристики → строка без лишних пробелов. Числа и bool допустимы, вложенные объекты — нет."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, (int, float, str)):
        return " ".join(str(value).split())
    if isinstance(value, list) and all(isinstance(v, (int, float, str)) for v in value):
        return ", ".join(s for s in (_clean(v) for v in value) if s)
    raise ValueError("значение характеристики должно быть строкой, числом или списком строк")


class ProductInput(BaseModel):
    """Всё, кроме названия, может отсутствовать: тогда карточка помечает пробелы, а не выдумывает."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=300)
    manufacturer: str = Field("", max_length=200)
    specs: dict[str, str] = Field(default_factory=dict, max_length=60)
    description: str = Field("", max_length=8000)

    @field_validator("manufacturer", "description", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> Any:
        return "" if v is None else v

    @field_validator("specs", mode="before")
    @classmethod
    def _clean_specs(cls, v: Any) -> Any:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("specs должен быть объектом {\"характеристика\": \"значение\"}")
        out: dict[str, str] = {}
        for key, value in v.items():
            name = " ".join(str(key).split())
            if not name:
                continue
            if len(name) > 100:
                raise ValueError(f"слишком длинное название характеристики: {name[:40]}…")
            text = _clean(value)
            if len(text) > 500:
                raise ValueError(f"слишком длинное значение характеристики «{name}»")
            out[name] = text
        return out


class SpecItem(BaseModel):
    name: str
    value: str
    # input — значение из входных данных; missing — характеристика важна, но её нет во входе.
    source: Literal["input", "missing"]


class Commercial(BaseModel):
    audience: list[str]
    tasks: list[str]


class Card(BaseModel):
    seo_title: str
    seo_description: str
    specs: list[SpecItem]
    search_queries: list[str]
    commercial: Commercial


class CardResult(BaseModel):
    card: Card
    # Что заполнить или проверить контент-менеджеру: отсутствующие поля, пустые значения и т. п.
    missing: list[str]
    # Что не прошло автоматические проверки после всех попыток — перепроверить вручную.
    warnings: list[str]
    markdown: str
    model: str
    attempts: int
