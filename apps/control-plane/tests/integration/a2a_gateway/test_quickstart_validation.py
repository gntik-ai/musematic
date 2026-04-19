from __future__ import annotations

from platform.a2a_gateway.exceptions import (
    A2AAgentNotFoundError,
    A2APolicyDeniedError,
    A2AUnsupportedCapabilityError,
)
from platform.a2a_gateway.external_registry import ExternalAgentCardRegistry
from platform.a2a_gateway.models import A2ATaskState
from platform.a2a_gateway.streaming import A2ASSEStream
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from tests.a2a_gateway_support import (
    AuthServiceStub,
    DecisionStub,
    FakeA2ARepository,
    FakeRedisClient,
    SanitizationStub,
    ToolGatewayStub,
    build_agent_profile,
    build_audit_record,
    build_endpoint,
    build_principal,
    build_task,
    expired_time,
)
from tests.integration.a2a_gateway.support import (
    SessionContext,
    build_app,
    build_client_stack,
    build_server_stack,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _build_card(*skill_names: str) -> dict[str, object]:
    return {
        "name": "Agentic Mesh Platform",
        "description": (
            "Multi-tenant agent orchestration platform exposing platform agents via A2A."
        ),
        "url": "http://testserver/api/v1/a2a",
        "version": "1.0",
        "capabilities": ["multi-turn", "streaming"],
        "authentication": [{"scheme": "bearer", "in": "header", "name": "Authorization"}],
        "skills": [
            {
                "id": name,
                "name": name,
                "description": f"Capability for {name}",
                "tags": ["quickstart"],
                "capabilities": ["streaming"],
            }
            for name in skill_names
        ],
    }


async def test_quickstart_validates_discovery_scenarios() -> None:
    # S1, S2, S3
    skills = ["finance:active-agent"]

    async def generate_platform_card(session: object, *, base_url: str) -> dict[str, object]:
        del session
        assert base_url == "http://testserver"
        return _build_card(*skills)

    stack = build_server_stack()
    stack.service.card_generator = SimpleNamespace(generate_platform_card=generate_platform_card)
    app = build_app(auth_service=AuthServiceStub(), server_service=stack.service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        first = await client.get("/.well-known/agent.json")
        skills.append("finance:new-agent")
        second = await client.get("/.well-known/agent.json")

    assert first.status_code == 200
    assert [skill["name"] for skill in first.json()["skills"]] == ["finance:active-agent"]
    assert "finance:archived-agent" not in {skill["name"] for skill in first.json()["skills"]}
    assert {skill["name"] for skill in second.json()["skills"]} == {
        "finance:active-agent",
        "finance:new-agent",
    }


async def test_quickstart_validates_inbound_lifecycle_and_rejections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # S4, S5, S6, S7, S8, S9, S18, S22, S23
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
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
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
        working = await client.get(
            f"/api/v1/a2a/tasks/{task_id}",
            headers={"Authorization": "Bearer token"},
        )
        completed = await client.get(
            f"/api/v1/a2a/tasks/{task_id}",
            headers={"Authorization": "Bearer token"},
        )
        cancelled_created = await client.post(
            "/api/v1/a2a/tasks",
            headers={"Authorization": "Bearer token"},
            json={
                "agent_fqn": agent.fqn,
                "message": {"role": "user", "parts": [{"type": "text", "text": "cancel me"}]},
            },
        )
        cancelled_task_id = cancelled_created.json()["task_id"]
        await client.get(
            f"/api/v1/a2a/tasks/{cancelled_task_id}",
            headers={"Authorization": "Bearer token"},
        )
        cancellation_requested = await client.delete(
            f"/api/v1/a2a/tasks/{cancelled_task_id}",
            headers={"Authorization": "Bearer token"},
        )
        cancelled = await client.get(
            f"/api/v1/a2a/tasks/{cancelled_task_id}",
            headers={"Authorization": "Bearer token"},
        )
        unauthenticated = await client.post(
            "/api/v1/a2a/tasks",
            json={
                "agent_fqn": agent.fqn,
                "message": {"role": "user", "parts": [{"type": "text", "text": "hi"}]},
            },
        )
        protocol_mismatch = await client.post(
            "/api/v1/a2a/tasks",
            headers={"Authorization": "Bearer token"},
            json={
                "agent_fqn": agent.fqn,
                "protocol_version": "2.0",
                "message": {"role": "user", "parts": [{"type": "text", "text": "hi"}]},
            },
        )

    denied_stack = build_server_stack(tool_gateway=ToolGatewayStub())
    denied_stack.service.tool_gateway.validate_result.allowed = False
    denied_stack.service.tool_gateway.validate_result.block_reason = "policy"
    monkeypatch.setattr(denied_stack.service, "_resolve_agent", AsyncMock(return_value=agent))
    denied_app = build_app(
        auth_service=AuthServiceStub(principal),
        server_service=denied_stack.service,
    )

    missing_stack = build_server_stack()
    monkeypatch.setattr(
        missing_stack.service,
        "_resolve_agent",
        AsyncMock(side_effect=A2AAgentNotFoundError("missing:agent")),
    )
    missing_app = build_app(
        auth_service=AuthServiceStub(principal),
        server_service=missing_stack.service,
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
        transport=httpx.ASGITransport(app=denied_app),
        base_url="http://testserver",
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
        transport=httpx.ASGITransport(app=missing_app),
        base_url="http://testserver",
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
        transport=httpx.ASGITransport(app=rate_app),
        base_url="http://testserver",
    ) as client:
        rate_limited = await client.post(
            "/api/v1/a2a/tasks",
            headers={"Authorization": "Bearer token"},
            json={
                "agent_fqn": agent.fqn,
                "message": {"role": "user", "parts": [{"type": "text", "text": "hi"}]},
            },
        )

    assert created.status_code == 202
    assert working.json()["a2a_state"] == "working"
    assert completed.json()["a2a_state"] == "completed"
    assert completed.json()["result"]["parts"][0]["text"] == "[REDACTED:bearer_token]"
    assert cancellation_requested.json()["a2a_state"] == "cancellation_pending"
    assert cancelled.json()["a2a_state"] == "cancelled"
    assert unauthenticated.status_code == 401
    assert protocol_mismatch.status_code == 400
    assert denied.status_code == 403
    assert missing.status_code == 404
    assert rate_limited.status_code == 429


async def test_quickstart_validates_streaming_follow_up_and_idle_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # S10, S11, S12, S13, S14
    stack = build_server_stack()
    principal = build_principal()
    completed_task = build_task(
        principal_id=UUID(principal["sub"]),
        a2a_state=A2ATaskState.completed,
        result_payload={"role": "agent", "parts": [{"type": "text", "text": "done"}]},
    )
    first = build_audit_record(task_id=completed_task.id, action="task_submitted")
    second = build_audit_record(task_id=completed_task.id, action="task_completed")
    stack.repository.tasks[completed_task.task_id] = completed_task
    stack.repository.audits[:] = [first, second]
    monkeypatch.setattr(
        "platform.a2a_gateway.streaming.A2AGatewayRepository", lambda session: stack.repository
    )
    stream = A2ASSEStream(session_factory=SessionContext, poll_interval_seconds=0)
    app = build_app(
        auth_service=AuthServiceStub(principal), server_service=stack.service, stream=stream
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resumed_stream = await client.get(
            f"/api/v1/a2a/tasks/{completed_task.task_id}/stream?token=good",
            headers={"Last-Event-ID": str(first.id)},
        )

    agent = build_agent_profile()
    follow_up_principal = build_principal(workspace_id=agent.workspace_id)
    follow_up_stack = build_server_stack()
    monkeypatch.setattr(
        "platform.a2a_gateway.server_service.InteractionsRepository",
        lambda session: follow_up_stack.interactions,
    )
    monkeypatch.setattr(follow_up_stack.service, "_resolve_agent", AsyncMock(return_value=agent))
    follow_up_app = build_app(
        auth_service=AuthServiceStub(follow_up_principal),
        server_service=follow_up_stack.service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=follow_up_app),
        base_url="http://testserver",
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
            f"/api/v1/a2a/tasks/{task_id}",
            headers={"Authorization": "Bearer token"},
        )
        resumed = await client.post(
            f"/api/v1/a2a/tasks/{task_id}/messages",
            headers={"Authorization": "Bearer token"},
            json={
                "message": {"role": "user", "parts": [{"type": "text", "text": "extra context"}]}
            },
        )
        timeout_created = await client.post(
            "/api/v1/a2a/tasks",
            headers={"Authorization": "Bearer token"},
            json={
                "agent_fqn": agent.fqn,
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "need more detail"}],
                },
            },
        )
        timeout_task_id = timeout_created.json()["task_id"]
        await client.get(
            f"/api/v1/a2a/tasks/{timeout_task_id}",
            headers={"Authorization": "Bearer token"},
        )
        timeout_waiting = await client.get(
            f"/api/v1/a2a/tasks/{timeout_task_id}",
            headers={"Authorization": "Bearer token"},
        )

    timeout_task = follow_up_stack.repository.tasks[timeout_task_id]
    timeout_task.idle_timeout_at = expired_time(1)
    scanned = await follow_up_stack.service.run_idle_timeout_scan()

    assert resumed_stream.status_code == 200
    assert f"id: {second.id}" in resumed_stream.text
    assert f"id: {first.id}" not in resumed_stream.text
    assert waiting.json()["a2a_state"] == "input_required"
    assert resumed.status_code == 202
    assert resumed.json()["a2a_state"] == "working"
    assert timeout_waiting.json()["a2a_state"] == "input_required"
    assert scanned == 1
    assert timeout_task.a2a_state is A2ATaskState.cancelled


