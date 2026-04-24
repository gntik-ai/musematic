from __future__ import annotations

from datetime import UTC, datetime
from platform.audit.dependencies import build_audit_chain_service
from platform.common.audit_hook import audit_chain_hook
from platform.common.clients.redis import AsyncRedisClient, RateLimitResult
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.mcp.events import MCPEventPayload, MCPEventType, publish_mcp_event
from platform.mcp.exceptions import (
    MCPDuplicateRegistrationError,
    MCPInsecureTransportError,
    MCPServerNotFoundError,
    MCPServerSuspendedError,
)
from platform.mcp.models import (
    MCPCatalogCache,
    MCPExposedTool,
    MCPInvocationAuditRecord,
    MCPInvocationDirection,
    MCPInvocationOutcome,
    MCPServerRegistration,
    MCPServerStatus,
)
from platform.mcp.repository import MCPRepository
from platform.mcp.schemas import (
    MCPCatalogResponse,
    MCPExposedToolListResponse,
    MCPExposedToolResponse,
    MCPExposedToolUpsertRequest,
    MCPServerHealthStatus,
    MCPServerListResponse,
    MCPServerPatch,
    MCPServerRegisterRequest,
    MCPServerResponse,
    MCPToolDefinition,
)
from typing import Any, cast
from uuid import UUID, uuid4


