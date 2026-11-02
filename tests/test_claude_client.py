"""Адаптер Anthropic: официальный SDK против поддельного HTTP-сервера."""
import json

import anthropic
import httpx2
import pytest

from app.llm import LLMError, LLMUnavailable
from app.llm.claude import ClaudeClient, strict_schema
from app.prompts import SCHEMA

CARD = {"seo_title": "Манометр DM 02"}


def message(text: str, stop_reason: str = "end_turn") -> httpx2.Response:
    return httpx2.Response(200, json={
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-test",
        "content": [{"type": "text", "text": text}], "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    })


def error(status: int, kind: str) -> httpx2.Response:
    return httpx2.Response(status, json={"type": "error", "error": {"type": kind, "message": "fake"}})


def claude(*responses):
    queue, seen = list(responses), []

    def handle(request):
        seen.append(request)
        return queue.pop(0)

    http = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handle))
    llm = ClaudeClient("claude-test", "sk-ant-test", http_client=http)
    llm._client = llm._client.with_options(max_retries=0)  # повторы SDK в тестах не нужны
    return llm, seen


def test_request_uses_structured_output_and_returns_json():
    llm, seen = claude(message(json.dumps(CARD, ensure_ascii=False)))
    assert llm.generate_json("Системный.", "Товар.", SCHEMA) == CARD
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/messages" and body["model"] == "claude-test"
    assert body["system"] == "Системный." and body["messages"] == [{"role": "user", "content": "Товар."}]
    assert body["output_config"]["format"]["type"] == "json_schema" and "temperature" not in body


def test_schema_is_made_strict_without_unsupported_constraints():
    schema = strict_schema(SCHEMA)
    text = json.dumps(schema)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["commercial"]["additionalProperties"] is False
    assert "minItems" not in text and "maxItems" not in text
    assert "minItems" in json.dumps(SCHEMA)  # исходная схема для Ollama не тронута


@pytest.mark.parametrize("response, exc", [
    (error(401, "authentication_error"), LLMUnavailable),
    (error(404, "not_found_error"), LLMUnavailable),
    (error(429, "rate_limit_error"), LLMError),
    (error(529, "overloaded_error"), LLMError),
    (message("не json"), LLMError),
    (message("{}", stop_reason="refusal"), LLMError),
])
def test_errors_are_classified(response, exc):
    llm, _ = claude(response)
    with pytest.raises(exc):
        llm.generate_json("s", "u", SCHEMA)


def test_health_lists_models():
    llm, seen = claude(httpx2.Response(200, json={"data": [], "has_more": False, "first_id": None, "last_id": None}))
    assert llm.is_up() and seen[0].url.path == "/v1/models"
