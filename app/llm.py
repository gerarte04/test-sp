"""Клиенты LLM. Возвращают уже разобранный JSON-ответ (dict) либо LLMError."""

from __future__ import annotations

import json
import re
from typing import Protocol

import httpx

from .config import ConfigError, Settings
from .prompts import TOOL_NAME


class LLMError(Exception):
    """Ошибка обращения к модели, понятная пользователю."""


class LLMClient(Protocol):
    provider: str
    model: str

    def generate(self, system: str, user: str, schema: dict) -> dict: ...


class AnthropicClient:
    """Anthropic Messages API. Структурированный ответ получаем через принудительный tool use."""

    provider = "anthropic"

    def __init__(self, settings: Settings):
        import anthropic

        if not settings.api_key:
            raise ConfigError("Не задан ANTHROPIC_API_KEY (переменная окружения или файл .env).")
        self._anthropic = anthropic
        self.model = settings.model
        self._client = anthropic.Anthropic(
            api_key=settings.api_key, timeout=settings.timeout, max_retries=2
        )

    def generate(self, system: str, user: str, schema: dict) -> dict:
        a = self._anthropic
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[
                    {
                        "name": TOOL_NAME,
                        "description": "Сохранить черновик карточки товара.",
                        "input_schema": schema,
                    }
                ],
                tool_choice={"type": "tool", "name": TOOL_NAME},
            )
        except a.AuthenticationError as exc:
            raise LLMError("Anthropic API: неверный или отозванный API-ключ.") from exc
        except a.PermissionDeniedError as exc:
            raise LLMError("Anthropic API: нет доступа к модели или ресурсу.") from exc
        except a.NotFoundError as exc:
            raise LLMError(f"Anthropic API: модель {self.model!r} не найдена.") from exc
        except a.RateLimitError as exc:
            raise LLMError("Anthropic API: превышен лимит запросов, повторите позже.") from exc
        except a.APITimeoutError as exc:
            raise LLMError("Anthropic API: превышено время ожидания ответа.") from exc
        except a.APIConnectionError as exc:
            raise LLMError("Anthropic API: нет соединения с сервером.") from exc
        except a.APIStatusError as exc:
            raise LLMError(f"Anthropic API вернул ошибку {exc.status_code}: {exc.message}") from exc
        except a.APIError as exc:
            raise LLMError(f"Anthropic API: {exc}") from exc

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == TOOL_NAME:
                if isinstance(block.input, dict):
                    return block.input
        if response.stop_reason == "max_tokens":
            raise LLMError("Ответ модели обрезан по лимиту токенов.")
        raise LLMError("Модель не вернула структурированный ответ.")


class OpenAICompatibleClient:
    """Любой OpenAI-совместимый Chat Completions API (OpenAI, Ollama, LM Studio, vLLM)."""

    provider = "openai"

    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.model = settings.model
        self.temperature = settings.temperature
        self._url = (settings.base_url or "").rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"
        elif "api.openai.com" in self._url:
            raise ConfigError("Не задан OPENAI_API_KEY (переменная окружения или файл .env).")
        self._http = http or httpx.Client(timeout=settings.timeout, headers=headers)

    def generate(self, system: str, user: str, schema: dict) -> dict:
        system_full = (
            system
            + "\n\nОтвет верни ОДНИМ JSON-объектом без пояснений и без markdown, строго по схеме:\n"
            + json.dumps(schema, ensure_ascii=False)
        )
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_full},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = self._http.post(self._url, json=body)
        except httpx.TimeoutException as exc:
            raise LLMError("LLM API: превышено время ожидания ответа.") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM API: нет соединения ({exc.__class__.__name__}).") from exc

        if resp.status_code == 401:
            raise LLMError("LLM API: неверный API-ключ.")
        if resp.status_code == 429:
            raise LLMError("LLM API: превышен лимит запросов, повторите позже.")
        if resp.status_code >= 400:
            raise LLMError(f"LLM API вернул ошибку {resp.status_code}: {resp.text[:300]}")

        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM API вернул ответ неожиданного формата.") from exc
        return parse_json_object(content)


def parse_json_object(text: str | None) -> dict:
    """Достаёт JSON-объект из текста модели (терпимо к ```json-обёртке и пояснениям)."""
    if not text:
        raise LLMError("Модель вернула пустой ответ.")
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("Модель вернула не JSON.") from None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError("Модель вернула некорректный JSON.") from exc
    if not isinstance(data, dict):
        raise LLMError("Модель вернула JSON, но не объект.")
    return data


def make_client(settings: Settings | None = None) -> LLMClient:
    settings = settings or Settings.from_env()
    if settings.provider == "anthropic":
        return AnthropicClient(settings)
    return OpenAICompatibleClient(settings)
