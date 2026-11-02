import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.generator import CardGenerator
from app.llm import LLMError, LLMUnavailable
from app.main import create_app
from app.models import ProductInput
from tests.fakes import PRODUCT, FakeLLM, answer


def client(*responses, **settings) -> TestClient:
    llm = FakeLLM(*responses)
    return TestClient(create_app(CardGenerator(llm), Settings(**settings)))


def test_generate_returns_card_json_and_markdown():
    r = client(answer()).post("/api/generate", json=PRODUCT)
    assert r.status_code == 200
    data = r.json()
    assert set(data) >= {"card", "missing", "warnings", "markdown"}
    assert data["card"]["specs"][0] == {"name": "Диапазон измерений", "value": "0–1,6 МПа", "source": "input"}
    assert r.headers["cache-control"] == "no-store"


def test_bad_json_is_400_with_message():
    r = client().post("/api/generate", content=b"{oops", headers={"content-type": "application/json"})
    assert r.status_code == 400 and "Некорректный JSON" in r.json()["error"]


def test_invalid_product_is_422_with_details():
    r = client().post("/api/generate", json={"name": "", "specs": "x"})
    assert r.status_code == 422
    assert any(d.startswith("name") for d in r.json()["details"])


def test_too_large_body_is_413():
    big = json.dumps({"name": "X", "description": "a" * 2000})
    r = client(max_body_bytes=1000).post("/api/generate", content=big)
    assert r.status_code == 413


def test_llm_down_is_503():
    r = client(LLMUnavailable("LLM недоступна")).post("/api/generate", json=PRODUCT)
    assert r.status_code == 503 and "недоступна" in r.json()["error"]


def test_llm_error_is_502():
    r = client(LLMError("timeout")).post("/api/generate", json=PRODUCT)
    assert r.status_code == 502


def test_full_queue_is_503():
    r = client(queue_limit=0).post("/api/generate", json=PRODUCT)
    assert r.status_code == 503 and "занята" in r.json()["error"]


def test_health_reports_llm_state():
    data = client().get("/api/health").json()
    assert data == {"status": "ok", "llm": "up", "model": "fake"}


def test_examples_are_served():
    r = client().get("/api/examples")
    assert r.status_code == 200 and isinstance(r.json(), list)


def test_unknown_api_route_is_json_404():
    assert client().get("/api/nope").status_code == 404


def test_cached_card_skips_full_queue():
    gen = CardGenerator(FakeLLM(answer()))
    gen.generate(ProductInput(**PRODUCT))
    c = TestClient(create_app(gen, Settings(queue_limit=0)))
    assert c.post("/api/generate", json=PRODUCT).status_code == 200
