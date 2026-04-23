from __future__ import annotations

from platform.a2a_gateway.exceptions import A2APolicyDeniedError
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from tests.a2a_gateway_support import (
    AuthServiceStub,
    DecisionStub,
    ToolGatewayStub,
    build_endpoint,
    build_principal,
)
from tests.integration.a2a_gateway.support import build_app, build_client_stack

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_external_endpoint_admin_routes_register_list_and_delete() -> None:
    principal = build_principal(roles=[{"role": "owner"}], workspace_id=uuid4())
    stack = build_client_stack(external_registry=SimpleNamespace(get_card=lambda endpoint_id: None))
    app = build_app(auth_service=AuthServiceStub(principal), client_service=stack.service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        created = await client.post(
            "/api/v1/a2a/external-endpoints",
            headers={"Authorization": "Bearer token"},
            json={
                "name": "partner:agent",
                "endpoint_url": "https://partner.example.com/tasks",
                "agent_card_url": "https://partner.example.com/.well-known/agent.json",
                "auth_config": {"scheme": "bearer", "token": "secret"},
                "card_ttl_seconds": 60,
            },
        )
        listed = await client.get(
            "/api/v1/a2a/external-endpoints", headers={"Authorization": "Bearer token"}
        )
        deleted = await client.delete(
            f"/api/v1/a2a/external-endpoints/{created.json()['id']}",
            headers={"Authorization": "Bearer token"},
        )
        http_blocked = await client.post(
            "/api/v1/a2a/external-endpoints",
            headers={"Authorization": "Bearer token"},
            json={
                "name": "bad",
                "endpoint_url": "http://partner.example.com/tasks",
                "agent_card_url": "https://partner.example.com/.well-known/agent.json",
                "auth_config": {},
                "card_ttl_seconds": 60,
            },
        )

    assert created.status_code == 201
    assert listed.json()["total"] == 1
    assert deleted.json()["status"] == "deleted"
    assert http_blocked.status_code == 400
    assert http_blocked.json()["code"] == "https_required"


async def test_client_mode_invokes_external_agent_and_denies_policy() -> None:
    endpoint = build_endpoint()

    async def get_card(endpoint_id):
        assert endpoint_id == endpoint.id
        return {"card": {"authentication": [{"scheme": "bearer"}], "skills": []}, "is_stale": False}

    from tests.a2a_gateway_support import FakeA2ARepository

    happy_repo = FakeA2ARepository()
    happy_repo.endpoints[endpoint.id] = endpoint
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "a2a_state": "completed",
                    "result": {"role": "agent", "parts": [{"type": "text", "text": "raw"}]},
                },
            )
        )
    )
    happy_stack = build_client_stack(
        repo=happy_repo,
        external_registry=SimpleNamespace(get_card=get_card),
        http_client=client,
    )
    task = await happy_stack.service.invoke_external_agent(
        calling_agent_id=uuid4(),
        calling_agent_fqn="finance:verifier",
        external_endpoint_id=endpoint.id,
        message={"role": "user", "parts": [{"type": "text", "text": "hello"}]},
        workspace_id=endpoint.workspace_id,
        execution_id=uuid4(),
        session=None,
    )
    await client.aclose()

    deny_repo = FakeA2ARepository()
    deny_repo.endpoints[endpoint.id] = endpoint
    deny_stack = build_client_stack(
        repo=deny_repo,
        external_registry=SimpleNamespace(get_card=get_card),
        tool_gateway=ToolGatewayStub(
            validate_result=DecisionStub(allowed=False, block_reason="policy")
        ),
    )
    with pytest.raises(A2APolicyDeniedError):
        await deny_stack.service.invoke_external_agent(
            calling_agent_id=uuid4(),
            calling_agent_fqn="finance:verifier",
            external_endpoint_id=endpoint.id,
            message={"role": "user", "parts": [{"type": "text", "text": "hello"}]},
            workspace_id=endpoint.workspace_id,
            execution_id=None,
            session=None,
        )

    assert task.a2a_state.value == "completed"
    assert happy_stack.publisher.events[0]["event_type"].value == "a2a.outbound.attempted"
    assert deny_stack.publisher.events[-1]["event_type"].value == "a2a.outbound.denied"
