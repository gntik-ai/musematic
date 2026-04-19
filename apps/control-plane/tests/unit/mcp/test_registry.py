from __future__ import annotations

import json
from platform.mcp.exceptions import (
    MCPPayloadTooLargeError,
    MCPPolicyDeniedError,
    MCPServerUnavailableError,
    MCPToolNotFoundError,
)
from platform.mcp.schemas import MCPToolDefinition, MCPToolResult
from platform.mcp.service import MCPService
from platform.registry.mcp_registry import MCPExecutionContext, MCPToolRegistry
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.mcp_support import (
    FakeMCPRepository,
    FakeRedisClient,
    RecordingProducer,
    build_agent_profile,
    build_catalog_cache,
    build_server,
    build_settings,
)


class GateResult:
    def __init__(self, *, allowed: bool, block_reason: str | None = None) -> None:
        self.allowed = allowed
        self.block_reason = block_reason

    def model_dump(self, mode: str = "python") -> dict[str, object]:
        del mode
        return {
            "allowed": self.allowed,
            "block_reason": self.block_reason,
        }


class ToolGatewayStub:
    def __init__(
        self,
        *,
        gate: GateResult | None = None,
        sanitized_output: str = "safe output",
    ) -> None:
        self.gate = gate or GateResult(allowed=True)
        self.sanitized_output = sanitized_output
        self.validate_calls: list[tuple[object, ...]] = []
        self.sanitize_calls: list[tuple[object, ...]] = []

    async def validate_tool_invocation(self, *args, **kwargs):
        self.validate_calls.append(args or tuple(kwargs.items()))
        return self.gate

    async def sanitize_tool_output(self, *args, **kwargs):
        self.sanitize_calls.append(args or tuple(kwargs.items()))
        return SimpleNamespace(output=self.sanitized_output)


class SessionStub:
    def __init__(self, agent) -> None:
        self.agent = agent

    async def get(self, model, identifier):
        del model
        if identifier == self.agent.id:
            return self.agent
        return None


class DummyAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _build_registry(
    *,
    repository: FakeMCPRepository | None = None,
    redis_client: FakeRedisClient | None = None,
    producer: RecordingProducer | None = None,
    tool_gateway: ToolGatewayStub | None = None,
    **settings_overrides,
) -> tuple[
    MCPToolRegistry,
    MCPService,
    FakeMCPRepository,
    FakeRedisClient,
    RecordingProducer,
    ToolGatewayStub,
]:
    repo = repository or FakeMCPRepository()
    redis = redis_client or FakeRedisClient()
    events = producer or RecordingProducer()
    gateway = tool_gateway or ToolGatewayStub()
    service = MCPService(
        repository=repo,
        settings=build_settings(**settings_overrides),
        producer=events,
        redis_client=redis,
    )
    registry = MCPToolRegistry(
        repository=repo,
        mcp_service=service,
        settings=service.settings,
        redis_client=redis,
        tool_gateway=gateway,
    )
    service.tool_registry = registry
    return registry, service, repo, redis, events, gateway


@pytest.mark.asyncio
async def test_resolve_agent_catalog_uses_cache_and_skips_inactive_servers() -> None:
    registry, _service, repo, redis, _events, _gateway = _build_registry()
    workspace_id = uuid4()
    active = build_server(workspace_id=workspace_id)
    suspended = build_server(
        workspace_id=workspace_id,
        status="suspended",
    )
    repo.servers[active.id] = active
    repo.servers[suspended.id] = suspended
    redis.values[f"cache:mcp_catalog:{active.id}"] = json.dumps(
        {
            "server_id": str(active.id),
            "tools": [
                {
                    "name": "search",
                    "description": "Search records",
                    "inputSchema": {"type": "object"},
                }
            ],
            "resources": [],
            "prompts": [],
            "version_snapshot": "2024-11-05",
            "is_stale": False,
            "fetched_at": "2026-04-19T00:00:00+00:00",
        }
    ).encode("utf-8")
    agent = build_agent_profile(
        id=uuid4(),
        workspace_id=workspace_id,
        mcp_server_refs=[active.id, suspended.id],
    )

    bindings = await registry.resolve_agent_catalog(
        agent.id,
        workspace_id,
        SessionStub(agent),
    )

    assert [binding.tool_fqn for binding in bindings] == [f"mcp:{active.id}:search"]


