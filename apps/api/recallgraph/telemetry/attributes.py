from __future__ import annotations

from datetime import UTC, datetime

SCENARIO = "unsafe-refund-memory"


def amount_bucket(amount: float) -> str:
    if amount < 10_000:
        return "0-10000"
    if amount < 50_000:
        return "10000-50000"
    return "50000-plus"


def memory_age_seconds(created_at: datetime) -> int:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - created_at).total_seconds()))


def safe_attributes(attributes: dict[str, object]) -> dict[str, object]:
    """Remove nulls and coerce unsupported values before sending them to OTel."""

    supported = (str, bool, int, float)
    result: dict[str, object] = {}
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, supported):
            result[key] = value
        elif isinstance(value, (list, tuple)) and all(
            isinstance(item, supported) for item in value
        ):
            result[key] = list(value)
        else:
            result[key] = str(value)
    return result
