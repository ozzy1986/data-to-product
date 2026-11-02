"""Сборка карточки: вызов модели → проверки кодом → повтор с замечаниями → финальная карточка.

Разделение ответственности:
- модель пишет только тексты (заголовок, описание, запросы, коммерческий блок) и называет,
  каких характеристик не хватает — без значений;
- список характеристик собирает код из входных данных, поэтому значения в нём не могут быть выдуманы;
- код проверяет длины и сверяет каждое число в текстах со входом; что не исправилось — в warnings.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict
from typing import Any

from . import prompts
from .completeness import find_gaps
from .factcheck import source_numbers, to_decimal_comma, unknown_numbers, uses_decimal_comma
from .llm import LLMClient, LLMError
from .models import NO_DATA, Card, CardResult, Commercial, ProductInput, SpecItem
from .render import to_markdown

log = logging.getLogger(__name__)


def _text(value: Any) -> str:
    """Строка без лишних пробелов; абзацы (пустая строка) сохраняются."""
    if not isinstance(value, str):
        return ""
    paragraphs = (" ".join(p.split()) for p in value.replace("\r", "").split("\n\n"))
    return "\n\n".join(p for p in paragraphs if p)


def _list(value: Any, limit: int) -> list[str]:
    out: list[str] = []
    for item in value if isinstance(value, list) else []:
        s = _text(item).strip(" .;")
        if s and s.casefold() not in (o.casefold() for o in out):
            out.append(s)
    return out[:limit]


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Ответ маленькой модели может нарушить схему — приводим к ожидаемым типам, не падаем."""
    commercial = raw.get("commercial") if isinstance(raw.get("commercial"), dict) else {}
    return {
        "seo_title": " ".join(_text(raw.get("seo_title")).split()).strip(" ."),
        "seo_description": _text(raw.get("seo_description")),
        "search_queries": [q.lower() for q in _list(raw.get("search_queries"), prompts.QUERIES_MAX)],
        "commercial": {"audience": _list(commercial.get("audience"), 4),
                       "tasks": _list(commercial.get("tasks"), 4)},
        "missing_characteristics": _list(raw.get("missing_characteristics"), 6),
    }


def find_problems(draft: dict[str, Any], allowed_numbers: set[str]) -> list[str]:
    """Замечания формулируются для модели (повтор) и для менеджера (warnings), поэтому — конкретно."""
    problems: list[str] = []
    title, description = draft["seo_title"], draft["seo_description"]
    if not title:
        problems.append("seo_title пустой.")
    elif len(title) > prompts.TITLE_MAX:
        problems.append(f"seo_title — {len(title)} символов, нужно не больше {prompts.TITLE_MAX}: сократи.")
    n = len(description)
    if n < prompts.DESCRIPTION_MIN:
        problems.append(f"seo_description — {n} символов, нужно {prompts.DESCRIPTION_MIN}–{prompts.DESCRIPTION_MAX}: "
                        "дополни абзацем о применении прибора, без новых чисел.")
    elif n > prompts.DESCRIPTION_MAX:
        problems.append(f"seo_description — {n} символов, нужно {prompts.DESCRIPTION_MIN}–{prompts.DESCRIPTION_MAX}: "
                        "сократи.")
    if len(draft["search_queries"]) < prompts.QUERIES_MIN:
        problems.append(f"search_queries: нужно {prompts.QUERIES_MIN}–{prompts.QUERIES_MAX} разных запроса.")
    if not draft["commercial"]["audience"] or not draft["commercial"]["tasks"]:
        problems.append("commercial: заполни и audience, и tasks.")
    # Где именно число — чтобы модель при повторе (и менеджер) нашли его сразу.
    fields = [("seo_title", title), ("seo_description", description),
              *(("search_queries", q) for q in draft["search_queries"]),
              *(("commercial.audience", a) for a in draft["commercial"]["audience"]),
              *(("commercial.tasks", t) for t in draft["commercial"]["tasks"]),
              *(("missing_characteristics", m) for m in draft["missing_characteristics"])]
    for field, text in fields:
        for number in unknown_numbers(text, allowed_numbers):
            problems.append(f"{field}: число «{number}» отсутствует во входных данных ({_snippet(text, number)}). "
                            "Напиши значение точно как во входе или убери его.")
    return problems


