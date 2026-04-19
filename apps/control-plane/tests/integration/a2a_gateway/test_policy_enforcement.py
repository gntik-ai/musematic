from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from tests.a2a_gateway_support import (
    AuthServiceStub,
    SanitizationStub,
    ToolGatewayStub,
    build_agent_profile,
    build_principal,
)
from tests.integration.a2a_gateway.support import build_app, build_server_stack

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_policy_enforcement_covers_authz_and_sanitization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = build_agent_profile()
    principal = build_principal(workspace_id=agent.workspace_id)
    stack = build_server_stack(
        tool_gateway=ToolGatewayStub(
            sanitize_result=SanitizationStub(
                output="[REDACTED:bearer_token]",
                redaction_count=1,
                redacted_types=["bearer_token"],
            )
        )
    )
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
                "message": {"role": "user", "parts": [{"type": "text", "text": "return token"}]},
            },
        )
        task_id = created.json()["task_id"]
        await client.get(f"/api/v1/a2a/tasks/{task_id}", headers={"Authorization": "Bearer token"})
        completed = await client.get(
            f"/api/v1/a2a/tasks/{task_id}", headers={"Authorization": "Bearer token"}
        )

    assert completed.status_code == 200
    assert completed.json()["result"]["parts"][0]["text"] == "[REDACTED:bearer_token]"
    assert any(record.action == "sanitized" for record in stack.repository.audits)
