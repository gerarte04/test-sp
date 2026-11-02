import json

import httpx
import pytest

from app.config import ConfigError, Settings
from app.llm import AnthropicClient, LLMError, OpenAICompatibleClient


def _settings(**kw) -> Settings:
    base = dict(
        provider="openai",
        api_key="test",
        model="m",
        base_url="http://llm.local/v1",
        timeout=5,
        max_attempts=2,
        temperature=0.2,
    )
    base.update(kw)
    return Settings(**base)


def _client(handler) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(_settings(), http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_openai_compatible_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"message": {"content": '```json\n{"seo_title": "x"}\n```'}}]})

    assert _client(handler).generate("sys", "user", {}) == {"seo_title": "x"}


@pytest.mark.parametrize(
    "status, text",
    [(401, "API-ключ"), (429, "лимит"), (500, "ошибку 500")],
)
def test_openai_compatible_http_errors(status, text):
    with pytest.raises(LLMError, match=text):
        _client(lambda r: httpx.Response(status, text="boom")).generate("s", "u", {})


def test_openai_compatible_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMError, match="время ожидания"):
        _client(handler).generate("s", "u", {})


def test_openai_compatible_bad_payload():
    with pytest.raises(LLMError, match="неожиданного формата"):
        _client(lambda r: httpx.Response(200, json={"oops": 1})).generate("s", "u", {})


def test_anthropic_requires_key():
    with pytest.raises(ConfigError):
        AnthropicClient(_settings(provider="anthropic", api_key=""))


def test_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gigachat")
    with pytest.raises(ConfigError):
        Settings.from_env()
