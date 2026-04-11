from __future__ import annotations

from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.context_engineering.adapters import build_default_adapters
from platform.context_engineering.compactor import ContextCompactor
from platform.context_engineering.privacy_filter import PrivacyFilter
from platform.context_engineering.quality_scorer import QualityScorer
from platform.context_engineering.repository import ContextEngineeringRepository
from platform.context_engineering.service import ContextEngineeringService
from platform.interactions.dependencies import build_interactions_service
from platform.memory.dependencies import build_memory_service
from platform.registry.dependencies import build_registry_service
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.service import WorkspacesService
from typing import Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_clickhouse(request: Request) -> AsyncClickHouseClient:
    return cast(AsyncClickHouseClient, request.app.state.clients["clickhouse"])


def _get_qdrant(request: Request) -> Any:
    return cast(Any, request.app.state.clients["qdrant"])


def _get_neo4j(request: Request) -> Any:
    return cast(Any, request.app.state.clients["neo4j"])


def _get_redis(request: Request) -> Any:
    return cast(Any, request.app.state.clients["redis"])


def _get_object_storage(request: Request) -> AsyncObjectStorageClient:
    return cast(AsyncObjectStorageClient, request.app.state.clients["minio"])


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_optional_state_service(request: Request, name: str) -> Any | None:
    if hasattr(request.app.state, name):
        return getattr(request.app.state, name)
    services = getattr(request.app.state, "services", None)
    if isinstance(services, dict):
        return services.get(name)
    return None


def build_context_engineering_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    clickhouse_client: AsyncClickHouseClient,
    object_storage: AsyncObjectStorageClient,
    producer: EventProducer | None,
    workspaces_service: WorkspacesService | None = None,
    registry_service: Any | None = None,
    execution_service: Any | None = None,
    interactions_service: Any | None = None,
    memory_service: Any | None = None,
    connectors_service: Any | None = None,
    policies_service: Any | None = None,
) -> ContextEngineeringService:
    return ContextEngineeringService(
        repository=ContextEngineeringRepository(session),
        adapters=build_default_adapters(
            registry_service=registry_service,
            execution_service=execution_service,
            interactions_service=interactions_service,
            memory_service=memory_service,
            connectors_service=connectors_service,
            workspaces_service=workspaces_service,
        ),
        quality_scorer=QualityScorer(),
        compactor=ContextCompactor(),
        privacy_filter=PrivacyFilter(
            policies_service=policies_service,
            cache_ttl_seconds=settings.context_engineering.policy_cache_ttl_seconds,
        ),
        object_storage=object_storage,
        clickhouse_client=clickhouse_client,
        settings=settings,
        event_producer=producer,
        workspaces_service=workspaces_service,
    )


async def get_context_engineering_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> ContextEngineeringService:
    settings = _get_settings(request)
    registry_service = build_registry_service(
        session=session,
        settings=settings,
        object_storage=_get_object_storage(request),
        opensearch=cast(Any, request.app.state.clients["opensearch"]),
        qdrant=_get_qdrant(request),
        workspaces_service=workspaces_service,
        producer=_get_producer(request),
    )
    memory_service = _get_optional_state_service(request, "memory_service")
    if memory_service is None:
        memory_service = build_memory_service(
            session=session,
            settings=settings,
            qdrant=_get_qdrant(request),
            neo4j=_get_neo4j(request),
            redis_client=_get_redis(request),
            producer=_get_producer(request),
            workspaces_service=workspaces_service,
            registry_service=registry_service,
        )
    interactions_service = _get_optional_state_service(request, "interactions_service")
    if interactions_service is None:
        interactions_service = build_interactions_service(
            session=session,
            settings=settings,
            producer=_get_producer(request),
            workspaces_service=workspaces_service,
            registry_service=registry_service,
        )
    return build_context_engineering_service(
        session=session,
        settings=settings,
        clickhouse_client=_get_clickhouse(request),
        object_storage=_get_object_storage(request),
        producer=_get_producer(request),
        workspaces_service=workspaces_service,
        registry_service=registry_service,
        execution_service=_get_optional_state_service(request, "execution_service"),
        interactions_service=interactions_service,
        memory_service=memory_service,
        connectors_service=_get_optional_state_service(request, "connectors_service"),
        policies_service=_get_optional_state_service(request, "policies_service"),
    )
