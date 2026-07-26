from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
provision_signoz = importlib.import_module("provision_signoz")


def test_existing_dashboard_is_reconciled(monkeypatch: pytest.MonkeyPatch) -> None:
    dashboard = {"title": "RecallGraph — Agent Memory Safety", "widgets": []}
    requests: list[tuple[str, str, object | None]] = []

    monkeypatch.setattr(provision_signoz, "load_object", lambda _: dashboard)

    def fake_request(method: str, path: str, payload: object | None = None) -> object:
        requests.append((method, path, payload))
        if method == "GET":
            return {"data": [{"id": "dashboard-id", "data": {"title": dashboard["title"]}}]}
        return {"status": "success"}

    monkeypatch.setattr(provision_signoz, "signoz_request", fake_request)

    state, response = provision_signoz.provision_dashboard(dry_run=False)

    assert state == "updated"
    assert response == {"status": "success"}
    assert requests[-1] == (
        "PUT",
        "/api/v1/dashboards/dashboard-id",
        dashboard,
    )


def test_existing_alert_is_reconciled(monkeypatch: pytest.MonkeyPatch) -> None:
    alert = {"alert": "High-risk agent action influenced by unsafe memory"}
    requests: list[tuple[str, str, object | None]] = []

    monkeypatch.setattr(provision_signoz, "render_alert", lambda _: alert)

    def fake_request(method: str, path: str, payload: object | None = None) -> object:
        requests.append((method, path, payload))
        if method == "GET":
            return {"data": [{"id": "rule-id", "alert": alert["alert"]}]}
        return {}

    monkeypatch.setattr(provision_signoz, "signoz_request", fake_request)

    state, _ = provision_signoz.provision_alert("RecallRoot Local Sink", dry_run=False)

    assert state == "updated"
    assert requests[-1] == ("PUT", "/api/v2/rules/rule-id", alert)
