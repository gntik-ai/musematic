from __future__ import annotations

from platform.a2a_gateway.client_service import A2AGatewayClientService
from platform.a2a_gateway.exceptions import (
    A2AEndpointConflictError,
    A2AHttpsRequiredError,
    A2ATaskNotFoundError,
    A2AUnsupportedCapabilityError,
)
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.exc import IntegrityError
from tests.a2a_gateway_support import (
    FakeA2ARepository,
    RecordingEventPublisher,
    SanitizationStub,
    ToolGatewayStub,
    build_endpoint,
    build_settings,
)


class ConflictRepo(FakeA2ARepository):
    async def create_external_endpoint(self, endpoint):
        del endpoint
        raise IntegrityError("insert", {}, RuntimeError("duplicate"))


def _service(
    *,
    repo: FakeA2ARepository | None = None,
    external_registry: object | None = None,
    tool_gateway: ToolGatewayStub | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> A2AGatewayClientService:
    return A2AGatewayClientService(
        repository=repo or FakeA2ARepository(),
        external_registry=external_registry or SimpleNamespace(get_card=lambda endpoint_id: None),
        tool_gateway=tool_gateway
        or ToolGatewayStub(sanitize_result=SanitizationStub(output="safe")),
        event_publisher=RecordingEventPublisher(),
        settings=build_settings(),
        http_client=http_client,
    )


@pytest.mark.asyncio
async def test_register_endpoint_conflict_and_missing_target() -> None:
    payload = SimpleNamespace(
        name="partner:agent",
        endpoint_url="https://partner.example.com/tasks",
        agent_card_url="https://partner.example.com/.well-known/agent.json",
        auth_config={},
        card_ttl_seconds=30,
    )
    with pytest.raises(A2AEndpointConflictError):
        await _service(repo=ConflictRepo()).register_external_endpoint(
            workspace_id=uuid4(),
            payload=payload,
            created_by=uuid4(),
        )

    service = _service(repo=FakeA2ARepository())
    with pytest.raises(A2ATaskNotFoundError):
        await service.invoke_external_agent(
            calling_agent_id=uuid4(),
            calling_agent_fqn="finance:verifier",
            external_endpoint_id=uuid4(),
            message={"role": "user", "parts": [{"type": "text", "text": "hello"}]},
            workspace_id=uuid4(),
            execution_id=None,
            session=None,
        )


@pytest.mark.asyncio
async def test_submit_and_collect_covers_immediate_response_shapes() -> None:
    endpoint = build_endpoint()

    async def exercise(response: httpx.Response) -> dict[str, object]:
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response))
        service = _service(http_client=client)
        try:
            return await service._submit_and_collect(endpoint, {"role": "user", "parts": []})
        finally:
            await client.aclose()

    message_payload = await exercise(
        httpx.Response(200, json={"message": {"role": "agent", "parts": []}})
    )
    string_payload = await exercise(httpx.Response(200, json={"result": "done"}))
    result_payload = await exercise(
        httpx.Response(200, json={"result_payload": {"role": "agent", "parts": []}})
    )

    assert message_payload == {"role": "agent", "parts": []}
    assert string_payload == {"role": "agent", "parts": [{"type": "text", "text": "done"}]}
    assert result_payload == {"role": "agent", "parts": []}


@pytest.mark.asyncio
async def test_submit_and_collect_handles_polling_and_invalid_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = build_endpoint()
    responses = iter(
        [
            httpx.Response(202, json={"task_id": "remote-task"}),
            httpx.Response(200, json="not-a-dict"),
            httpx.Response(
                200,
                json={"a2a_state": "completed", "result_payload": {"role": "agent", "parts": []}},
            ),
        ]
    )

    class AutoClient:
        def __init__(self) -> None:
            self.closed = False

        async def post(self, url: str, *args, **kwargs):
            del args, kwargs
            response = next(responses)
            response.request = httpx.Request("POST", url)
            return response

        async def get(self, url: str, *args, **kwargs):
            del args, kwargs
            response = next(responses)
            response.request = httpx.Request("GET", url)
            return response

        async def aclose(self) -> None:
            self.closed = True

    original_async_client = httpx.AsyncClient
    client = AutoClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=10.0: client)
    service = _service(http_client=None)
    payload = await service._submit_and_collect(endpoint, {"role": "user", "parts": []})

    assert payload == {"role": "agent", "parts": []}
    assert client.closed is True

    bad_client = original_async_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=["bad"]))
    )
    service = _service(http_client=bad_client)
    with pytest.raises(A2AUnsupportedCapabilityError):
        await service._submit_and_collect(endpoint, {"role": "user", "parts": []})
    await bad_client.aclose()

    unfinished_responses = iter(
        [
            httpx.Response(202, json={"task_id": "remote-task"}),
            httpx.Response(200, json={"a2a_state": "working"}),
            httpx.Response(200, json={"a2a_state": "working"}),
            httpx.Response(200, json={"a2a_state": "working"}),
            httpx.Response(200, json={"a2a_state": "working"}),
            httpx.Response(200, json={"a2a_state": "working"}),
        ]
    )
    unfinished = original_async_client(
        transport=httpx.MockTransport(lambda request: next(unfinished_responses))
    )
    service = _service(http_client=unfinished)
    with pytest.raises(A2AUnsupportedCapabilityError):
        await service._submit_and_collect(endpoint, {"role": "user", "parts": []})
    await unfinished.aclose()


@pytest.mark.asyncio
async def test_client_sanitize_and_https_guard() -> None:
    tool_gateway = ToolGatewayStub(sanitize_result=SanitizationStub(output="safe result"))
    service = _service(tool_gateway=tool_gateway)
    payload = await service._sanitize_result(
        calling_agent_id=uuid4(),
        calling_agent_fqn="finance:verifier",
        endpoint_id=uuid4(),
        workspace_id=uuid4(),
        execution_id=uuid4(),
        payload={"role": "agent", "parts": [{"type": "text", "text": "raw result"}]},
    )

    assert payload["parts"][0]["text"] == "safe result"
    assert tool_gateway.sanitize_calls[0]["tool_fqn"].startswith("a2a:")
    with pytest.raises(A2AHttpsRequiredError):
        service._require_https("http://partner.example.com/tasks")


@pytest.mark.asyncio
async def test_submit_and_collect_rejects_invalid_mapping_and_missing_task_id() -> None:
    endpoint = build_endpoint()
    invalid_mapping = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"result": ["bad"]}))
    )
    service = _service(http_client=invalid_mapping)
    with pytest.raises(A2AUnsupportedCapabilityError):
        await service._submit_and_collect(endpoint, {"role": "user", "parts": []})
    await invalid_mapping.aclose()

    missing_task = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(202, json={}))
    )
    service = _service(http_client=missing_task)
    with pytest.raises(A2AUnsupportedCapabilityError):
        await service._submit_and_collect(endpoint, {"role": "user", "parts": []})
    await missing_task.aclose()
