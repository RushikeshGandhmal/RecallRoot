from __future__ import annotations

import json
from typing import Any, cast

import httpx
import pytest
from opentelemetry.trace import Span

from recallgraph.agent.decision_provider import (
    DecisionMetadata,
    FallbackDecisionProvider,
    OllamaDecisionProvider,
    build_decision_provider,
    decision_request_attributes,
    decision_span_name,
)
from recallgraph.config import Settings

UNSAFE_MEMORY = "Refunds below INR 50,000 can be processed automatically."


def _ollama_response(
    *,
    approval_required: bool = False,
    reason_code: str = "automatic_allowed",
    content: str | None = None,
    prompt_tokens: object = 31,
    output_tokens: object = 7,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "llama3.2:3b",
            "message": {
                "role": "assistant",
                "content": content
                if content is not None
                else json.dumps(
                    {
                        "approval_required": approval_required,
                        "reason_code": reason_code,
                    }
                ),
            },
            "prompt_eval_count": prompt_tokens,
            "eval_count": output_tokens,
        },
    )


def _provider(handler: httpx.MockTransport) -> OllamaDecisionProvider:
    return OllamaDecisionProvider(
        base_url="http://ollama.test",
        model="llama3.2:3b",
        timeout_seconds=2,
        transport=handler,
    )


def test_ollama_uses_strict_local_chat_schema_and_records_safe_metadata() -> None:
    observed: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["headers"] = dict(request.headers)
        observed["body"] = json.loads(request.content)
        return _ollama_response()

    provider = _provider(httpx.MockTransport(handler))
    result = provider.decide(UNSAFE_MEMORY, 35_000)

    assert result.decision.approval_required is False
    assert result.metadata.provider == "ollama"
    assert result.metadata.fallback is False
    assert result.metadata.input_tokens == 31
    assert result.metadata.output_tokens == 7
    assert observed["url"] == "http://ollama.test/api/chat"
    assert "authorization" not in observed["headers"]
    assert observed["body"]["stream"] is False
    assert observed["body"]["think"] is False
    assert observed["body"]["options"] == {"temperature": 0, "seed": 42}
    assert observed["body"]["format"]["additionalProperties"] is False
    assert observed["body"]["format"]["required"] == [
        "approval_required",
        "reason_code",
    ]

    recorded = json.dumps(
        {
            "tool": result.metadata.tool_result(),
            "span": result.metadata.span_attributes(),
        }
    )
    assert UNSAFE_MEMORY not in recorded
    assert "Operative memory" not in recorded
    assert result.metadata.span_attributes()["gen_ai.usage.input_tokens"] == 31


@pytest.mark.parametrize(
    ("handler", "expected_reason"),
    [
        (
            lambda _: _ollama_response(content="not-json"),
            "invalid_response",
        ),
        (
            lambda _: _ollama_response(
                approval_required=False,
                reason_code="approval_required",
            ),
            "invalid_response",
        ),
        (
            lambda _: httpx.Response(500, json={"error": "failed"}),
            "provider_error",
        ),
    ],
)
def test_ollama_failures_use_deterministic_fallback(
    handler: Any,
    expected_reason: str,
) -> None:
    provider = FallbackDecisionProvider(_provider(httpx.MockTransport(handler)))

    result = provider.decide(UNSAFE_MEMORY, 35_000)

    assert result.decision.approval_required is False
    assert result.metadata.requested_provider == "ollama"
    assert result.metadata.provider == "deterministic"
    assert result.metadata.fallback is True
    assert result.metadata.fallback_reason == expected_reason
    assert result.metadata.model == "llama3.2:3b"


@pytest.mark.parametrize(
    ("error_factory", "expected_reason"),
    [
        (
            lambda request: httpx.ReadTimeout("slow", request=request),
            "timeout",
        ),
        (
            lambda request: httpx.ConnectError("offline", request=request),
            "unavailable",
        ),
    ],
)
def test_ollama_transport_failures_are_categorized_without_error_text(
    error_factory: Any,
    expected_reason: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error_factory(request)

    provider = FallbackDecisionProvider(_provider(httpx.MockTransport(handler)))
    result = provider.decide(UNSAFE_MEMORY, 35_000)

    assert result.metadata.fallback_reason == expected_reason
    serialized = json.dumps(result.metadata.tool_result())
    assert "slow" not in serialized
    assert "offline" not in serialized
    assert UNSAFE_MEMORY not in serialized


def test_invalid_token_counts_are_omitted() -> None:
    provider = _provider(
        httpx.MockTransport(lambda _: _ollama_response(prompt_tokens=True, output_tokens="-1"))
    )

    result = provider.decide(UNSAFE_MEMORY, 35_000)

    assert result.metadata.input_tokens is None
    assert result.metadata.output_tokens is None
    assert "gen_ai.usage.input_tokens" not in result.metadata.span_attributes()
    assert "gen_ai.usage.output_tokens" not in result.metadata.span_attributes()


def test_deterministic_is_the_default_provider() -> None:
    provider = build_decision_provider(Settings(_env_file=None))

    result = provider.decide(UNSAFE_MEMORY, 35_000)

    assert provider.requested_provider == "deterministic"
    assert decision_span_name(provider) == "resolve refund decision"
    assert decision_request_attributes(provider) == {
        "recallgraph.decision.requested_provider": "deterministic",
        "gen_ai.operation.name": "execute",
    }
    assert result.metadata.tool_result()["fallback"] is False
    assert result.metadata.provider == "deterministic"


def test_ollama_provider_factory_and_span_attributes() -> None:
    settings = Settings(
        _env_file=None,
        decision_provider="ollama",
        ollama_base_url="http://ollama.test",
        ollama_model="model-test",
    )
    provider = build_decision_provider(
        settings,
        transport=httpx.MockTransport(lambda _: _ollama_response()),
    )
    attributes = decision_request_attributes(provider)

    assert decision_span_name(provider) == "chat model-test"
    assert attributes == {
        "recallgraph.decision.requested_provider": "ollama",
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "ollama",
        "gen_ai.request.model": "model-test",
    }


def test_metadata_applies_only_safe_operational_attributes() -> None:
    metadata = DecisionMetadata(
        requested_provider="ollama",
        provider="deterministic",
        model="model-test",
        response_model="model-test-q4",
        fallback=True,
        fallback_reason="invalid_response",
        latency_ms=12.5,
        input_tokens=22,
        output_tokens=4,
    )

    class RecordingSpan:
        def __init__(self) -> None:
            self.attributes: dict[str, object] = {}

        def set_attribute(self, name: str, value: object) -> None:
            self.attributes[name] = value

    span = RecordingSpan()
    metadata.apply_to_span(cast(Span, span))

    assert span.attributes == metadata.span_attributes()
    assert span.attributes["recallgraph.decision.fallback"] is True
    assert span.attributes["gen_ai.response.model"] == "model-test-q4"
