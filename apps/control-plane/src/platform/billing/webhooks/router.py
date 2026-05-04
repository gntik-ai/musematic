"""UPD-052 — Stripe webhook ingress router.

Public ingress (no platform JWT). Per the contract in
``specs/105-billing-payment-provider/contracts/stripe-webhook-rest.md``:

1. Read the raw body and ``Stripe-Signature`` header.
2. Load the active + previous signing secrets from Vault (fail-closed → 503).
3. Verify the signature; on failure → 401 with a generic body.
4. Acquire the two-layer idempotency guard. If duplicate / in-flight, return
   200 with the matching ``status`` value.
5. Dispatch to the registered handler. Handler exceptions propagate as 500
   so Stripe retries.
6. Mark the durable idempotency record before commit.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from platform.billing.metrics import metrics
from platform.billing.providers.exceptions import (
    BillingSecretsUnavailableError,
    BillingWebhookSignatureError,
)
from platform.billing.providers.stripe.secrets import (
    StripeSecrets,
    StripeSecretsLoader,
)
from platform.billing.providers.stripe.webhook_signing import verify_stripe_signature
from platform.billing.webhooks.handlers.registry import (
    HandlerContext,
    HandlerRegistry,
    build_default_registry,
)
from platform.billing.webhooks.idempotency import WebhookIdempotency
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.database import AsyncSessionLocal
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from typing import Any, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)

webhook_router = APIRouter(prefix="/api/webhooks", tags=["billing:webhooks"])


async def _get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def _registry(request: Request) -> HandlerRegistry:
    registry = getattr(request.app.state, "billing_webhook_registry", None)
    if registry is None:
        registry = build_default_registry()
        request.app.state.billing_webhook_registry = registry
    return registry


def _settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def _producer(request: Request) -> EventProducer | None:
    return cast("EventProducer | None", request.app.state.clients.get("kafka"))


def _secret_provider(request: Request) -> Any:
    return request.app.state.clients["secret_provider"]


@webhook_router.post(
    "/stripe",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,  # public ingress; not part of the user-facing API
)
async def stripe_webhook(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(_get_session),
) -> dict[str, str]:
    body = await request.body()
    signature = request.headers.get("stripe-signature", "")

    settings = _settings(request)
    loader = StripeSecretsLoader(_secret_provider(request), settings)

    try:
        secrets: StripeSecrets = await loader.load()
    except BillingSecretsUnavailableError as exc:
        LOGGER.warning("billing.webhook_secrets_unavailable", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="secrets_unavailable",
        ) from exc

    try:
        event = verify_stripe_signature(body, signature, secrets.webhook)
    except BillingWebhookSignatureError as exc:
        metrics.record_webhook_signature_failed()
        LOGGER.info("billing.webhook_signature_rejected", reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_signature",
        ) from exc

    redis = _redis(request)
    idempotency = WebhookIdempotency(
        redis=redis,
        lock_ttl_seconds=settings.billing_stripe.webhook_lock_ttl_seconds,
    )
    decision = await idempotency.acquire(session, event.id)
    if not decision.proceed:
        metrics.record_webhook_processed(
            event_type=event.type,
            outcome=decision.reason,
        )
        return {"status": decision.reason}

    correlation_ctx = CorrelationContext(correlation_id=uuid4())
    context = HandlerContext(
        session=session,
        producer=_producer(request),
        correlation_ctx=correlation_ctx,
        extras={"settings": settings, "stripe_event": event},
    )

    started = time.perf_counter()
    try:
        outcome = await _registry(request).dispatch(event, context)
    except Exception:
        await idempotency.release_lock(event.id)
        await session.rollback()
        metrics.record_webhook_processed(event_type=event.type, outcome="failed")
        LOGGER.exception(
            "billing.webhook_handler_failed",
            event_id=event.id,
            event_type=event.type,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="handler_failed",
        ) from None

    if outcome == "processed" or outcome == "ignored":
        await idempotency.mark_processed(session, event.id, event.type)
        await session.commit()

    metrics.record_webhook_processed(event_type=event.type, outcome=outcome)
    metrics.record_webhook_handler_duration(
        time.perf_counter() - started,
        event_type=event.type,
    )
    response.headers["X-Billing-Webhook-Outcome"] = outcome
    return {"status": outcome}
