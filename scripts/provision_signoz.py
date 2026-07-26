#!/usr/bin/env python3
"""Provision RecallRoot's dashboard and alert into an existing SigNoz instance."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from _client import JsonValue, ServiceError, fail, list_from, print_json, request_json

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = ROOT / "infra" / "signoz" / "recallroot-dashboard.json"
ALERT_PATH = ROOT / "infra" / "signoz" / "alert-rule.template.json"
ALERT_CHANNEL_TOKEN = "__SIGNOZ_ALERT_CHANNEL__"


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ServiceError("SigNoz provisioning", f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ServiceError("SigNoz provisioning", f"{path} must contain a JSON object")
    return value


def signoz_request(method: str, path: str, payload: JsonValue | None = None) -> JsonValue:
    api_key = os.getenv("SIGNOZ_API_KEY", "").strip()
    if not api_key:
        raise ServiceError(
            "SigNoz provisioning",
            "SIGNOZ_API_KEY is required; create a service-account key in SigNoz Settings",
        )
    return request_json(
        method,
        path,
        payload=payload,
        base_url=os.getenv("SIGNOZ_URL", "http://localhost:3301"),
        headers={"SIGNOZ-API-KEY": api_key},
        service="SigNoz API",
        timeout=30,
    )


def named_resources(response: JsonValue, *keys: str) -> list[dict[str, Any]]:
    resources = list_from(response, *keys)
    if resources:
        return resources
    if isinstance(response, dict):
        data = response.get("data")
        if isinstance(data, dict):
            return list_from(data, *keys)
    return []


def find_resource(
    resources: list[dict[str, Any]], expected: str, *fields: str
) -> dict[str, Any] | None:
    def field_value(resource: dict[str, Any], path: str) -> object:
        current: object = resource
        for part in path.split("."):
            if not isinstance(current, dict):
                return ""
            current = current.get(part, "")
        return current

    return next(
        (
            resource
            for resource in resources
            if any(str(field_value(resource, field)).strip() == expected for field in fields)
        ),
        None,
    )


def resource_id(resource: dict[str, Any], kind: str) -> str:
    identifier = str(resource.get("id") or resource.get("uuid") or "").strip()
    if not identifier:
        raise ServiceError("SigNoz provisioning", f"existing {kind} is missing its ID")
    return identifier


def validate_channel(channel: str) -> None:
    response = signoz_request("GET", "/api/v1/channels")
    channels = named_resources(response, "channels", "items")
    names = sorted(
        {
            str(item.get("name", "")).strip()
            for item in channels
            if str(item.get("name", "")).strip()
        }
    )
    if channel not in names:
        available = ", ".join(names) if names else "none"
        raise ServiceError(
            "SigNoz provisioning",
            f"SIGNOZ_ALERT_CHANNEL={channel!r} does not exist; available channels: {available}",
        )


def render_alert(channel: str) -> dict[str, Any]:
    alert = load_object(ALERT_PATH)
    thresholds = alert["condition"]["thresholds"]["spec"]
    for threshold in thresholds:
        threshold["channels"] = [channel]
    if ALERT_CHANNEL_TOKEN in json.dumps(alert):
        raise ServiceError("SigNoz provisioning", "alert channel substitution was incomplete")
    return alert


def provision_dashboard(*, dry_run: bool) -> tuple[str, JsonValue | None]:
    dashboard = load_object(DASHBOARD_PATH)
    title = str(dashboard["title"])
    current = signoz_request("GET", "/api/v1/dashboards")
    existing = find_resource(
        named_resources(current, "dashboards", "items"),
        title,
        "data.title",
        "title",
        "name",
    )
    if existing is not None:
        if dry_run:
            return "would-update", dashboard
        identifier = resource_id(existing, "dashboard")
        return "updated", signoz_request("PUT", f"/api/v1/dashboards/{identifier}", dashboard)
    if dry_run:
        return "would-create", dashboard
    return "created", signoz_request("POST", "/api/v1/dashboards", dashboard)


def provision_alert(channel: str, *, dry_run: bool) -> tuple[str, JsonValue | None]:
    alert = render_alert(channel)
    name = str(alert["alert"])
    current = signoz_request("GET", "/api/v2/rules")
    existing = find_resource(named_resources(current, "rules", "items"), name, "alert", "name")
    if existing is not None:
        if dry_run:
            return "would-update", alert
        identifier = resource_id(existing, "alert rule")
        return "updated", signoz_request("PUT", f"/api/v2/rules/{identifier}", alert)
    if dry_run:
        return "would-create", alert
    return "created", signoz_request("POST", "/api/v2/rules", alert)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--dashboard-only", action="store_true")
    selection.add_argument("--alert-only", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate prerequisites and print payloads without creating resources",
    )
    args = parser.parse_args()

    create_dashboard = not args.alert_only
    create_alert = not args.dashboard_only
    channel = os.getenv("SIGNOZ_ALERT_CHANNEL", "").strip()

    try:
        if create_alert:
            if not channel:
                raise ServiceError(
                    "SigNoz provisioning",
                    "SIGNOZ_ALERT_CHANNEL is required for alert provisioning",
                )
            validate_channel(channel)

        results: dict[str, JsonValue] = {}
        if create_dashboard:
            state, response = provision_dashboard(dry_run=args.dry_run)
            results["dashboard"] = {"state": state, "response": response}
        if create_alert:
            state, response = provision_alert(channel, dry_run=args.dry_run)
            results["alert"] = {"state": state, "response": response}
    except (KeyError, TypeError) as exc:
        fail(f"SigNoz provisioning: malformed local asset: {exc}")
    except ServiceError as exc:
        fail(str(exc))

    print_json(results)


if __name__ == "__main__":
    main()