async def test_quickstart_validates_outbound_and_registry_paths() -> None:
    # S15, S16, S17, S19, S20, S21, S24
    principal = build_principal(roles=[{"role": "owner"}], workspace_id=uuid4())
    admin_stack = build_client_stack(
        external_registry=SimpleNamespace(get_card=lambda endpoint_id: None)
    )
    admin_app = build_app(
        auth_service=AuthServiceStub(principal),
        client_service=admin_stack.service,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=admin_app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/a2a/external-endpoints",
            headers={"Authorization": "Bearer token"},
            json={
                "name": "partner:agent",
                "endpoint_url": "https://partner.example.com/tasks",
                "agent_card_url": "https://partner.example.com/.well-known/agent.json",
                "auth_config": {"scheme": "bearer", "token": "secret"},
                "card_ttl_seconds": 5,
            },
        )
        listed = await client.get(
            "/api/v1/a2a/external-endpoints",
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
                "card_ttl_seconds": 5,
            },
        )

    endpoint = build_endpoint(workspace_id=UUID(principal["workspace_id"]), card_ttl_seconds=5)
    happy_repo = FakeA2ARepository()
    happy_repo.endpoints[endpoint.id] = endpoint
    call_counter = {"count": 0}

    def external_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("agent.json"):
            call_counter["count"] += 1
            return httpx.Response(
                200,
                json={
                    "skills": [],
                    "version": str(call_counter["count"]),
                    "authentication": [{"scheme": "bearer"}],
                },
            )
        return httpx.Response(
            200,
            json={
                "a2a_state": "completed",
                "result": {"role": "agent", "parts": [{"type": "text", "text": "raw"}]},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(external_handler))
    registry = ExternalAgentCardRegistry(
        repository=happy_repo,
        redis_client=FakeRedisClient(),
        http_client=client,
    )
    happy_stack = build_client_stack(
        repo=happy_repo,
        external_registry=registry,
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
    cached = await registry.get_card(endpoint.id)
    endpoint.card_cached_at = expired_time(10)
    refreshed = await registry.refresh_if_expired(endpoint)
    await client.aclose()

    stale_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503, json={"error": "down"}))
    )
    stale_registry = ExternalAgentCardRegistry(
        repository=happy_repo,
        redis_client=FakeRedisClient(),
        http_client=stale_client,
    )
    endpoint.card_cached_at = expired_time(10)
    stale = await stale_registry.refresh_if_expired(endpoint)
    await stale_client.aclose()

    deny_repo = FakeA2ARepository()
    deny_repo.endpoints[endpoint.id] = endpoint
    deny_stack = build_client_stack(
        repo=deny_repo,
        external_registry=SimpleNamespace(
            get_card=AsyncMock(
                return_value={
                    "card": {"authentication": [{"scheme": "bearer"}], "skills": []},
                    "is_stale": False,
                }
            )
        ),
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

    unsupported_repo = FakeA2ARepository()
    unsupported_repo.endpoints[endpoint.id] = endpoint
    unsupported_stack = build_client_stack(
        repo=unsupported_repo,
        external_registry=SimpleNamespace(
            get_card=AsyncMock(
                return_value={
                    "card": {"authentication": [{"scheme": "mutual_tls"}], "skills": []},
                    "is_stale": False,
                }
            )
        ),
    )
    with pytest.raises(A2AUnsupportedCapabilityError):
        await unsupported_stack.service.invoke_external_agent(
            calling_agent_id=uuid4(),
            calling_agent_fqn="finance:verifier",
            external_endpoint_id=endpoint.id,
            message={"role": "user", "parts": [{"type": "text", "text": "hello"}]},
            workspace_id=endpoint.workspace_id,
            execution_id=None,
            session=None,
        )

    assert created.status_code == 201
    assert listed.json()["total"] == 1
    assert http_blocked.status_code == 400
    assert task.a2a_state is A2ATaskState.completed
    assert happy_stack.publisher.events[0]["event_type"].value == "a2a.outbound.attempted"
    assert cached["card"]["version"] == "1"
    assert refreshed["card"]["version"] == "2"
    assert stale["is_stale"] is True
