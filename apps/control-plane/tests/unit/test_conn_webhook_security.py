from __future__ import annotations

import hmac
from platform.connectors.exceptions import WebhookSignatureError
from platform.connectors.security import assert_webhook_signature, compute_hmac_sha256

import pytest


def test_webhook_signature_accepts_valid_hmac() -> None:
    payload = b'{"hello":"world"}'
    secret = "top-secret"
    signature = "sha256=" + compute_hmac_sha256(secret, payload)

    assert_webhook_signature(secret, payload, signature)


@pytest.mark.parametrize("signature_header", [None, "", "sha256=deadbeef"])
def test_webhook_signature_rejects_missing_or_invalid_hmac(signature_header: str | None) -> None:
    with pytest.raises(WebhookSignatureError):
        assert_webhook_signature("secret", b"{}", signature_header)


def test_webhook_signature_uses_timing_safe_compare(monkeypatch: pytest.MonkeyPatch) -> None:
    compared: list[tuple[str, str]] = []

    def _record(left: str, right: str) -> bool:
        compared.append((left, right))
        return True

    monkeypatch.setattr(hmac, "compare_digest", _record)
    payload = b'{"ok":true}'
    signature = "sha256=" + compute_hmac_sha256("secret", payload)

    assert_webhook_signature("secret", payload, signature)

    assert len(compared) == 1
