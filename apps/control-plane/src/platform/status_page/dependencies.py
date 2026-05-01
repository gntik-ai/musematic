"""Status page dependencies for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

from platform.common.dependencies import get_db
from platform.status_page.repository import StatusPageRepository
from platform.status_page.service import StatusPageService
from typing import Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def get_status_page_repository(
    session: AsyncSession = Depends(get_db),
) -> StatusPageRepository:
    return StatusPageRepository(session)


def get_status_page_service(
    request: Request,
    repository: StatusPageRepository = Depends(get_status_page_repository),
) -> StatusPageService:
    clients: dict[str, Any] = getattr(request.app.state, "clients", {})
    return StatusPageService(
        repository=repository,
        redis_client=clients.get("redis"),
    )
