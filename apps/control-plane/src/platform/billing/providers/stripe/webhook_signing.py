"""UPD-052 — Stripe webhook signature verification with dual-secret rotation.

Verifies the ``Stripe-Signature`` header against both the active and the
previous webhook signing secrets stored in Vault. Returns the parsed
:class:`WebhookEvent` on success and raises
:class:`BillingWebhookSignatureError` on failure (research R2).

The signature parsing logic is delegated to ``stripe.Webhook.construct_event``
from the Stripe Python SDK — we never roll our own HMAC verifier so the
constant-time comparison and replay-window logic stay in lockstep with the
SDK.
"""

from __future__ import annotations

from datetime import UTC, datetime
from platform.billing.providers.exceptions import BillingWebhookSignatureError
from platform.billing.providers.protocol import WebhookEvent
from platform.billing.providers.stripe.secrets import WebhookSecretPair
from platform.common.logging import get_logger

LOGGER = get_logger(__name__)

# Stripe's recommended replay-window is 5 minutes; the SDK's default is 300s
# but exposing the constant lets unit tests freeze time without skew.
REPLAY_TOLERANCE_SECONDS = 300


def verify_stripe_signature(
    payload: bytes,
    signature_header: str,
    secrets: WebhookSecretPair,
    *,
    tolerance: int = REPLAY_TOLERANCE_SECONDS,
) -> WebhookEvent:
    """Verify the webhook signature against active + previous secrets.

    Try the ``active`` secret first; if it fails, retry with ``previous`` (when
    set). Both failures raise :class:`BillingWebhookSignatureError` with a
    generic message so the wrapping 401 cannot leak which secret was tried
    (rule 35 anti-enumeration analogue).
    """
    if not signature_header:
        raise BillingWebhookSignatureError("Missing Stripe-Signature header")

    try:
        import stripe
    except ImportError as exc:  # pragma: no cover — module-level optional
        raise BillingWebhookSignatureError(
            "stripe SDK is not installed; cannot verify webhook"
        ) from exc

    candidates = [secrets.active]
    if secrets.previous:
        candidates.append(secrets.previous)
    last_error: Exception | None = None
    for secret in candidates:
        try:
            event_obj = stripe.Webhook.construct_event(  # type: ignore[no-untyped-call]
                payload=payload,
                sig_header=signature_header,
                secret=secret,
                tolerance=tolerance,
            )
            return _to_webhook_event(event_obj, raw=payload)
        except stripe.error.SignatureVerificationError as exc:  # type: ignore[attr-defined]
            last_error = exc
            continue

    LOGGER.warning(
        "billing.stripe_webhook_signature_failed",
        candidates_tried=len(candidates),
    )
    raise BillingWebhookSignatureError("Invalid webhook signature") from last_error


def _to_webhook_event(event_obj: object, *, raw: bytes) -> WebhookEvent:
    """Adapt a ``stripe.Event`` into our internal :class:`WebhookEvent`."""
    event_id = str(getattr(event_obj, "id", "") or "")
    event_type = str(getattr(event_obj, "type", "") or "")
    api_version = getattr(event_obj, "api_version", None)
    created_ts = getattr(event_obj, "created", None)
    if isinstance(created_ts, int | float):
        created_at = datetime.fromtimestamp(int(created_ts), tz=UTC)
    else:
        created_at = datetime.now(UTC)
    data = getattr(event_obj, "data", None) or {}
    object_data = (
        data.get("object", data) if isinstance(data, dict) else getattr(data, "object", {})
    )
    if not isinstance(object_data, dict):
        # The Stripe SDK returns a ``StripeObject`` whose ``to_dict`` returns
        # a plain dict; fall back to that conversion when available.
        to_dict = getattr(object_data, "to_dict_recursive", None) or getattr(
            object_data, "to_dict", None
        )
        if callable(to_dict):
            object_data = to_dict()
    if not isinstance(object_data, dict):
        object_data = {}
    return WebhookEvent(
        id=event_id,
        type=event_type,
        payload=object_data,
        created_at=created_at,
        api_version=str(api_version) if api_version else None,
        raw=raw,
    )
