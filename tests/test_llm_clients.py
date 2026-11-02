"""Адаптеры LLM против поддельного HTTP-сервера: формат запроса, разбор ответа, толкование ошибок."""
import json

import httpx
import pytest

from app.config import Settings
from app.factory import build_llm
from app.llm import LLMError, LLMUnavailable
from app.llm.ollama import OllamaClient
from app.llm.openai import OpenAIClient

SCHEMA = {"type": "object", "properties": {"seo_title": {"type": "string"}}}
CARD = {"seo_title": "Манометр DM 02"}


def server(*responses: httpx.Response):
    """MockTransport, отдающий ответы по очереди и запоминающий запросы."""
    queue, seen = list(responses), []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0)

    return httpx.MockTransport(handle), seen


def openai_reply(content) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


def openai(*responses, key="sk-test"):
    transport, seen = server(*responses)
    return OpenAIClient("https://api.example.com/v1/", "gpt-test", key, transport=transport), seen


def test_openai_request_and_answer():
    llm, seen = openai(openai_reply(json.dumps(CARD, ensure_ascii=False)))
    assert llm.generate_json("Системный.", "Товар.", SCHEMA) == CARD
    req = seen[0]
    body = json.loads(req.content)
    assert req.url == "https://api.example.com/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer sk-test"
    assert body["model"] == "gpt-test" and body["response_format"] == {"type": "json_object"}
    assert body["messages"][0]["content"].startswith("Системный.") and '"seo_title"' in body["messages"][0]["content"]
    assert body["messages"][1] == {"role": "user", "content": "Товар."}


def test_openai_without_key_sends_no_auth_header():
    llm, seen = openai(openai_reply("{}"), key="")
    llm.generate_json("s", "u", SCHEMA)
    assert "authorization" not in seen[0].headers


def test_openai_retries_without_temperature_when_model_rejects_it():
    llm, seen = openai(httpx.Response(400, json={"error": {"message": "Unsupported value: 'temperature'"}}),
                       openai_reply("{}"))
    assert llm.generate_json("s", "u", SCHEMA) == {}
    assert "temperature" in json.loads(seen[0].content) and "temperature" not in json.loads(seen[1].content)


@pytest.mark.parametrize("response, error, retryable", [
    (httpx.Response(401, json={"error": "bad key"}), LLMUnavailable, False),
    (httpx.Response(404, json={"error": "no model"}), LLMUnavailable, False),
    (httpx.Response(429, json={"error": "rate limit"}), LLMError, True),
    (httpx.Response(503, text="overloaded"), LLMError, True),
    (httpx.Response(400, json={"error": "bad request"}), LLMError, False),
    (openai_reply("не json"), LLMError, True),
    (openai_reply("[1, 2]"), LLMError, True),
    (httpx.Response(200, json={"unexpected": True}), LLMError, True),
])
def test_openai_errors_are_classified(response, error, retryable):
    llm, _ = openai(response)
    with pytest.raises(error) as e:
        llm.generate_json("s", "u", SCHEMA)
    assert e.value.retryable is retryable


def test_unreachable_api_is_unavailable_and_timeout_is_not_retried():
    def down(request):
        raise httpx.ConnectError("refused")

    def slow(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(LLMUnavailable):
        OpenAIClient("http://x/v1", "m", transport=httpx.MockTransport(down)).generate_json("s", "u", SCHEMA)
    with pytest.raises(LLMError) as e:
        OpenAIClient("http://x/v1", "m", transport=httpx.MockTransport(slow)).generate_json("s", "u", SCHEMA)
    assert not e.value.retryable


def test_openai_health_checks_models_endpoint():
    llm, seen = openai(httpx.Response(200, json={"data": []}))
    assert llm.is_up() and seen[0].url.path == "/v1/models"


def test_ollama_request_and_answer():
    transport, seen = server(httpx.Response(200, json={"message": {"content": json.dumps(CARD)}}))
    llm = OllamaClient("http://127.0.0.1:11434", "gemma3:4b", transport=transport)
    assert llm.generate_json("s", "u", SCHEMA) == CARD
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/api/chat" and body["format"] == SCHEMA and body["stream"] is False


def test_ollama_retries_without_think_for_old_models():
    transport, seen = server(httpx.Response(400, json={"error": "think value not supported"}),
                             httpx.Response(200, json={"message": {"content": "{}"}}))
    OllamaClient("http://o", "m", transport=transport).generate_json("s", "u", SCHEMA)
    assert "think" in json.loads(seen[0].content) and "think" not in json.loads(seen[1].content)


def test_factory_picks_client_by_provider():
    assert isinstance(build_llm(Settings(llm_provider="ollama")), OllamaClient)
    llm = build_llm(Settings(llm_provider="openai", llm_url="https://api.openai.com/v1", llm_model="gpt-x"))
    assert isinstance(llm, OpenAIClient) and llm.model == "gpt-x"
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        build_llm(Settings(llm_provider="nope"))


def test_api_key_is_hidden_from_settings_repr():
    assert "sk-secret" not in repr(Settings(llm_api_key="sk-secret"))