@pytest.mark.asyncio
async def test_refresh_server_catalog_fetches_and_persists_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _service, repo, redis, events, _gateway = _build_registry()
    server = build_server()
    repo.servers[server.id] = server

    class ClientStub:
        def __init__(self, base_url, auth_config, *, http_client, timeout_seconds) -> None:
            del base_url, auth_config, http_client, timeout_seconds

        async def initialize(self):
            return SimpleNamespace(protocol_version="2024-11-05")

        async def list_tools(self):
            return [
                MCPToolDefinition(
                    name="search",
                    description="Search records",
                    inputSchema={"type": "object"},
                )
            ]

    monkeypatch.setattr("platform.registry.mcp_registry.httpx.AsyncClient", DummyAsyncClient)
    monkeypatch.setattr("platform.registry.mcp_registry.MCPClient", ClientStub)

    payload = await registry.refresh_server_catalog(server.id, force_refresh=True)

    assert payload is not None
    assert payload["is_stale"] is False
    assert repo.catalog_caches[server.id].version_snapshot == "2024-11-05"
    assert redis.values[f"cache:mcp_catalog:{server.id}"]
    assert [event["event_type"] for event in events.events] == ["mcp.catalog.refreshed"]


@pytest.mark.asyncio
async def test_refresh_server_catalog_falls_back_to_stale_cache_on_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _service, repo, _redis, _events, _gateway = _build_registry()
    server = build_server(catalog_ttl_seconds=30)
    repo.servers[server.id] = server
    repo.catalog_caches[server.id] = build_catalog_cache(server_id=server.id, is_stale=False)

    class ClientStub:
        def __init__(self, base_url, auth_config, *, http_client, timeout_seconds) -> None:
            del base_url, auth_config, http_client, timeout_seconds

        async def initialize(self):
            raise MCPServerUnavailableError(
                "temporary outage",
                classification="transient",
                retry_safe=True,
            )

    monkeypatch.setattr("platform.registry.mcp_registry.httpx.AsyncClient", DummyAsyncClient)
    monkeypatch.setattr("platform.registry.mcp_registry.MCPClient", ClientStub)

    payload = await registry.refresh_server_catalog(server.id, force_refresh=True)

    assert payload is not None
    assert payload["is_stale"] is True
    assert repo.catalog_caches[server.id].is_stale is True


@pytest.mark.asyncio
async def test_invoke_tool_rejects_payloads_that_exceed_size_limit() -> None:
    registry, _service, repo, _redis, _events, gateway = _build_registry(MCP_MAX_PAYLOAD_BYTES=8)
    server = build_server()
    repo.servers[server.id] = server
    context = MCPExecutionContext(
        agent_id=uuid4(),
        agent_fqn="finance:analyst",
        workspace_id=server.workspace_id,
        execution_id=None,
        session=object(),
    )

    with pytest.raises(MCPPayloadTooLargeError):
        await registry.invoke_tool(
            f"mcp:{server.id}:search",
            {"query": "payload-too-large"},
            execution_ctx=context,
        )

    assert repo.audit_records[-1].error_code == "payload_too_large"
    assert gateway.validate_calls == []


@pytest.mark.asyncio
async def test_invoke_tool_blocks_when_policy_denies() -> None:
    registry, _service, repo, _redis, events, _gateway = _build_registry(
        tool_gateway=ToolGatewayStub(
            gate=GateResult(allowed=False, block_reason="permission_denied")
        )
    )
    server = build_server()
    repo.servers[server.id] = server
    context = MCPExecutionContext(
        agent_id=uuid4(),
        agent_fqn="finance:analyst",
        workspace_id=server.workspace_id,
        execution_id=None,
        session=object(),
    )

    with pytest.raises(MCPPolicyDeniedError):
        await registry.invoke_tool(
            f"mcp:{server.id}:search",
            {"query": "ok"},
            execution_ctx=context,
        )

    assert repo.audit_records[-1].error_code == "permission_denied"
    assert events.events[-1]["event_type"] == "mcp.tool.denied"


