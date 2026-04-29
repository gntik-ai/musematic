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
    tag_service: object | None = None,
    label_service: object | None = None,
    tagging_service: object | None = None,
) -> WorkflowService:
    """Handle build workflow service."""
    return WorkflowService(
        repository=WorkflowRepository(session),
        settings=settings,
        producer=producer,
        scheduler=scheduler,
        tag_service=tag_service,
        label_service=label_service,
        tagging_service=tagging_service,
    )


async def get_workflow_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> WorkflowService:
    """Return workflow service."""
    from platform.common.tagging.dependencies import (
        get_label_service,
        get_tag_service,
        get_tagging_service,
    )

    scheduler = getattr(request.app.state, "workflow_scheduler", None)
    return build_workflow_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        scheduler=scheduler,
        tag_service=await get_tag_service(request, session),
        label_service=await get_label_service(request, session),
        tagging_service=await get_tagging_service(request, session),
    )
