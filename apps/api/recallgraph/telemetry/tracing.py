from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import (
    Link,
    Span,
    SpanContext,
    Status,
    StatusCode,
    TraceFlags,
    TraceState,
)
from sqlalchemy.orm import Session

from recallgraph.config import Settings
from recallgraph.ids import new_id
from recallgraph.memory.models import TelemetrySpan
from recallgraph.telemetry.attributes import safe_attributes

_configure_lock = threading.Lock()
_configured = False
_provider: TracerProvider | None = None


def _otlp_endpoint(base: str, signal: str) -> str:
    stripped = base.rstrip("/")
    if stripped.endswith(f"/v1/{signal}"):
        return stripped
    return f"{stripped}/v1/{signal}"


def _parse_headers(raw_headers: str | None) -> dict[str, str] | None:
    if not raw_headers:
        return None
    headers: dict[str, str] = {}
    for item in raw_headers.split(","):
        key, separator, value = item.partition("=")
        if separator and key.strip():
            headers[key.strip()] = value.strip()
    return headers or None


def configure_tracing(settings: Settings) -> TracerProvider:
    """Install one process-wide SDK provider; exporting is optional and non-blocking."""

    global _configured, _provider
    with _configure_lock:
        if _configured and _provider is not None:
            return _provider
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": settings.telemetry_service_name,
                    "deployment.environment.name": settings.environment,
                    "service.version": "0.1.0",
                }
            )
        )
        if settings.otel_exporter_otlp_endpoint:
            exporter = OTLPSpanExporter(
                endpoint=_otlp_endpoint(settings.otel_exporter_otlp_endpoint, "traces"),
                headers=_parse_headers(settings.otel_exporter_otlp_headers),
                timeout=settings.otel_export_timeout_seconds,
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _provider = provider
        _configured = True
        return provider


def tracer() -> trace.Tracer:
    return trace.get_tracer("recallgraph", "0.1.0")


def current_span_ids() -> tuple[str, str, int]:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return "0" * 32, "0" * 16, 0
    return f"{context.trace_id:032x}", f"{context.span_id:016x}", int(context.trace_flags)


def reconstruct_span_context(trace_id: str, span_id: str, trace_flags: int = 1) -> SpanContext:
    """Rehydrate a persisted remote span context for an actual cross-trace Link."""

    if len(trace_id) != 32 or len(span_id) != 16:
        raise ValueError("Persisted trace and span IDs must be 32 and 16 hex characters")
    try:
        trace_id_int = int(trace_id, 16)
        span_id_int = int(span_id, 16)
    except ValueError as exc:
        raise ValueError("Persisted trace and span IDs must be hexadecimal") from exc
    context = SpanContext(
        trace_id=trace_id_int,
        span_id=span_id_int,
        is_remote=True,
        trace_flags=TraceFlags(trace_flags),
        trace_state=TraceState(),
    )
    if not context.is_valid:
        raise ValueError("Persisted trace or span context is invalid")
    return context


def persisted_link(trace_id: str, span_id: str, trace_flags: int = 1) -> Link:
    return Link(reconstruct_span_context(trace_id, span_id, trace_flags))


def _link_payload(link: Link) -> dict[str, Any]:
    context = link.context
    return {
        "trace_id": f"{context.trace_id:032x}",
        "span_id": f"{context.span_id:016x}",
        "trace_flags": int(context.trace_flags),
        "attributes": dict(link.attributes or {}),
    }


@contextmanager
def recorded_span(
    session: Session,
    name: str,
    *,
    attributes: dict[str, object] | None = None,
    links: list[Link] | None = None,
) -> Generator[Span, None, None]:
    """Create an OTel span and persist a queryable semantic evidence copy.

    The local copy is deliberately telemetry-shaped and is only used when SigNoz
    cannot answer a graph query. It is not derived from operational joins.
    """

    clean_attributes = safe_attributes(attributes or {})
    clean_links = links or []
    parent_context = trace.get_current_span().get_span_context()
    started_at = datetime.now(UTC)
    failure: BaseException | None = None

    with tracer().start_as_current_span(
        name,
        attributes=clean_attributes,
        links=clean_links,
    ) as span:
        try:
            yield span
        except BaseException as exc:
            failure = exc
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        finally:
            context = span.get_span_context()
            if context.is_valid:
                evidence = TelemetrySpan(
                    id=new_id("tspan"),
                    trace_id=f"{context.trace_id:032x}",
                    span_id=f"{context.span_id:016x}",
                    parent_span_id=(
                        f"{parent_context.span_id:016x}" if parent_context.is_valid else None
                    ),
                    name=name,
                    started_at=started_at,
                    ended_at=datetime.now(UTC),
                    status="error" if failure else "ok",
                    attributes=clean_attributes,
                    links=[_link_payload(link) for link in clean_links],
                )
                session.add(evidence)
                session.flush()
