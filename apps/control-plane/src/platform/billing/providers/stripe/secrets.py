"""UPD-052 — Stripe secret loader.

Reads ``secret/data/musematic/{env}/_platform/billing/stripe/{api-key,webhook-secret}``
via the existing :class:`SecretProvider`. Returns the API key plus the active
and previous webhook signing secrets in the rotation-safe shape required by
the webhook ingress (research R2).

Fail-closed semantics (rule 39): any Vault unavailability raises
:class:`BillingSecretsUnavailableError` so the webhook router and the upgrade
endpoint can return 503 cleanly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from platform.billing.providers.exceptions import BillingSecretsUnavailableError
from platform.common.config import PlatformSettings
from platform.common.logging import get_logger
from platform.common.secret_provider import SecretProvider

LOGGER = get_logger(__name__)


def stripe_api_key_path(environment: str) -> str:
    """Return the Vault path of the Stripe API key for the given environment."""
    return f"secret/data/musematic/{environment}/_platform/billing/stripe/api-key"


def stripe_webhook_secret_path(environment: str) -> str:
    """Return the Vault path of the Stripe webhook signing secret pair."""
    return f"secret/data/musematic/{environment}/_platform/billing/stripe/webhook-secret"


@dataclass(frozen=True)
class WebhookSecretPair:
    """Active + previous webhook signing secrets supporting rotation."""

    active: str
    previous: str | None


@dataclass(frozen=True)
class StripeSecrets:
    """Bundle of Stripe-side secrets resolved from Vault."""

    api_key: str
    webhook: WebhookSecretPair


class StripeSecretsLoader:
    """Lazy loader that fetches the Stripe secrets from Vault on demand.

    The loader does NOT cache — the SecretProvider has its own short-lived
    cache. This keeps secret rotation responsive (the webhook router
    re-reads on every event, the upgrade endpoint re-reads once per request).
    """

    def __init__(
        self,
        secret_provider: SecretProvider,
        settings: PlatformSettings,
    ) -> None:
        self._provider = secret_provider
        self._settings = settings

    @property
    def _environment(self) -> str:
        env = getattr(self._settings, "environment", None) or "dev"
        return str(env).lower()

    async def load(self) -> StripeSecrets:
        """Load the API key + webhook secret pair from Vault.

        Raises :class:`BillingSecretsUnavailableError` if Vault is unreachable
        or the documents are missing required keys.
        """
        env = self._environment
        try:
            api_key_doc = await self._provider.get(
                stripe_api_key_path(env),
                key="key",
                critical=True,
            )
            webhook_raw = await self._provider.get(
                stripe_webhook_secret_path(env),
                key="value",
                critical=True,
            )
        except Exception as exc:
            LOGGER.warning(
                "billing.stripe_secrets_unavailable",
                error=str(exc),
                environment=env,
            )
            raise BillingSecretsUnavailableError(
                f"Stripe secrets unavailable: {exc!s}"
            ) from exc

        webhook = _parse_webhook_secret(webhook_raw)
        return StripeSecrets(api_key=api_key_doc.strip(), webhook=webhook)


def _parse_webhook_secret(raw: str) -> WebhookSecretPair:
    """Parse the JSON-encoded webhook secret pair stored at the Vault path.

    Format: ``{"active": "whsec_...", "previous": "whsec_..." | null}``.
    Falls back to treating the raw string as the active secret with no
    previous (operator stored the secret directly without the wrapping JSON).
    """
    raw = (raw or "").strip()
    if not raw:
        raise BillingSecretsUnavailableError(
            "Stripe webhook signing secret is empty in Vault."
        )
    if raw.startswith("{"):
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BillingSecretsUnavailableError(
                f"Stripe webhook secret is not valid JSON: {exc!s}"
            ) from exc
        active = decoded.get("active")
        if not isinstance(active, str) or not active:
            raise BillingSecretsUnavailableError(
                "Stripe webhook secret JSON is missing the 'active' field."
            )
        previous = decoded.get("previous")
        if previous is not None and not isinstance(previous, str):
            raise BillingSecretsUnavailableError(
                "Stripe webhook secret 'previous' must be string or null."
            )
        return WebhookSecretPair(
            active=active,
            previous=previous if previous else None,
        )
    return WebhookSecretPair(active=raw, previous=None)
