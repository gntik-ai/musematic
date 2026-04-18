from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.notifications.dependencies import get_notifications_service
from platform.notifications.schemas import (
    AlertListResponse,
    UnreadCountResponse,
    UserAlertDetail,
    UserAlertRead,
    UserAlertSettingsRead,
    UserAlertSettingsUpdate,
)
from platform.notifications.service import AlertService
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/me", tags=["notifications"])


def _user_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


@router.get("/alert-settings", response_model=UserAlertSettingsRead)
async def get_alert_settings(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: AlertService = Depends(get_notifications_service),
) -> UserAlertSettingsRead:
    return await service.get_or_default_settings(_user_id(current_user))


@router.put("/alert-settings", response_model=UserAlertSettingsRead)
async def upsert_alert_settings(
    data: UserAlertSettingsUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: AlertService = Depends(get_notifications_service),
) -> UserAlertSettingsRead:
    return await service.upsert_settings(_user_id(current_user), data)


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    read: Literal["all", "read", "unread"] = Query(default="all"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: AlertService = Depends(get_notifications_service),
) -> AlertListResponse:
    return await service.list_alerts(
        _user_id(current_user),
        read_filter=read,
        cursor=cursor,
        limit=limit,
    )


@router.get("/alerts/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: AlertService = Depends(get_notifications_service),
) -> UnreadCountResponse:
    return await service.get_unread_count(_user_id(current_user))


@router.patch("/alerts/{alert_id}/read", response_model=UserAlertRead)
async def mark_alert_read(
    alert_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: AlertService = Depends(get_notifications_service),
) -> UserAlertRead:
    return await service.mark_alert_read(alert_id, _user_id(current_user))


@router.get("/alerts/{alert_id}", response_model=UserAlertDetail)
async def get_alert(
    alert_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: AlertService = Depends(get_notifications_service),
) -> UserAlertDetail:
    return await service.get_alert(alert_id, _user_id(current_user))
