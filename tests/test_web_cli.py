import json

from fastapi.testclient import TestClient

from app import web
from app.cli import main

from .conftest import ROOT, FakeClient, good_draft


class _Settings:
    max_attempts = 2


def test_api_generate(monkeypatch, manometer):
    monkeypatch.setattr(web, "get_client", lambda: (FakeClient(good_draft()), _Settings()))
    client = TestClient(web.app)
    resp = client.post("/api/generate", content=json.dumps(manometer.model_dump(), ensure_ascii=False))
    assert resp.status_code == 200
    body = resp.json()
    assert body["card"]["status"] == "ok"
    assert body["markdown"].startswith("# Манометр")


def test_api_invalid_json():
    resp = TestClient(web.app).post("/api/generate", content='{"name": ')
    assert resp.status_code == 400
    assert resp.json()["error"] == "Некорректный JSON."


def test_api_llm_error(monkeypatch, manometer):
    class Broken(FakeClient):
        def generate(self, *a):
            from app.llm import LLMError

            raise LLMError("Anthropic API: неверный или отозванный API-ключ.")

    monkeypatch.setattr(web, "get_client", lambda: (Broken(), _Settings()))
    resp = TestClient(web.app).post("/api/generate", json=manometer.model_dump())
    assert resp.status_code == 502
    assert "API-ключ" in resp.json()["error"]


def test_index_served():
    resp = TestClient(web.app).get("/")
    assert resp.status_code == 200 and "Сгенерировать" in resp.text


def test_cli_invalid_json(capsys):
    assert main(["generate", str(ROOT / "examples/inputs/invalid.json")]) == 1
    assert "Некорректный JSON" in capsys.readouterr().err


def test_cli_dry_run(capsys):
    assert main(["generate", str(ROOT / "examples/inputs/products.json"), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.count("=== USER ===") == 2


def test_cli_missing_key(monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    assert main(["generate", str(ROOT / "examples/inputs/products.json")]) == 3
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
