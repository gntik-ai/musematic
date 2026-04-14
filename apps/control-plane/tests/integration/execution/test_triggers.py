from __future__ import annotations

import hmac
from hashlib import sha256
from platform.common.events.envelope import make_envelope
from platform.common.exceptions import ValidationError
from platform.execution.events import (
    event_bus_consumer_handler,
    fire_cron_trigger,
    workspace_goal_consumer_handler,
)
from platform.workflows.models import TriggerType
from platform.workflows.schemas import TriggerCreate
from uuid import uuid4

import pytest

from tests.integration.execution.support import create_workflow


@pytest.mark.asyncio
async def test_trigger_handlers_support_webhook_cron_workspace_goal_and_event_bus(
    workflow_execution_stack,
    workflow_execution_client,
) -> None:
    workspace_id = uuid4()
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Trigger Workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ops.fetch
        """,
    )

    webhook_trigger = await workflow_execution_stack.workflow_service.create_trigger(
        workflow_id,
        TriggerCreate(
            trigger_type=TriggerType.webhook,
            name="Webhook trigger",
            config={"secret": "hook-secret"},
        ),
    )
    cron_trigger = await workflow_execution_stack.workflow_service.create_trigger(
        workflow_id,
        TriggerCreate(
            trigger_type=TriggerType.cron,
            name="Cron trigger",
            config={"cron_expression": "0 5 * * *", "timezone": "UTC"},
        ),
    )
    goal_trigger = await workflow_execution_stack.workflow_service.create_trigger(
        workflow_id,
        TriggerCreate(
            trigger_type=TriggerType.workspace_goal,
            name="Goal trigger",
            config={
                "workspace_id": str(workspace_id),
                "goal_type_pattern": "analyze-*",
            },
        ),
    )
    event_trigger = await workflow_execution_stack.workflow_service.create_trigger(
        workflow_id,
        TriggerCreate(
            trigger_type=TriggerType.event_bus,
            name="Event bus trigger",
            config={"topic": "connector.ingress", "event_type_pattern": "order.*"},
        ),
    )
    del goal_trigger, event_trigger

    raw_payload = b'{"invoice":"INV-1"}'
    signature = hmac.new(b"hook-secret", raw_payload, sha256).hexdigest()
    accepted = await workflow_execution_client.post(
        f"/api/v1/workflows/{workflow_id}/webhook/{webhook_trigger.id}",
        content=raw_payload,
        headers={
            "content-type": "application/json",
            "x-webhook-signature": signature,
        },
    )
    rejected = await workflow_execution_client.post(
        f"/api/v1/workflows/{workflow_id}/webhook/{webhook_trigger.id}",
        content=raw_payload,
        headers={
            "content-type": "application/json",
            "x-webhook-signature": "invalid",
        },
    )

    cron_execution_id = await fire_cron_trigger(
        cron_trigger.id,
        workflow_service=workflow_execution_stack.workflow_service,
        execution_service=workflow_execution_stack.execution_service,
    )
    goal_execution_ids = await workspace_goal_consumer_handler(
        make_envelope(
            "goal.created",
            "workspace.goal",
            {
                "workspace_id": str(workspace_id),
                "goal_id": str(uuid4()),
                "goal_type": "analyze-quarterly-spend",
            },
        ),
        workflow_service=workflow_execution_stack.workflow_service,
        execution_service=workflow_execution_stack.execution_service,
    )
    event_execution_ids = await event_bus_consumer_handler(
        make_envelope(
            "order.created",
            "event.bus",
            {"topic": "connector.ingress", "event_type": "order.created"},
        ),
        workflow_service=workflow_execution_stack.workflow_service,
        execution_service=workflow_execution_stack.execution_service,
    )

    assert accepted.status_code == 202
    assert rejected.status_code == 401

    cron_execution = await workflow_execution_stack.execution_service.get_execution(
        cron_execution_id
    )
    goal_execution = await workflow_execution_stack.execution_service.get_execution(
        goal_execution_ids[0]
    )
    event_execution = await workflow_execution_stack.execution_service.get_execution(
        event_execution_ids[0]
    )

    assert cron_execution.trigger_type == TriggerType.cron
    assert goal_execution.trigger_type == TriggerType.workspace_goal
    assert goal_execution.correlation_goal_id is not None
    assert event_execution.trigger_type == TriggerType.event_bus


@pytest.mark.asyncio
async def test_trigger_handlers_enforce_concurrency_limits_and_ignore_non_matches(
    workflow_execution_stack,
) -> None:
    workspace_id = uuid4()
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Limited Trigger Workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ops.fetch
        """,
    )

    await workflow_execution_stack.workflow_service.create_trigger(
        workflow_id,
        TriggerCreate(
            trigger_type=TriggerType.workspace_goal,
            name="Single active goal trigger",
            config={
                "workspace_id": str(workspace_id),
                "goal_type_pattern": "match-*",
            },
            max_concurrent_executions=1,
        ),
    )
    await workflow_execution_stack.workflow_service.create_trigger(
        workflow_id,
        TriggerCreate(
            trigger_type=TriggerType.event_bus,
            name="Non matching bus trigger",
            config={"topic": "connector.ingress", "event_type_pattern": "invoice.*"},
        ),
    )

    matching_goal_event = make_envelope(
        "goal.created",
        "workspace.goal",
        {
            "workspace_id": str(workspace_id),
            "goal_id": str(uuid4()),
            "goal_type": "match-quarterly",
        },
    )
    created_execution_ids = await workspace_goal_consumer_handler(
        matching_goal_event,
        workflow_service=workflow_execution_stack.workflow_service,
        execution_service=workflow_execution_stack.execution_service,
    )

    assert len(created_execution_ids) == 1

    with pytest.raises(ValidationError, match="Trigger concurrency limit reached"):
        await workspace_goal_consumer_handler(
            make_envelope(
                "goal.created",
                "workspace.goal",
                {
                    "workspace_id": str(workspace_id),
                    "goal_id": str(uuid4()),
                    "goal_type": "match-yearly",
                },
            ),
            workflow_service=workflow_execution_stack.workflow_service,
            execution_service=workflow_execution_stack.execution_service,
        )

    non_matching_event_ids = await event_bus_consumer_handler(
        make_envelope(
            "order.created",
            "event.bus",
            {"topic": "connector.egress", "event_type": "order.created"},
        ),
        workflow_service=workflow_execution_stack.workflow_service,
        execution_service=workflow_execution_stack.execution_service,
    )
    assert non_matching_event_ids == []
