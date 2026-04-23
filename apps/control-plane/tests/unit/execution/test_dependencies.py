from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.execution.dependencies import (
    _get_object_storage,
    _get_producer,
    _get_reasoning_engine,
    _get_redis,
    _get_runtime_controller,
    _get_settings,
    build_execution_service,
    build_scheduler_service,
    get_execution_service,
    get_scheduler_service,
)
from platform.execution.repository import ExecutionRepository
from platform.execution.scheduler import SchedulerService
from platform.execution.service import ExecutionService
from types import SimpleNamespace

import pytest

from tests.workflow_execution_support import FakeObjectStorage, FakeProducer, FakeRedisClient


def _request(settings: PlatformSettings) -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={
                    "kafka": FakeProducer(),
                    "redis": FakeRedisClient(),
                    "runtime_controller": object(),
                    "reasoning_engine": object(),
                    "object_storage": FakeObjectStorage(),
                },
                context_engineering_service="context",
                interactions_service="interactions",
            )
        )
    )


def test_execution_dependency_helpers_read_from_request_state() -> None:
    settings = PlatformSettings()
    request = _request(settings)

    assert _get_settings(request) is settings
    assert _get_producer(request) is request.app.state.clients["kafka"]
    assert _get_redis(request) is request.app.state.clients["redis"]
    assert _get_runtime_controller(request) is request.app.state.clients["runtime_controller"]
    assert _get_reasoning_engine(request) is request.app.state.clients["reasoning_engine"]
    assert _get_object_storage(request) is request.app.state.clients["object_storage"]


@pytest.mark.asyncio
async def test_execution_dependency_factories_build_services() -> None:
    settings = PlatformSettings()
    request = _request(settings)
    session = object()

    execution_service = build_execution_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        producer=request.app.state.clients["kafka"],  # type: ignore[arg-type]
        redis_client=request.app.state.clients["redis"],  # type: ignore[arg-type]
        object_storage=request.app.state.clients["object_storage"],  # type: ignore[arg-type]
        runtime_controller=request.app.state.clients["runtime_controller"],
        reasoning_engine=request.app.state.clients["reasoning_engine"],
        context_engineering_service="context",
    )
    scheduler_service = build_scheduler_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,
        producer=request.app.state.clients["kafka"],  # type: ignore[arg-type]
        redis_client=request.app.state.clients["redis"],  # type: ignore[arg-type]
        object_storage=request.app.state.clients["object_storage"],  # type: ignore[arg-type]
        runtime_controller=request.app.state.clients["runtime_controller"],
        reasoning_engine=request.app.state.clients["reasoning_engine"],
        context_engineering_service="context",
        interactions_service="interactions",
    )
    resolved_execution = await get_execution_service(
        request=request,
        session=session,  # type: ignore[arg-type]
    )
    resolved_scheduler = await get_scheduler_service(
        request=request,
        session=session,  # type: ignore[arg-type]
    )

    assert isinstance(execution_service, ExecutionService)
    assert isinstance(execution_service.repository, ExecutionRepository)
    assert execution_service.repository.session is session
    assert execution_service.context_engineering_service == "context"
    assert isinstance(scheduler_service, SchedulerService)
    assert scheduler_service.repository.session is session
    assert scheduler_service.interactions_service == "interactions"
    assert isinstance(resolved_execution, ExecutionService)
    assert isinstance(resolved_scheduler, SchedulerService)
