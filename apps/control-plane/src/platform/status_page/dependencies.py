"""Status page dependencies for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

from platform.common.dependencies import get_db
from platform.status_page.exceptions import RateLimitExceededError
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
        email_deliverer=clients.get("email_deliverer"),
        webhook_deliverer=clients.get("webhook_deliverer"),
        slack_deliverer=clients.get("slack_deliverer"),
        smtp_settings=getattr(request.app.state, "smtp_settings", {}),
        platform_version=getattr(getattr(request.app.state, "settings", None), "profile", "dev"),
    )


async def enforce_subscribe_rate_limit(request: Request) -> None:
    clients: dict[str, Any] = getattr(request.app.state, "clients", {})
    redis_client = clients.get("redis")
    if redis_client is None:
        return

    host = request.client.host if request.client else "unknown"
    key = f"status:subscribe:rate:{host}"
    limit = 10
    window_seconds = 60
    increment = getattr(redis_client, "incr", None)
    if not callable(increment):
        return
    count = await increment(key)
    if int(count) == 1:
        expire = getattr(redis_client, "expire", None)
        if callable(expire):
            await expire(key, window_seconds)
    if int(count) > limit:
        raise RateLimitExceededError(window_seconds)
