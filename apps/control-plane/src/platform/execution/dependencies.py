from __future__ import annotations

from platform.billing.quotas.dependencies import build_quota_enforcer
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.reasoning_engine import ReasoningEngineClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.execution.checkpoint_service import CheckpointService
from platform.execution.projector import ExecutionProjector
from platform.execution.repository import ExecutionRepository
from platform.execution.reprioritization import ReprioritizationService
from platform.execution.scheduler import SchedulerService
from platform.execution.service import ExecutionService
from typing import Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def get_runtime_controller_client(request: Request) -> RuntimeControllerClient:
    return cast(RuntimeControllerClient, request.app.state.clients["runtime_controller"])


def _get_runtime_controller(request: Request) -> RuntimeControllerClient:
    return get_runtime_controller_client(request)


def _get_reasoning_engine(request: Request) -> ReasoningEngineClient:
    return cast(ReasoningEngineClient, request.app.state.clients["reasoning_engine"])


def _get_object_storage(request: Request) -> AsyncObjectStorageClient:
    return cast(AsyncObjectStorageClient, request.app.state.clients["object_storage"])


def build_execution_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    object_storage: AsyncObjectStorageClient,
    runtime_controller: RuntimeControllerClient | Any | None,
    reasoning_engine: ReasoningEngineClient | Any | None,
    context_engineering_service: Any | None = None,
) -> ExecutionService:
    """Build execution service."""
    repository = ExecutionRepository(session)
    checkpoint_service = CheckpointService(
        repository=repository,
        settings=settings,
        producer=producer,
        projector=ExecutionProjector(),
    )
    return ExecutionService(
        repository=repository,
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        object_storage=object_storage,
        runtime_controller=runtime_controller,
        reasoning_engine=reasoning_engine,
        context_engineering_service=context_engineering_service,
        projector=ExecutionProjector(),
        checkpoint_service=checkpoint_service,
        quota_enforcer=build_quota_enforcer(
            session=session,
            settings=settings,
            redis_client=redis_client,
        ),
    )


def build_reprioritization_service(
    *,
    session: AsyncSession,
    repository: ExecutionRepository | None = None,
) -> ReprioritizationService:
    """Build reprioritization service."""
    return ReprioritizationService(repository=repository or ExecutionRepository(session))


def build_checkpoint_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    repository: ExecutionRepository | None = None,
) -> CheckpointService:
    """Build checkpoint service."""
    return CheckpointService(
        repository=repository or ExecutionRepository(session),
        settings=settings,
        producer=producer,
        projector=ExecutionProjector(),
    )


def build_scheduler_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    object_storage: AsyncObjectStorageClient,
    runtime_controller: RuntimeControllerClient | Any | None,
    reasoning_engine: ReasoningEngineClient | Any | None,
    context_engineering_service: Any | None = None,
    interactions_service: Any | None = None,
) -> SchedulerService:
    """Build scheduler service."""
    repository = ExecutionRepository(session)
    checkpoint_service = build_checkpoint_service(
        session=session,
        settings=settings,
        producer=producer,
        repository=repository,
    )
    execution_service = ExecutionService(
        repository=repository,
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        object_storage=object_storage,
        runtime_controller=runtime_controller,
        reasoning_engine=reasoning_engine,
        context_engineering_service=context_engineering_service,
        projector=ExecutionProjector(),
        checkpoint_service=checkpoint_service,
        quota_enforcer=build_quota_enforcer(
            session=session,
            settings=settings,
            redis_client=redis_client,
        ),
    )
    return SchedulerService(
        repository=repository,
        execution_service=execution_service,
        projector=ExecutionProjector(),
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        object_storage=object_storage,
        runtime_controller=runtime_controller,
        reasoning_engine=reasoning_engine,
        context_engineering_service=context_engineering_service,
        interactions_service=interactions_service,
        reprioritization_service=build_reprioritization_service(
            session=session,
            repository=repository,
        ),
        checkpoint_service=checkpoint_service,
    )


async def get_execution_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ExecutionService:
    """Return execution service."""
    return build_execution_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
        object_storage=_get_object_storage(request),
        runtime_controller=get_runtime_controller_client(request),
        reasoning_engine=_get_reasoning_engine(request),
        context_engineering_service=getattr(request.app.state, "context_engineering_service", None),
    )


async def get_reprioritization_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ReprioritizationService:
    """Return reprioritization service."""
    del request
    return build_reprioritization_service(session=session)


async def get_checkpoint_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> CheckpointService:
    """Return checkpoint service."""
    return build_checkpoint_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
    )


async def get_scheduler_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> SchedulerService:
    """Return scheduler service."""
    return build_scheduler_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
        object_storage=_get_object_storage(request),
        runtime_controller=get_runtime_controller_client(request),
        reasoning_engine=_get_reasoning_engine(request),
        context_engineering_service=getattr(request.app.state, "context_engineering_service", None),
        interactions_service=getattr(request.app.state, "interactions_service", None),
    )
