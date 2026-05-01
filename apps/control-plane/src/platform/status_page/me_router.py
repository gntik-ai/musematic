"""Status page authenticated router for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

from platform.common.dependencies import get_current_user
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
) -> MyStatusSubscription:
    return await service.create_my_subscription(
        current_user,
        channel=payload.channel,
        target=payload.target,
        scope_components=payload.scope_components,
    )


@router.patch(
    "/api/v1/me/status-subscriptions/{subscription_id}",
    response_model=MyStatusSubscription,
)
async def update_my_status_subscription(
    subscription_id: UUID,
    payload: UpdateMyStatusSubscriptionRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: StatusPageService = Depends(get_status_page_service),
) -> MyStatusSubscription:
    return await service.update_my_subscription(
        current_user,
        subscription_id,
        target=payload.target,
        scope_components=payload.scope_components,
    )


@router.delete(
    "/api/v1/me/status-subscriptions/{subscription_id}",
    response_model=TokenActionResponse,
)
async def delete_my_status_subscription(
    subscription_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: StatusPageService = Depends(get_status_page_service),
) -> TokenActionResponse:
    return await service.delete_my_subscription(current_user, subscription_id)
