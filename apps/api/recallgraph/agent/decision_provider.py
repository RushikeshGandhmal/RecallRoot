from __future__ import annotations

import json
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Any, Literal, Protocol

import httpx
from opentelemetry.trace import Span
from pydantic import BaseModel, ConfigDict

from recallgraph.agent.policy_engine import AgentPolicyDecision, decide_from_memory
from recallgraph.config import Settings

DecisionProviderName = Literal["deterministic", "ollama"]
FallbackReason = Literal[
    "invalid_response",
    "provider_error",
    "timeout",
    "unavailable",
]

_DECISION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "approval_required": {"type": "boolean"},
        "reason_code": {
            "type": "string",
            "enum": ["automatic_allowed", "approval_required", "ambiguous_fail_safe"],
        },
    },
    "required": ["approval_required", "reason_code"],
    "additionalProperties": False,
}

_RATIONALES = {
    "automatic_allowed": "Operative memory permits this refund without manager approval",
    "approval_required": "Operative memory requires manager approval for this refund",
    "ambiguous_fail_safe": "Operative memory was ambiguous; fail-safe approval selected",
}


class _OllamaDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_required: bool
    reason_code: Literal[
        "automatic_allowed",
        "approval_required",
        "ambiguous_fail_safe",
    ]


@dataclass(frozen=True, slots=True)
class DecisionMetadata:
    requested_provider: DecisionProviderName
    provider: DecisionProviderName
    model: str | None
    response_model: str | None
    fallback: bool
    fallback_reason: FallbackReason | None
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None

    def tool_result(self) -> dict[str, object]:
        return {
            "requested_provider": self.requested_provider,
            "provider": self.provider,
            "model": self.model,
            "response_model": self.response_model,
            "fallback": self.fallback,
            "fallback_reason": self.fallback_reason,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }

    def span_attributes(self) -> dict[str, object]:
        attributes: dict[str, object] = {
            "recallgraph.decision.requested_provider": self.requested_provider,
            "recallgraph.decision.provider": self.provider,
            "recallgraph.decision.fallback": self.fallback,
            "recallgraph.decision.latency_ms": self.latency_ms,
        }
        if self.fallback_reason:
            attributes["recallgraph.decision.fallback.reason"] = self.fallback_reason
        if self.model:
            attributes["gen_ai.request.model"] = self.model
        if self.response_model:
            attributes["gen_ai.response.model"] = self.response_model
        if self.input_tokens is not None:
            attributes["gen_ai.usage.input_tokens"] = self.input_tokens
        if self.output_tokens is not None:
            attributes["gen_ai.usage.output_tokens"] = self.output_tokens
        return attributes

    def apply_to_span(self, span: Span) -> None:
        for name, value in self.span_attributes().items():
            span.set_attribute(name, value)


@dataclass(frozen=True, slots=True)
class DecisionResult:
    decision: AgentPolicyDecision
    metadata: DecisionMetadata


class DecisionProvider(Protocol):
    @property
    def requested_provider(self) -> DecisionProviderName: ...

    @property
    def requested_model(self) -> str | None: ...

    def decide(self, memory_content: str, amount: float) -> DecisionResult: ...


@dataclass(frozen=True, slots=True)
class _ProviderFailure(Exception):
    reason: FallbackReason
    latency_ms: float
    model: str | None = None
    response_model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class DeterministicDecisionProvider:
    requested_provider: DecisionProviderName = "deterministic"
    requested_model: str | None = None

    def decide(self, memory_content: str, amount: float) -> DecisionResult:
        started = perf_counter()
        decision = decide_from_memory(memory_content, amount)
        return DecisionResult(
            decision=decision,
            metadata=DecisionMetadata(
                requested_provider="deterministic",
                provider="deterministic",
                model=None,
                response_model=None,
                fallback=False,
                fallback_reason=None,
                latency_ms=_milliseconds_since(started),
            ),
        )


