from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from recallgraph.graph.models import SpanEvidence


class CausalEvidenceMismatch(ValueError):
    """Raised when telemetry exists but does not belong to the requested incident."""


@dataclass(frozen=True, slots=True)
class ValidatedCausalSpans:
    memory_write: SpanEvidence
    memory_use: SpanEvidence
    tool: SpanEvidence
    outcome: SpanEvidence


def derive_memory_origin(
    spans: list[SpanEvidence],
    *,
    action_trace_id: str,
    memory_id: str,
) -> tuple[str, str]:
    uses = [
        span
        for span in spans
        if span.trace_id == action_trace_id
        and span.name == "recallgraph.memory.use"
        and span.attributes.get("recallgraph.memory.id") == memory_id
    ]
    if len(uses) != 1:
        observed = [
            {
                "trace_id": span.trace_id,
                "memory_id": span.attributes.get("recallgraph.memory.id"),
            }
            for span in spans
            if span.name == "recallgraph.memory.use"
        ]
        raise CausalEvidenceMismatch(
            "expected exactly one memory-use span for "
            f"memory {memory_id} in action trace {action_trace_id}; observed {observed}"
        )
    attributes = uses[0].attributes
    origin_trace_id = attributes.get("recallgraph.memory.origin.trace_id")
    origin_span_id = attributes.get("recallgraph.memory.origin.span_id")
    if not isinstance(origin_trace_id, str) or not isinstance(origin_span_id, str):
        raise CausalEvidenceMismatch("memory-use span omitted its persisted origin trace/span IDs")
    if len(origin_trace_id) != 32 or len(origin_span_id) != 16:
        raise CausalEvidenceMismatch("memory-use span contained invalid origin trace/span IDs")
    return origin_trace_id, origin_span_id


def _require_attributes(
    label: str,
    attributes: dict[str, Any],
    names: tuple[str, ...],
) -> None:
    missing = [name for name in names if name not in attributes or attributes[name] in (None, "")]
    if missing:
        raise CausalEvidenceMismatch(
            f"{label} span omitted required facts: {', '.join(sorted(missing))}"
        )


def validate_causal_evidence(
    spans: list[SpanEvidence],
    *,
    action_id: str,
    action_type: str,
    memory_id: str,
    action_trace_id: str,
    origin_trace_id: str,
    origin_span_id: str,
) -> ValidatedCausalSpans:
    observed_origin = derive_memory_origin(
        spans,
        action_trace_id=action_trace_id,
        memory_id=memory_id,
    )
    expected_origin = (origin_trace_id, origin_span_id)
    if observed_origin != expected_origin:
        raise CausalEvidenceMismatch(
            "memory-use origin mismatch: "
            f"expected {origin_trace_id}/{origin_span_id}, "
            f"observed {observed_origin[0]}/{observed_origin[1]}"
        )

    memory_use = next(
        span
        for span in spans
        if span.trace_id == action_trace_id
        and span.name == "recallgraph.memory.use"
        and span.attributes.get("recallgraph.memory.id") == memory_id
    )
    tool_candidates = [
        span
        for span in spans
        if span.trace_id == action_trace_id
        and span.name == f"execute_tool {action_type}"
        and span.attributes.get("recallgraph.action.id") == action_id
        and span.attributes.get("recallgraph.action.type") == action_type
        and span.attributes.get("recallgraph.memory.id") == memory_id
    ]
    if len(tool_candidates) != 1:
        raise CausalEvidenceMismatch(
            f"required {action_type} tool span for action {action_id} was missing or ambiguous"
        )
    outcome_candidates = [
        span
        for span in spans
        if span.trace_id == action_trace_id
        and span.name == "recallgraph.outcome.evaluate"
        and span.attributes.get("recallgraph.action.id") == action_id
        and span.attributes.get("recallgraph.action.type") == action_type
        and span.attributes.get("recallgraph.memory.id") == memory_id
    ]
    if len(outcome_candidates) != 1:
        raise CausalEvidenceMismatch(
            f"required policy-outcome span for action {action_id} was missing or ambiguous"
        )
    write_candidates = [
        span
        for span in spans
        if span.trace_id == origin_trace_id
        and span.span_id == origin_span_id
        and span.name == "recallgraph.memory.write"
        and span.attributes.get("recallgraph.memory.id") == memory_id
        and span.attributes.get("recallgraph.memory.operation") == "write"
    ]
    if len(write_candidates) != 1:
        raise CausalEvidenceMismatch(
            "exact origin memory-write span was missing: "
            f"{origin_trace_id}/{origin_span_id} for {memory_id}"
        )

    memory_write = write_candidates[0]
    tool = tool_candidates[0]
    outcome = outcome_candidates[0]
    _require_attributes(
        "memory-use",
        memory_use.attributes,
        (
            "recallgraph.memory.source.name",
            "recallgraph.memory.source.trust",
            "recallgraph.memory.sanitized_preview",
            "recallgraph.memory.origin.trace_id",
            "recallgraph.memory.origin.span_id",
        ),
    )
    _require_attributes(
        "memory-write",
        memory_write.attributes,
        (
            "recallgraph.memory.source.name",
            "recallgraph.memory.source.trust",
            "recallgraph.memory.sanitized_preview",
        ),
    )
    _require_attributes(
        "policy-outcome",
        outcome.attributes,
        ("recallgraph.approval.required", "recallgraph.policy.outcome"),
    )
    return ValidatedCausalSpans(
        memory_write=memory_write,
        memory_use=memory_use,
        tool=tool,
        outcome=outcome,
    )
