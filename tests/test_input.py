import pytest

from app.completeness import find_gaps
from app.models import ProductInput
from app.parsing import ApiError, parse_product
from tests.fakes import PRODUCT


def test_valid_product_is_parsed():
    p = parse_product('{"name": "  Манометр  ", "specs": {"класс": 1.5, "IP": "", "ok": true}}'.encode())
    assert p.name == "Манометр"
    assert p.specs == {"класс": "1.5", "IP": "", "ok": "да"}
    assert p.manufacturer == "" and p.description == ""


@pytest.mark.parametrize("body, status, text", [
    (b"", 400, "Пустой запрос"),
    (b"{\"name\": ", 400, "Некорректный JSON"),
    (b"\xff\xfe\x00", 400, ""),
    (b"[1, 2]", 400, "JSON-объект"),
    (b'{"manufacturer": "X"}', 422, "name: обязательное поле"),
    (b'{"name": ""}', 422, "name: не может быть пустым"),
    (b'{"name": "X", "price": 1}', 422, "price: неизвестное поле"),
    (b'{"name": "X", "specs": ["a"]}', 422, "specs должен быть объектом"),
    (b'{"name": "X", "specs": {"a": {"b": 1}}}', 422, "строкой, числом или списком"),
])
def test_bad_input_has_clear_error(body, status, text):
    with pytest.raises(ApiError) as e:
        parse_product(body)
    assert e.value.status == status
    assert text in " ".join([e.value.message, *e.value.details])


def test_null_fields_become_empty():
    p = parse_product(b'{"name": "X", "manufacturer": null, "specs": null, "description": null}')
    assert (p.manufacturer, p.specs, p.description) == ("", {}, "")


def test_complete_product_has_no_gaps():
    assert find_gaps(ProductInput(**PRODUCT)) == []


def test_gaps_are_reported():
    gaps = find_gaps(ProductInput(name="X", specs={"питание": ""}, description="Прибор предназначен..."))
    text = "\n".join(gaps)
    assert "производитель" in text
    assert "«питание»: значение не указано" in text
    assert "многоточием" in text


def test_empty_specs_and_description_are_reported():
    text = "\n".join(find_gaps(ProductInput(name="X", manufacturer="Y")))
    assert "Нет характеристик" in text and "Нет описания" in text
