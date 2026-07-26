from __future__ import annotations

import hashlib
import re

from recallgraph.memory.models import MemoryRecord

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_KNOWN_SECRET = re.compile(
    r"\b(?:"
    r"sk-(?:ant-)?[A-Za-z0-9_-]{16,}"
    r"|github_pat_[A-Za-z0-9_]{16,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{16,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|AIza[0-9A-Za-z_-]{30,}"
    r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
    r")\b",
    re.IGNORECASE,
)
_NAMED_SECRET = re.compile(
    r"\b(?:api[_-]?key|access[_-]?token|auth(?:orization)?|password|passwd|secret|"
    r"client[_-]?secret)\b\s*[:=]\s*(?:bearer\s+)?[\"']?[^\s,\"';]+[\"']?",
    re.IGNORECASE,
)
_BEARER_TOKEN = re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_PAYMENT_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_PHONE = re.compile(r"(?<!\w)\+?(?:\d[\s().-]?){9,14}\d(?!\w)")


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sanitized_preview(content: str, limit: int = 180) -> str:
    """Create a bounded preview with common identifiers and credentials removed."""

    normalized = " ".join(content.split())
    normalized = _NAMED_SECRET.sub("[redacted-secret]", normalized)
    normalized = _BEARER_TOKEN.sub("[redacted-secret]", normalized)
    normalized = _KNOWN_SECRET.sub("[redacted-secret]", normalized)
    normalized = _EMAIL.sub("[redacted-email]", normalized)
    normalized = _PAYMENT_CARD.sub("[redacted-payment-card]", normalized)
    normalized = _PHONE.sub("[redacted-phone]", normalized)
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"


def origin_attributes(memory: MemoryRecord) -> dict[str, str | int]:
    return {
        "recallgraph.memory.id": memory.id,
        "recallgraph.memory.origin.trace_id": memory.created_trace_id,
        "recallgraph.memory.origin.span_id": memory.created_span_id,
        "recallgraph.memory.source.type": memory.source_type,
        "recallgraph.memory.source.trust": memory.source_trust,
        "recallgraph.memory.status": memory.status,
    }
