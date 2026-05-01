"""Status page authenticated router for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.status_page.dependencies import get_status_page_service
from platform.status_page.schemas import MyPlatformStatus
from platform.status_page.service import StatusPageService
from typing import Any

from fastapi import APIRouter, Depends

router = APIRouter(tags=["me-platform-status"])


@router.get("/api/v1/me/platform-status", response_model=MyPlatformStatus)
async def get_my_platform_status(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: StatusPageService = Depends(get_status_page_service),
) -> MyPlatformStatus:
    return await service.get_my_platform_status(current_user)
