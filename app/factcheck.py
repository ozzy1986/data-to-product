"""Защита от выдуманных характеристик: каждое число в тексте модели должно встречаться во входных данных.

Технические значения в карточке почти всегда числовые (диапазоны, классы точности, размеры, IP, токи),
поэтому сверка чисел ловит основную массу выдумок дёшево и без второй модели.
"""
import re
from decimal import Decimal, InvalidOperation

from .models import ProductInput

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _norm(token: str) -> str:
    """«1,6» == «1.6» == «1.60»; «02» == «2»."""
    try:
        value = Decimal(token.replace(",", "."))
    except InvalidOperation:
        return token
    return format(value.normalize(), "f")


def numbers(text: str) -> set[str]:
    return {_norm(m) for m in _NUMBER.findall(text)}


def source_numbers(product: ProductInput) -> set[str]:
    parts = [product.name, product.manufacturer, product.description]
    for name, value in product.specs.items():
        parts += [name, value]
    return numbers(" ".join(parts))


def unknown_numbers(text: str, allowed: set[str]) -> list[str]:
    """Числа из text, которых нет во входе, в порядке появления, без повторов."""
    seen: list[str] = []
    for m in _NUMBER.findall(text):
        n = _norm(m)
        if n not in allowed and m not in seen:
            seen.append(m)
    return seen


_DOT_DECIMAL = re.compile(r"(?<=\d)\.(?=\d)")
_COMMA_DECIMAL = re.compile(r"\d,\d")


def uses_decimal_comma(product: ProductInput) -> bool:
    """Во входе десятичная запятая («1,6 МПа») и нет десятичной точки — так и пишем в карточке."""
    text = " ".join([product.name, product.description, *product.specs.values()])
    return bool(_COMMA_DECIMAL.search(text)) and not _DOT_DECIMAL.search(text)


def to_decimal_comma(text: str) -> str:
    return _DOT_DECIMAL.sub(",", text)