class OllamaDecisionProvider:
    requested_provider: DecisionProviderName = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.requested_model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def decide(self, memory_content: str, amount: float) -> DecisionResult:
        started = perf_counter()
        payload = {
            "model": self.requested_model,
            "stream": False,
            "think": False,
            "format": _DECISION_SCHEMA,
            "options": {"temperature": 0, "seed": 42},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a refund decision component. Follow only the supplied "
                        "operative memory. If it is ambiguous, require manager approval. "
                        "Return only the requested structured decision."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Refund amount: INR {amount:.2f}\nOperative memory:\n{memory_content}"
                    ),
                },
            ],
        }
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            raise _ProviderFailure(
                reason="timeout",
                latency_ms=_milliseconds_since(started),
                model=self.requested_model,
            ) from exc
        except httpx.ConnectError as exc:
            raise _ProviderFailure(
                reason="unavailable",
                latency_ms=_milliseconds_since(started),
                model=self.requested_model,
            ) from exc
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise _ProviderFailure(
                reason="provider_error",
                latency_ms=_milliseconds_since(started),
                model=self.requested_model,
            ) from exc

        if not isinstance(body, dict):
            raise _ProviderFailure(
                reason="invalid_response",
                latency_ms=_milliseconds_since(started),
                model=self.requested_model,
            )
        response_model = _optional_text(body.get("model"))
        input_tokens = _optional_nonnegative_int(body.get("prompt_eval_count"))
        output_tokens = _optional_nonnegative_int(body.get("eval_count"))
        try:
            message = body["message"]
            content = message["content"]
            if not isinstance(content, str):
                raise TypeError("Ollama message content was not text")
            parsed = _OllamaDecision.model_validate(json.loads(content))
            _validate_reason(parsed)
        except (KeyError, TypeError, ValueError) as exc:
            raise _ProviderFailure(
                reason="invalid_response",
                latency_ms=_milliseconds_since(started),
                model=self.requested_model,
                response_model=response_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ) from exc

        return DecisionResult(
            decision=AgentPolicyDecision(
                approval_required=parsed.approval_required,
                rationale=_RATIONALES[parsed.reason_code],
            ),
            metadata=DecisionMetadata(
                requested_provider="ollama",
                provider="ollama",
                model=self.requested_model,
                response_model=response_model,
                fallback=False,
                fallback_reason=None,
                latency_ms=_milliseconds_since(started),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
        )


class FallbackDecisionProvider:
    def __init__(
        self,
        primary: OllamaDecisionProvider,
        fallback: DeterministicDecisionProvider | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback or DeterministicDecisionProvider()

    @property
    def requested_provider(self) -> DecisionProviderName:
        return self.primary.requested_provider

    @property
    def requested_model(self) -> str | None:
        return self.primary.requested_model

    def decide(self, memory_content: str, amount: float) -> DecisionResult:
        started = perf_counter()
        try:
            return self.primary.decide(memory_content, amount)
        except _ProviderFailure as exc:
            fallback = self.fallback.decide(memory_content, amount)
            metadata = DecisionMetadata(
                requested_provider="ollama",
                provider="deterministic",
                model=exc.model or self.primary.requested_model,
                response_model=exc.response_model,
                fallback=True,
                fallback_reason=exc.reason,
                latency_ms=_milliseconds_since(started),
                input_tokens=exc.input_tokens,
                output_tokens=exc.output_tokens,
            )
            return replace(fallback, metadata=metadata)
        except Exception:
            fallback = self.fallback.decide(memory_content, amount)
            metadata = DecisionMetadata(
                requested_provider="ollama",
                provider="deterministic",
                model=self.primary.requested_model,
                response_model=None,
                fallback=True,
                fallback_reason="provider_error",
                latency_ms=_milliseconds_since(started),
            )
            return replace(fallback, metadata=metadata)


def build_decision_provider(
    settings: Settings,
    *,
    transport: httpx.BaseTransport | None = None,
) -> DecisionProvider:
    if settings.decision_provider == "ollama":
        return FallbackDecisionProvider(
            OllamaDecisionProvider(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                timeout_seconds=settings.ollama_timeout_seconds,
                transport=transport,
            )
        )
    return DeterministicDecisionProvider()


def decision_request_attributes(provider: DecisionProvider) -> dict[str, object]:
    attributes: dict[str, object] = {
        "recallgraph.decision.requested_provider": provider.requested_provider,
        "gen_ai.operation.name": "chat" if provider.requested_provider == "ollama" else "execute",
    }
    if provider.requested_provider == "ollama":
        attributes["gen_ai.provider.name"] = "ollama"
    if provider.requested_model:
        attributes["gen_ai.request.model"] = provider.requested_model
    return attributes


def decision_span_name(provider: DecisionProvider) -> str:
    if provider.requested_provider == "ollama" and provider.requested_model:
        return f"chat {provider.requested_model}"
    return "resolve refund decision"


def _validate_reason(decision: _OllamaDecision) -> None:
    if decision.reason_code == "automatic_allowed" and decision.approval_required:
        raise ValueError("automatic_allowed cannot require approval")
    if decision.reason_code != "automatic_allowed" and not decision.approval_required:
        raise ValueError("safe reason codes must require approval")


def _milliseconds_since(started: float) -> float:
    return round((perf_counter() - started) * 1_000, 2)


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _optional_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