class MCPService:
    def __init__(
        self,
        *,
        repository: MCPRepository,
        settings: PlatformSettings,
        producer: EventProducer | None,
        redis_client: AsyncRedisClient,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.redis_client = redis_client
        self.tool_registry: Any | None = None
        self.audit_chain = build_audit_chain_service(repository.session, settings, producer)

    async def register_server(
        self,
        workspace_id: UUID,
        request: MCPServerRegisterRequest,
        created_by: UUID,
    ) -> MCPServerResponse:
        if not request.endpoint_url.startswith("https://"):
            raise MCPInsecureTransportError()
        existing = await self.repository.get_server_by_url(workspace_id, request.endpoint_url)
        if existing is not None:
            raise MCPDuplicateRegistrationError()
        server = await self.repository.create_server(
            MCPServerRegistration(
                workspace_id=workspace_id,
                display_name=request.display_name,
                endpoint_url=request.endpoint_url,
                auth_config=dict(request.auth_config),
                status=MCPServerStatus.active,
                catalog_ttl_seconds=request.catalog_ttl_seconds,
                created_by=created_by,
            )
        )
        await self._commit()
        await publish_mcp_event(
            self.producer,
            MCPEventType.server_registered,
            MCPEventPayload(
                server_id=server.id,
                workspace_id=workspace_id,
                details={"endpoint_url": server.endpoint_url},
            ),
            self._correlation(workspace_id),
            key=str(server.id),
        )
        return await self._server_response(server)

    async def get_server_record(self, workspace_id: UUID, server_id: UUID) -> MCPServerRegistration:
        server = await self.repository.get_server(server_id, workspace_id)
        if server is None:
            raise MCPServerNotFoundError(server_id)
        return server

    async def get_server(self, workspace_id: UUID, server_id: UUID) -> MCPServerResponse:
        return await self._server_response(await self.get_server_record(workspace_id, server_id))

    async def list_servers(
        self,
        workspace_id: UUID,
        *,
        status: MCPServerStatus | None,
        page: int,
        page_size: int,
    ) -> MCPServerListResponse:
        items, total = await self.repository.list_servers(
            workspace_id,
            status=status,
            offset=max(page - 1, 0) * page_size,
            limit=page_size,
        )
        return MCPServerListResponse(
            items=[await self._server_response(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def update_server(
        self,
        workspace_id: UUID,
        server_id: UUID,
        patch: MCPServerPatch,
    ) -> MCPServerResponse:
        server = await self.get_server_record(workspace_id, server_id)
        if server.status is MCPServerStatus.deregistered:
            raise MCPServerSuspendedError(server_id)
        updates: dict[str, Any] = {}
        if "display_name" in patch.model_fields_set and patch.display_name is not None:
            updates["display_name"] = patch.display_name
        if "status" in patch.model_fields_set and patch.status is not None:
            updates["status"] = patch.status
        if (
            "catalog_ttl_seconds" in patch.model_fields_set
            and patch.catalog_ttl_seconds is not None
        ):
            updates["catalog_ttl_seconds"] = patch.catalog_ttl_seconds
        if updates:
            await self.repository.update_server(server, **updates)
            await self._commit()
            if updates.get("status") is MCPServerStatus.suspended:
                await publish_mcp_event(
                    self.producer,
                    MCPEventType.server_suspended,
                    MCPEventPayload(server_id=server.id, workspace_id=workspace_id),
                    self._correlation(workspace_id),
                    key=str(server.id),
                )
        return await self._server_response(server)

    async def deregister_server(self, workspace_id: UUID, server_id: UUID) -> MCPServerResponse:
        server = await self.get_server_record(workspace_id, server_id)
        await self.repository.update_server(server, status=MCPServerStatus.deregistered)
        await self._commit()
        await publish_mcp_event(
            self.producer,
            MCPEventType.server_deregistered,
            MCPEventPayload(server_id=server.id, workspace_id=workspace_id),
            self._correlation(workspace_id),
            key=str(server.id),
        )
        return await self._server_response(server)

    async def list_exposed_tools(
        self,
        workspace_id: UUID | None,
        *,
        is_exposed: bool | None,
        page: int,
        page_size: int,
    ) -> MCPExposedToolListResponse:
        items, total = await self.repository.get_exposed_tools(
            workspace_id,
            is_exposed=is_exposed,
            offset=max(page - 1, 0) * page_size,
            limit=page_size,
        )
        return MCPExposedToolListResponse(
            items=[MCPExposedToolResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def toggle_exposure(
        self,
        workspace_id: UUID | None,
        tool_fqn: str,
        request: MCPExposedToolUpsertRequest,
        created_by: UUID,
    ) -> MCPExposedToolResponse:
        tool, _created = await self.repository.upsert_exposed_tool(
            MCPExposedTool(
                workspace_id=workspace_id,
                tool_fqn=tool_fqn,
                mcp_tool_name=request.mcp_tool_name,
                mcp_description=request.mcp_description,
                mcp_input_schema=dict(request.mcp_input_schema),
                is_exposed=request.is_exposed,
                created_by=created_by,
            )
        )
        await self._commit()
        await self.redis_client.delete(self._exposed_tools_cache_key(workspace_id))
        return MCPExposedToolResponse.model_validate(tool)

    async def get_catalog(self, workspace_id: UUID, server_id: UUID) -> MCPCatalogResponse:
        await self.get_server_record(workspace_id, server_id)
        cache = await self.repository.get_catalog_cache(server_id)
        if cache is None:
            raise MCPServerNotFoundError(server_id)
        return self._catalog_response(server_id, cache)

    async def force_refresh(self, workspace_id: UUID, server_id: UUID) -> dict[str, Any]:
        await self.get_server_record(workspace_id, server_id)
        now = datetime.now(UTC)
        cache = await self.repository.mark_refresh_requested(server_id, now)
        if cache is None:
            await self.repository.upsert_catalog_cache(
                server_id,
                tools_catalog=[],
                resources_catalog=[],
                prompts_catalog=[],
                fetched_at=now,
                version_snapshot=None,
                is_stale=True,
                next_refresh_at=now,
            )
        await self._commit()
        return {"server_id": server_id, "refresh_scheduled": True}

    async def refresh_due_catalogs(self) -> int:
        if self.tool_registry is None:
            return 0
        due = await self.repository.list_due_catalog_refresh()
        refreshed = 0
        for entry in due:
            try:
                await self.tool_registry.refresh_server_catalog(entry.server_id, force_refresh=True)
                refreshed += 1
            except Exception:
                continue
        return refreshed

    async def get_server_health(self, server_id: UUID) -> MCPServerHealthStatus:
        raw = await self.redis_client.hgetall(self._health_key(server_id))
        if raw:
            return MCPServerHealthStatus(
                status=str(raw.get("status", "unknown")),
                last_success_at=self._parse_datetime(raw.get("last_success_at")),
                error_count_5m=int(raw.get("error_count_5m", 0) or 0),
                last_error_at=self._parse_datetime(raw.get("last_error_at")),
            )
        cache = await self.repository.get_catalog_cache(server_id)
        if cache is not None:
            return MCPServerHealthStatus(
                status="healthy" if not cache.is_stale else "degraded",
                last_success_at=cache.fetched_at,
                error_count_5m=0,
                last_error_at=None,
            )
        return MCPServerHealthStatus(status="unknown")

    async def update_health(
        self,
        server_id: UUID,
        *,
        ok: bool,
        classification: str | None = None,
    ) -> None:
        key = self._health_key(server_id)
        client = await self.redis_client._get_client()
        now = datetime.now(UTC)
        current = cast(dict[str, Any], await cast(Any, client.hgetall(key)))
        error_count = int(current.get("error_count_5m", 0) or 0)
        if ok:
            mapping = {
                "status": "healthy",
                "last_success_at": now.isoformat(),
                "error_count_5m": 0,
                "last_error_at": current.get("last_error_at", ""),
            }
        else:
            error_count += 1
            mapping = {
                "status": "degraded" if classification == "transient" else "unhealthy",
                "last_success_at": current.get("last_success_at", ""),
                "error_count_5m": error_count,
                "last_error_at": now.isoformat(),
            }
        await cast(Any, client.hset(key, mapping=mapping))
        await cast(Any, client.expire(key, 90))

    async def check_rate_limit(self, principal_id: UUID) -> RateLimitResult:
        checker = getattr(self.redis_client, "check_rate_limit", None)
        if callable(checker):
            result = await cast(
                Any,
                checker(
                    "mcp",
                    str(principal_id),
                    self.settings.MCP_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE,
                    60_000,
                ),
            )
            return cast(RateLimitResult, result)
        return RateLimitResult(
            allowed=True,
            remaining=self.settings.MCP_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE,
            retry_after_ms=0,
        )

    async def create_audit_record(
        self,
        *,
        workspace_id: UUID | None,
        principal_id: UUID | None,
        agent_id: UUID | None,
        agent_fqn: str | None,
        server_id: UUID | None,
        tool_identifier: str,
        direction: MCPInvocationDirection,
        outcome: MCPInvocationOutcome,
        policy_decision: dict[str, Any] | None = None,
        payload_size_bytes: int | None = None,
        error_code: str | None = None,
        error_classification: str | None = None,
    ) -> MCPInvocationAuditRecord:
        record = await self.repository.create_audit_record(
            MCPInvocationAuditRecord(
                workspace_id=workspace_id,
                principal_id=principal_id,
                agent_id=agent_id,
                agent_fqn=agent_fqn,
                server_id=server_id,
                tool_identifier=tool_identifier,
                direction=direction,
                outcome=outcome,
                policy_decision=policy_decision,
                payload_size_bytes=payload_size_bytes,
                error_code=error_code,
                error_classification=error_classification,
            )
        )
        await audit_chain_hook(
            self.audit_chain,
            record.id,
            "mcp",
            {
                "workspace_id": record.workspace_id,
                "principal_id": record.principal_id,
                "agent_id": record.agent_id,
                "agent_fqn": record.agent_fqn,
                "server_id": record.server_id,
                "tool_identifier": record.tool_identifier,
                "direction": record.direction.value,
                "outcome": record.outcome.value,
                "policy_decision": record.policy_decision,
                "payload_size_bytes": record.payload_size_bytes,
                "error_code": record.error_code,
                "error_classification": record.error_classification,
                "timestamp": record.timestamp,
            },
        )
        await self._commit()
        return record

    async def _server_response(self, server: MCPServerRegistration) -> MCPServerResponse:
        cache = await self.repository.get_catalog_cache(server.id)
        health = await self.get_server_health(server.id)
        tool_count = len(cache.tools_catalog) if cache is not None else 0
        return MCPServerResponse(
            server_id=server.id,
            display_name=server.display_name,
            endpoint_url=server.endpoint_url,
            status=server.status,
            catalog_ttl_seconds=server.catalog_ttl_seconds,
            last_catalog_fetched_at=server.last_catalog_fetched_at,
            catalog_version_snapshot=server.catalog_version_snapshot,
            catalog_is_stale=bool(cache.is_stale) if cache is not None else False,
            tool_count=tool_count,
            health=health,
            created_at=server.created_at,
            created_by=server.created_by,
        )

    def _catalog_response(self, server_id: UUID, cache: MCPCatalogCache) -> MCPCatalogResponse:
        return MCPCatalogResponse(
            server_id=server_id,
            fetched_at=cache.fetched_at,
            version_snapshot=cache.version_snapshot,
            is_stale=cache.is_stale,
            tool_count=len(cache.tools_catalog),
            tools=[
                MCPToolDefinition.model_validate(
                    {
                        "name": item.get("name", ""),
                        "description": item.get("description"),
                        "inputSchema": item.get("inputSchema") or item.get("input_schema") or {},
                    }
                )
                for item in cache.tools_catalog
            ],
        )

    async def _commit(self) -> None:
        commit = getattr(self.repository.session, "commit", None)
        if callable(commit):
            await commit()

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    @staticmethod
    def _correlation(workspace_id: UUID | None) -> CorrelationContext:
        return CorrelationContext(workspace_id=workspace_id, correlation_id=uuid4())

    @staticmethod
    def _health_key(server_id: UUID) -> str:
        return f"cache:mcp_server_health:{server_id}"

    @staticmethod
    def _exposed_tools_cache_key(workspace_id: UUID | None) -> str:
        return f"cache:mcp_exposed_tools:{workspace_id or 'global'}"
