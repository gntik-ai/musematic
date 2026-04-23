from __future__ import annotations

from platform.a2a_gateway.models import A2ATaskState
from platform.a2a_gateway.streaming import A2ASSEStream
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from tests.a2a_gateway_support import (
    AuthServiceStub,
    build_agent_profile,
    build_audit_record,
    build_principal,
    build_task,
)
from tests.integration.a2a_gateway.support import SessionContext, build_app, build_server_stack

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_stream_endpoint_supports_resume_with_last_event_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = build_server_stack()
    principal = build_principal()
    task = build_task(
        principal_id=UUID(principal["sub"]),
        a2a_state=A2ATaskState.completed,
        result_payload={"role": "agent", "parts": [{"type": "text", "text": "done"}]},
    )
    first = build_audit_record(task_id=task.id, action="task_submitted")
    second = build_audit_record(task_id=task.id, action="task_completed")
    stack.repository.tasks[task.task_id] = task
    stack.repository.audits[:] = [first, second]
    monkeypatch.setattr(
        "platform.a2a_gateway.streaming.A2AGatewayRepository", lambda session: stack.repository
    )
    stream = A2ASSEStream(session_factory=SessionContext, poll_interval_seconds=0)
    app = build_app(
        auth_service=AuthServiceStub(principal), server_service=stack.service, stream=stream
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(
            f"/api/v1/a2a/tasks/{task.task_id}/stream?token=good",
            headers={"Last-Event-ID": str(first.id)},
        )

    assert response.status_code == 200
    assert f"id: {second.id}" in response.text
    assert f"id: {first.id}" not in response.text


async def test_follow_up_endpoint_resumes_input_required_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = build_server_stack()
    agent = build_agent_profile()
    principal = build_principal(workspace_id=agent.workspace_id)
    monkeypatch.setattr(
        "platform.a2a_gateway.server_service.InteractionsRepository",
        lambda session: stack.interactions,
    )
    monkeypatch.setattr(stack.service, "_resolve_agent", AsyncMock(return_value=agent))
    app = build_app(auth_service=AuthServiceStub(principal), server_service=stack.service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        created = await client.post(
            "/api/v1/a2a/tasks",
            headers={"Authorization": "Bearer token"},
            json={
                "agent_fqn": agent.fqn,
                "message": {"role": "user", "parts": [{"type": "text", "text": "clarify this"}]},
            },
        )
        task_id = created.json()["task_id"]
        await client.get(f"/api/v1/a2a/tasks/{task_id}", headers={"Authorization": "Bearer token"})
        waiting = await client.get(
            f"/api/v1/a2a/tasks/{task_id}", headers={"Authorization": "Bearer token"}
        )
        resumed = await client.post(
            f"/api/v1/a2a/tasks/{task_id}/messages",
            headers={"Authorization": "Bearer token"},
            json={
                "message": {"role": "user", "parts": [{"type": "text", "text": "extra context"}]}
            },
        )

    assert waiting.json()["a2a_state"] == "input_required"
    assert resumed.status_code == 202
    assert resumed.json()["a2a_state"] == "working"
