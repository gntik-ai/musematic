from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from platform.mcp.exceptions import (
    MCPPayloadTooLargeError,
    MCPPolicyDeniedError,
    MCPProtocolVersionError,
    MCPToolNotFoundError,
)
from platform.mcp.models import MCPInvocationDirection, MCPInvocationOutcome
from platform.mcp.schemas import (
    MCPInitializeRequest,
    MCPInitializeResponse,
    MCPToolCallRequest,
    MCPToolCallResponse,
    MCPToolsListResponse,
)
from platform.mcp.service import MCPService
from platform.policies.gateway import ToolGatewayService
from platform.policies.sanitizer import OutputSanitizer
from typing import Any
from uuid import UUID

ToolExecutor = Callable[[str, dict[str, Any], dict[str, Any]], Awaitable[Any]]


async def _default_tool_executor(
    tool_fqn: str,
    arguments: dict[str, Any],
    principal: dict[str, Any],
) -> dict[str, Any]:
    return {
        "tool_fqn": tool_fqn,
        "arguments": arguments,
        "principal": principal.get("sub"),
    }


class MCPServerService:
    def __init__(
        self,
        *,
        mcp_service: MCPService,
        tool_gateway_service: ToolGatewayService,
        sanitizer: OutputSanitizer,
        settings: Any,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self.mcp_service = mcp_service
        self.tool_gateway_service = tool_gateway_service
        self.sanitizer = sanitizer
        self.settings = settings
        self.tool_executor = tool_executor or _default_tool_executor

    async def handle_initialize(
        self,
        request: MCPInitializeRequest,
        principal: dict[str, Any],
    ) -> MCPInitializeResponse:
        del principal
        if request.protocol_version != self.settings.MCP_PROTOCOL_VERSION:
            raise MCPProtocolVersionError([self.settings.MCP_PROTOCOL_VERSION])
        return MCPInitializeResponse(
            protocolVersion=self.settings.MCP_PROTOCOL_VERSION,
            capabilities={"tools": {"listChanged": True}},
            serverInfo={"name": "musematic-platform", "version": "1.0"},
        )

    async def handle_tools_list(
        self,
        principal: dict[str, Any],
        workspace_id: UUID,
    ) -> MCPToolsListResponse:
        del principal
        tools = await self.mcp_service.list_exposed_tools(
            workspace_id,
            is_exposed=True,
            page=1,
            page_size=1000,
        )
        return MCPToolsListResponse(
            tools=[
                {
                    "name": item.mcp_tool_name,
                    "description": item.mcp_description,
                    "inputSchema": item.mcp_input_schema,
                }
                for item in tools.items
            ]
        )

    async def handle_tools_call(
        self,
        request: MCPToolCallRequest,
        principal: dict[str, Any],
        workspace_id: UUID,
        session: Any,
    ) -> MCPToolCallResponse:
        principal_id = self._principal_id(principal)
        payload_size = len(json.dumps(request.arguments).encode("utf-8"))
        if payload_size > self.settings.MCP_MAX_PAYLOAD_BYTES:
            await self.mcp_service.create_audit_record(
                workspace_id=workspace_id,
                principal_id=principal_id,
                agent_id=None,
                agent_fqn=None,
                server_id=None,
                tool_identifier=request.name,
                direction=MCPInvocationDirection.inbound,
                outcome=MCPInvocationOutcome.denied,
                payload_size_bytes=payload_size,
                error_code="payload_too_large",
            )
            raise MCPPayloadTooLargeError(self.settings.MCP_MAX_PAYLOAD_BYTES, payload_size)
        rate_limit = await self.mcp_service.check_rate_limit(principal_id)
        if not rate_limit.allowed:
            await self.mcp_service.create_audit_record(
                workspace_id=workspace_id,
                principal_id=principal_id,
                agent_id=None,
                agent_fqn=None,
                server_id=None,
                tool_identifier=request.name,
                direction=MCPInvocationDirection.inbound,
                outcome=MCPInvocationOutcome.denied,
                payload_size_bytes=payload_size,
                error_code="rate_limit_exceeded",
            )
            raise MCPPolicyDeniedError("rate_limit")
        exposed = await self.mcp_service.repository.get_exposed_tool_by_name(
            request.name,
            workspace_id,
        )
        if exposed is None or not exposed.is_exposed:
            await self.mcp_service.create_audit_record(
                workspace_id=workspace_id,
                principal_id=principal_id,
                agent_id=None,
                agent_fqn=None,
                server_id=None,
                tool_identifier=request.name,
                direction=MCPInvocationDirection.inbound,
                outcome=MCPInvocationOutcome.denied,
                payload_size_bytes=payload_size,
                error_code="tool_not_found",
            )
            raise MCPToolNotFoundError(request.name)
        gate = await self.tool_gateway_service.validate_tool_invocation(
            principal_id,
            f"principal:{principal_id}",
            exposed.tool_fqn,
            "mcp_inbound",
            None,
            workspace_id,
            session,
        )
        if not gate.allowed:
            await self.mcp_service.create_audit_record(
                workspace_id=workspace_id,
                principal_id=principal_id,
                agent_id=None,
                agent_fqn=None,
                server_id=None,
                tool_identifier=exposed.tool_fqn,
                direction=MCPInvocationDirection.inbound,
                outcome=MCPInvocationOutcome.denied,
                policy_decision=gate.model_dump(mode="json"),
                payload_size_bytes=payload_size,
                error_code=gate.block_reason,
            )
            raise MCPPolicyDeniedError(gate.block_reason or "permission_denied")
        executed = await self.tool_executor(exposed.tool_fqn, dict(request.arguments), principal)
        rendered = json.dumps(executed) if not isinstance(executed, str) else executed
        sanitized = await self.sanitizer.sanitize(
            rendered,
            agent_id=principal_id,
            agent_fqn=f"principal:{principal_id}",
            tool_fqn=exposed.tool_fqn,
            execution_id=None,
            workspace_id=workspace_id,
            session=session,
        )
        await self.mcp_service.create_audit_record(
            workspace_id=workspace_id,
            principal_id=principal_id,
            agent_id=None,
            agent_fqn=None,
            server_id=None,
            tool_identifier=exposed.tool_fqn,
            direction=MCPInvocationDirection.inbound,
            outcome=MCPInvocationOutcome.allowed,
            policy_decision=gate.model_dump(mode="json"),
            payload_size_bytes=payload_size,
        )
        return MCPToolCallResponse(
            content=[{"type": "text", "text": sanitized.output}],
            structuredContent=executed if isinstance(executed, (dict, list)) else None,
            isError=False,
        )

    @staticmethod
    def _principal_id(principal: dict[str, Any]) -> UUID:
        value = principal.get("sub")
        if not isinstance(value, str):
            raise MCPPolicyDeniedError("invalid_principal")
        return UUID(value)
