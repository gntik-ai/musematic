from __future__ import annotations

from platform.a2a_gateway.exceptions import (
    A2AAuthenticationError,
    A2AAuthorizationError,
    A2AInvalidTaskStateError,
    A2ARateLimitError,
)
from platform.a2a_gateway.models import A2ATaskState
from platform.a2a_gateway.schemas import (
    A2AFollowUpRequest,
    A2AMessage,
    A2AMessagePart,
    A2ATaskSubmitRequest,
)
from platform.a2a_gateway.server_service import A2AServerService
from platform.auth.exceptions import InvalidAccessTokenError
from platform.common.clients.redis import RateLimitResult
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from tests.a2a_gateway_support import (
    AuthServiceStub,
    DecisionStub,
    FakeA2ARepository,
    FakeRedisClient,
    InteractionRepositoryStub,
    RecordingEventPublisher,
    SanitizationStub,
    ToolGatewayStub,
    build_agent_profile,
    build_principal,
    build_settings,
    build_task,
    expired_time,
)


def _service(
    *,
    repo: FakeA2ARepository | None = None,
    tool_gateway: ToolGatewayStub | None = None,
    redis: FakeRedisClient | None = None,
    auth: AuthServiceStub | None = None,
) -> tuple[A2AServerService, FakeA2ARepository, RecordingEventPublisher, InteractionRepositoryStub]:
    repository = repo or FakeA2ARepository()
    publisher = RecordingEventPublisher()
    interactions = InteractionRepositoryStub()
    service = A2AServerService(
        repository=repository,
        settings=build_settings(),
        auth_service=auth or AuthServiceStub(),
        tool_gateway=(
            tool_gateway or ToolGatewayStub(sanitize_result=SanitizationStub(output="clean result"))
        ),
        redis_client=redis or FakeRedisClient(),
        event_publisher=publisher,
        card_generator=SimpleNamespace(
            generate_platform_card=AsyncMock(return_value={"name": "mesh"})
        ),
    )
    return service, repository, publisher, interactions


@pytest.mark.asyncio
async def test_authenticate_wraps_invalid_tokens_and_card_generation() -> None:
    failing_service, _, _, _ = _service(auth=AuthServiceStub(InvalidAccessTokenError()))
    with pytest.raises(A2AAuthenticationError):
        await failing_service.authenticate("bad-token")

    service, _, _, _ = _service()
    card = await service.get_platform_agent_card(base_url="https://mesh.example")
    assert card == {"name": "mesh"}


@pytest.mark.asyncio
async def test_submit_task_creates_task_interaction_and_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, repository, publisher, interactions = _service()
    agent = build_agent_profile()
    principal = build_principal(workspace_id=agent.workspace_id)
    monkeypatch.setattr(
        "platform.a2a_gateway.server_service.InteractionsRepository",
        lambda session: interactions,
    )
    monkeypatch.setattr(service, "_resolve_agent", AsyncMock(return_value=agent))

    response = await service.submit_task(
        A2ATaskSubmitRequest(
            agent_fqn=agent.fqn,
            message=A2AMessage(
                role="user",
                parts=[A2AMessagePart(text="please summarize")],
            ),
        ),
        principal=principal,
    )

    stored = repository.tasks[response.task_id]
    assert response.a2a_state is A2ATaskState.submitted
    assert stored.workspace_id == agent.workspace_id
    assert interactions.conversations
    assert interactions.messages[0]["metadata"]["a2a_message"]["role"] == "user"
    assert publisher.events[0]["event_type"].value == "a2a.task.submitted"
    assert repository.audits[0].action == "task_submitted"


@pytest.mark.asyncio
async def test_submit_task_policy_denial_and_rate_limit_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = build_agent_profile()
    principal = build_principal(workspace_id=agent.workspace_id)

    denied_service, denied_repo, _, _ = _service(
        tool_gateway=ToolGatewayStub(
            validate_result=DecisionStub(allowed=False, block_reason="policy")
        )
    )
    monkeypatch.setattr(denied_service, "_resolve_agent", AsyncMock(return_value=agent))
    with pytest.raises(A2AAuthorizationError):
        await denied_service.submit_task(
            A2ATaskSubmitRequest(
                agent_fqn=agent.fqn,
                message=A2AMessage(role="user", parts=[A2AMessagePart(text="do work")]),
            ),
            principal=principal,
        )
    assert denied_repo.policy_blocked[-1].block_reason == "policy"
    assert denied_repo.audits[-1].result == "denied"

    limited_service, limited_repo, _, interactions = _service(
        redis=FakeRedisClient(
            rate_limit_results=[RateLimitResult(allowed=False, remaining=0, retry_after_ms=1200)]
        )
    )
    monkeypatch.setattr(
        "platform.a2a_gateway.server_service.InteractionsRepository",
        lambda session: interactions,
    )
    monkeypatch.setattr(limited_service, "_resolve_agent", AsyncMock(return_value=agent))
    with pytest.raises(A2ARateLimitError):
        await limited_service.submit_task(
            A2ATaskSubmitRequest(
                agent_fqn=agent.fqn,
                message=A2AMessage(role="user", parts=[A2AMessagePart(text="do work")]),
            ),
            principal=principal,
        )
    assert limited_repo.policy_blocked[-1].block_reason == "rate_limit_exceeded"
    assert limited_repo.audits[-1].action == "rate_limited"


