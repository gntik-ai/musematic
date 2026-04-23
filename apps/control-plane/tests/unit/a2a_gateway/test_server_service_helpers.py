from __future__ import annotations

from platform.a2a_gateway.exceptions import (
    A2AAgentNotFoundError,
    A2AAuthenticationError,
    A2AAuthorizationError,
    A2APayloadTooLargeError,
    A2AProtocolVersionError,
    A2ATaskNotFoundError,
)
from platform.a2a_gateway.models import A2ATaskState
from platform.a2a_gateway.schemas import A2AMessage, A2AMessagePart, A2ATaskSubmitRequest
from platform.a2a_gateway.server_service import (
    A2AServerService,
    build_result_message,
    extract_text,
    replace_text,
)
from platform.interactions.models import InteractionState
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from tests.a2a_gateway_support import (
    AuthServiceStub,
    ExecuteResultStub,
    FakeA2ARepository,
    FakeRedisClient,
    RecordingEventPublisher,
    SanitizationStub,
    SessionStub,
    ToolGatewayStub,
    build_agent_profile,
    build_principal,
    build_settings,
    build_task,
)


def _service(
    *,
    repo: FakeA2ARepository | None = None,
    tool_gateway: ToolGatewayStub | None = None,
) -> tuple[A2AServerService, FakeA2ARepository]:
    repository = repo or FakeA2ARepository()
    service = A2AServerService(
        repository=repository,
        settings=build_settings(),
        auth_service=AuthServiceStub(),
        tool_gateway=tool_gateway
        or ToolGatewayStub(sanitize_result=SanitizationStub(output="clean result")),
        redis_client=FakeRedisClient(),
        event_publisher=RecordingEventPublisher(),
        card_generator=SimpleNamespace(generate_platform_card=AsyncMock(return_value={})),
    )
    return service, repository


@pytest.mark.asyncio
async def test_submit_task_rejects_workspace_mismatch_before_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository = _service()
    agent = build_agent_profile()
    principal = build_principal(workspace_id=uuid4())
    monkeypatch.setattr(service, "_resolve_agent", AsyncMock(return_value=agent))

    with pytest.raises(A2AAuthorizationError):
        await service.submit_task(
            A2ATaskSubmitRequest(
                agent_fqn=agent.fqn,
                message=A2AMessage(role="user", parts=[A2AMessagePart(text="do work")]),
            ),
            principal=principal,
        )

    assert service.tool_gateway.validate_calls == []
    assert repository.policy_blocked[-1].block_reason == "workspace_denied"


@pytest.mark.asyncio
async def test_cancel_and_access_helpers_cover_missing_terminal_and_forbidden() -> None:
    service, repository = _service()
    principal = build_principal()
    completed = build_task(principal_id=UUID(principal["sub"]), a2a_state=A2ATaskState.completed)
    foreign = build_task(principal_id=uuid4())
    repository.tasks[completed.task_id] = completed
    repository.tasks[foreign.task_id] = foreign

    response = await service.cancel_task(completed.task_id, principal=principal)

    assert response.a2a_state is A2ATaskState.completed
    with pytest.raises(A2ATaskNotFoundError):
        await service.get_task_status("missing", principal=principal)
    with pytest.raises(A2AAuthorizationError):
        await service.get_task_status(foreign.task_id, principal=principal)


