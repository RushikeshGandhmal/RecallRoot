#!/usr/bin/env python3
"""Validate the configured SigNoz service-account key without printing it."""

from __future__ import annotations

import os

from _client import ServiceError, fail, request_json


def main() -> None:
    api_key = os.getenv("SIGNOZ_API_KEY", "").strip()
    if not api_key:
        fail("SIGNOZ_API_KEY is empty in the root .env")

    try:
        request_json(
            "GET",
            "/api/v1/service_accounts/me",
            base_url=os.getenv("SIGNOZ_URL", "http://localhost:3301"),
            headers={"SIGNOZ-API-KEY": api_key},
            service="SigNoz service-account API",
            timeout=10,
        )
    except ServiceError as exc:
        fail(str(exc))

    print("SigNoz service-account key is valid (HTTP 200).")


if __name__ == "__main__":
    main()
