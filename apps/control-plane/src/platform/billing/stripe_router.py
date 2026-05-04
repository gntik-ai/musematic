"""UPD-052 — Stripe-specific billing endpoints.

Sits next to (not inside) the UPD-047 ``billing/subscriptions/router.py``
because these endpoints assume a real :class:`StripePaymentProvider` and
emit ``billing.events`` Kafka envelopes. The UPD-047 router stays in
charge of the plan/quota/usage endpoints that work with both the stub
and Stripe.
"""

from __future__ import annotations

from datetime import UTC, datetime
from platform.billing.events import (
    BillingEventType,
    PaymentMethodAttachedPayload,
    SubscriptionCancelledPayload,
    SubscriptionUpdatedPayload,
    publish_billing_event,
)
from platform.billing.payment_methods.repository import PaymentMethodsRepository
from platform.billing.payment_methods.service import PaymentMethodsService
from platform.billing.providers.protocol import PaymentProvider
from platform.billing.subscriptions.models import Subscription
from platform.common.dependencies import get_current_user
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)

stripe_billing_router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/billing",
    tags=["billing:stripe"],
)


class CancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=64)
    reason_text: str | None = Field(default=None, max_length=1000)


class StoreCardRequest(BaseModel):
    payment_method_token: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def _get_session(request: Request) -> Any:  # pragma: no cover - real path
    from platform.common.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def _provider(request: Request) -> PaymentProvider:
    provider = getattr(request.app.state, "payment_provider", None)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="payment_provider_unavailable",
        )
    return cast(PaymentProvider, provider)


def _producer(request: Request) -> EventProducer | None:
    return cast("EventProducer | None", request.app.state.clients.get("kafka"))


def _actor_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


async def _require_subscription(
    session: AsyncSession,
    workspace_id: UUID,
) -> Subscription:
    stmt = select(Subscription).where(
        Subscription.scope_type == "workspace",
        Subscription.scope_id == workspace_id,
    )
    result = await session.execute(stmt)
    sub = result.scalars().first()
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="subscription_not_found",
        )
    return sub


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class StripeUpgradeRequest(BaseModel):
    target_plan_slug: str = Field(min_length=1, max_length=64)
    payment_method_token: str = Field(min_length=1)


@stripe_billing_router.post(
    "/stripe-upgrade",
    status_code=status.HTTP_201_CREATED,
    summary="Upgrade workspace to a paid plan via Stripe (UPD-052 US1)",
)
async def stripe_upgrade(
    workspace_id: UUID,
    payload: StripeUpgradeRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    sub = await _require_subscription(session, workspace_id)
    provider = _provider(request)
    correlation = CorrelationContext(correlation_id=uuid4())

    if not sub.stripe_customer_id:
        try:
            customer_id = await provider.create_customer(
                workspace_id=workspace_id,
                tenant_id=sub.tenant_id,
                email=str(current_user.get("email", "unknown@example.com")),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="stripe_unavailable",
            ) from exc
        sub.stripe_customer_id = customer_id
        await session.flush()
    try:
        attached_id = await provider.attach_payment_method(
            sub.stripe_customer_id,
            payload.payment_method_token,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="payment_method_invalid",
        ) from exc

    try:
        provider_sub = await provider.create_subscription(
            sub.stripe_customer_id,
            payload.target_plan_slug,
            trial_days=0,
            idempotency_key=f"upgrade:{sub.id}:{payload.target_plan_slug}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="stripe_unavailable",
        ) from exc

    sub.stripe_subscription_id = provider_sub.provider_subscription_id
    sub.status = "pending"
    # Plan slug is tracked on the plan_versions table (FK plan_id+plan_version);
    # the customer.subscription.created webhook handler reconciles the local
    # plan reference once Stripe finalises the subscription.
    await session.flush()
    LOGGER.info(
        "billing.stripe_upgrade_initiated",
        workspace_id=str(workspace_id),
        target_plan_slug=payload.target_plan_slug,
        stripe_subscription_id=provider_sub.provider_subscription_id,
        attached_payment_method_id=attached_id,
        correlation_id=str(correlation.correlation_id),
    )
    await session.commit()
    return {
        "subscription_id": str(sub.id),
        "stripe_subscription_id": provider_sub.provider_subscription_id,
        "status": "pending",
    }


@stripe_billing_router.post(
    "/cancel-with-reason",
    summary="Cancel subscription at period end with retention reason (UPD-052 US5)",
)
async def cancel_with_reason(
    workspace_id: UUID,
    payload: CancelRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    sub = await _require_subscription(session, workspace_id)
    if sub.status in {"canceled", "cancellation_pending"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="already_cancelled",
        )
    if not sub.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no_stripe_subscription",
        )
    provider = _provider(request)
    correlation = CorrelationContext(correlation_id=uuid4())
    try:
        await provider.cancel_subscription(
            sub.stripe_subscription_id,
            at_period_end=True,
        )
    except Exception as exc:
        LOGGER.warning(
            "billing.cancel_failed",
            error=str(exc),
            workspace_id=str(workspace_id),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="stripe_unavailable",
        ) from exc
    sub.status = "cancellation_pending"
    sub.cancel_at_period_end = True
    cancellation_metadata = dict(getattr(sub, "metadata_json", {}) or {})
    cancellation_metadata["cancellation_reason"] = payload.reason
    if payload.reason_text:
        cancellation_metadata["cancellation_reason_text"] = payload.reason_text
    # Subscription model doesn't currently expose metadata_json; the
    # cancellation reason is logged + emitted on the Kafka event for
    # retention analysis.
    LOGGER.info(
        "billing.cancel_metadata",
        subscription_id=str(sub.id),
        cancellation_reason=cancellation_metadata.get("cancellation_reason"),
    )
    await session.flush()

    await publish_billing_event(
        _producer(request),
        BillingEventType.subscription_cancelled,
        SubscriptionCancelledPayload(
            subscription_id=sub.id,
            scheduled_at=datetime.now(UTC),
            effective_at=sub.current_period_end,
            reason=payload.reason,
            correlation_context=correlation,
        ),
        correlation,
        partition_key=sub.tenant_id,
    )
    await session.commit()
    return {
        "subscription_id": str(sub.id),
        "status": sub.status,
        "ends_at": sub.current_period_end.isoformat(),
    }


@stripe_billing_router.post(
    "/reactivate",
    summary="Reactivate a cancellation-pending subscription (UPD-052 US5)",
)
async def reactivate_subscription(
    workspace_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    sub = await _require_subscription(session, workspace_id)
    if sub.status != "cancellation_pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="not_cancellation_pending",
        )
    if sub.current_period_end < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="period_already_ended",
        )
    if not sub.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no_stripe_subscription",
        )
    provider = _provider(request)
    correlation = CorrelationContext(correlation_id=uuid4())
    try:
        await provider.update_subscription(
            sub.stripe_subscription_id,
            target_plan_external_id=sub.stripe_subscription_id,
            prorate=False,
            idempotency_key=f"reactivate:{sub.id}",
        )
    except Exception as exc:
        LOGGER.warning(
            "billing.reactivate_failed",
            error=str(exc),
            workspace_id=str(workspace_id),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="stripe_unavailable",
        ) from exc
    sub.status = "active"
    sub.cancel_at_period_end = False
    await session.flush()

    await publish_billing_event(
        _producer(request),
        BillingEventType.subscription_updated,
        SubscriptionUpdatedPayload(
            subscription_id=sub.id,
            from_plan_slug=None,
            to_plan_slug=str(sub.stripe_subscription_id or ""),
            cancel_at_period_end=False,
            current_period_end=sub.current_period_end,
            correlation_context=correlation,
        ),
        correlation,
        partition_key=sub.tenant_id,
    )
    await session.commit()
    return {"subscription_id": str(sub.id), "status": sub.status}