@pytest.mark.asyncio
async def test_progress_task_handles_state_transitions(monkeypatch: pytest.MonkeyPatch) -> None:
    service, repository = _service()

    pending = build_task(a2a_state=A2ATaskState.cancellation_pending)
    waiting = build_task(a2a_state=A2ATaskState.working)
    failed = build_task(task_id="failed-task", a2a_state=A2ATaskState.working)
    canceled = build_task(task_id="canceled-task", a2a_state=A2ATaskState.working)
    submitted = build_task(task_id="submitted-task", a2a_state=A2ATaskState.submitted)
    erroring = build_task(
        task_id="error-task",
        a2a_state=A2ATaskState.working,
        submitted_message=build_result_message("please fail"),
    )

    monkeypatch.setattr(service, "_interaction_state", AsyncMock(return_value=None))
    await service._progress_task(pending)
    await service._progress_task(submitted)
    await service._progress_task(erroring)

    monkeypatch.setattr(
        service, "_interaction_state", AsyncMock(return_value=InteractionState.waiting)
    )
    await service._progress_task(waiting)

    monkeypatch.setattr(
        service, "_interaction_state", AsyncMock(return_value=InteractionState.failed)
    )
    await service._progress_task(failed)

    monkeypatch.setattr(
        service, "_interaction_state", AsyncMock(return_value=InteractionState.canceled)
    )
    await service._progress_task(canceled)

    assert pending.a2a_state is A2ATaskState.cancelled
    assert submitted.a2a_state is A2ATaskState.working
    assert waiting.a2a_state is A2ATaskState.input_required
    assert failed.a2a_state is A2ATaskState.failed
    assert canceled.a2a_state is A2ATaskState.cancelled
    assert erroring.a2a_state is A2ATaskState.failed
    assert {record.action for record in repository.audits} >= {
        "task_cancelled",
        "task_state_changed",
        "task_failed",
    }


@pytest.mark.asyncio
async def test_resolve_agent_sanitize_and_helper_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    service, repository = _service(
        tool_gateway=ToolGatewayStub(sanitize_result=SanitizationStub(output="safe"))
    )
    repository.session = SessionStub(execute_results=[ExecuteResultStub(scalar=None)])

    with pytest.raises(A2AAgentNotFoundError):
        await service._resolve_agent("missing:agent")

    agent = build_agent_profile()
    task = build_task(agent_fqn=agent.fqn, workspace_id=agent.workspace_id)
    monkeypatch.setattr(service, "_resolve_agent", AsyncMock(return_value=agent))
    sanitized = await service._sanitize_result(task, build_result_message("raw result"))

    assert sanitized["parts"][0]["text"] == "safe"
    assert repository.audits == []
    assert (
        await service._interaction_state(build_task(interaction_id=None, workspace_id=None)) is None
    )


def test_validation_and_text_helpers_cover_edge_cases() -> None:
    service, _ = _service()
    service.settings = build_settings(A2A_MAX_PAYLOAD_BYTES=10)

    with pytest.raises(A2AProtocolVersionError):
        service._validate_protocol("2.0")
    with pytest.raises(A2APayloadTooLargeError):
        service._validate_payload_size(
            A2ATaskSubmitRequest(
                agent_fqn="finance:verifier",
                message=A2AMessage(role="user", parts=[A2AMessagePart(text="x" * 50)]),
            )
        )
    with pytest.raises(A2AAuthenticationError):
        service._principal_id({})

    workspace_id = uuid4()
    assert (
        service._principal_can_access_workspace(
            {"roles": [{"role": "owner"}]},
            workspace_id,
        )
        is True
    )
    assert (
        service._principal_can_access_workspace(
            {"workspace_id": str(workspace_id)},
            workspace_id,
        )
        is True
    )
    assert (
        service._principal_can_access_workspace(
            {"roles": [{"role": "member", "workspace_id": str(workspace_id)}]},
            workspace_id,
        )
        is True
    )
    assert (
        service._principal_can_access_workspace(
            {"roles": [{"role": "member", "workspace_id": str(uuid4())}]},
            workspace_id,
        )
        is False
    )
    assert service._is_operator({"roles": [{"role": "platform_operator"}]}) is True
    assert service._is_operator({"roles": [{"role": "member"}]}) is False

    assert extract_text({"parts": ["x", {"type": "text", "text": "hello"}]}) == "hello"
    assert replace_text({}, "fallback")["parts"][0]["text"] == "fallback"
    assert replace_text({"parts": ["raw"]}, "safe")["parts"][0]["text"] == "raw"
