from __future__ import annotations

from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.clients.reasoning_engine import ReasoningEngineClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.composition.events import CompositionEventPublisher
from platform.composition.llm.client import LLMCompositionClient
from platform.composition.repository import CompositionRepository
from platform.composition.service import CompositionService, WorkspaceServices
from platform.connectors.dependencies import build_connectors_service
from platform.policies.dependencies import build_policy_service
from platform.registry.dependencies import build_registry_service
from platform.workspaces.dependencies import build_workspaces_service
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def build_composition_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    object_storage: AsyncObjectStorageClient,
    opensearch: AsyncOpenSearchClient,
    qdrant: AsyncQdrantClient,
    reasoning_client: ReasoningEngineClient | None,
) -> CompositionService:
    """Build a composition service with cross-context service interfaces."""
    workspaces_service = build_workspaces_service(
        session=session,
        settings=settings,
        producer=producer,
        accounts_service=None,
    )
    registry_service = build_registry_service(
        session=session,
        settings=settings,
        object_storage=object_storage,
        opensearch=opensearch,
        qdrant=qdrant,
        workspaces_service=workspaces_service,
        producer=producer,
    )
    policy_service = build_policy_service(
        session=session,
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        registry_service=registry_service,
        workspaces_service=workspaces_service,
        reasoning_client=reasoning_client,
    )
    connectors_service = build_connectors_service(
        session=session,
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        object_storage=object_storage,
    )
    return CompositionService(
        repository=CompositionRepository(session),
        publisher=CompositionEventPublisher(producer),
        llm_client=LLMCompositionClient(settings),
        settings=settings,
        services=WorkspaceServices(
            registry=registry_service,
            policy=policy_service,
            connector=connectors_service,
        ),
    )


async def get_composition_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> CompositionService:
    """Return a request-scoped composition service."""
    return build_composition_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=cast(AsyncRedisClient, request.app.state.clients["redis"]),
        object_storage=cast(AsyncObjectStorageClient, request.app.state.clients["object_storage"]),
        opensearch=cast(AsyncOpenSearchClient, request.app.state.clients["opensearch"]),
        qdrant=cast(AsyncQdrantClient, request.app.state.clients["qdrant"]),
        reasoning_client=cast(
            ReasoningEngineClient | None,
            request.app.state.clients.get("reasoning_engine"),
        ),
    )


CompositionServiceDep = Annotated[CompositionService, Depends(get_composition_service)]
