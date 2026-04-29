from __future__ import annotations

from platform.admin.rbac import require_admin
from platform.admin.responses import AdminActionResponse, AdminListResponse, accepted, empty_list
from typing import Any

from fastapi import APIRouter, Depends

router = APIRouter(tags=["admin", "notifications"])


@router.get("/integrations/notifications", response_model=AdminListResponse)
async def list_notification_channels(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("notification-channels", current_user)


@router.post("/integrations/notifications", response_model=AdminActionResponse)
async def create_notification_channel(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("create", "notification-channels", affected_count=1)


@router.put("/integrations/notifications/{channel_id}", response_model=AdminActionResponse)
async def update_notification_channel(
    channel_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("update", f"notification-channels/{channel_id}", affected_count=1)


@router.delete("/integrations/notifications/{channel_id}", response_model=AdminActionResponse)
async def delete_notification_channel(
    channel_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("delete", f"notification-channels/{channel_id}", affected_count=1)


@router.get("/integrations/webhooks", response_model=AdminListResponse)
async def list_webhooks(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("webhooks", current_user)


@router.post("/integrations/webhooks", response_model=AdminActionResponse)
async def create_webhook(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("create", "webhooks", affected_count=1)


@router.get("/integrations/a2a", response_model=AdminListResponse)
async def list_a2a_directory(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("a2a-directory", current_user)


@router.get("/integrations/mcp", response_model=AdminListResponse)
async def list_mcp_catalog(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("mcp-catalog", current_user)


@router.get("/notification-templates", response_model=AdminListResponse)
async def list_notification_templates(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("notification-templates", current_user)


@router.put("/notification-templates/{template_id}", response_model=AdminActionResponse)
async def update_notification_template(
    template_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("update", f"notification-templates/{template_id}", affected_count=1)
