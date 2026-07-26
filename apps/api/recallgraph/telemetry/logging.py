from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace
from sqlalchemy.orm import Session

from recallgraph.config import Settings
from recallgraph.ids import new_id
from recallgraph.memory.models import TelemetryLog

_logger = logging.getLogger("recallgraph.events")
_configure_lock = threading.Lock()
_configured = False
_provider: Any | None = None


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
        }
        event_fields = getattr(record, "event_fields", None)
        if isinstance(event_fields, dict):
            payload.update(event_fields)
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(settings: Settings) -> Any | None:
    global _configured, _provider
    with _configure_lock:
        if _configured:
            return _provider
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        _logger.handlers.clear()
        _logger.addHandler(handler)
        _logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)
        _logger.propagate = False

        # Attach the Python logging bridge to the OTel LoggerProvider when an
        # exporter is configured. Import lazily because the logs API is evolving.
        if settings.otel_exporter_otlp_endpoint:
            try:
                from opentelemetry import _logs
                from opentelemetry.exporter.otlp.proto.http._log_exporter import (
                    OTLPLogExporter,
                )
                from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
                from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
                from opentelemetry.sdk.resources import Resource

                from recallgraph.telemetry.tracing import _otlp_endpoint, _parse_headers

                provider = LoggerProvider(
                    resource=Resource.create(
                        {
                            "service.name": settings.telemetry_service_name,
                            "deployment.environment.name": settings.environment,
                        }
                    )
                )
                provider.add_log_record_processor(
                    BatchLogRecordProcessor(
                        OTLPLogExporter(
                            endpoint=_otlp_endpoint(settings.otel_exporter_otlp_endpoint, "logs"),
                            headers=_parse_headers(settings.otel_exporter_otlp_headers),
                            timeout=settings.otel_export_timeout_seconds,
                        )
                    )
                )
                _logs.set_logger_provider(provider)
                _provider = provider
                otel_handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
                _logger.addHandler(otel_handler)
            except (ImportError, RuntimeError, TypeError, ValueError):
                _logger.warning("OpenTelemetry log exporter could not be configured")
        _configured = True
        return _provider


def emit_event(session: Session, event: str, **fields: object) -> None:
    context = trace.get_current_span().get_span_context()
    trace_id = f"{context.trace_id:032x}" if context.is_valid else None
    span_id = f"{context.span_id:016x}" if context.is_valid else None
    payload: dict[str, Any] = {
        "event": event,
        "trace_id": trace_id,
        "span_id": span_id,
        **fields,
    }
    _logger.info(event, extra={"event_fields": payload})
    session.add(
        TelemetryLog(
            id=new_id("tlog"),
            event=event,
            trace_id=trace_id,
            span_id=span_id,
            payload=payload,
        )
    )
    session.flush()
