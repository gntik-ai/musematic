"""T076 — unit tests for the dual-secret Stripe webhook verifier."""

from __future__ import annotations

import hmac
import json
import time
from hashlib import sha256

import pytest

from platform.billing.providers.exceptions import BillingWebhookSignatureError
from platform.billing.providers.stripe.secrets import WebhookSecretPair
from platform.billing.providers.stripe.webhook_signing import verify_stripe_signature


def _make_signed_event(
    secret: str,
    *,
    event_id: str = "evt_test_1",
    event_type: str = "customer.subscription.created",
    timestamp: int | None = None,
) -> tuple[bytes, str]:
    """Construct a payload + Stripe-Signature header signed with `secret`.

    Mirrors Stripe's signature scheme so we can drive the verifier without
    a real Stripe SDK round-trip.
    """
    timestamp = timestamp or int(time.time())
    payload = json.dumps(
        {
            "id": event_id,
            "type": event_type,
            "created": timestamp,
            "data": {"object": {"id": "sub_test_1", "customer": "cus_test_1"}},
        }
    ).encode("utf-8")
    signed_payload = f"{timestamp}.".encode() + payload
    signature = hmac.new(secret.encode("utf-8"), signed_payload, sha256).hexdigest()
    sig_header = f"t={timestamp},v1={signature}"
    return payload, sig_header


def test_active_secret_verifies() -> None:
    secret = "whsec_test_active"
    payload, sig = _make_signed_event(secret)
    secrets = WebhookSecretPair(active=secret, previous=None)

    event = verify_stripe_signature(payload, sig, secrets)

    assert event.id == "evt_test_1"
    assert event.type == "customer.subscription.created"
    assert event.payload.get("id") == "sub_test_1"
    assert event.raw == payload


def test_previous_secret_verifies_during_rotation() -> None:
    active = "whsec_test_new"
    previous = "whsec_test_old"
    payload, sig = _make_signed_event(previous)
    secrets = WebhookSecretPair(active=active, previous=previous)

    event = verify_stripe_signature(payload, sig, secrets)

    assert event.id == "evt_test_1"


def test_neither_secret_verifies_raises_signature_error() -> None:
    payload, sig = _make_signed_event("whsec_attacker")
    secrets = WebhookSecretPair(
        active="whsec_active",
        previous="whsec_previous",
    )

    with pytest.raises(BillingWebhookSignatureError):
        verify_stripe_signature(payload, sig, secrets)


def test_missing_signature_header_raises_signature_error() -> None:
    secrets = WebhookSecretPair(active="whsec_active", previous=None)
    with pytest.raises(BillingWebhookSignatureError):
        verify_stripe_signature(b"{}", "", secrets)


def test_tampered_payload_rejected() -> None:
    secret = "whsec_active"
    payload, sig = _make_signed_event(secret)
    tampered = payload + b"  "
    secrets = WebhookSecretPair(active=secret, previous=None)

    with pytest.raises(BillingWebhookSignatureError):
        verify_stripe_signature(tampered, sig, secrets)


def test_replay_outside_tolerance_rejected() -> None:
    secret = "whsec_active"
    old_ts = int(time.time()) - 10_000  # well outside tolerance
    payload, sig = _make_signed_event(secret, timestamp=old_ts)
    secrets = WebhookSecretPair(active=secret, previous=None)

    with pytest.raises(BillingWebhookSignatureError):
        verify_stripe_signature(payload, sig, secrets, tolerance=300)
