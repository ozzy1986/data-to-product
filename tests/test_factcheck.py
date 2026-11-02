from app.factcheck import numbers, source_numbers, to_decimal_comma, unknown_numbers, uses_decimal_comma
from app.models import ProductInput
from tests.fakes import PRODUCT


def test_numbers_are_normalized():
    assert numbers("0–1,6 МПа, 1.60, DM 02, G1/2") == {"0", "1.6", "2", "1"}


def test_numbers_from_input_are_allowed():
    allowed = source_numbers(ProductInput(**PRODUCT))
    assert unknown_numbers("Манометр DM 02: 0–1.6 МПа, класс 1,5, G1/2, корпус 100 мм", allowed) == []


def test_invented_numbers_are_found_once_in_order():
    allowed = source_numbers(ProductInput(**PRODUCT))
    text = "Степень защиты IP65, температура до 120 °C, снова IP65, выход 4–20 мА"
    assert unknown_numbers(text, allowed) == ["65", "120", "4", "20"]


def test_decimal_style_follows_input():
    assert uses_decimal_comma(ProductInput(**PRODUCT))
    assert not uses_decimal_comma(ProductInput(name="X", specs={"a": "1.6 МПа", "b": "1,5"}))
    assert to_decimal_comma("0–1.6 МПа, G1/2, класс 1.5") == "0–1,6 МПа, G1/2, класс 1,5"