@pytest.mark.asyncio
async def test_get_task_status_follow_up_and_completion_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = build_agent_profile()
    service, repository, _, interactions = _service(
        tool_gateway=ToolGatewayStub(
            sanitize_result=SanitizationStub(
                output="clean result",
                redaction_count=1,
                redacted_types=["secret"],
            )
        )
    )
    principal = build_principal(subject=UUID(str(agent.id)), workspace_id=agent.workspace_id)
    clarify_task = build_task(
        principal_id=UUID(principal["sub"]),
        workspace_id=agent.workspace_id,
        submitted_message={
            "role": "user",
            "parts": [{"type": "text", "text": "clarify this"}],
        },
    )
    done_task = build_task(
        task_id="done-task",
        principal_id=UUID(principal["sub"]),
        workspace_id=agent.workspace_id,
        a2a_state=A2ATaskState.working,
        submitted_message={
            "role": "user",
            "parts": [{"type": "text", "text": "normal request"}],
        },
    )
    repository.tasks[clarify_task.task_id] = clarify_task
    repository.tasks[done_task.task_id] = done_task
    monkeypatch.setattr(
        "platform.a2a_gateway.server_service.InteractionsRepository",
        lambda session: interactions,
    )
    monkeypatch.setattr(service, "_resolve_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(service, "_interaction_state", AsyncMock(return_value=None))

    first = await service.get_task_status(clarify_task.task_id, principal=principal)
    second = await service.get_task_status(clarify_task.task_id, principal=principal)
    assert first.a2a_state is A2ATaskState.working
    assert second.a2a_state is A2ATaskState.input_required
    assert second.result is not None
    assert second.result["prompt"]
    assert clarify_task.idle_timeout_at is not None

    follow_up = await service.submit_follow_up(
        clarify_task.task_id,
        A2AFollowUpRequest(
            message=A2AMessage(role="user", parts=[A2AMessagePart(text="extra detail")])
        ),
        principal=principal,
    )
    assert follow_up.a2a_state is A2ATaskState.working
    assert interactions.messages[-1]["content"] == "extra detail"

    completed = await service.get_task_status(done_task.task_id, principal=principal)
    assert completed.a2a_state is A2ATaskState.completed
    assert completed.result == {
        "role": "agent",
        "parts": [{"type": "text", "text": "clean result"}],
    }
    assert {record.action for record in repository.audits} >= {"sanitized", "task_completed"}

    with pytest.raises(A2AInvalidTaskStateError):
        await service.submit_follow_up(
            done_task.task_id,
            A2AFollowUpRequest(
                message=A2AMessage(role="user", parts=[A2AMessagePart(text="retry")])
            ),
            principal=principal,
        )


@pytest.mark.asyncio
async def test_cancel_and_idle_timeout_scan_emit_cancellation_events() -> None:
    service, repository, publisher, _ = _service()
    principal = build_principal()
    task = build_task(principal_id=UUID(principal["sub"]))
    expired = build_task(
        task_id="expired-task",
        a2a_state=A2ATaskState.input_required,
        principal_id=UUID(principal["sub"]),
        idle_timeout_at=expired_time(),
    )
    repository.tasks[task.task_id] = task
    repository.tasks[expired.task_id] = expired

    cancelled = await service.cancel_task(task.task_id, principal=principal)
    scanned = await service.run_idle_timeout_scan()

    assert cancelled.a2a_state is A2ATaskState.cancellation_pending
    assert scanned == 1
    assert expired.a2a_state is A2ATaskState.cancelled
    assert expired.error_code == "idle_timeout"
    assert publisher.events[-1]["event_type"].value == "a2a.task.cancelled"
