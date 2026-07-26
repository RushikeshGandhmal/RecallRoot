from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Request

from recallgraph.config import Settings
from recallgraph.database import Database
from recallgraph.schemas import (
    HealthResponse,
    LLMReadiness,
    ReadinessCheck,
    ReadinessResponse,
)

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    database: Database = request.app.state.database
    settings: Settings = request.app.state.settings
    database.check()
    return HealthResponse(
        status="ok",
        service="recallroot-api",
        version="0.1.0",
        database="ok",
        telemetry_export=("configured" if settings.otel_exporter_otlp_endpoint else "local-only"),
    )


def _http_check(url: str, *, timeout: float) -> tuple[bool, str]:
    try:
        response = httpx.get(url, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return False, f"Connection failed: {type(exc).__name__}"
    return True, f"HTTP {response.status_code}"


def _mcp_liveness_url(mcp_url: str) -> str:
    parsed = urlsplit(mcp_url)
    return urlunsplit((parsed.scheme, parsed.netloc, "/livez", "", ""))


def _ollama_readiness(settings: Settings) -> ReadinessCheck:
    try:
        response = httpx.get(
            f"{settings.ollama_base_url.rstrip('/')}/api/tags",
            timeout=min(settings.ollama_timeout_seconds, 2.0),
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError:
        return ReadinessCheck(
            status="unavailable",
            detail="Ollama is selected but its local API is unavailable.",
        )
    except ValueError:
        return ReadinessCheck(
            status="unavailable",
            detail="Ollama returned an invalid model-list response.",
        )

    models = payload.get("models") if isinstance(payload, dict) else None
    installed = (
        {
            str(item.get("name") or item.get("model"))
            for item in models
            if isinstance(item, dict) and (item.get("name") or item.get("model"))
        }
        if isinstance(models, list)
        else set()
    )
    if settings.ollama_model not in installed:
        return ReadinessCheck(
            status="unconfigured",
            detail=f"Pull the configured local Ollama model: {settings.ollama_model}.",
        )
    return ReadinessCheck(
        status="ready",
        detail=f"Local Ollama model {settings.ollama_model} is ready.",
    )


@router.get("/ready", response_model=ReadinessResponse)
def readiness(request: Request) -> ReadinessResponse:
    database: Database = request.app.state.database
    settings: Settings = request.app.state.settings
    checks: dict[str, ReadinessCheck] = {}

    database.check()
    checks["api"] = ReadinessCheck(status="ready", detail="API and database are responsive.")
    checks["otlp"] = ReadinessCheck(
        status="ready" if settings.otel_exporter_otlp_endpoint else "unconfigured",
        detail=(
            "OTLP/HTTP export is configured."
            if settings.otel_exporter_otlp_endpoint
            else "Set OTEL_EXPORTER_OTLP_ENDPOINT to export telemetry."
        ),
    )

    if not settings.signoz_api_url:
        checks["signoz"] = ReadinessCheck(
            status="unconfigured",
            detail="SigNoz API URL is not configured.",
        )
    else:
        reachable, detail = _http_check(
            f"{settings.signoz_api_url.rstrip('/')}/api/v1/health",
            timeout=min(settings.signoz_timeout_seconds, 2.0),
        )
        if not reachable:
            checks["signoz"] = ReadinessCheck(status="unavailable", detail=detail)
        elif not settings.signoz_api_key:
            checks["signoz"] = ReadinessCheck(
                status="unconfigured",
                detail="SigNoz is reachable, but its service-account API key is not configured.",
            )
        else:
            checks["signoz"] = ReadinessCheck(
                status="ready",
                detail="SigNoz is reachable and Query Builder authentication is configured.",
            )

    if not settings.signoz_mcp_url:
        checks["mcp"] = ReadinessCheck(
            status="unconfigured",
            detail="SigNoz MCP URL is not configured.",
        )
    else:
        reachable, detail = _http_check(
            _mcp_liveness_url(settings.signoz_mcp_url),
            timeout=min(settings.signoz_timeout_seconds, 2.0),
        )
        checks["mcp"] = ReadinessCheck(
            status="ready" if reachable else "unavailable",
            detail=("SigNoz MCP is reachable." if reachable else detail),
        )

    checks["decision_engine"] = (
        _ollama_readiness(settings)
        if settings.decision_provider == "ollama"
        else ReadinessCheck(
            status="ready",
            detail="Deterministic fail-safe decision provider is active.",
        )
    )
    required = ("api", "otlp", "signoz", "mcp", "decision_engine")
    overall = "ready" if all(checks[name].status == "ready" for name in required) else "degraded"
    return ReadinessResponse(
        status=overall,
        checks=checks,
        llm=LLMReadiness(
            provider=settings.decision_provider,
            model=settings.ollama_model if settings.decision_provider == "ollama" else None,
            fallback_provider="deterministic",
            local_only=True,
        ),
    )
