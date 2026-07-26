from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import Counter, MeterProvider
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource

from recallgraph.config import Settings
from recallgraph.telemetry.tracing import _otlp_endpoint, _parse_headers

_configure_lock = threading.Lock()
_configured = False
_instruments: dict[str, object] = {}
_provider: MeterProvider | None = None


def configure_metrics(settings: Settings) -> MeterProvider:
    global _configured, _instruments, _provider
    with _configure_lock:
        if _configured and _provider is not None:
            return _provider
        readers = []
        if settings.otel_exporter_otlp_endpoint:
            exporter = OTLPMetricExporter(
                endpoint=_otlp_endpoint(settings.otel_exporter_otlp_endpoint, "metrics"),
                headers=_parse_headers(settings.otel_exporter_otlp_headers),
                timeout=settings.otel_export_timeout_seconds,
                preferred_temporality={Counter: AggregationTemporality.DELTA},
            )
            readers.append(PeriodicExportingMetricReader(exporter, export_interval_millis=15_000))
        provider = MeterProvider(
            resource=Resource.create(
                {
                    "service.name": settings.telemetry_service_name,
                    "deployment.environment.name": settings.environment,
                }
            ),
            metric_readers=readers,
        )
        metrics.set_meter_provider(provider)
        _provider = provider
        meter = metrics.get_meter("recallgraph", "0.1.0")
        _instruments = {
            "memory_uses": meter.create_counter(
                "recallgraph.memory.uses", description="Durable memory retrievals"
            ),
            "policy_violations": meter.create_counter(
                "recallgraph.policy.violations", description="Policy-violating actions"
            ),
            "sensitive_actions": meter.create_counter(
                "recallgraph.sensitive.actions", description="Sensitive agent actions"
            ),
            "risk_score": meter.create_gauge(
                "recallgraph.memory.risk.score", unit="1", description="Memory risk score"
            ),
            "replays": meter.create_counter(
                "recallgraph.replays", description="Agent request replays"
            ),
            "investigation_duration": meter.create_histogram(
                "recallgraph.investigation.duration",
                unit="ms",
                description="Causal investigation duration",
            ),
            "causal_depth": meter.create_histogram(
                "recallgraph.causal_chain.depth", unit="1", description="Causal graph depth"
            ),
        }
        _configured = True
        return provider


def _instrument(name: str) -> object | None:
    return _instruments.get(name)


def count_memory_use(trust: str, status: str) -> None:
    instrument = _instrument("memory_uses")
    if instrument:
        instrument.add(1, {"trust": trust, "status": status})  # type: ignore[attr-defined]


def count_policy_violation(action_type: str, source_trust: str) -> None:
    instrument = _instrument("policy_violations")
    if instrument:
        instrument.add(  # type: ignore[attr-defined]
            1, {"action_type": action_type, "source_trust": source_trust}
        )


def count_sensitive_action(outcome: str) -> None:
    instrument = _instrument("sensitive_actions")
    if instrument:
        instrument.add(1, {"outcome": outcome})  # type: ignore[attr-defined]


def record_risk_score(score: int, trust: str) -> None:
    instrument = _instrument("risk_score")
    if instrument:
        instrument.set(score, {"trust": trust})  # type: ignore[attr-defined]


def count_replay(result: str) -> None:
    instrument = _instrument("replays")
    if instrument:
        instrument.add(1, {"result": result})  # type: ignore[attr-defined]


def record_investigation_duration(milliseconds: float, result: str) -> None:
    instrument = _instrument("investigation_duration")
    if instrument:
        instrument.record(milliseconds, {"result": result})  # type: ignore[attr-defined]


def record_causal_depth(depth: int, scenario: str) -> None:
    instrument = _instrument("causal_depth")
    if instrument:
        instrument.record(depth, {"scenario": scenario})  # type: ignore[attr-defined]


@dataclass(frozen=True, slots=True)
class TelemetryRuntime:
    providers: tuple[Any, ...]

    def shutdown(self, timeout_millis: int = 5_000) -> None:
        for provider in self.providers:
            force_flush = getattr(provider, "force_flush", None)
            if callable(force_flush):
                force_flush(timeout_millis=timeout_millis)
        for provider in reversed(self.providers):
            shutdown = getattr(provider, "shutdown", None)
            if callable(shutdown):
                shutdown()


def configure_telemetry(settings: Settings) -> TelemetryRuntime:
    from recallgraph.telemetry.logging import configure_logging
    from recallgraph.telemetry.tracing import configure_tracing

    providers = [
        configure_tracing(settings),
        configure_logging(settings),
        configure_metrics(settings),
    ]
    return TelemetryRuntime(tuple(provider for provider in providers if provider is not None))
