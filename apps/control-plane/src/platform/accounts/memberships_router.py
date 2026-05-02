"""Cross-tenant `/me/memberships` router for UPD-048 FR-020 through FR-023."""

from __future__ import annotations

from platform.accounts.memberships import MembershipsService
from platform.accounts.schemas import MembershipsListResponse
from platform.audit.dependencies import build_audit_chain_service
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.dependencies import get_current_user
from platform.common.events.producer import EventProducer
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["me.memberships"])


@router.get("/memberships", response_model=MembershipsListResponse)
async def list_memberships(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(database.get_platform_staff_session),
) -> MembershipsListResponse:
    settings = _settings(request)
    producer = _producer(request)
    service = MembershipsService(
        platform_staff_session=session,
        settings=settings,
        audit_chain=build_audit_chain_service(session, settings, producer),
    )
    memberships = await service.list_for_user(current_user)
    return MembershipsListResponse(memberships=memberships, count=len(memberships))


def _settings(request: Request) -> PlatformSettings:
    value = getattr(request.app.state, "settings", None)
    return value if isinstance(value, PlatformSettings) else default_settings


def _producer(request: Request) -> EventProducer | None:
    clients = getattr(request.app.state, "clients", {})
    producer = clients.get("kafka") if isinstance(clients, dict) else None
    return producer if isinstance(producer, EventProducer) else None
