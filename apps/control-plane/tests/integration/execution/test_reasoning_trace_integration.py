from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.execution.models import ExecutionReasoningTraceRecord
from uuid import uuid4

import pytest

from tests.integration.execution.support import create_execution, create_workflow, create_workspace


@pytest.mark.asyncio
async def test_reasoning_trace_endpoint_returns_completed_and_in_progress_traces(
    workflow_execution_stack,
    workflow_execution_client,
    object_storage_client,
) -> None:
    workspace_id = await create_workspace(workflow_execution_stack)
    workflow_execution_stack.current_user["workspace_id"] = str(workspace_id)
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Reasoning trace workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: reasoning_step
    step_type: agent_task
    agent_fqn: ns:reasoner
""",
    )
    execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
    )
    await object_storage_client.create_bucket_if_not_exists(
        workflow_execution_stack.execution_service.reasoning_trace_bucket
    )

    debate_key = f"reasoning-debates/{execution_id}/deb-1/trace.json"
    await object_storage_client.upload_object(
        workflow_execution_stack.execution_service.reasoning_trace_bucket,
        debate_key,
        json.dumps(
            {
                "execution_id": str(execution_id),
                "technique": "DEBATE",
                "schema_version": "1.0",
                "status": "complete",
                "steps": [
                    {
                        "step_number": 1,
                        "type": "position",
                        "agent_fqn": "agents.alpha",
                        "content": "Prefer accuracy.",
                        "tokens_used": 13,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    {
                        "step_number": 2,
                        "type": "synthesis",
                        "agent_fqn": "agents.beta",
                        "content": "Use accuracy with fallback.",
                        "tokens_used": 21,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                ],
                "total_tokens": 34,
                "compute_budget_used": 0.6,
                "effective_budget_scope": "step",
                "consensus_reached": True,
                "compute_budget_exhausted": False,
            }
        ).encode("utf-8"),
    )
    await workflow_execution_stack.execution_repository.upsert_reasoning_trace_record(
        ExecutionReasoningTraceRecord(
            execution_id=execution_id,
            step_id="reasoning_step",
            technique="DEBATE",
            storage_key=debate_key,
            step_count=2,
            status="complete",
            compute_budget_used=0.6,
            consensus_reached=True,
            stabilized=None,
            degradation_detected=None,
            compute_budget_exhausted=False,
            effective_budget_scope="step",
        )
    )

    completed = await workflow_execution_client.get(
        f"/api/v1/executions/{execution_id}/reasoning-trace?step_id=reasoning_step"
    )
    paged = await workflow_execution_client.get(
        f"/api/v1/executions/{execution_id}/reasoning-trace?step_id=reasoning_step&page=1&page_size=1"
    )

    correction_key = f"reasoning-corrections/{execution_id}/loop-1/trace.json"
    await object_storage_client.upload_object(
        workflow_execution_stack.execution_service.reasoning_trace_bucket,
        correction_key,
        json.dumps(
            {
                "execution_id": str(execution_id),
                "technique": "SELF_CORRECTION",
                "schema_version": "1.0",
                "status": "in_progress",
                "steps": [
                    {
                        "step_number": 1,
                        "type": "iteration_input",
                        "content": "Draft answer",
                        "tokens_used": 5,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                ],
                "total_tokens": 5,
                "compute_budget_used": 0.2,
                "effective_budget_scope": "workflow",
                "stabilized": False,
                "degradation_detected": False,
                "last_updated_at": datetime.now(UTC).isoformat(),
            }
        ).encode("utf-8"),
    )
    await workflow_execution_stack.execution_repository.upsert_reasoning_trace_record(
        ExecutionReasoningTraceRecord(
            execution_id=execution_id,
            step_id="live_step",
            technique="SELF_CORRECTION",
            storage_key=correction_key,
            step_count=1,
            status="in_progress",
            compute_budget_used=0.2,
            consensus_reached=None,
            stabilized=False,
            degradation_detected=False,
            compute_budget_exhausted=False,
            effective_budget_scope="workflow",
        )
    )
    in_progress = await workflow_execution_client.get(
        f"/api/v1/executions/{execution_id}/reasoning-trace?step_id=live_step"
    )

    assert completed.status_code == 200
    assert completed.json()["technique"] == "DEBATE"
    assert completed.json()["consensus_reached"] is True
    assert completed.json()["effective_budget_scope"] == "step"
    assert paged.status_code == 200
    assert paged.json()["pagination"]["has_more"] is True
    assert len(paged.json()["steps"]) == 1
    assert in_progress.status_code == 200
    assert in_progress.json()["status"] == "in_progress"
    assert in_progress.json()["effective_budget_scope"] == "workflow"
    assert in_progress.json()["last_updated_at"] is not None


@pytest.mark.asyncio
async def test_reasoning_trace_endpoint_rejects_unauthorized_and_expired_requests(
    workflow_execution_stack,
    workflow_execution_client,
) -> None:
    workspace_id = await create_workspace(workflow_execution_stack)
    workflow_execution_stack.current_user["workspace_id"] = str(workspace_id)
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Reasoning trace auth workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: reasoning_step
    step_type: agent_task
    agent_fqn: ns:reasoner
""",
    )
    execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
    )
    expired_key = f"reasoning-debates/{execution_id}/deb-2/trace.json"
    await workflow_execution_stack.execution_repository.upsert_reasoning_trace_record(
        ExecutionReasoningTraceRecord(
            execution_id=execution_id,
            step_id="expired_step",
            technique="DEBATE",
            storage_key=expired_key,
            step_count=0,
            status="expired",
            compute_budget_used=0.0,
            consensus_reached=None,
            stabilized=None,
            degradation_detected=None,
            compute_budget_exhausted=False,
            effective_budget_scope="workflow",
        )
    )

    expired = await workflow_execution_client.get(
        f"/api/v1/executions/{execution_id}/reasoning-trace?step_id=expired_step"
    )
    workflow_execution_stack.current_user["workspace_id"] = str(uuid4())
    forbidden = await workflow_execution_client.get(
        f"/api/v1/executions/{execution_id}/reasoning-trace?step_id=expired_step"
    )
    missing = await workflow_execution_client.get(
        f"/api/v1/executions/{uuid4()}/reasoning-trace"
    )

    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "TRACE_NOT_AVAILABLE"
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "AUTHORIZATION_ERROR"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "EXECUTION_NOT_FOUND"
