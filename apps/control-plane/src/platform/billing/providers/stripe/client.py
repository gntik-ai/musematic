"""UPD-052 — Stripe SDK client wrapper.

Initializes the global ``stripe`` module with the active API key and pins
the API version per request via the ``Stripe-Version`` header. Wraps the
synchronous SDK calls in :func:`asyncio.to_thread` so the FastAPI request
loop stays unblocked, and adds a small exponential-backoff retry for the
two transient errors that should be retried (``RateLimitError`` and
``APIConnectionError``).

Sensitive values (api key, webhook signing secrets) are NEVER printed or
logged — the wrapper limits structured-logger keys to public data only.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from platform.billing.providers.exceptions import ProviderUnavailable
from platform.common.config import PlatformSettings
from platform.common.logging import get_logger
from typing import Any, TypeVar

LOGGER = get_logger(__name__)

T = TypeVar("T")

DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BASE_DELAY_SECONDS = 0.25


class StripeClient:
    """Thin wrapper around the synchronous ``stripe`` SDK.

    Exposes :meth:`call` to run any synchronous Stripe SDK callable on a worker
    thread with retries and structured logging. Tests inject a fake ``stripe``
    module via the ``stripe_module`` constructor argument.
    """

    def __init__(
        self,
        *,
        settings: PlatformSettings,
        api_key: str,
        stripe_module: Any | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
    ) -> None:
        if not api_key:
            raise ValueError("Stripe API key is empty; aborting client initialization.")
        if stripe_module is None:
            import stripe as stripe_module
        assert stripe_module is not None  # narrows the typing for mypy
        self._stripe: Any = stripe_module
        self._stripe.api_key = api_key
        # Request-level API version pin so SDK upgrades are independent of the
        # behavioural pin. Stripe-Version header is sent by every call.
        self._stripe.api_version = settings.billing_stripe.stripe_api_version
        self._settings = settings
        self._max_attempts = max_attempts
        self._base_delay_seconds = base_delay_seconds

    @property
    def stripe(self) -> Any:
        return self._stripe

    @property
    def mode(self) -> str:
        return self._settings.billing_stripe.stripe_mode

    @property
    def api_version(self) -> str:
        return self._settings.billing_stripe.stripe_api_version

    async def call(
        self,
        operation: str,
        fn: Callable[[], T],
    ) -> T:
        """Invoke a synchronous Stripe SDK callable with retry + threading.

        ``operation`` is a stable label used for log lines (e.g.
        ``"customer.create"``). The callable receives no arguments — bind any
        keyword arguments via ``functools.partial`` or a lambda before calling
        :meth:`call`.
        """
        attempt = 0
        last_error: Exception | None = None
        while attempt < self._max_attempts:
            attempt += 1
            try:
                return await asyncio.to_thread(fn)
            except Exception as exc:
                error_name = type(exc).__name__
                if not _is_retryable(self._stripe, exc):
                    LOGGER.warning(
                        "billing.stripe_call_non_retryable_error",
                        operation=operation,
                        error=error_name,
                        attempt=attempt,
                    )
                    raise
                last_error = exc
                if attempt >= self._max_attempts:
                    break
                sleep_for = self._base_delay_seconds * (2 ** (attempt - 1))
                sleep_for *= 0.5 + random.random()
                LOGGER.info(
                    "billing.stripe_call_retrying",
                    operation=operation,
                    error=error_name,
                    attempt=attempt,
                    sleep_seconds=round(sleep_for, 3),
                )
                await asyncio.sleep(sleep_for)
        # Out of attempts — surface as ProviderUnavailable so callers can map
        # to HTTP 503.
        raise ProviderUnavailable(
            "stripe",
            reason=(
                f"Stripe operation {operation!r} failed after "
                f"{self._max_attempts} attempts: {last_error!s}"
            ),
        ) from last_error


def _is_retryable(stripe_module: Any, exc: Exception) -> bool:
    """Return True for transient errors that should be retried."""
    rate_limit = getattr(stripe_module, "error", None)
    if rate_limit is None:
        return False
    rate_cls = getattr(rate_limit, "RateLimitError", None)
    api_cls = getattr(rate_limit, "APIConnectionError", None)
    transient_classes: list[type[Exception]] = []
    if isinstance(rate_cls, type):
        transient_classes.append(rate_cls)
    if isinstance(api_cls, type):
        transient_classes.append(api_cls)
    return any(isinstance(exc, cls) for cls in transient_classes)


async def build_stripe_client(
    *,
    settings: PlatformSettings,
    api_key: str,
    stripe_module: Any | None = None,
) -> StripeClient:
    """Async factory used by FastAPI dependencies.

    Provided as an async function so future implementations can fetch the
    api key from Vault inline if needed; today the caller passes the key in.
    """
    return StripeClient(
        settings=settings,
        api_key=api_key,
        stripe_module=stripe_module,
    )
