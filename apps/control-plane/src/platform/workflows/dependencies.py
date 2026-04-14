from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.workflows.repository import WorkflowRepository
from platform.workflows.service import WorkflowService
from typing import Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def build_workflow_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    scheduler: Any | None = None,
) -> WorkflowService:
    """Handle build workflow service."""
    return WorkflowService(
        repository=WorkflowRepository(session),
        settings=settings,
        producer=producer,
        scheduler=scheduler,
    )


async def get_workflow_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> WorkflowService:
    """Return workflow service."""
    scheduler = getattr(request.app.state, "workflow_scheduler", None)
    return build_workflow_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        scheduler=scheduler,
    )
