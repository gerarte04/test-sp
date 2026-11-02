"""Настройки приложения из переменных окружения (и необязательного файла .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# .env подхватывается, если он есть; переменные окружения имеют приоритет.
load_dotenv(override=False)


class ConfigError(Exception):
    """Ошибка конфигурации: не задан ключ, неизвестный провайдер и т.п."""


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} должен быть целым числом, получено: {raw!r}") from exc


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} должен быть числом, получено: {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    provider: str
    api_key: str
    model: str
    base_url: str | None
    timeout: float
    max_attempts: int
    temperature: float

    @classmethod
    def from_env(cls) -> "Settings":
        provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
        if provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
            model = os.getenv("ANTHROPIC_MODEL", "").strip() or "claude-sonnet-5-5"
            base_url = None
        elif provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            model = os.getenv("OPENAI_MODEL", "").strip() or "gpt-4o-mini"
            base_url = os.getenv("OPENAI_BASE_URL", "").strip() or "https://api.openai.com/v1"
        else:
            raise ConfigError(
                f"Неизвестный LLM_PROVIDER={provider!r}. Допустимо: anthropic, openai."
            )

        return cls(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=_float("LLM_TIMEOUT", 60.0),
            max_attempts=max(1, _int("LLM_MAX_ATTEMPTS", 2)),
            temperature=_float("LLM_TEMPERATURE", 0.2),
        )
