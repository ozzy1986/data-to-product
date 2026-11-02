"""Проверка полноты входа кодом — до модели и независимо от неё."""
from .models import ProductInput

SHORT_DESCRIPTION = 150  # символов: меньше — тексту карточки не на что опереться, кроме характеристик


def find_gaps(product: ProductInput) -> list[str]:
    gaps: list[str] = []
    if not product.manufacturer:
        gaps.append("Не указан производитель (manufacturer).")
    if not product.specs:
        gaps.append("Нет характеристик (specs): список характеристик в карточке будет пустым.")
    for name, value in product.specs.items():
        if not value:
            gaps.append(f"Характеристика «{name}»: значение не указано.")
    description = product.description
    if not description:
        gaps.append("Нет описания (description): тексты построены только на названии и характеристиках.")
    elif description.endswith(("...", "…")):
        gaps.append("Описание обрывается многоточием — похоже на неполный фрагмент паспорта.")
    elif len(description) < SHORT_DESCRIPTION:
        gaps.append(f"Описание короткое (меньше {SHORT_DESCRIPTION} символов) — стоит добавить фрагмент паспорта.")
    return gaps
