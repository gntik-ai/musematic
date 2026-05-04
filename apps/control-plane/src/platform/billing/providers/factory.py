"""UPD-052 — PaymentProvider factory.

Selects between the real Stripe implementation (`StripePaymentProvider`) and
the in-memory stub (`StubPaymentProvider`) based on
``PlatformSettings.billing_stripe.provider``. Used by FastAPI dependencies and
the webhook router to obtain a provider instance per request.
"""

from __future__ import annotations

from platform.billing.providers.protocol import PaymentProvider
from platform.billing.providers.stub_provider import StubPaymentProvider
from platform.common.config import PlatformSettings
from platform.common.logging import get_logger

LOGGER = get_logger(__name__)


def build_payment_provider(settings: PlatformSettings) -> PaymentProvider:
    """Return the active PaymentProvider per configuration.

    The Stripe provider is loaded lazily so unit tests that never set up
    Vault don't need to import the Stripe SDK or its dependencies.
    """
    provider_name = settings.billing_stripe.provider.lower()
    if provider_name == "stripe":
        from platform.billing.providers.stripe.provider import StripePaymentProvider

        return StripePaymentProvider(settings=settings)
    if provider_name == "stub":
        return StubPaymentProvider()
    LOGGER.warning(
        "billing.unknown_provider_falling_back_to_stub",
        configured_provider=provider_name,
    )
    return StubPaymentProvider()
