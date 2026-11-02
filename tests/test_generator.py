import pytest

from app.generator import CardGenerator, build_specs, find_problems, normalize, shorten
from app.llm import LLMError, LLMUnavailable
from app.models import NO_DATA, ProductInput
from tests.fakes import PRODUCT, FakeLLM, answer

product = ProductInput(**PRODUCT)


def test_good_answer_needs_one_call():
    llm = FakeLLM(answer())
    result = CardGenerator(llm).generate(product)
    assert result.attempts == 1 and result.warnings == []
    assert len(result.card.seo_title) <= 70
    assert 800 <= len(result.card.seo_description) <= 1200
    assert "<product>" in llm.prompts[0] and "0–1,6 МПа" in llm.prompts[0]


def test_specs_come_from_input_only():
    card = CardGenerator(FakeLLM(answer())).generate(product).card
    by_name = {s.name: s for s in card.specs}
    assert by_name["Диапазон измерений"].value == "0–1,6 МПа"
    assert by_name["Диапазон измерений"].source == "input"
    # модель назвала отсутствующую характеристику — значение только «данных нет»
    assert by_name["Рабочая температура среды"].value == NO_DATA
    # уже имеющуюся во входе характеристику модель не может продублировать
    assert [s.name.lower() for s in card.specs].count("диапазон измерений") == 1


def test_missing_lists_gaps_and_unknown_characteristics():
    result = CardGenerator(FakeLLM(answer())).generate(product)
    assert any("рабочая температура среды" in m for m in result.missing)


def test_invented_number_triggers_repair_with_feedback():
    bad = answer(seo_title="Манометр DM 02 Манотомь IP65")
    llm = FakeLLM(bad, answer())
    result = CardGenerator(llm).generate(product)
    assert result.attempts == 2 and result.warnings == []
    assert "seo_title: число «65»" in llm.prompts[1] and "<previous>" in llm.prompts[1]


def test_short_description_triggers_repair():
    llm = FakeLLM(answer(seo_description="Коротко."), answer())
    assert CardGenerator(llm).generate(product).attempts == 2
    assert "seo_description — 8 символов" in llm.prompts[1]


def test_unfixed_problems_become_warnings_and_best_attempt_is_kept():
    bad = answer(seo_description="Коротко, IP65.")
    worse = answer(seo_description="Коротко, IP65.", search_queries=[])
    result = CardGenerator(FakeLLM(bad, worse, worse), repairs=2).generate(product)
    assert result.attempts == 3
    assert result.card.search_queries  # взята лучшая попытка
    assert any("65" in w for w in result.warnings)
    assert any("seo_description" in w for w in result.warnings)


def test_long_title_is_shortened_with_warning():
    long_title = "Манометр показывающий DM 02 Манотомь " * 3
    result = CardGenerator(FakeLLM(*[answer(seo_title=long_title)] * 3)).generate(product)
    assert len(result.card.seo_title) <= 70
    assert any("обрезан" in w for w in result.warnings)


def test_retryable_error_is_retried_once():
    llm = FakeLLM(LLMError("bad json", retryable=True), answer())
    assert CardGenerator(llm).generate(product).attempts == 1


def test_unavailable_llm_is_not_retried():
    with pytest.raises(LLMUnavailable):
        CardGenerator(FakeLLM(LLMUnavailable("down"), answer())).generate(product)


def test_same_input_is_cached():
    llm = FakeLLM(answer())
    gen = CardGenerator(llm)
    assert gen.generate(product) is gen.generate(ProductInput(**PRODUCT))
    assert len(llm.prompts) == 1


def test_normalize_survives_broken_answer():
    draft = normalize({"seo_title": 5, "search_queries": "x", "commercial": [], "missing_characteristics": None})
    assert draft["seo_title"] == "" and draft["search_queries"] == []
    assert draft["commercial"] == {"audience": [], "tasks": []}


def test_normalize_dedupes_queries_and_keeps_paragraphs():
    draft = normalize({"seo_description": "a  b\n\n\n\nc", "search_queries": ["Купить X", "купить x", " ", "Y"]})
    assert draft["seo_description"] == "a b\n\nc"
    assert draft["search_queries"] == ["купить x", "y"]


def test_shorten_cuts_on_word_boundary():
    assert shorten("слово " * 20, 20) == "слово слово слово"
    assert shorten("коротко", 20) == "коротко"


def test_markdown_contains_all_sections():
    md = CardGenerator(FakeLLM(answer())).generate(product).markdown
    for section in ("SEO-заголовок", "SEO-описание", "Характеристики", "Поисковые запросы",
                    "Кому подходит", "Какие задачи решает", "Нужно уточнить", "| Диапазон измерений | 0–1,6 МПа |"):
        assert section in md


def test_empty_input_spec_is_listed_once():
    p = ProductInput(name="Термометр ТБ-63", specs={"длина погружной части": ""})
    llm = FakeLLM(answer(missing_characteristics=["Длина погружной части"]))
    result = CardGenerator(llm, repairs=0).generate(p)
    rows = [s for s in result.card.specs if s.name.lower() == "длина погружной части"]
    assert len(rows) == 1 and rows[0].value == NO_DATA
    assert sum("длина погружной части" in m.lower() for m in result.missing) == 1


def test_number_problem_names_field_and_fragment():
    draft = normalize(answer(search_queries=["манометр 0 16 мпа", "a b", "c d"]))
    problems = find_problems(draft, {"0", "1.6"})
    assert any(p.startswith("search_queries: число «16»") and "манометр 0 16 мпа" in p for p in problems)


def test_dot_decimals_are_rewritten_to_input_style():
    card = CardGenerator(FakeLLM(answer(seo_title="Манометр DM 02 0–1.6 МПа"))).generate(product).card
    assert card.seo_title == "Манометр DM 02 0–1,6 МПа"


def test_unsupported_claim_triggers_repair():
    llm = FakeLLM(answer(seo_title="Надёжный манометр DM 02 Манотомь"), answer())
    assert CardGenerator(llm).generate(product).attempts == 2
    assert "seo_title: «надёжный»" in llm.prompts[1]


def test_missing_name_covered_by_input_name_is_skipped():
    p = ProductInput(name="X", specs={"материал корпуса и мембраны": "сталь"})
    specs = build_specs(p, ["Материал мембраны", "Степень защиты"])
    assert [s.name for s in specs] == ["Материал корпуса и мембраны", "Степень защиты"]
