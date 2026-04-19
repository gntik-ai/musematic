from __future__ import annotations

from platform.a2a_gateway.mcp_server import MCPServerService
from platform.common.clients.redis import RateLimitResult
from platform.mcp.exceptions import (
    MCPPayloadTooLargeError,
    MCPPolicyDeniedError,
    MCPProtocolVersionError,
    MCPToolNotFoundError,
)
from platform.mcp.schemas import MCPInitializeRequest, MCPToolCallRequest
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.mcp_support import FakeMCPRepository, build_exposed_tool, build_settings


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
    def __init__(self, gate: GateResult | None = None) -> None:
        self.gate = gate or GateResult(allowed=True)
        self.validate_calls: list[tuple[object, ...]] = []

    async def validate_tool_invocation(self, *args):
        self.validate_calls.append(args)
        return self.gate


class SanitizerStub:
    def __init__(self, output: str = "safe") -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    async def sanitize(self, text: str, **kwargs):
        self.calls.append({"text": text, **kwargs})
        return SimpleNamespace(output=self.output)


class MCPServiceStub:
    def __init__(
        self,
        *,
        repository: FakeMCPRepository | None = None,
        rate_limit_results: list[RateLimitResult] | None = None,
    ) -> None:
        self.repository = repository or FakeMCPRepository()
        self.rate_limit_results = list(
            rate_limit_results or [RateLimitResult(allowed=True, remaining=59, retry_after_ms=0)]
        )
        self.audit_records: list[dict[str, object]] = []

    async def list_exposed_tools(self, workspace_id, *, is_exposed, page, page_size):
        items = [tool for tool in self.repository.exposed_tools.values() if tool.is_exposed]
        return SimpleNamespace(items=items, total=len(items), page=page, page_size=page_size)

    async def check_rate_limit(self, principal_id):
        del principal_id
        if self.rate_limit_results:
            return self.rate_limit_results.pop(0)
        return RateLimitResult(allowed=True, remaining=59, retry_after_ms=0)

    async def create_audit_record(self, **kwargs):
        self.audit_records.append(kwargs)
        return SimpleNamespace(**kwargs)


async def _tool_executor(tool_fqn: str, arguments: dict[str, object], principal: dict[str, object]):
    return {
        "tool_fqn": tool_fqn,
        "arguments": arguments,
        "principal": principal["sub"],
    }


@pytest.mark.asyncio
async def test_mcp_server_initialize_and_list_tools() -> None:
    repo = FakeMCPRepository()
    workspace_id = uuid4()
    repo.exposed_tools[(workspace_id, "finance:lookup")] = build_exposed_tool(
        workspace_id=workspace_id,
        tool_fqn="finance:lookup",
        mcp_tool_name="lookup",
    )
    service = MCPServerService(
        mcp_service=MCPServiceStub(repository=repo),
        tool_gateway_service=ToolGatewayStub(),
        sanitizer=SanitizerStub(),
        settings=build_settings(),
    )
    principal = {"sub": str(uuid4())}

    initialized = await service.handle_initialize(
        MCPInitializeRequest(protocolVersion="2024-11-05"),
        principal,
    )
    listed = await service.handle_tools_list(principal, workspace_id)

    assert initialized.protocol_version == "2024-11-05"
    assert [tool.name for tool in listed.tools] == ["lookup"]

    with pytest.raises(MCPProtocolVersionError):
        await service.handle_initialize(
            MCPInitializeRequest(protocolVersion="1999-01-01"),
            principal,
        )


@pytest.mark.asyncio
async def test_mcp_server_tool_call_success_and_denial_paths() -> None:
    repo = FakeMCPRepository()
    workspace_id = uuid4()
    repo.exposed_tools[(workspace_id, "finance:lookup")] = build_exposed_tool(
        workspace_id=workspace_id,
        tool_fqn="finance:lookup",
        mcp_tool_name="lookup",
    )
    gateway = ToolGatewayStub()
    sanitizer = SanitizerStub(output="[REDACTED]")
    mcp_service = MCPServiceStub(repository=repo)
    principal = {"sub": str(uuid4())}
    service = MCPServerService(
        mcp_service=mcp_service,
        tool_gateway_service=gateway,
        sanitizer=sanitizer,
        settings=build_settings(),
        tool_executor=_tool_executor,
    )

    result = await service.handle_tools_call(
        MCPToolCallRequest(name="lookup", arguments={"query": "revenue"}),
        principal,
        workspace_id,
        session=object(),
    )

    assert result.content[0]["text"] == "[REDACTED]"
    assert result.structured_content == {
        "tool_fqn": "finance:lookup",
        "arguments": {"query": "revenue"},
        "principal": principal["sub"],
    }
    assert gateway.validate_calls
    assert sanitizer.calls
    assert mcp_service.audit_records[-1]["outcome"].value == "allowed"

    denied_service = MCPServerService(
        mcp_service=MCPServiceStub(repository=repo),
        tool_gateway_service=ToolGatewayStub(
            GateResult(allowed=False, block_reason="permission_denied")
        ),
        sanitizer=SanitizerStub(),
        settings=build_settings(),
        tool_executor=_tool_executor,
    )
    with pytest.raises(MCPPolicyDeniedError):
        await denied_service.handle_tools_call(
            MCPToolCallRequest(name="lookup", arguments={"query": "revenue"}),
            principal,
            workspace_id,
            session=object(),
        )


@pytest.mark.asyncio
async def test_mcp_server_tool_call_rejects_missing_tools_payloads_and_rate_limits() -> None:
    repo = FakeMCPRepository()
    workspace_id = uuid4()
    principal = {"sub": str(uuid4())}
    service = MCPServerService(
        mcp_service=MCPServiceStub(
            repository=repo,
            rate_limit_results=[RateLimitResult(allowed=False, remaining=0, retry_after_ms=250)],
        ),
        tool_gateway_service=ToolGatewayStub(),
        sanitizer=SanitizerStub(),
        settings=build_settings(MCP_MAX_PAYLOAD_BYTES=8),
        tool_executor=_tool_executor,
    )

    with pytest.raises(MCPPayloadTooLargeError):
        await service.handle_tools_call(
            MCPToolCallRequest(name="lookup", arguments={"query": "payload-too-large"}),
            principal,
            workspace_id,
            session=object(),
        )

    repo.exposed_tools[(workspace_id, "finance:lookup")] = build_exposed_tool(
        workspace_id=workspace_id,
        tool_fqn="finance:lookup",
        mcp_tool_name="lookup",
    )
    with pytest.raises(MCPPolicyDeniedError):
        await service.handle_tools_call(
            MCPToolCallRequest(name="lookup", arguments={}),
            principal,
            workspace_id,
            session=object(),
        )

    missing_tool_service = MCPServerService(
        mcp_service=MCPServiceStub(repository=FakeMCPRepository()),
        tool_gateway_service=ToolGatewayStub(),
        sanitizer=SanitizerStub(),
        settings=build_settings(),
        tool_executor=_tool_executor,
    )
    with pytest.raises(MCPToolNotFoundError):
        await missing_tool_service.handle_tools_call(
            MCPToolCallRequest(name="unknown", arguments={}),
            principal,
            workspace_id,
            session=object(),
        )