@pytest.mark.asyncio
async def test_invoke_tool_calls_remote_server_and_sanitizes_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _service, repo, _redis, events, gateway = _build_registry(
        tool_gateway=ToolGatewayStub(sanitized_output="[REDACTED]")
    )
    server = build_server()
    repo.servers[server.id] = server
    context = MCPExecutionContext(
        agent_id=uuid4(),
        agent_fqn="finance:analyst",
        workspace_id=server.workspace_id,
        execution_id=uuid4(),
        session=object(),
    )

    class ClientStub:
        def __init__(self, base_url, auth_config, *, http_client, timeout_seconds) -> None:
            del base_url, auth_config, http_client, timeout_seconds

        async def call_tool(self, name: str, arguments: dict[str, object]) -> MCPToolResult:
            assert name == "search"
            assert arguments == {"query": "revenue"}
            return MCPToolResult(
                content=[{"type": "text", "text": "token secret"}],
                structuredContent={"hits": 1},
                isError=False,
            )

    monkeypatch.setattr("platform.registry.mcp_registry.httpx.AsyncClient", DummyAsyncClient)
    monkeypatch.setattr("platform.registry.mcp_registry.MCPClient", ClientStub)

    result = await registry.invoke_tool(
        f"mcp:{server.id}:search",
        {"query": "revenue"},
        execution_ctx=context,
    )

    assert result.content[0]["text"] == "[REDACTED]"
    assert result.structured_content == {"hits": 1}
    assert repo.audit_records[-1].outcome.value == "allowed"
    assert events.events[-1]["event_type"] == "mcp.tool.invoked"
    assert gateway.validate_calls
    assert gateway.sanitize_calls


@pytest.mark.asyncio
async def test_registry_handles_missing_agent_invalid_refs_and_cache_edge_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _service, repo, redis, _events, _gateway = _build_registry()
    workspace_id = uuid4()

    class MissingSession:
        async def get(self, model, identifier):
            del model, identifier
            return None

    assert await registry.resolve_agent_catalog(uuid4(), workspace_id, MissingSession()) == []

    invalid_agent = build_agent_profile(
        id=uuid4(),
        workspace_id=workspace_id,
        mcp_server_refs=["not-a-uuid"],
    )
    assert await registry.resolve_agent_catalog(
        invalid_agent.id,
        workspace_id,
        SessionStub(invalid_agent),
    ) == []

    server = build_server(workspace_id=workspace_id)
    repo.servers[server.id] = server
    cache_key = f"cache:mcp_catalog:{server.id}"
    redis.values[cache_key] = b"not-json"

    class ClientStub:
        def __init__(self, base_url, auth_config, *, http_client, timeout_seconds) -> None:
            del base_url, auth_config, http_client, timeout_seconds

        async def initialize(self):
            raise MCPServerUnavailableError(
                "temporary outage",
                classification="transient",
                retry_safe=True,
            )

    monkeypatch.setattr("platform.registry.mcp_registry.httpx.AsyncClient", DummyAsyncClient)
    monkeypatch.setattr("platform.registry.mcp_registry.MCPClient", ClientStub)

    assert await registry.refresh_server_catalog(server.id, force_refresh=False) is None
    assert redis.deleted == [cache_key]

    context = MCPExecutionContext(
        agent_id=uuid4(),
        agent_fqn="finance:analyst",
        workspace_id=workspace_id,
        execution_id=None,
        session=object(),
    )
    with pytest.raises(MCPToolNotFoundError):
        await registry.invoke_tool("bad-tool-fqn", {}, execution_ctx=context)

    assert registry._render_result_text(
        MCPToolResult(content=[], structuredContent={"hits": 1}, isError=False)
    ) == '{"hits": 1}'
    assert registry._render_result_text(
        MCPToolResult(content=[], structuredContent=None, isError=False)
    ) == ""
