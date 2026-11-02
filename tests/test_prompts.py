from app import prompts
from app.models import ProductInput


def test_missing_manufacturer_is_not_offered_as_text():
    # Иначе модель пишет «от производителя данных нет».
    block = prompts.product_block(ProductInput(name="Термометр ТБ-63"))
    assert "Производитель: не указан" in block and "Производитель: данных нет" not in block
