"""Сборка зависимостей из настроек — в одном месте для API и CLI."""
from .config import Settings
from .generator import CardGenerator
from .llm import LLMClient
from .llm.ollama import OllamaClient
from .llm.openai import OpenAIClient


def build_llm(settings: Settings) -> LLMClient:
    if settings.llm_provider == "ollama":
        return OllamaClient(settings.llm_url, settings.llm_model, timeout=settings.llm_timeout,
                            temperature=settings.llm_temperature, keep_alive=settings.llm_keep_alive,
                            num_ctx=settings.llm_num_ctx)
    if settings.llm_provider == "openai":
        return OpenAIClient(settings.llm_url, settings.llm_model, settings.llm_api_key,
                            timeout=settings.llm_timeout, temperature=settings.llm_temperature)
    raise ValueError(f"LLM_PROVIDER={settings.llm_provider!r}: допустимо ollama или openai")


def build_generator(settings: Settings) -> CardGenerator:
    return CardGenerator(build_llm(settings), repairs=settings.llm_repairs, cache_size=settings.cache_size)
