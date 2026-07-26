from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from recallgraph.config import Settings
from recallgraph.routes import health


def test_signoz_alert_webhook_accepts_local_notification(client: TestClient) -> None:
    response = client.post(
        "/integrations/signoz-alerts",
        json={
            "status": "firing",
            "alerts": [{"labels": {"project": "recallgraph"}}],
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "message": "Local SigNoz alert notification received.",
    }


def test_readiness_exposes_default_decision_provider_without_a_model_key(
    client: TestClient,
) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["checks"]["decision_engine"] == {
        "status": "ready",
        "detail": "Deterministic fail-safe decision provider is active.",
    }
    assert payload["llm"] == {
        "provider": "deterministic",
        "model": None,
        "fallback_provider": "deterministic",
        "local_only": True,
    }


def test_ollama_readiness_requires_the_configured_local_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        decision_provider="ollama",
        ollama_base_url="http://ollama.test",
        ollama_model="llama3.2:3b",
    )

    def installed(_: str, *, timeout: float) -> httpx.Response:
        assert timeout == 2.0
        return httpx.Response(
            200,
            request=httpx.Request("GET", "http://ollama.test/api/tags"),
            json={"models": [{"name": "llama3.2:3b"}]},
        )

    monkeypatch.setattr(health.httpx, "get", installed)
    assert health._ollama_readiness(settings).model_dump() == {
        "status": "ready",
        "detail": "Local Ollama model llama3.2:3b is ready.",
    }

    def missing(_: str, *, timeout: float) -> httpx.Response:
        return httpx.Response(
            200,
            request=httpx.Request("GET", "http://ollama.test/api/tags"),
            json={"models": [{"model": "another-model"}]},
        )

    monkeypatch.setattr(health.httpx, "get", missing)
    assert health._ollama_readiness(settings).model_dump() == {
        "status": "unconfigured",
        "detail": "Pull the configured local Ollama model: llama3.2:3b.",
    }
