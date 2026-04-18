from __future__ import annotations

from platform.common.exceptions import PolicySecretLeakError
from platform.execution.models import ExecutionStatus
from platform.policies.repository import PolicyRepository
from platform.workflows.ir import WorkflowIR

import pytest

from tests.unit.execution.test_scheduler import _build_scheduler


def make_bearer_token() -> str:
    return "".join(["Bearer ", "abcdefgh", "ijklmnop", "123456"])


def make_api_key() -> str:
    return "".join(["sk-", "abcdefgh", "ijklmnop", "123456"])


def make_jwt_token() -> str:
    return ".".join(
        [
            "eyJhbGciOiJIUzI1NiJ9",
            "eyJzdWIiOiJ1c2VyMSJ9",
            "signature123",
        ]
    )


def make_connection_string() -> str:
    return "".join(["postgres", "://", "user", ":", "pass", "@db", ":5432", "/prod"])


def make_password_literal() -> str:
    return "".join(["pass", "word=", "secret123"])


@pytest.mark.asyncio
async def test_prompt_preflight_blocks_bearer_token_and_publishes_alert(monkeypatch) -> None:
    workflow_service, execution_service, scheduler, _ = _build_scheduler()
    execution, step = await _create_execution_and_step(workflow_service, execution_service)
    blocked_records = []

    async def _record(self, record):
        blocked_records.append(record)
        return record

    monkeypatch.setattr(PolicyRepository, "create_blocked_action_record", _record)
    baseline = len(scheduler.producer.messages)

    with pytest.raises(PolicySecretLeakError) as excinfo:
        await scheduler._prompt_secret_preflight(
            {"prompt": make_bearer_token()},
            execution=execution,
            step=step,
        )

    assert excinfo.value.secret_type == "bearer_token"
    assert blocked_records[0].block_reason == "prompt_secret_detected:bearer_token"
    emitted = scheduler.producer.messages[baseline:]
    assert emitted[0]["event_type"] == "prompt_secret_detected"
    assert emitted[0]["payload"]["secret_type"] == "bearer_token"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "secret_type"),
    [
        ({"prompt": make_bearer_token()}, "bearer_token"),
        ({"prompt": make_api_key()}, "api_key"),
        ({"prompt": make_jwt_token()}, "jwt_token"),
        ({"prompt": make_connection_string()}, "connection_string"),
        ({"prompt": make_password_literal()}, "password_literal"),
    ],
)
async def test_prompt_preflight_detects_all_secret_patterns(
    monkeypatch,
    payload: dict[str, str],
    secret_type: str,
) -> None:
    workflow_service, execution_service, scheduler, _ = _build_scheduler()
    execution, step = await _create_execution_and_step(workflow_service, execution_service)

    async def _record(self, record):
        return record

    monkeypatch.setattr(PolicyRepository, "create_blocked_action_record", _record)

    with pytest.raises(PolicySecretLeakError) as excinfo:
        await scheduler._prompt_secret_preflight(payload, execution=execution, step=step)

    assert excinfo.value.secret_type == secret_type


@pytest.mark.asyncio
async def test_prompt_preflight_allows_clean_payload(monkeypatch) -> None:
    workflow_service, execution_service, scheduler, _ = _build_scheduler()
    execution, step = await _create_execution_and_step(workflow_service, execution_service)
    blocked_records = []

    async def _record(self, record):
        blocked_records.append(record)
        return record

    monkeypatch.setattr(PolicyRepository, "create_blocked_action_record", _record)
    baseline = len(scheduler.producer.messages)

    await scheduler._prompt_secret_preflight(
        {"prompt": "Summarize the latest ticket without exposing credentials."},
        execution=execution,
        step=step,
    )

    assert blocked_records == []
    assert scheduler.producer.messages[baseline:] == []


@pytest.mark.asyncio
async def test_process_execution_catches_policy_secret_leak_error(monkeypatch) -> None:
    workflow_service, execution_service, scheduler, _ = _build_scheduler()
    execution, _ = await _create_execution_and_step(workflow_service, execution_service)

    async def _persist(*args, **kwargs):
        del args, kwargs
        raise PolicySecretLeakError("api_key")

    monkeypatch.setattr(scheduler, "_persist_task_plan", _persist)

    await scheduler._process_execution(execution)

    refreshed = await execution_service.get_execution(execution.id)
    assert refreshed.status == ExecutionStatus.failed


async def _create_execution_and_step(workflow_service, execution_service):
    from platform.execution.schemas import ExecutionCreate
    from platform.workflows.schemas import WorkflowCreate
    from uuid import uuid4

    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Prompt Preflight Workflow",
            description=None,
            yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
            """.strip(),
            tags=[],
            workspace_id=workspace_id,
        ),
        actor_id,
    )
    execution_response = await execution_service.create_execution(
        ExecutionCreate(
            workflow_definition_id=workflow.id,
            workspace_id=workspace_id,
        ),
        created_by=actor_id,
    )
    execution = await execution_service.repository.get_execution_by_id(execution_response.id)
    assert execution is not None
    version = await execution_service._resolve_workflow_version(workflow.id, None)
    step = WorkflowIR.from_dict(version.compiled_ir).steps[0]
    return execution, step
