from __future__ import annotations

import pytest

from recallgraph.memory.provenance import sanitized_preview

_OPENAI_LIKE_TOKEN = "sk-" + "proj-examplecredential123456789"
_GITHUB_LIKE_TOKEN = "ghp_" + "abcdefghijklmnopqrstuvwxyz123456"
_JWT_LIKE_TOKEN = ".".join(("eyJhbGciOiJIUzI1NiJ9", "payloadvalue", "signaturevalue"))


@pytest.mark.parametrize(
    ("content", "marker", "sensitive"),
    [
        (
            "Contact alice@example.com about the refund.",
            "[redacted-email]",
            "alice@example.com",
        ),
        (
            "Call the customer at +91 98765 43210.",
            "[redacted-phone]",
            "+91 98765 43210",
        ),
        (
            "Charge card 4242 4242 4242 4242.",
            "[redacted-payment-card]",
            "4242 4242 4242 4242",
        ),
        (
            f"api_key={_OPENAI_LIKE_TOKEN}",
            "[redacted-secret]",
            _OPENAI_LIKE_TOKEN,
        ),
        (
            f"Authorization: Bearer {_JWT_LIKE_TOKEN}",
            "[redacted-secret]",
            "eyJhbGciOiJIUzI1NiJ9",
        ),
        (
            f"GitHub token {_GITHUB_LIKE_TOKEN}",
            "[redacted-secret]",
            _GITHUB_LIKE_TOKEN,
        ),
    ],
)
def test_sanitized_preview_redacts_sensitive_values(
    content: str,
    marker: str,
    sensitive: str,
) -> None:
    preview = sanitized_preview(content)

    assert marker in preview
    assert sensitive not in preview


def test_sanitized_preview_preserves_policy_amounts() -> None:
    content = "Refunds above ₹10,000 require manager approval."

    assert sanitized_preview(content) == content


def test_sanitized_preview_redacts_before_truncating() -> None:
    secret = _OPENAI_LIKE_TOKEN
    preview = sanitized_preview(f"{secret} {'context ' * 40}", limit=80)

    assert secret not in preview
    assert preview.endswith("…")
