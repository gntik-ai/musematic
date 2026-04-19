from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.execution.dependencies import get_execution_service
from platform.execution.exceptions import TraceNotAvailableError, TraceNotFoundError
from platform.execution.models import ExecutionReasoningTraceRecord
from platform.execution.router import router
from platform.execution.schemas import ExecutionCreate
from platform.workflows.schemas import WorkflowCreate
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from tests.unit.execution.test_service import _build_services


async def _seed_execution() -> tuple[Any, Any, Any, UUID, UUID]:
    workflow_service, execution_service, object_storage = _build_services()
    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Reasoning Trace Workflow",
            description=None,
            yaml_source="""
schema_version: 1
steps:
  - id: reasoning_step
    step_type: agent_task
    agent_fqn: ns:reasoner
""".strip(),
            tags=[],
            workspace_id=workspace_id,
        ),
        actor_id,
    )
    execution = await execution_service.create_execution(
        ExecutionCreate(
            workflow_definition_id=workflow.id,
            workspace_id=workspace_id,
            input_parameters={"prompt": "why"},
        ),
        created_by=actor_id,
    )
    await object_storage.create_bucket_if_not_exists(execution_service.reasoning_trace_bucket)
    return workflow_service, execution_service, object_storage, workspace_id, execution.id


@pytest.mark.asyncio
async def test_execution_service_get_reasoning_trace_supports_pagination_and_adapter_alias(
    ) -> None:
    _, execution_service, object_storage, workspace_id, execution_id = await _seed_execution()
    storage_key = f"reasoning-debates/{execution_id}/deb-1/trace.json"
    payload = {
        "execution_id": str(execution_id),
        "technique": "DEBATE",
        "schema_version": "1.0",
        "status": "complete",
        "steps": [
            {
                "step_number": 1,
                "type": "position",
                "agent_fqn": "agents.alpha",
                "content": "Prefer latency first.",
                "quality_score": 0.8,
                "tokens_used": 10,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            {
                "step_number": 2,
                "type": "critique",
                "agent_fqn": "agents.beta",
                "content": "Accuracy matters more.",
                "quality_score": 0.82,
                "tokens_used": 12,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            {
                "step_number": 3,
                "type": "synthesis",
                "agent_fqn": "agents.alpha",
                "content": "Use a latency-first default with escalation.",
                "quality_score": 0.9,
                "tokens_used": 15,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        ],
        "total_tokens": 37,
        "compute_budget_used": 0.42,
        "effective_budget_scope": "step",
        "consensus_reached": True,
        "compute_budget_exhausted": False,
    }
    await object_storage.upload_object(
        execution_service.reasoning_trace_bucket,
        storage_key,
        json.dumps(payload).encode("utf-8"),
    )
    await execution_service.repository.upsert_reasoning_trace_record(
        ExecutionReasoningTraceRecord(
            execution_id=execution_id,
            step_id="reasoning_step",
            technique="DEBATE",
            storage_key=storage_key,
            step_count=3,
            status="complete",
            compute_budget_used=0.42,
            consensus_reached=True,
            stabilized=None,
            degradation_detected=None,
            compute_budget_exhausted=False,
            effective_budget_scope="step",
        )
    )

    trace = await execution_service.get_reasoning_trace(
        execution_id,
        "reasoning_step",
        page=2,
        page_size=2,
        requester_workspace_id=workspace_id,
    )
    alias = await execution_service.get_reasoning_traces(execution_id, "reasoning_step")

    assert trace.technique == "DEBATE"
    assert trace.total_tokens == 37
    assert trace.consensus_reached is True
    assert trace.effective_budget_scope == "step"
    assert [item.step_number for item in trace.steps] == [3]
    assert trace.pagination.total_steps == 3
    assert trace.pagination.has_more is False
    assert len(alias) == 3
    assert alias[0]["type"] == "position"


@pytest.mark.asyncio
async def test_execution_service_get_reasoning_trace_raises_expected_errors() -> None:
    _, execution_service, _, workspace_id, execution_id = await _seed_execution()

    with pytest.raises(TraceNotFoundError):
        await execution_service.get_reasoning_trace(
            execution_id,
            "missing-step",
            requester_workspace_id=workspace_id,
        )

    expired_key = f"reasoning-corrections/{execution_id}/loop-1/trace.json"
    await execution_service.repository.upsert_reasoning_trace_record(
        ExecutionReasoningTraceRecord(
            execution_id=execution_id,
            step_id="expired_step",
            technique="SELF_CORRECTION",
            storage_key=expired_key,
            step_count=1,
            status="expired",
            compute_budget_used=0.1,
            consensus_reached=None,
            stabilized=False,
            degradation_detected=False,
            compute_budget_exhausted=False,
            effective_budget_scope="workflow",
        )
    )
    with pytest.raises(TraceNotAvailableError):
        await execution_service.get_reasoning_trace(
            execution_id,
            "expired_step",
            requester_workspace_id=workspace_id,
        )

    missing_key = f"reasoning-traces/{execution_id}/react-step/react_trace.json"
    await execution_service.repository.upsert_reasoning_trace_record(
        ExecutionReasoningTraceRecord(
            execution_id=execution_id,
            step_id="react_step",
            technique="REACT",
            storage_key=missing_key,
            step_count=1,
            status="in_progress",
            compute_budget_used=0.2,
            consensus_reached=None,
            stabilized=None,
            degradation_detected=None,
            compute_budget_exhausted=False,
            effective_budget_scope="workflow",
        )
    )
    with pytest.raises(TraceNotAvailableError):
        await execution_service.get_reasoning_trace(
            execution_id,
            "react_step",
            requester_workspace_id=workspace_id,
        )


@pytest.mark.asyncio
async def test_reasoning_trace_router_enforces_workspace_authorization() -> None:
    _, execution_service, object_storage, workspace_id, execution_id = await _seed_execution()
    storage_key = f"reasoning-corrections/{execution_id}/loop-1/trace.json"
    payload = {
        "execution_id": str(execution_id),
        "technique": "SELF_CORRECTION",
        "schema_version": "1.0",
        "status": "in_progress",
        "steps": [
            {
                "step_number": 1,
                "type": "iteration_input",
                "content": "Initial answer",
                "tokens_used": 8,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ],
        "total_tokens": 8,
        "compute_budget_used": 0.2,
        "stabilized": False,
        "degradation_detected": False,
        "last_updated_at": datetime.now(UTC).isoformat(),
    }
    await object_storage.upload_object(
        execution_service.reasoning_trace_bucket,
        storage_key,
        json.dumps(payload).encode("utf-8"),
    )
    await execution_service.repository.upsert_reasoning_trace_record(
        ExecutionReasoningTraceRecord(
            execution_id=execution_id,
            step_id="reasoning_step",
            technique="SELF_CORRECTION",
            storage_key=storage_key,
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

    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_execution_service] = lambda: execution_service
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(uuid4()),
        "workspace_id": str(workspace_id),
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        success = await client.get(f"/api/v1/executions/{execution_id}/reasoning-trace")

    app.dependency_overrides[get_current_user] = lambda: {
        "sub": str(uuid4()),
        "workspace_id": str(uuid4()),
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        forbidden = await client.get(f"/api/v1/executions/{execution_id}/reasoning-trace")

    assert success.status_code == 200
    assert success.json()["technique"] == "SELF_CORRECTION"
    assert success.json()["status"] == "in_progress"
    assert success.json()["effective_budget_scope"] == "workflow"
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "AUTHORIZATION_ERROR"
