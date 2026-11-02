"""Сборка зависимостей из настроек — в одном месте для API и CLI."""
from .config import Settings
from .generator import CardGenerator
from .llm import LLMClient

# Адрес и модель по умолчанию, если LLM_URL / LLM_MODEL не заданы.
DEFAULTS = {
    "ollama": ("http://127.0.0.1:11434", "gemma3:4b"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "anthropic": ("", "claude-opus-5-5"),  # пустой адрес — адрес SDK
}


def build_llm(settings: Settings) -> LLMClient:
    if settings.llm_provider not in DEFAULTS:
        raise ValueError(f"LLM_PROVIDER={settings.llm_provider!r}: допустимо {', '.join(DEFAULTS)}")
    default_url, default_model = DEFAULTS[settings.llm_provider]
    url, model = settings.llm_url or default_url, settings.llm_model or default_model
    # SDK провайдера импортируется, только если он выбран: серверу с Ollama он не нужен.
    if settings.llm_provider == "ollama":
        from .llm.ollama import OllamaClient
        return OllamaClient(url, model, timeout=settings.llm_timeout, temperature=settings.llm_temperature,
                            keep_alive=settings.llm_keep_alive, num_ctx=settings.llm_num_ctx)
    if settings.llm_provider == "openai":
        from .llm.openai import OpenAIClient
        return OpenAIClient(url, model, settings.llm_api_key, timeout=settings.llm_timeout,
                            temperature=settings.llm_temperature)
    from .llm.claude import ClaudeClient
    return ClaudeClient(model, settings.llm_api_key, base_url=url, timeout=settings.llm_timeout)


def build_generator(settings: Settings) -> CardGenerator:
    return CardGenerator(build_llm(settings), repairs=settings.llm_repairs, cache_size=settings.cache_size)
