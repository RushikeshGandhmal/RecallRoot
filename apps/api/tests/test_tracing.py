from __future__ import annotations

import pytest

from recallgraph.telemetry.tracing import persisted_link, reconstruct_span_context


def test_persisted_context_round_trip() -> None:
    trace_id = "0123456789abcdef0123456789abcdef"
    span_id = "0123456789abcdef"
    context = reconstruct_span_context(trace_id, span_id, 1)
    assert f"{context.trace_id:032x}" == trace_id
    assert f"{context.span_id:016x}" == span_id
    assert context.is_remote is True
    assert context.is_valid is True
    assert int(context.trace_flags) == 1
    assert persisted_link(trace_id, span_id, 1).context == context


@pytest.mark.parametrize(
    ("trace_id", "span_id"),
    [("bad", "0" * 16), ("0" * 32, "bad"), ("z" * 32, "1" * 16)],
)
def test_invalid_persisted_context_is_rejected(trace_id: str, span_id: str) -> None:
    with pytest.raises(ValueError):
        reconstruct_span_context(trace_id, span_id)
