from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from platform.common.clients.mcp_client import MCPClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.mcp.events import MCPEventPayload, MCPEventType, publish_mcp_event
from platform.mcp.exceptions import (
    MCPPayloadTooLargeError,
    MCPPolicyDeniedError,
    MCPServerNotFoundError,
    MCPServerSuspendedError,
    MCPServerUnavailableError,
    MCPToolError,
    MCPToolNotFoundError,
)
from platform.mcp.models import MCPInvocationDirection, MCPInvocationOutcome, MCPServerStatus
from platform.mcp.repository import MCPRepository
from platform.mcp.schemas import MCPToolBinding, MCPToolDefinition, MCPToolResult
from platform.mcp.service import MCPService
from platform.registry.models import AgentProfile
from typing import Any, cast
from uuid import UUID, uuid4

import httpx


@dataclass(slots=True)
class MCPExecutionContext:
    agent_id: UUID
    agent_fqn: str
    workspace_id: UUID
    execution_id: UUID | None
    session: Any


class MCPToolRegistry:
    def __init__(
        self,
        *,
        repository: MCPRepository,
        mcp_service: MCPService,
        settings: PlatformSettings,
        redis_client: AsyncRedisClient,
        tool_gateway: Any | None,
    ) -> None:
        self.repository = repository
        self.mcp_service = mcp_service
        self.settings = settings
        self.redis_client = redis_client
        self.tool_gateway = tool_gateway

    async def resolve_agent_catalog(
        self,
        agent_id: UUID,
        workspace_id: UUID,
        session: Any,
        *,
        force_refresh: bool = False,
    ) -> list[MCPToolBinding]:
        agent = await session.get(AgentProfile, agent_id)
        if agent is None:
            return []
        refs = list(getattr(agent, "mcp_server_refs", []) or [])
        if not refs:
            return []
        server_ids: list[UUID] = []
        for raw in refs:
            try:
                server_ids.append(UUID(str(raw)))
            except ValueError:
                continue
        bindings: list[MCPToolBinding] = []
        servers = await self.repository.list_servers_by_ids(workspace_id, server_ids)
        for server in servers:
            if server.status is not MCPServerStatus.active:
                continue
            catalog = await self._get_server_catalog(server.id, force_refresh=force_refresh)
            if catalog is None:
                continue
            for item in catalog["tools"]:
                definition = MCPToolDefinition.model_validate(item)
                bindings.append(
                    MCPToolBinding(
                        tool_fqn=f"mcp:{server.id}:{definition.name}",
                        server_id=server.id,
                        tool_name=definition.name,
                        description=definition.description,
                        input_schema=definition.input_schema,
                        is_stale=bool(catalog["is_stale"]),
                    )
                )
        return bindings

    async def refresh_server_catalog(
        self,
        server_id: UUID,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any] | None:
        return await self._get_server_catalog(server_id, force_refresh=force_refresh)

    async def invoke_tool(
        self,
        tool_fqn: str,
        arguments: dict[str, Any],
        *,
        execution_ctx: MCPExecutionContext,
    ) -> MCPToolResult:
        server_id, tool_name = self._parse_tool_fqn(tool_fqn)
        payload_size = len(json.dumps(arguments).encode("utf-8"))
        if payload_size > self.settings.MCP_MAX_PAYLOAD_BYTES:
            await self.mcp_service.create_audit_record(
                workspace_id=execution_ctx.workspace_id,
                principal_id=execution_ctx.agent_id,
                agent_id=execution_ctx.agent_id,
                agent_fqn=execution_ctx.agent_fqn,
                server_id=server_id,
                tool_identifier=tool_fqn,
                direction=MCPInvocationDirection.outbound,
                outcome=MCPInvocationOutcome.denied,
                payload_size_bytes=payload_size,
                error_code="payload_too_large",
            )
            raise MCPPayloadTooLargeError(self.settings.MCP_MAX_PAYLOAD_BYTES, payload_size)
        if self.tool_gateway is None:
            raise MCPPolicyDeniedError("tool_gateway_unavailable")
        gate = await self.tool_gateway.validate_tool_invocation(
            execution_ctx.agent_id,
            execution_ctx.agent_fqn,
            tool_fqn,
            "mcp_outbound",
            execution_ctx.execution_id,
            execution_ctx.workspace_id,
            execution_ctx.session,
        )
        if not gate.allowed:
            await self.mcp_service.create_audit_record(
                workspace_id=execution_ctx.workspace_id,
                principal_id=execution_ctx.agent_id,
                agent_id=execution_ctx.agent_id,
                agent_fqn=execution_ctx.agent_fqn,
                server_id=server_id,
                tool_identifier=tool_fqn,
                direction=MCPInvocationDirection.outbound,
                outcome=MCPInvocationOutcome.denied,
                policy_decision=gate.model_dump(mode="json"),
                payload_size_bytes=payload_size,
                error_code=gate.block_reason,
            )
            await publish_mcp_event(
                self.mcp_service.producer,
                MCPEventType.tool_denied,
                MCPEventPayload(
                    server_id=server_id,
                    workspace_id=execution_ctx.workspace_id,
                    agent_id=execution_ctx.agent_id,
                    agent_fqn=execution_ctx.agent_fqn,
                    tool_identifier=tool_fqn,
                    direction="outbound",
                    outcome="denied",
                    block_reason=gate.block_reason,
                ),
                self._correlation(execution_ctx.workspace_id, execution_ctx.agent_fqn),
                key=str(server_id),
            )
            raise MCPPolicyDeniedError(gate.block_reason or "permission_denied")

        server = await self.repository.get_server(server_id, execution_ctx.workspace_id)
        if server is None:
            raise MCPServerNotFoundError(server_id)
        if server.status is not MCPServerStatus.active:
            raise MCPServerSuspendedError(server_id)

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.MCP_INVOCATION_TIMEOUT_SECONDS
            ) as http_client:
                client = MCPClient(
                    server.endpoint_url,
                    server.auth_config,
                    http_client=http_client,
                    timeout_seconds=self.settings.MCP_INVOCATION_TIMEOUT_SECONDS,
                )
                result = await client.call_tool(tool_name, arguments)
        except (MCPServerUnavailableError, MCPToolError) as exc:
            classification = getattr(exc, "classification", "permanent")
            await self.mcp_service.update_health(server_id, ok=False, classification=classification)
            await self.mcp_service.create_audit_record(
                workspace_id=execution_ctx.workspace_id,
                principal_id=execution_ctx.agent_id,
                agent_id=execution_ctx.agent_id,
                agent_fqn=execution_ctx.agent_fqn,
                server_id=server_id,
                tool_identifier=tool_fqn,
                direction=MCPInvocationDirection.outbound,
                outcome=(
                    MCPInvocationOutcome.error_transient
                    if classification == "transient"
                    else MCPInvocationOutcome.error_permanent
                ),
                policy_decision=gate.model_dump(mode="json"),
                payload_size_bytes=payload_size,
                error_code=getattr(exc, "code", "mcp_error"),
                error_classification=classification,
            )
            if classification == "transient":
                await publish_mcp_event(
                    self.mcp_service.producer,
                    MCPEventType.catalog_stale,
                    MCPEventPayload(
                        server_id=server_id,
                        workspace_id=execution_ctx.workspace_id,
                        agent_id=execution_ctx.agent_id,
                        agent_fqn=execution_ctx.agent_fqn,
                        tool_identifier=tool_fqn,
                        direction="outbound",
                        outcome="error_transient",
                        error_summary=str(exc),
                    ),
                    self._correlation(execution_ctx.workspace_id, execution_ctx.agent_fqn),
                    key=str(server_id),
                )
            raise

        sanitized = await self.tool_gateway.sanitize_tool_output(
            self._render_result_text(result),
            execution_ctx.agent_id,
            execution_ctx.agent_fqn,
            tool_fqn,
            execution_ctx.execution_id,
            execution_ctx.session,
            workspace_id=execution_ctx.workspace_id,
        )
        await self.mcp_service.update_health(server_id, ok=True)
        await self.mcp_service.create_audit_record(
            workspace_id=execution_ctx.workspace_id,
            principal_id=execution_ctx.agent_id,
            agent_id=execution_ctx.agent_id,
            agent_fqn=execution_ctx.agent_fqn,
            server_id=server_id,
            tool_identifier=tool_fqn,
            direction=MCPInvocationDirection.outbound,
            outcome=MCPInvocationOutcome.allowed,
            policy_decision=gate.model_dump(mode="json"),
            payload_size_bytes=payload_size,
        )
        await publish_mcp_event(
            self.mcp_service.producer,
            MCPEventType.tool_invoked,
            MCPEventPayload(
                server_id=server_id,
                workspace_id=execution_ctx.workspace_id,
                agent_id=execution_ctx.agent_id,
                agent_fqn=execution_ctx.agent_fqn,
                tool_identifier=tool_fqn,
                direction="outbound",
                outcome="allowed",
            ),
            self._correlation(execution_ctx.workspace_id, execution_ctx.agent_fqn),
            key=str(server_id),
        )
        return MCPToolResult(
            content=[{"type": "text", "text": sanitized.output}],
            structuredContent=result.structured_content,
            isError=result.is_error,
        )

    async def _get_server_catalog(
        self,
        server_id: UUID,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any] | None:
        cache_key = f"cache:mcp_catalog:{server_id}"
        if not force_refresh:
            cached = await self.redis_client.get(cache_key)
            if cached is not None:
                try:
                    return cast(dict[str, Any], json.loads(cached.decode("utf-8")))
                except Exception:
                    await self.redis_client.delete(cache_key)
        server = await self.repository.get_server(server_id)
        if server is None:
            raise MCPServerNotFoundError(server_id)
        if server.status is not MCPServerStatus.active:
            raise MCPServerSuspendedError(server_id)
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.MCP_INVOCATION_TIMEOUT_SECONDS
            ) as http_client:
                client = MCPClient(
                    server.endpoint_url,
                    server.auth_config,
                    http_client=http_client,
                    timeout_seconds=self.settings.MCP_INVOCATION_TIMEOUT_SECONDS,
                )
                capabilities = await client.initialize()
                tools = await client.list_tools()
            now = datetime.now(UTC)
            tools_payload: list[dict[str, Any]] = [
                tool.model_dump(mode="json", by_alias=True) for tool in tools
            ]
            payload: dict[str, Any] = {
                "server_id": str(server.id),
                "tools": tools_payload,
                "resources": [],
                "prompts": [],
                "version_snapshot": capabilities.protocol_version,
                "is_stale": False,
                "fetched_at": now.isoformat(),
            }
            await self.redis_client.set(
                cache_key,
                json.dumps(payload).encode("utf-8"),
                ttl=server.catalog_ttl_seconds or self.settings.MCP_CATALOG_TTL_SECONDS,
            )
            await self.repository.upsert_catalog_cache(
                server.id,
                tools_catalog=tools_payload,
                resources_catalog=[],
                prompts_catalog=[],
                fetched_at=now,
                version_snapshot=capabilities.protocol_version,
                is_stale=False,
                next_refresh_at=now + timedelta(seconds=server.catalog_ttl_seconds),
            )
            await self.repository.update_server(
                server,
                last_catalog_fetched_at=now,
                catalog_version_snapshot=capabilities.protocol_version,
            )
            await self.mcp_service.update_health(server.id, ok=True)
            await self._commit()
            await publish_mcp_event(
                self.mcp_service.producer,
                MCPEventType.catalog_refreshed,
                MCPEventPayload(
                    server_id=server.id,
                    workspace_id=server.workspace_id,
                    tool_count=len(tools),
                    version_snapshot=capabilities.protocol_version,
                ),
                self._correlation(server.workspace_id),
                key=str(server.id),
            )
            return payload
        except MCPServerUnavailableError as exc:
            await self.mcp_service.update_health(
                server.id,
                ok=False,
                classification=exc.classification,
            )
            cache = await self.repository.get_catalog_cache(server.id)
            if cache is None:
                return None
            cache.is_stale = True
            cache.next_refresh_at = datetime.now(UTC) + timedelta(
                seconds=server.catalog_ttl_seconds
            )
            await self._commit()
            payload = {
                "server_id": str(server.id),
                "tools": list(cache.tools_catalog),
                "resources": list(cache.resources_catalog),
                "prompts": list(cache.prompts_catalog),
                "version_snapshot": cache.version_snapshot,
                "is_stale": True,
                "fetched_at": cache.fetched_at.isoformat(),
            }
            await publish_mcp_event(
                self.mcp_service.producer,
                MCPEventType.catalog_stale,
                MCPEventPayload(
                    server_id=server.id,
                    workspace_id=server.workspace_id,
                    error_summary=str(exc),
                    version_snapshot=cache.version_snapshot,
                ),
                self._correlation(server.workspace_id),
                key=str(server.id),
            )
            return payload

    @staticmethod
    def _parse_tool_fqn(tool_fqn: str) -> tuple[UUID, str]:
        try:
            _scheme, raw_server_id, tool_name = tool_fqn.split(":", 2)
            return UUID(raw_server_id), tool_name
        except ValueError as exc:
            raise MCPToolNotFoundError(tool_fqn) from exc

    @staticmethod
    def _render_result_text(result: MCPToolResult) -> str:
        for item in result.content:
            if item.get("type") == "text" and item.get("text"):
                return str(item["text"])
        if result.structured_content is not None:
            return json.dumps(result.structured_content)
        return ""

    async def _commit(self) -> None:
        commit = getattr(self.repository.session, "commit", None)
        if callable(commit):
            await commit()

    @staticmethod
    def _correlation(workspace_id: UUID | None, agent_fqn: str | None = None) -> CorrelationContext:
        return CorrelationContext(
            workspace_id=workspace_id,
            agent_fqn=agent_fqn,
            correlation_id=uuid4(),
        )
