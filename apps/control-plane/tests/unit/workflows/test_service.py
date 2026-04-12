from __future__ import annotations

from platform.execution.service import ExecutionService
from platform.workflows.schemas import TriggerCreate, WorkflowCreate, WorkflowUpdate
from platform.workflows.service import WorkflowService
from typing import Any, cast
from uuid import uuid4

import pytest

from tests.workflow_execution_support import (
    FakeExecutionRepository,
    FakeObjectStorage,
    FakeProducer,
    FakeRedisClient,
    FakeRuntimeController,
    FakeWorkflowRepository,
    make_settings,
)


def _build_services() -> tuple[WorkflowService, ExecutionService, FakeWorkflowRepository]:
    workflow_repository = FakeWorkflowRepository()
    execution_repository = FakeExecutionRepository()
    producer = FakeProducer()
    workflow_service = WorkflowService(
        repository=cast(Any, workflow_repository),
        settings=make_settings(),
        producer=cast(Any, producer),
    )
    execution_service = ExecutionService(
        repository=cast(Any, execution_repository),
        settings=make_settings(),
        producer=cast(Any, producer),
        redis_client=cast(Any, FakeRedisClient()),
        object_storage=cast(Any, FakeObjectStorage()),
        runtime_controller=FakeRuntimeController(),
        reasoning_engine=None,
        context_engineering_service=None,
        projector=__import__(
            "platform.execution.projector",
            fromlist=["ExecutionProjector"],
        ).ExecutionProjector(),
    )
    execution_service.workflow_repository = cast(Any, workflow_repository)
    return workflow_service, execution_service, workflow_repository


@pytest.mark.asyncio
async def test_workflow_service_crud_and_trigger_lifecycle() -> None:
    workflow_service, _, workflow_repository = _build_services()
    actor_id = uuid4()
    workspace_id = uuid4()

    created = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Invoice Pipeline",
            description="first",
            yaml_source="""
schema_version: 1
steps:
  - id: fetch
    step_type: agent_task
    agent_fqn: finance.fetcher
            """.strip(),
            change_summary="initial",
            tags=["finance"],
            workspace_id=workspace_id,
        ),
        actor_id,
    )

    updated = await workflow_service.update_workflow(
        created.id,
        WorkflowUpdate(
            yaml_source="""
schema_version: 1
steps:
  - id: fetch
    step_type: agent_task
    agent_fqn: finance.fetcher
  - id: classify
    step_type: tool_call
    tool_fqn: finance.classifier
    depends_on: [fetch]
            """.strip(),
            change_summary="second",
        ),
        actor_id,
    )
    archived = await workflow_service.archive_workflow(created.id, actor_id)
    versions = await workflow_service.list_versions(created.id)

    trigger = await workflow_service.create_trigger(
        created.id,
        TriggerCreate(
            trigger_type="webhook",
            name="incoming",
            config={"secret": "super-secret"},
        ),
    )
    await workflow_service.record_trigger_fired(trigger.id, execution_id=None)
    trigger_list = await workflow_service.list_triggers(created.id)

    assert created.current_version is not None
    assert updated.current_version is not None
    assert updated.current_version.version_number == 2
    assert archived.status.value == "archived"
    assert [item.version_number for item in versions] == [1, 2]
    assert trigger.config["secret"] == "***"
    assert trigger_list.items[0].last_fired_at is not None
    assert (
        workflow_repository.definitions[created.id].current_version_id == updated.current_version.id
    )
