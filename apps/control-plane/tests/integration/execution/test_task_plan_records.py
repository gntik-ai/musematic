from __future__ import annotations

import json
from uuid import uuid4

import pytest

from tests.integration.execution.support import create_execution, create_workflow


@pytest.mark.asyncio
async def test_task_plan_records_exist_before_dispatch_and_are_exposed_via_api(
    workflow_execution_stack,
    workflow_execution_client,
    object_storage_client,
) -> None:
    workspace_id = uuid4()
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Task Plan Workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: choose_agent
    step_type: agent_task
    agent_fqn: ops.triage
    input_bindings:
      ticket_id: $.input.ticket_id
        """,
    )
    execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        input_parameters={"ticket_id": "INC-42"},
    )

    observed: dict[str, object] = {}

    async def capture_dispatch(payload: dict[str, object]) -> None:
        record = await workflow_execution_stack.execution_repository.get_task_plan_record(
            execution_id,
            "choose_agent",
        )
        assert record is not None
        observed["record_step_id"] = record.step_id
        observed["storage_key"] = record.storage_key
        raw = await object_storage_client.download_object(
            workflow_execution_stack.execution_service.task_plan_bucket,
            f"{execution_id}/choose_agent/task-plan.json",
        )
        observed["payload"] = json.loads(raw.decode("utf-8"))

    workflow_execution_stack.runtime_controller_stub.dispatch.side_effect = capture_dispatch

    await workflow_execution_stack.scheduler_service.tick()

    assert observed["record_step_id"] == "choose_agent"
    payload = observed["payload"]
    assert isinstance(payload, dict)
    assert payload["parameters"]["ticket_id"]["provenance"] == "user_input"
    assert payload["considered_agents"] == [
        {"fqn": "ops.triage", "capabilities": [], "selection_score": 1.0}
    ]
    assert payload["rejected_alternatives"] == []

    list_response = await workflow_execution_client.get(
        f"/api/v1/executions/{execution_id}/task-plan",
    )
    detail_response = await workflow_execution_client.get(
        f"/api/v1/executions/{execution_id}/task-plan/choose_agent",
    )
    journal_response = await workflow_execution_client.get(
        f"/api/v1/executions/{execution_id}/journal",
    )

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert journal_response.status_code == 200

    list_payload = list_response.json()
    detail_payload = detail_response.json()
    journal_payload = journal_response.json()

    assert len(list_payload) == 1
    assert list_payload[0]["step_id"] == "choose_agent"
    assert detail_payload["considered_agents"] == [
        {"fqn": "ops.triage", "capabilities": [], "selection_score": 1.0}
    ]
    assert detail_payload["parameters"]["ticket_id"]["provenance"] == "user_input"
    assert detail_payload["rejected_alternatives"] == []
    assert "storage_key" in list_payload[0]
    assert "storage_key" not in journal_payload["items"][0]
