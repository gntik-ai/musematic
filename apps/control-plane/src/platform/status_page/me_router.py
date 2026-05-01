"""Status page authenticated router for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.notifications.channel_router import AuditChainService
from platform.notifications.dependencies import get_audit_chain_service
from platform.status_page.dependencies import get_status_page_service
from platform.status_page.schemas import (
    CreateMyStatusSubscriptionRequest,
    MyPlatformStatus,
    MyStatusSubscription,
    MyStatusSubscriptionList,
    TokenActionResponse,
    UpdateMyStatusSubscriptionRequest,
)
from platform.status_page.service import StatusPageService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

router = APIRouter(tags=["me-platform-status"])


@router.get("/api/v1/me/platform-status", response_model=MyPlatformStatus)
async def get_my_platform_status(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: StatusPageService = Depends(get_status_page_service),
) -> MyPlatformStatus:
    return await service.get_my_platform_status(current_user)


@router.get("/api/v1/me/status-subscriptions", response_model=MyStatusSubscriptionList)
async def list_my_status_subscriptions(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: StatusPageService = Depends(get_status_page_service),
) -> MyStatusSubscriptionList:
    return MyStatusSubscriptionList(items=await service.list_my_subscriptions(current_user))


@router.post(
    "/api/v1/me/status-subscriptions",
    response_model=MyStatusSubscription,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_status_subscription(
    payload: CreateMyStatusSubscriptionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: StatusPageService = Depends(get_status_page_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> MyStatusSubscription:
    created = await service.create_my_subscription(
        current_user,
        channel=payload.channel,
        target=payload.target,
        scope_components=payload.scope_components,
    )
    await _append_audit(
        audit_chain,
        event="status.subscription.created",
        current_user=current_user,
        subscription=created,
        before=None,
        after=_subscription_audit(created),
    )
    return created


@router.patch(
    "/api/v1/me/status-subscriptions/{subscription_id}",
    response_model=MyStatusSubscription,
)
async def update_my_status_subscription(
    subscription_id: UUID,
    payload: UpdateMyStatusSubscriptionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: StatusPageService = Depends(get_status_page_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> MyStatusSubscription:
    updated = await service.update_my_subscription(
        current_user,
        subscription_id,
        target=payload.target,
        scope_components=payload.scope_components,
    )
    await _append_audit(
        audit_chain,
        event="status.subscription.updated",
        current_user=current_user,
        subscription=updated,
        before=None,
        after=_subscription_audit(updated),
    )
    return updated


@router.delete(
    "/api/v1/me/status-subscriptions/{subscription_id}",
    response_model=TokenActionResponse,
)
async def delete_my_status_subscription(
    subscription_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: StatusPageService = Depends(get_status_page_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> TokenActionResponse:
    response = await service.delete_my_subscription(current_user, subscription_id)
    await _append_audit(
        audit_chain,
        event="status.subscription.unsubscribed",
        current_user=current_user,
        subscription_id=subscription_id,
        before=None,
        after={"health": "unsubscribed"},
    )
    return response


async def _append_audit(
    audit_chain: AuditChainService,
    *,
    event: str,
    current_user: dict[str, Any],
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    subscription: MyStatusSubscription | None = None,
    subscription_id: UUID | None = None,
) -> None:
    subject = subscription.id if subscription is not None else str(subscription_id)
    workspace_id = current_user.get("workspace_id") or current_user.get("workspace")
    await audit_chain.append(
        {
            "event": event,
            "actor": str(current_user["sub"]),
            "subject": subject,
            "scope": {"workspace_id": str(workspace_id)} if workspace_id else {},
            "diff": {"before": before, "after": after},
            "occurred_at": datetime.now(UTC).isoformat(),
        }
    )


def _subscription_audit(subscription: MyStatusSubscription) -> dict[str, Any]:
    return {
        "id": subscription.id,
        "channel": subscription.channel,
        "scope_components": subscription.scope_components,
        "health": subscription.health,
    }
