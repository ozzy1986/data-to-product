"""Сборка зависимостей из настроек — в одном месте для API и CLI."""
from .config import Settings
from .generator import CardGenerator
from .llm.ollama import OllamaClient


def build_generator(settings: Settings) -> CardGenerator:
    llm = OllamaClient(settings.llm_url, settings.llm_model, timeout=settings.llm_timeout,
                       temperature=settings.llm_temperature, keep_alive=settings.llm_keep_alive,
                       num_ctx=settings.llm_num_ctx)
    return CardGenerator(llm, repairs=settings.llm_repairs, cache_size=settings.cache_size)