@stripe_billing_router.post(
    "/portal-session",
    summary="Open a Stripe Customer Portal session (UPD-052 US4)",
)
async def create_portal_session(
    workspace_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, str]:
    sub = await _require_subscription(session, workspace_id)
    if not sub.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="customer_not_found",
        )
    provider = _provider(request)
    portal_return_url = (
        request.app.state.settings.billing_stripe.portal_return_url_allowlist[0]
        .replace("{id}", str(workspace_id))
    )
    try:
        portal = await provider.create_customer_portal_session(
            sub.stripe_customer_id,
            portal_return_url,
        )
    except Exception as exc:
        LOGGER.warning(
            "billing.portal_session_failed",
            error=str(exc),
            workspace_id=str(workspace_id),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="stripe_unavailable",
        ) from exc
    return {"portal_url": portal.url}


@stripe_billing_router.post(
    "/store-card",
    summary="Add a card on file without upgrading (UPD-052 US6)",
    status_code=status.HTTP_201_CREATED,
)
async def store_card_on_file(
    workspace_id: UUID,
    payload: StoreCardRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict[str, Any]:
    sub = await _require_subscription(session, workspace_id)
    provider = _provider(request)
    correlation = CorrelationContext(correlation_id=uuid4())

    if not sub.stripe_customer_id:
        try:
            customer_id = await provider.create_customer(
                workspace_id=workspace_id,
                tenant_id=sub.tenant_id,
                email=str(current_user.get("email", "unknown@example.com")),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="stripe_unavailable",
            ) from exc
        sub.stripe_customer_id = customer_id
        await session.flush()

    try:
        attached_id = await provider.attach_payment_method(
            sub.stripe_customer_id,
            payload.payment_method_token,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="stripe_unavailable",
        ) from exc

    pm_service = PaymentMethodsService(PaymentMethodsRepository(session))
    record = await pm_service.record_attached(
        tenant_id=sub.tenant_id,
        workspace_id=workspace_id,
        stripe_payment_method_id=attached_id,
        brand=None,
        last4=None,
        exp_month=None,
        exp_year=None,
        is_default=True,
    )
    await pm_service.set_default(
        tenant_id=sub.tenant_id,
        workspace_id=workspace_id,
        payment_method_id=record.id,
    )
    sub.payment_method_id = record.id
    await session.flush()

    await publish_billing_event(
        _producer(request),
        BillingEventType.payment_method_attached,
        PaymentMethodAttachedPayload(
            payment_method_id=record.id,
            tenant_id=sub.tenant_id,
            workspace_id=workspace_id,
            stripe_payment_method_id=attached_id,
            brand=None,
            last4=None,
            is_default=True,
            correlation_context=correlation,
        ),
        correlation,
        partition_key=sub.tenant_id,
    )
    await session.commit()
    return {
        "payment_method_id": str(record.id),
        "stripe_payment_method_id": attached_id,
        "is_default": True,
    }
