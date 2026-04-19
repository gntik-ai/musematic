from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.execution.checkpoint_service import CheckpointService
from platform.execution.dependencies import (
    get_checkpoint_service,
    get_execution_service,
    get_reprioritization_service,
)
from platform.execution.projector import ExecutionProjector
from platform.execution.repository import ExecutionRepository
from platform.execution.reprioritization import ReprioritizationService
from platform.execution.router import router as execution_router
from platform.execution.router import trigger_router as execution_trigger_router
from platform.execution.scheduler import PriorityScorer, SchedulerService
from platform.execution.service import ExecutionService
from platform.workflows.dependencies import get_workflow_service
from platform.workflows.repository import WorkflowRepository
from platform.workflows.router import router as workflow_router
from platform.workflows.service import WorkflowService
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class KafkaMock:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def publish(self, **payload: Any) -> None:
        self.messages.append(payload)


@dataclass
class WorkflowExecutionStack:
    session: AsyncSession
    workflow_repository: WorkflowRepository
    execution_repository: ExecutionRepository
    workflow_service: WorkflowService
    execution_service: ExecutionService
    checkpoint_service: CheckpointService
    reprioritization_service: ReprioritizationService
    scheduler_service: SchedulerService
    kafka_mock: KafkaMock
    runtime_controller_stub: Any
    reasoning_engine_stub: AsyncMock
    context_engineering_stub: AsyncMock
    current_user: dict[str, str]


@pytest.fixture
def kafka_mock() -> KafkaMock:
    return KafkaMock()


@pytest.fixture
def current_user() -> dict[str, str]:
    return {"sub": str(uuid4())}


@pytest.fixture
def runtime_controller_stub(workflow_execution_stack: WorkflowExecutionStack) -> Any:
    return workflow_execution_stack.runtime_controller_stub


@pytest.fixture
def reasoning_engine_stub(workflow_execution_stack: WorkflowExecutionStack) -> AsyncMock:
    return workflow_execution_stack.reasoning_engine_stub


@pytest.fixture
def context_engineering_stub(workflow_execution_stack: WorkflowExecutionStack) -> AsyncMock:
    return workflow_execution_stack.context_engineering_stub


@pytest_asyncio.fixture
async def integration_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def workflow_execution_stack(
    integration_session: AsyncSession,
    auth_settings,
    redis_client,
    object_storage_client,
    kafka_mock: KafkaMock,
    current_user: dict[str, str],
) -> AsyncIterator[WorkflowExecutionStack]:
    settings = auth_settings.model_copy(deep=True)
    workflow_repository = WorkflowRepository(integration_session)
    execution_repository = ExecutionRepository(integration_session)
    runtime_controller_stub = SimpleNamespace(dispatch=AsyncMock())
    reasoning_engine_stub = AsyncMock()
    context_engineering_stub = AsyncMock()

    workflow_service = WorkflowService(
        repository=workflow_repository,
        settings=settings,
        producer=kafka_mock,  # type: ignore[arg-type]
    )
    checkpoint_service = CheckpointService(
        repository=execution_repository,
        settings=settings,
        producer=kafka_mock,  # type: ignore[arg-type]
        projector=ExecutionProjector(),
    )
    execution_service = ExecutionService(
        repository=execution_repository,
        settings=settings,
        producer=kafka_mock,  # type: ignore[arg-type]
        redis_client=redis_client,
        object_storage=object_storage_client,
        runtime_controller=runtime_controller_stub,
        reasoning_engine=reasoning_engine_stub,
        context_engineering_service=context_engineering_stub,
        projector=ExecutionProjector(),
        checkpoint_service=checkpoint_service,
    )
    execution_service.workflow_repository = workflow_repository
    await object_storage_client.create_bucket_if_not_exists(execution_service.task_plan_bucket)

    reprioritization_service = ReprioritizationService(repository=execution_repository)
    scheduler_service = SchedulerService(
        repository=execution_repository,
        execution_service=execution_service,
        projector=ExecutionProjector(),
        settings=settings,
        producer=kafka_mock,  # type: ignore[arg-type]
        redis_client=redis_client,
        object_storage=object_storage_client,
        runtime_controller=runtime_controller_stub,
        reasoning_engine=reasoning_engine_stub,
        context_engineering_service=context_engineering_stub,
        interactions_service=None,
        priority_scorer=PriorityScorer(),
        reprioritization_service=reprioritization_service,
        checkpoint_service=checkpoint_service,
    )

    yield WorkflowExecutionStack(
        session=integration_session,
        workflow_repository=workflow_repository,
        execution_repository=execution_repository,
        workflow_service=workflow_service,
        execution_service=execution_service,
        checkpoint_service=checkpoint_service,
        reprioritization_service=reprioritization_service,
        scheduler_service=scheduler_service,
        kafka_mock=kafka_mock,
        runtime_controller_stub=runtime_controller_stub,
        reasoning_engine_stub=reasoning_engine_stub,
        context_engineering_stub=context_engineering_stub,
        current_user=current_user,
    )


@pytest_asyncio.fixture
async def workflow_execution_app(
    workflow_execution_stack: WorkflowExecutionStack,
) -> AsyncIterator[FastAPI]:
    app = FastAPI()
    app.state.settings = workflow_execution_stack.execution_service.settings
    app.state.clients = {
        "kafka": workflow_execution_stack.kafka_mock,
        "redis": workflow_execution_stack.execution_service.redis_client,
        "object_storage": workflow_execution_stack.execution_service.object_storage,
        "runtime_controller": workflow_execution_stack.runtime_controller_stub,
        "reasoning_engine": workflow_execution_stack.reasoning_engine_stub,
    }
    app.state.context_engineering_service = workflow_execution_stack.context_engineering_stub
    app.state.interactions_service = None
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(workflow_router)
    app.include_router(execution_router)
    app.include_router(execution_trigger_router)
    app.dependency_overrides[get_current_user] = lambda: workflow_execution_stack.current_user
    app.dependency_overrides[get_workflow_service] = lambda: (
        workflow_execution_stack.workflow_service
    )
    app.dependency_overrides[get_execution_service] = lambda: (
        workflow_execution_stack.execution_service
    )
    app.dependency_overrides[get_checkpoint_service] = lambda: (
        workflow_execution_stack.checkpoint_service
    )
    app.dependency_overrides[get_reprioritization_service] = lambda: (
        workflow_execution_stack.reprioritization_service
    )
    yield app


@pytest_asyncio.fixture
async def workflow_execution_client(
    workflow_execution_app: FastAPI,
) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=workflow_execution_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
