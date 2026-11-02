"""FakeLLM: отдаёт заранее заданные ответы (dict) или бросает заданные исключения, запоминает промпты."""
from typing import Any

from app.llm import LLMError

PRODUCT = {
    "name": "Манометр показывающий DM 02",
    "manufacturer": "Манотомь",
    "specs": {
        "диапазон измерений": "0–1,6 МПа",
        "класс точности": "1,5",
        "присоединение": "G1/2",
        "диаметр корпуса": "100 мм",
    },
    "description": "Прибор предназначен для измерения избыточного давления неагрессивных жидкостей и газов "
                   "в системах водоснабжения, отопления и на технологическом оборудовании.",
}

GOOD_DESCRIPTION = (
    "Манометр показывающий DM 02 производства Манотомь предназначен для измерения избыточного давления "
    "неагрессивных жидкостей и газов.\n\n"
    "Диапазон измерений прибора 0–1,6 МПа, класс точности 1,5. Присоединение G1/2, диаметр корпуса 100 мм — "
    "шкала хорошо читается с рабочего места оператора.\n\n"
    + "Прибор применяется в системах водоснабжения, отопления и на технологическом оборудовании. " * 7
).strip()


def answer(**overrides: Any) -> dict[str, Any]:
    data = {
        "seo_title": "Манометр DM 02 Манотомь 0–1,6 МПа, класс 1,5",
        "seo_description": GOOD_DESCRIPTION,
        "search_queries": ["манометр dm 02", "манометр 1,6 мпа g1/2", "купить манометр манотомь"],
        "commercial": {"audience": ["Службы эксплуатации котельных"], "tasks": ["Контроль давления в трубопроводе"]},
        "missing_characteristics": ["рабочая температура среды", "диапазон измерений"],
    }
    data.update(overrides)
    return data


class FakeLLM:
    model = "fake"

    def __init__(self, *responses: Any, up: bool = True):
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.up = up

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.prompts.append(user)
        item = self.responses.pop(0)
        if isinstance(item, LLMError):
            raise item
        return item

    def is_up(self) -> bool:
        return self.up
