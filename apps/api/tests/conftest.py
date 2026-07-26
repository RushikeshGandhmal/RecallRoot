from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from recallgraph.config import Settings
from recallgraph.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "recallroot-test.db"
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{database_path}",
        signoz_api_url=None,
        signoz_mcp_url=None,
        otel_exporter_otlp_endpoint=None,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
