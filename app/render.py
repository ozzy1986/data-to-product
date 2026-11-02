"""Карточка → Markdown для копирования в CMS или задачу контент-менеджеру."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Card, ProductInput


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def to_markdown(product: ProductInput, card: Card, missing: list[str], warnings: list[str]) -> str:
    out = [f"# {product.name}", ""]
    if warnings:
        out += ["> **Проверить вручную:**", *[f"> - {w}" for w in warnings], ""]
    out += [
        f"## SEO-заголовок ({len(card.seo_title)} симв.)", "", card.seo_title, "",
        f"## SEO-описание ({len(card.seo_description)} симв.)", "", card.seo_description, "",
        "## Характеристики", "", "| Характеристика | Значение |", "|---|---|",
    ]
    out += [f"| {_cell(s.name)} | {_cell(s.value)} |" for s in card.specs] or ["| — | данных нет |"]
    out += ["", "## Поисковые запросы", "", *[f"- {q}" for q in card.search_queries], ""]
    out += ["## Для менеджера", "", "**Кому подходит:**", "", *[f"- {a}" for a in card.commercial.audience], ""]
    out += ["**Какие задачи решает:**", "", *[f"- {t}" for t in card.commercial.tasks], ""]
    if missing:
        out += ["## Нужно уточнить", "", *[f"- {m}" for m in missing], ""]
    return "\n".join(out)
