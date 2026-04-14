from __future__ import annotations

from datetime import UTC, datetime
from platform.common.exceptions import ValidationError
from platform.workflows.exceptions import TriggerNotFoundError, WorkflowNotFoundError
from platform.workflows.models import TriggerType, WorkflowDefinition, WorkflowStatus
from platform.workflows.schemas import TriggerCreate, WorkflowCreate
from platform.workflows.service import WorkflowService
from typing import Any, cast
from unittest.mock import Mock
from uuid import uuid4

import pytest

from tests.workflow_execution_support import FakeProducer, FakeWorkflowRepository, make_settings


def _build_service(
    *,
    scheduler: Any | None = None,
) -> tuple[WorkflowService, FakeWorkflowRepository]:
    repository = FakeWorkflowRepository()
    service = WorkflowService(
        repository=cast(Any, repository),
        settings=make_settings(),
        producer=cast(Any, FakeProducer()),
        scheduler=scheduler,
    )
    return service, repository


@pytest.mark.asyncio
async def test_workflow_service_rejects_duplicate_and_missing_resources() -> None:
    service, _ = _build_service()
    actor_id = uuid4()
    workspace_id = uuid4()
    created = await service.create_workflow(
        WorkflowCreate(
            name="Invoice Workflow",
            description=None,
            yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: finance.agent
            """.strip(),
            tags=["finance"],
            workspace_id=workspace_id,
        ),
        actor_id,
    )

    with pytest.raises(ValidationError, match="already exists"):
        await service.create_workflow(
            WorkflowCreate(
                name="Invoice Workflow",
                description=None,
                yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: finance.agent
                """.strip(),
                tags=[],
                workspace_id=workspace_id,
            ),
            actor_id,
        )

    with pytest.raises(WorkflowNotFoundError):
        await service.get_workflow(uuid4())
    with pytest.raises(WorkflowNotFoundError):
        await service.get_version(created.id, 99)
    with pytest.raises(TriggerNotFoundError):
        await service.update_trigger(
            created.id,
            uuid4(),
            TriggerCreate(trigger_type=TriggerType.webhook, name="missing", config={}),
        )
    with pytest.raises(TriggerNotFoundError):
        await service.delete_trigger(created.id, uuid4())
    with pytest.raises(TriggerNotFoundError):
        await service.record_trigger_fired(uuid4(), execution_id=None)

    await service.archive_workflow(created.id, actor_id)
    with pytest.raises(ValidationError, match="already archived"):
        await service.archive_workflow(created.id, actor_id)


@pytest.mark.asyncio
async def test_workflow_service_manages_cron_scheduler_hooks_and_response_helpers() -> None:
    scheduler = Mock()
    scheduler.add_job = Mock()
    scheduler.remove_job = Mock(side_effect=RuntimeError("missing"))
    service, repository = _build_service(scheduler=scheduler)
    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await service.create_workflow(
        WorkflowCreate(
            name="Cron Workflow",
            description=None,
            yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: finance.agent
            """.strip(),
            tags=[],
            workspace_id=workspace_id,
        ),
        actor_id,
    )

    cron_trigger = await service.create_trigger(
        workflow.id,
        TriggerCreate(
            trigger_type=TriggerType.cron,
            name="nightly",
            config={"cron_expression": "0 3 * * *", "secret": "top-secret"},
        ),
    )
    noop_trigger = await service.create_trigger(
        workflow.id,
        TriggerCreate(
            trigger_type=TriggerType.cron,
            name="disabled",
            is_active=False,
            config={},
        ),
    )
    updated_trigger = await service.update_trigger(
        workflow.id,
        cron_trigger.id,
        TriggerCreate(
            trigger_type=TriggerType.cron,
            name="nightly-v2",
            config={"cron_expression": "0 4 * * *", "secret": "another"},
        ),
    )
    await service.delete_trigger(workflow.id, cron_trigger.id)

    orphan = WorkflowDefinition(
        name="Orphan",
        description=None,
        status=WorkflowStatus.active,
        schema_version=1,
        tags=[],
        workspace_id=workspace_id,
        created_by=actor_id,
        updated_by=actor_id,
    )
    orphan.id = uuid4()
    orphan.current_version = None
    orphan.created_at = datetime.now(UTC)
    orphan.updated_at = orphan.created_at

    orphan_response = WorkflowService._workflow_response(orphan)

    assert cron_trigger.config["secret"] == "***"
    assert noop_trigger.is_active is False
    assert updated_trigger.name == "nightly-v2"
    assert orphan_response.current_version is None
    assert scheduler.add_job.call_count == 2
    scheduler.remove_job.assert_called()
    assert cron_trigger.id not in repository.triggers
