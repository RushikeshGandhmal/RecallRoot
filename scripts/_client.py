"""Small, dependency-free JSON clients shared by operator scripts."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, NoReturn
from urllib import error, request

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


@dataclass(slots=True)
class ServiceError(RuntimeError):
    """A service returned an error or an unusable response."""

    service: str
    message: str
    status: int | None = None
    body: str | None = None

    def __str__(self) -> str:
        status = f" (HTTP {self.status})" if self.status is not None else ""
        detail = f": {self.body}" if self.body else ""
        return f"{self.service}{status}: {self.message}{detail}"


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ServiceError("configuration", f"{name} must be numeric") from exc


def request_json(
    method: str,
    path: str,
    *,
    payload: JsonValue | None = None,
    base_url: str | None = None,
    headers: dict[str, str] | None = None,
    service: str = "RecallRoot API",
    timeout: float | None = None,
) -> JsonValue:
    """Send one JSON request and return its decoded body."""

    root = (base_url or os.getenv("API_URL", "http://localhost:8000")).rstrip("/")
    url = path if path.startswith(("http://", "https://")) else f"{root}/{path.lstrip('/')}"
    body = None
    all_headers = {"accept": "application/json", **(headers or {})}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        all_headers["content-type"] = "application/json"

    http_request = request.Request(url, data=body, headers=all_headers, method=method.upper())
    request_timeout = timeout or env_float("DEMO_HTTP_TIMEOUT_SECONDS", 15.0)
    try:
        with request.urlopen(http_request, timeout=request_timeout) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise ServiceError(service, "request failed", exc.code, raw[:2_000]) from exc
    except error.URLError as exc:
        raise ServiceError(service, f"cannot reach {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ServiceError(service, f"request to {url} timed out") from exc

    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ServiceError(service, "response was not valid JSON", body=raw[:2_000]) from exc


def print_json(value: JsonValue) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def unwrap_data(value: JsonValue) -> JsonValue:
    """Remove common API envelopes without discarding ordinary dictionaries."""

    if isinstance(value, dict):
        for key in ("data", "result"):
            if key in value and len(value) <= 3:
                return value[key]
    return value


def list_from(value: JsonValue, *keys: str) -> list[dict[str, Any]]:
    """Extract a list of objects from a list or a conventional response envelope."""

    unwrapped = unwrap_data(value)
    if isinstance(unwrapped, list):
        return [item for item in unwrapped if isinstance(item, dict)]
    if isinstance(unwrapped, dict):
        for key in keys:
            candidate = unwrapped.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
    return []


def nested(value: JsonValue, *paths: Iterable[str]) -> Any:
    """Return the first value found at one of the supplied key paths."""

    for path in paths:
        current: Any = value
        for key in path:
            if not isinstance(current, dict) or key not in current:
                break
            current = current[key]
        else:
            return current
    return None


def scalar_items(value: JsonValue, prefix: str = "") -> list[tuple[str, Any]]:
    """Flatten scalar JSON fields for response-shape-tolerant assertions."""

    output: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            output.extend(scalar_items(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            output.extend(scalar_items(item, f"{prefix}[{index}]"))
    else:
        output.append((prefix, value))
    return output


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)
