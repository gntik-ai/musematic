from __future__ import annotations

from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.interactions.repository import InteractionsRepository
from platform.interactions.service import InteractionsService
from platform.registry.dependencies import get_registry_service
from platform.registry.service import RegistryService
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.service import WorkspacesService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_qdrant(request: Request) -> AsyncQdrantClient | None:
    return cast(AsyncQdrantClient | None, request.app.state.clients.get("qdrant"))


def build_interactions_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    qdrant: AsyncQdrantClient | None = None,
    workspaces_service: WorkspacesService | None = None,
    registry_service: RegistryService | None = None,
) -> InteractionsService:
    return InteractionsService(
        repository=InteractionsRepository(session),
        settings=settings,
        producer=producer,
        qdrant=qdrant,
        workspaces_service=workspaces_service,
        registry_service=registry_service,
    )


async def get_interactions_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
    registry_service: RegistryService = Depends(get_registry_service),
) -> InteractionsService:
    return build_interactions_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        qdrant=_get_qdrant(request),
        workspaces_service=workspaces_service,
        registry_service=registry_service,
    )
