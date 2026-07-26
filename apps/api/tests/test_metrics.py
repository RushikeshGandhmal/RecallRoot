from __future__ import annotations

from typing import Any

import pytest
from opentelemetry.sdk.metrics import Counter
from opentelemetry.sdk.metrics.export import AggregationTemporality

from recallgraph.config import Settings
from recallgraph.telemetry import metrics as telemetry_metrics


class _Instrument:
    pass


class _Meter:
    def create_counter(self, *_: object, **__: object) -> _Instrument:
        return _Instrument()

    def create_histogram(self, *_: object, **__: object) -> _Instrument:
        return _Instrument()

    def create_gauge(self, *_: object, **__: object) -> _Instrument:
        return _Instrument()


class _MeterProvider:
    def __init__(self, **_: object) -> None:
        pass

    def get_meter(self, *_: object, **__: object) -> _Meter:
        return _Meter()


def test_counter_export_uses_delta_temporality(monkeypatch: pytest.MonkeyPatch) -> None:
    exporter_options: dict[str, Any] = {}

    class CapturingExporter:
        def __init__(self, **options: Any) -> None:
            exporter_options.update(options)

    monkeypatch.setattr(telemetry_metrics, "_configured", False)
    monkeypatch.setattr(telemetry_metrics, "_instruments", {})
    monkeypatch.setattr(telemetry_metrics, "OTLPMetricExporter", CapturingExporter)
    monkeypatch.setattr(telemetry_metrics, "MeterProvider", _MeterProvider)
    monkeypatch.setattr(
        telemetry_metrics,
        "PeriodicExportingMetricReader",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(telemetry_metrics.metrics, "set_meter_provider", lambda _: None)
    monkeypatch.setattr(telemetry_metrics.metrics, "get_meter", lambda *_: _Meter())
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

    telemetry_metrics.configure_metrics(Settings(_env_file=None))

    assert exporter_options["preferred_temporality"] == {Counter: AggregationTemporality.DELTA}


def test_risk_score_is_recorded_as_a_gauge(monkeypatch: pytest.MonkeyPatch) -> None:
    observations: list[tuple[int, dict[str, str]]] = []

    class CapturingGauge:
        def set(self, value: int, attributes: dict[str, str]) -> None:
            observations.append((value, attributes))

    monkeypatch.setattr(telemetry_metrics, "_instruments", {"risk_score": CapturingGauge()})

    telemetry_metrics.record_risk_score(90, "untrusted")

    assert observations == [(90, {"trust": "untrusted"})]
