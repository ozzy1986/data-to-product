"""Настройки из переменных окружения (на сервере — shared/.env через systemd)."""
import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # ollama — локальная модель (по умолчанию); openai — любой OpenAI-совместимый API.
    llm_provider: str = os.environ.get("LLM_PROVIDER", "ollama")
    llm_url: str = os.environ.get("LLM_URL", "http://127.0.0.1:11434")
    llm_model: str = os.environ.get("LLM_MODEL", "gemma3:4b")
    # Ключ только из окружения; repr=False — чтобы не попал в логи и трейсбеки.
    llm_api_key: str = field(default=os.environ.get("LLM_API_KEY", ""), repr=False)
    llm_timeout: float = _float("LLM_TIMEOUT", 240.0)      # сек на один вызов модели
    llm_temperature: float = _float("LLM_TEMPERATURE", 0.3)
    llm_keep_alive: str = os.environ.get("LLM_KEEP_ALIVE", "30m")
    # 4096 токенов хватает промпту с повтором и целиком помещается в 4 ГБ видеопамяти ноутбука.
    llm_num_ctx: int = _int("LLM_NUM_CTX", 4096)
    # Повторные вызовы модели с замечаниями, если ответ не прошёл проверки (длины, выдуманные числа).
    llm_repairs: int = _int("LLM_REPAIRS", 2)
    # Модель одна (видеокарта ноутбука): одновременно генерируем по одной карточке,
    # остальные ждут в очереди. Слишком длинная очередь — сразу 503, а не таймаут у клиента.
    llm_concurrency: int = _int("LLM_CONCURRENCY", 1)
    queue_limit: int = _int("QUEUE_LIMIT", 4)
    cache_size: int = _int("CACHE_SIZE", 256)               # готовые карточки по хэшу входа
    max_body_bytes: int = _int("MAX_BODY_BYTES", 64_000)


settings = Settings()
