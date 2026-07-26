from __future__ import annotations

from pathlib import Path

import pytest

from recallgraph.config import Settings
from recallgraph.database import Database


def test_standard_observability_environment_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    monkeypatch.setenv("SIGNOZ_URL", "http://signoz:8080")
    monkeypatch.setenv("SIGNOZ_API_KEY", "secret")
    monkeypatch.setenv("SIGNOZ_MCP_URL", "http://mcp:8001/mcp")
    monkeypatch.setenv("RECALLGRAPH_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    monkeypatch.setenv("RECALLGRAPH_DECISION_PROVIDER", "ollama")
    monkeypatch.setenv("RECALLGRAPH_OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setenv("RECALLGRAPH_OLLAMA_MODEL", "local-model")

    settings = Settings(_env_file=None)

    assert settings.otel_exporter_otlp_endpoint == "http://collector:4318"
    assert settings.signoz_api_url == "http://signoz:8080"
    assert settings.signoz_ui_url == "http://signoz:8080"
    assert settings.signoz_api_key == "secret"
    assert settings.signoz_mcp_api_key == "secret"
    assert settings.signoz_mcp_url == "http://mcp:8001/mcp"
    assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]
    assert settings.decision_provider == "ollama"
    assert settings.ollama_base_url == "http://ollama:11434"
    assert settings.ollama_model == "local-model"


def test_sqlite_parent_directory_is_created(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "state" / "recallroot.db"
    database = Database(Settings(database_url=f"sqlite:///{database_path}"))
    try:
        database.create_schema()
        assert database_path.exists()
    finally:
        database.dispose()
