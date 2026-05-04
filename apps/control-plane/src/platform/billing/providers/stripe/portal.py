"""UPD-052 — Stripe Customer Portal session helper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.billing.providers.protocol import PortalSession
from platform.billing.providers.stripe.client import StripeClient
from platform.common.logging import get_logger

LOGGER = get_logger(__name__)


async def create_portal_session(
    client: StripeClient,
    *,
    customer_id: str,
    return_url: str,
) -> PortalSession:
    session = await client.call(
        "billing_portal.session.create",
        lambda: client.stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        ),
    )
    url = str(session["url"])
    LOGGER.info(
        "billing.stripe_portal_session_created",
        customer_id=customer_id,
    )
    return PortalSession(
        url=url,
        # Stripe Portal sessions are short-lived (~5 min); we don't track
        # the precise expiry, but expose a conservative ~5 min for callers
        # that want a hint.
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
