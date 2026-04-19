from __future__ import annotations

from platform.common.exceptions import ValidationError
from platform.execution.schemas import NamedStepsCheckpointPolicy
from platform.workflows.models import TriggerType
from platform.workflows.schemas import TriggerCreate, WorkflowCreate
from platform.workflows.service import WorkflowService
from textwrap import dedent
from typing import Any, cast
from uuid import uuid4

import pytest

from tests.workflow_execution_support import FakeProducer, FakeWorkflowRepository, make_settings


@pytest.mark.asyncio
async def test_workflow_service_validates_checkpoint_policy_and_cron_scheduler_hooks() -> None:
    scheduled_jobs: list[str] = []
    removed_jobs: list[str] = []

    class _Scheduler:
        def add_job(self, func, trigger, **kwargs: Any) -> None:
            del func, trigger
            scheduled_jobs.append(str(kwargs["id"]))

        def remove_job(self, job_id: str) -> None:
            removed_jobs.append(job_id)
            raise RuntimeError("already gone")

    workflow_repository = FakeWorkflowRepository()
    workflow_service = WorkflowService(
        repository=cast(Any, workflow_repository),
        settings=make_settings(),
        producer=cast(Any, FakeProducer()),
        scheduler=_Scheduler(),
    )
    actor_id = uuid4()
    workspace_id = uuid4()

    with pytest.raises(ValidationError, match="unknown step ids"):
        await workflow_service.create_workflow(
            WorkflowCreate(
                name="Invalid checkpoints",
                description=None,
                yaml_source=dedent("""
                    schema_version: 1
                    steps:
                      - id: fetch
                        step_type: agent_task
                        agent_fqn: finance.fetcher
                """).strip(),
                checkpoint_policy=NamedStepsCheckpointPolicy(
                    type="named_steps",
                    step_ids=["missing-step"],
                ),
                tags=[],
                workspace_id=workspace_id,
            ),
            actor_id,
        )

    created = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Cron workflow",
            description=None,
            yaml_source=dedent("""
                schema_version: 1
                steps:
                  - id: fetch
                    step_type: agent_task
                    agent_fqn: finance.fetcher
            """).strip(),
            checkpoint_policy=NamedStepsCheckpointPolicy(type="named_steps", step_ids=["fetch"]),
            tags=[],
            workspace_id=workspace_id,
        ),
        actor_id,
    )

    trigger = await workflow_service.create_trigger(
        created.id,
        TriggerCreate(
            trigger_type=TriggerType.cron,
            name="nightly",
            config={"cron_expression": "0 * * * *"},
        ),
    )
    await workflow_service.update_trigger(
        created.id,
        trigger.id,
        TriggerCreate(
            trigger_type=TriggerType.cron,
            name="nightly-updated",
            config={"cron_expression": "15 * * * *"},
        ),
    )
    await workflow_service.delete_trigger(created.id, trigger.id)

    assert scheduled_jobs.count(str(trigger.id)) == 2
    assert removed_jobs == [str(trigger.id), str(trigger.id)]
