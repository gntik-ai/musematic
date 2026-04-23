from __future__ import annotations

from platform.a2a_gateway.exceptions import A2AAgentNotFoundError
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from tests.a2a_gateway_support import (
    AuthServiceStub,
    FakeRedisClient,
    ToolGatewayStub,
    build_agent_profile,
    build_principal,
)
from tests.integration.a2a_gateway.support import build_app, build_server_stack

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_server_mode_discovery_submit_and_completion(monkeypatch: pytest.MonkeyPatch) -> None:
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
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        card = await client.get("/.well-known/agent.json")
        created = await client.post(
            "/api/v1/a2a/tasks",
            headers={"Authorization": "Bearer token"},
            json={
                "agent_fqn": agent.fqn,
                "message": {"role": "user", "parts": [{"type": "text", "text": "summarize"}]},
            },
        )
        task_id = created.json()["task_id"]
        working = await client.get(
            f"/api/v1/a2a/tasks/{task_id}",
            headers={"Authorization": "Bearer token"},
        )
        completed = await client.get(
            f"/api/v1/a2a/tasks/{task_id}",
            headers={"Authorization": "Bearer token"},
        )

    assert card.status_code == 200
    assert created.status_code == 202
    assert working.json()["a2a_state"] == "working"
    assert completed.json()["a2a_state"] == "completed"
    assert stack.publisher.events[0]["event_type"].value == "a2a.task.submitted"
    assert {record.action for record in stack.repository.audits} >= {
        "task_submitted",
        "task_completed",
    }


async def test_server_mode_rejects_missing_auth_and_protocol_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = build_server_stack()
    agent = build_agent_profile()
    monkeypatch.setattr(stack.service, "_resolve_agent", AsyncMock(return_value=agent))
    app = build_app(
        auth_service=AuthServiceStub(build_principal(workspace_id=agent.workspace_id)),
        server_service=stack.service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        unauthenticated = await client.post(
            "/api/v1/a2a/tasks",
            json={
                "agent_fqn": agent.fqn,
                "message": {"role": "user", "parts": [{"type": "text", "text": "hi"}]},
            },
        )
        mismatch = await client.post(
            "/api/v1/a2a/tasks",
            headers={"Authorization": "Bearer token"},
            json={
                "agent_fqn": agent.fqn,
                "protocol_version": "2.0",
                "message": {"role": "user", "parts": [{"type": "text", "text": "hi"}]},
            },
        )

    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "authentication_error"
    assert mismatch.status_code == 400
    assert mismatch.json()["code"] == "protocol_version_unsupported"


async def test_server_mode_rejects_denied_missing_agent_and_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied_stack = build_server_stack(tool_gateway=ToolGatewayStub())
    denied_stack.service.tool_gateway.validate_result.allowed = False
    denied_stack.service.tool_gateway.validate_result.block_reason = "policy"
    agent = build_agent_profile()
    principal = build_principal(workspace_id=agent.workspace_id)
    monkeypatch.setattr(
        denied_stack.service,
        "_resolve_agent",
        AsyncMock(return_value=agent),
    )
    denied_app = build_app(
        auth_service=AuthServiceStub(principal), server_service=denied_stack.service
    )

    missing_stack = build_server_stack()
    monkeypatch.setattr(
        missing_stack.service,
        "_resolve_agent",
        AsyncMock(side_effect=A2AAgentNotFoundError("missing:agent")),
    )
    missing_app = build_app(
        auth_service=AuthServiceStub(principal), server_service=missing_stack.service
    )

    rate_stack = build_server_stack()
    rate_stack.service.redis_client = FakeRedisClient(
        rate_limit_results=[SimpleNamespace(allowed=False, remaining=0, retry_after_ms=1200)]
    )
    monkeypatch.setattr(rate_stack.service, "_resolve_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        "platform.a2a_gateway.server_service.InteractionsRepository",
        lambda session: rate_stack.interactions,
    )
    rate_app = build_app(auth_service=AuthServiceStub(principal), server_service=rate_stack.service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=denied_app), base_url="http://testserver"
    ) as client:
        denied = await client.post(
            "/api/v1/a2a/tasks",
            headers={"Authorization": "Bearer token"},
            json={
                "agent_fqn": agent.fqn,
                "message": {"role": "user", "parts": [{"type": "text", "text": "hi"}]},
            },
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=missing_app), base_url="http://testserver"
    ) as client:
        missing = await client.post(
            "/api/v1/a2a/tasks",
            headers={"Authorization": "Bearer token"},
            json={
                "agent_fqn": "missing:agent",
                "message": {"role": "user", "parts": [{"type": "text", "text": "hi"}]},
            },
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=rate_app), base_url="http://testserver"
    ) as client:
        rate_limited = await client.post(
            "/api/v1/a2a/tasks",
            headers={"Authorization": "Bearer token"},
            json={
                "agent_fqn": agent.fqn,
                "message": {"role": "user", "parts": [{"type": "text", "text": "hi"}]},
            },
        )

    assert denied.status_code == 403
    assert denied.json()["code"] == "authorization_error"
    assert missing.status_code == 404
    assert missing.json()["code"] == "agent_not_found"
    assert rate_limited.status_code == 429
    assert rate_limited.json()["code"] == "rate_limit_exceeded"
