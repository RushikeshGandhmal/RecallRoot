#!/usr/bin/env python3
"""Verify that the configured Ollama model makes both demo decisions safely."""

from __future__ import annotations

from recallgraph.agent.decision_provider import build_decision_provider
from recallgraph.agent.prompts import TRUSTED_POLICY, UNSAFE_MEMORY
from recallgraph.config import Settings


def main() -> None:
    settings = Settings()
    if settings.decision_provider != "ollama":
        raise SystemExit(
            "RECALLGRAPH_DECISION_PROVIDER is not ollama; deterministic mode needs no model check."
        )

    provider = build_decision_provider(settings)
    unsafe = provider.decide(UNSAFE_MEMORY, 35_000)
    repaired = provider.decide(TRUSTED_POLICY, 35_000)
    results = (unsafe, repaired)
    if any(result.metadata.provider != "ollama" or result.metadata.fallback for result in results):
        reasons = ", ".join(
            result.metadata.fallback_reason or "unknown"
            for result in results
            if result.metadata.fallback
        )
        raise SystemExit(f"Ollama preflight used the deterministic fallback: {reasons}")
    if unsafe.decision.approval_required or not repaired.decision.approval_required:
        raise SystemExit(
            "Ollama returned decisions that do not match the controlled demo contract."
        )

    total_input = sum(result.metadata.input_tokens or 0 for result in results)
    total_output = sum(result.metadata.output_tokens or 0 for result in results)
    print(
        f"Ollama model {settings.ollama_model} passed: unsafe=auto-refund, "
        f"repaired=approval-required, tokens={total_input}+{total_output}."
    )


if __name__ == "__main__":
    main()
