from __future__ import annotations

from platform.a2a_gateway.client_service import A2AGatewayClientService
from platform.a2a_gateway.exceptions import (
    A2AHttpsRequiredError,
    A2APolicyDeniedError,
    A2ATaskNotFoundError,
    A2AUnsupportedCapabilityError,
)
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
from tests.a2a_gateway_support import (
    DecisionStub,
    FakeA2ARepository,
    RecordingEventPublisher,
    SanitizationStub,
    ToolGatewayStub,
    build_endpoint,
    build_settings,
)


def _service(
    *,
    repo: FakeA2ARepository | None = None,
    external_registry: Any | None = None,
    tool_gateway: ToolGatewayStub | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> tuple[A2AGatewayClientService, FakeA2ARepository, RecordingEventPublisher]:
    repository = repo or FakeA2ARepository()
    publisher = RecordingEventPublisher()
    service = A2AGatewayClientService(
        repository=repository,
        external_registry=external_registry or SimpleNamespace(get_card=lambda endpoint_id: None),
        tool_gateway=(
            tool_gateway or ToolGatewayStub(sanitize_result=SanitizationStub(output="safe output"))
        ),
        event_publisher=publisher,
        settings=build_settings(),
        http_client=http_client,
    )
    return service, repository, publisher


@pytest.mark.asyncio
async def test_register_list_and_delete_external_endpoints() -> None:
    service, _, _ = _service()
    workspace_id = uuid4()
    created_by = uuid4()

    created = await service.register_external_endpoint(
        workspace_id=workspace_id,
        payload=SimpleNamespace(
            name="partner:agent",
            endpoint_url="https://partner.example.com/tasks",
            agent_card_url="https://partner.example.com/.well-known/agent.json",
            auth_config={"scheme": "bearer", "token": "secret"},
            card_ttl_seconds=600,
        ),
        created_by=created_by,
    )
    listed = await service.list_external_endpoints(workspace_id)
    deleted = await service.delete_external_endpoint(
        workspace_id=workspace_id,
        endpoint_id=created.id,
    )

    assert listed.total == 1
    assert listed.items[0].id == created.id
    assert deleted.status == "deleted"

    with pytest.raises(A2AHttpsRequiredError):
        await service.register_external_endpoint(
            workspace_id=workspace_id,
            payload=SimpleNamespace(
                name="bad",
                endpoint_url="http://partner.example.com/tasks",
                agent_card_url="https://partner.example.com/.well-known/agent.json",
                auth_config={},
                card_ttl_seconds=60,
            ),
            created_by=created_by,
        )

    with pytest.raises(A2ATaskNotFoundError):
        await service.delete_external_endpoint(workspace_id=workspace_id, endpoint_id=uuid4())


@pytest.mark.asyncio
async def test_invoke_external_agent_happy_path_sanitizes_output() -> None:
    repo = FakeA2ARepository()
    endpoint = build_endpoint()
    repo.endpoints[endpoint.id] = endpoint
    external_registry = SimpleNamespace(
        get_card=lambda endpoint_id: None,
    )

    async def _get_card(endpoint_id):
        assert endpoint_id == endpoint.id
        return {"card": {"authentication": [{"scheme": "bearer"}], "skills": []}, "is_stale": False}

    external_registry.get_card = _get_card

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={
                "task_id": "remote-task",
                "a2a_state": "completed",
                "result": {"role": "agent", "parts": [{"type": "text", "text": "raw"}]},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service, repository, publisher = _service(
        repo=repo,
        external_registry=external_registry,
        http_client=client,
    )

    task = await service.invoke_external_agent(
        calling_agent_id=uuid4(),
        calling_agent_fqn="finance:verifier",
        external_endpoint_id=endpoint.id,
        message={"role": "user", "parts": [{"type": "text", "text": "hello"}]},
        workspace_id=endpoint.workspace_id,
        execution_id=uuid4(),
        session=None,
    )
    await client.aclose()

    assert task.a2a_state.value == "completed"
    assert task.result_payload == {
        "role": "agent",
        "parts": [{"type": "text", "text": "safe output"}],
    }
    assert [audit.action for audit in repository.audits] == ["outbound_call", "task_completed"]
    assert publisher.events[0]["event_type"].value == "a2a.outbound.attempted"


@pytest.mark.asyncio
async def test_invoke_external_agent_policy_deny_and_capability_validation() -> None:
    repo = FakeA2ARepository()
    endpoint = build_endpoint()
    repo.endpoints[endpoint.id] = endpoint

    deny_service, deny_repo, publisher = _service(
        repo=repo,
        external_registry=SimpleNamespace(
            get_card=lambda endpoint_id: None,
        ),
        tool_gateway=ToolGatewayStub(
            validate_result=DecisionStub(allowed=False, block_reason="policy")
        ),
    )

    with pytest.raises(A2APolicyDeniedError):
        await deny_service.invoke_external_agent(
            calling_agent_id=uuid4(),
            calling_agent_fqn="finance:verifier",
            external_endpoint_id=endpoint.id,
            message={"role": "user", "parts": [{"type": "text", "text": "hi"}]},
            workspace_id=endpoint.workspace_id,
            execution_id=None,
            session=None,
        )

    assert deny_repo.policy_blocked[-1].block_reason == "policy"
    assert publisher.events[-1]["event_type"].value == "a2a.outbound.denied"

    async def _bad_card(endpoint_id):
        del endpoint_id
        return {
            "card": {"authentication": [{"scheme": "api_key"}], "skills": []},
            "is_stale": False,
        }

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    )
    unsupported_service, _, _ = _service(
        repo=repo,
        external_registry=SimpleNamespace(get_card=_bad_card),
        http_client=client,
    )
    with pytest.raises(A2AUnsupportedCapabilityError):
        await unsupported_service.invoke_external_agent(
            calling_agent_id=uuid4(),
            calling_agent_fqn="finance:verifier",
            external_endpoint_id=endpoint.id,
            message={"role": "user", "parts": [{"type": "text", "text": "hi"}]},
            workspace_id=endpoint.workspace_id,
            execution_id=None,
            session=None,
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_submit_and_collect_polls_until_completed() -> None:
    responses = iter(
        [
            httpx.Response(202, json={"task_id": "remote-task"}),
            httpx.Response(200, json={"a2a_state": "working"}),
            httpx.Response(
                200,
                json={
                    "a2a_state": "completed",
                    "result_payload": {
                        "role": "agent",
                        "parts": [{"type": "text", "text": "done"}],
                    },
                },
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return next(responses)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service, _, _ = _service(http_client=client)
    endpoint = build_endpoint()

    payload = await service._submit_and_collect(
        endpoint,
        {"role": "user", "parts": [{"type": "text", "text": "hello"}]},
    )
    await client.aclose()

    assert payload == {"role": "agent", "parts": [{"type": "text", "text": "done"}]}
