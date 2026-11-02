"""Настройки из переменных окружения и файла .env в корне проекта (на сервере — shared/.env через systemd)."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """Простые строки KEY=value; уже заданные переменные окружения важнее файла."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Если LLM_API_KEY не задан, берём привычную переменную провайдера.
_KEY_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")


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
    # ollama — локальная модель; openai — любой OpenAI-совместимый API; anthropic — Claude.
    llm_provider: str = _PROVIDER
    llm_url: str = os.environ.get("LLM_URL", "")      # пусто — адрес провайдера по умолчанию
    llm_model: str = os.environ.get("LLM_MODEL", "")  # пусто — модель провайдера по умолчанию
    # Ключ только из окружения; repr=False — чтобы не попал в логи и трейсбеки.
    llm_api_key: str = field(repr=False, default=os.environ.get("LLM_API_KEY")
                             or os.environ.get(_KEY_ENV.get(_PROVIDER, ""), ""))
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
