from __future__ import annotations

from platform.common.clients.neo4j import AsyncNeo4jClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.memory.repository import MemoryRepository
from platform.memory.retrieval_coordinator import RetrievalCoordinator
from platform.memory.service import MemoryService
from platform.memory.write_gate import MemoryWriteGate
from platform.registry.dependencies import get_registry_service
from platform.registry.service import RegistryService
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.service import WorkspacesService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_qdrant(request: Request) -> AsyncQdrantClient:
    return cast(AsyncQdrantClient, request.app.state.clients["qdrant"])


def _get_neo4j(request: Request) -> AsyncNeo4jClient:
    return cast(AsyncNeo4jClient, request.app.state.clients["neo4j"])


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def build_memory_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    qdrant: AsyncQdrantClient,
    neo4j: AsyncNeo4jClient,
    redis_client: AsyncRedisClient,
    producer: EventProducer | None,
    workspaces_service: WorkspacesService,
    registry_service: RegistryService,
) -> MemoryService:
    repository = MemoryRepository(session)
    write_gate = MemoryWriteGate(
        repository=repository,
        qdrant=qdrant,
        redis_client=redis_client,
        settings=settings,
        registry_service=registry_service,
        workspaces_service=workspaces_service,
        producer=producer,
    )
    retrieval = RetrievalCoordinator(
        repository=repository,
        qdrant=qdrant,
        neo4j=neo4j,
        settings=settings,
        registry_service=registry_service,
    )
    return MemoryService(
        repository=repository,
        write_gate=write_gate,
        retrieval_coordinator=retrieval,
        neo4j=neo4j,
        qdrant=qdrant,
        settings=settings,
        producer=producer,
        workspaces_service=workspaces_service,
        registry_service=registry_service,
    )


async def get_memory_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
    registry_service: RegistryService = Depends(get_registry_service),
) -> MemoryService:
    return build_memory_service(
        session=session,
        settings=_get_settings(request),
        qdrant=_get_qdrant(request),
        neo4j=_get_neo4j(request),
        redis_client=_get_redis(request),
        producer=_get_producer(request),
        workspaces_service=workspaces_service,
        registry_service=registry_service,
    )
