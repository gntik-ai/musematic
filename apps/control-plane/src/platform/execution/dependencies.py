from __future__ import annotations

from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.reasoning_engine import ReasoningEngineClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.execution.projector import ExecutionProjector
from platform.execution.repository import ExecutionRepository
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
    return cast(AsyncObjectStorageClient, request.app.state.clients["minio"])


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
    """Handle build execution service."""
    return ExecutionService(
        repository=ExecutionRepository(session),
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        object_storage=object_storage,
        runtime_controller=runtime_controller,
        reasoning_engine=reasoning_engine,
        context_engineering_service=context_engineering_service,
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
    """Handle build scheduler service."""
    execution_service = build_execution_service(
        session=session,
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        object_storage=object_storage,
        runtime_controller=runtime_controller,
        reasoning_engine=reasoning_engine,
        context_engineering_service=context_engineering_service,
    )
    return SchedulerService(
        repository=ExecutionRepository(session),
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