def _snippet(text: str, number: str, radius: int = 30) -> str:
    i = text.find(number)
    start, end = max(0, i - radius), min(len(text), i + len(number) + radius)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


def shorten(title: str, limit: int = prompts.TITLE_MAX) -> str:
    if len(title) <= limit:
        return title
    cut = title[: limit + 1].rsplit(" ", 1)[0] if " " in title[:limit] else title[:limit]
    return cut.rstrip(" ,.;:–-")


def _capitalize(name: str) -> str:
    """Единый вид названий в таблице; значения не трогаем никогда."""
    return name[:1].upper() + name[1:]


def build_specs(product: ProductInput, missing_names: list[str]) -> list[SpecItem]:
    specs = [SpecItem(name=_capitalize(k), value=v or NO_DATA, source="input" if v else "missing")
             for k, v in product.specs.items()]
    known = [k.casefold() for k in product.specs]
    for name in missing_names:
        key = name.casefold()
        if not any(key in k or k in key for k in known):  # «диапазон измерений» уже есть во входе
            specs.append(SpecItem(name=_capitalize(name), value=NO_DATA, source="missing"))
            known.append(key)
    return specs


class CardGenerator:
    def __init__(self, llm: LLMClient, *, repairs: int = 2, cache_size: int = 256):
        self.llm = llm
        self.repairs = repairs
        self._cache: OrderedDict[str, CardResult] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()

    def cached(self, product: ProductInput) -> CardResult | None:
        key = self._key(product)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def generate(self, product: ProductInput) -> CardResult:
        cached = self.cached(product)
        if cached:
            return cached
        result = self._generate(product)
        key = self._key(product)
        with self._lock:
            self._cache[key] = result
            if len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return result

    def _key(self, product: ProductInput) -> str:
        raw = f"{prompts.PROMPT_VERSION}|{self.llm.model}|{product.model_dump_json()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _generate(self, product: ProductInput) -> CardResult:
        allowed = source_numbers(product)
        comma = uses_decimal_comma(product)
        draft = self._draft(prompts.user_prompt(product), comma)
        problems = find_problems(draft, allowed)
        attempts = 1
        best = (draft, problems)
        while problems and attempts <= self.repairs:
            log.info("attempt %d problems: %s", attempts, problems)
            draft = self._draft(prompts.repair_prompt(product, draft, problems), comma)
            problems = find_problems(draft, allowed)
            attempts += 1
            if len(problems) <= len(best[1]):
                best = (draft, problems)
        draft, problems = best

        warnings = list(problems)
        title = shorten(draft["seo_title"]) or product.name[: prompts.TITLE_MAX]
        if title != draft["seo_title"]:
            warnings.append("SEO-заголовок обрезан кодом до 70 символов — проверьте формулировку.")

        specs = build_specs(product, draft["missing_characteristics"])
        missing = find_gaps(product) + [
            f"Нет данных: {s.name.lower()} — уточнить у производителя или в паспорте."
            for s in specs[len(product.specs):]  # первые — из входа, их пустоты уже в find_gaps
        ]
        card = Card(
            seo_title=title,
            seo_description=draft["seo_description"],
            specs=specs,
            search_queries=draft["search_queries"],
            commercial=Commercial(**draft["commercial"]),
        )
        return CardResult(card=card, missing=missing, warnings=warnings,
                          markdown=to_markdown(product, card, missing, warnings),
                          model=self.llm.model, attempts=attempts)

    def _draft(self, user: str, decimal_comma: bool) -> dict[str, Any]:
        draft = normalize(self._call(user))
        if decimal_comma:  # модель любит «1.6» вместо «1,6» из входа — правим кодом, а не повтором
            fix = to_decimal_comma
            draft = {**draft,
                     "seo_title": fix(draft["seo_title"]), "seo_description": fix(draft["seo_description"]),
                     "search_queries": [fix(q) for q in draft["search_queries"]],
                     "commercial": {k: [fix(x) for x in v] for k, v in draft["commercial"].items()}}
        return draft

    def _call(self, user: str) -> dict[str, Any]:
        try:
            return self.llm.generate_json(prompts.SYSTEM, user, prompts.SCHEMA)
        except LLMError as e:
            if not e.retryable:
                raise
            log.warning("LLM error, retrying once: %s", e)
            return self.llm.generate_json(prompts.SYSTEM, user, prompts.SCHEMA)
