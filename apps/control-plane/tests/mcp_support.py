from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from platform.common.clients.redis import RateLimitResult
from platform.common.config import PlatformSettings
from platform.mcp.models import (
    MCPCatalogCache,
    MCPExposedTool,
    MCPInvocationAuditRecord,
    MCPServerRegistration,
    MCPServerStatus,
)
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4


def build_settings(**overrides: Any) -> PlatformSettings:
    base = {
        "AUTH_JWT_SECRET_KEY": "secret" * 6,
        "AUTH_JWT_ALGORITHM": "HS256",
    }
    base.update(overrides)
    return PlatformSettings(**base)


@dataclass
class SessionTracker:
    commit_calls: int = 0
    rollback_calls: int = 0
    flush_calls: int = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1

    async def flush(self) -> None:
        self.flush_calls += 1


class FakeRedisClient:
    def __init__(
        self,
        *,
        rate_limit_results: list[RateLimitResult] | None = None,
        values: dict[str, bytes] | None = None,
    ) -> None:
        self.rate_limit_results = list(
            rate_limit_results
            or [RateLimitResult(allowed=True, remaining=59, retry_after_ms=0)]
        )
        self.values = dict(values or {})
        self.hashes: dict[str, dict[str, str]] = {}
        self.expirations: dict[str, int] = {}
        self.deleted: list[str] = []
        self.rate_limit_calls: list[dict[str, Any]] = []

    async def _get_client(self) -> FakeRedisClient:
        return self

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        self.values[key] = value
        if ttl is not None:
            self.expirations[key] = ttl

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)
        self.hashes.pop(key, None)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    async def hset(self, key: str, mapping: dict[str, Any]) -> int:
        self.hashes[key] = {field: str(value) for field, value in mapping.items()}
        return len(mapping)

    async def expire(self, key: str, seconds: int) -> bool:
        self.expirations[key] = seconds
        return True

    async def check_rate_limit(
        self,
        resource: str,
        key: str,
        limit: int,
        window_ms: int,
    ) -> RateLimitResult:
        self.rate_limit_calls.append(
            {
                "resource": resource,
                "key": key,
                "limit": limit,
                "window_ms": window_ms,
            }
        )
        if self.rate_limit_results:
            return self.rate_limit_results.pop(0)
        return RateLimitResult(allowed=True, remaining=max(limit - 1, 0), retry_after_ms=0)


class RecordingProducer:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(
        self,
        topic: str,
        key: str,
        event_type: str,
        payload: dict[str, Any],
        correlation_ctx: Any,
        source: str,
    ) -> None:
        self.events.append(
            {
                "topic": topic,
                "key": key,
                "event_type": event_type,
                "payload": payload,
                "correlation_ctx": correlation_ctx,
                "source": source,
            }
        )


@dataclass
class FakeMCPRepository:
    session: SessionTracker = field(default_factory=SessionTracker)
    servers: dict[UUID, MCPServerRegistration] = field(default_factory=dict)
    exposed_tools: dict[tuple[UUID | None, str], MCPExposedTool] = field(default_factory=dict)
    catalog_caches: dict[UUID, MCPCatalogCache] = field(default_factory=dict)
    audit_records: list[MCPInvocationAuditRecord] = field(default_factory=list)

    async def create_server(self, server: MCPServerRegistration) -> MCPServerRegistration:
        now = datetime.now(UTC)
        if getattr(server, "id", None) is None:
            server.id = uuid4()
        if getattr(server, "created_at", None) is None:
            server.created_at = now
        if getattr(server, "updated_at", None) is None:
            server.updated_at = now
        self.servers[server.id] = server
        await self.session.flush()
        return server

    async def get_server(
        self,
        server_id: UUID,
        workspace_id: UUID | None = None,
    ) -> MCPServerRegistration | None:
        server = self.servers.get(server_id)
        if server is None:
            return None
        if workspace_id is not None and server.workspace_id != workspace_id:
            return None
        return server

    async def get_server_by_url(
        self,
        workspace_id: UUID,
        endpoint_url: str,
    ) -> MCPServerRegistration | None:
        return next(
            (
                server
                for server in self.servers.values()
                if server.workspace_id == workspace_id and server.endpoint_url == endpoint_url
            ),
            None,
        )

    async def list_servers(
        self,
        workspace_id: UUID,
        *,
        status: MCPServerStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[MCPServerRegistration], int]:
        items = [
            server
            for server in self.servers.values()
            if server.workspace_id == workspace_id
            and (status is None or server.status is status)
        ]
        items.sort(key=lambda server: (server.created_at, server.id))
        return items[offset : offset + limit], len(items)

    async def list_servers_by_ids(
        self,
        workspace_id: UUID,
        server_ids: list[UUID],
    ) -> list[MCPServerRegistration]:
        return [
            server
            for server_id in server_ids
            if (server := self.servers.get(server_id)) is not None
            and server.workspace_id == workspace_id
        ]

    async def update_server(
        self,
        server: MCPServerRegistration,
        **fields: Any,
    ) -> MCPServerRegistration:
        for key, value in fields.items():
            setattr(server, key, value)
        server.updated_at = datetime.now(UTC)
        await self.session.flush()
        return server

    async def get_exposed_tools(
        self,
        workspace_id: UUID | None,
        *,
        is_exposed: bool | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[MCPExposedTool], int]:
        items = [
            tool
            for tool in self.exposed_tools.values()
            if (
                workspace_id is None
                or tool.workspace_id is None
                or tool.workspace_id == workspace_id
            )
            and (is_exposed is None or tool.is_exposed is is_exposed)
        ]
        items.sort(key=lambda tool: (tool.updated_at, tool.id))
        return items[offset : offset + limit], len(items)

    async def get_exposed_tool_by_fqn(
        self,
        tool_fqn: str,
        workspace_id: UUID | None,
    ) -> MCPExposedTool | None:
        return self.exposed_tools.get((workspace_id, tool_fqn)) or self.exposed_tools.get(
            (None, tool_fqn)
        )

    async def get_exposed_tool_by_name(
        self,
        tool_name: str,
        workspace_id: UUID | None,
    ) -> MCPExposedTool | None:
        for tool in self.exposed_tools.values():
            if tool.mcp_tool_name != tool_name:
                continue
            if workspace_id is None and tool.workspace_id is None:
                return tool
            if workspace_id is not None and tool.workspace_id in {None, workspace_id}:
                return tool
        return None

    async def upsert_exposed_tool(self, tool: MCPExposedTool) -> tuple[MCPExposedTool, bool]:
        existing = await self.get_exposed_tool_by_fqn(tool.tool_fqn, tool.workspace_id)
        if existing is None or existing.workspace_id != tool.workspace_id:
            now = datetime.now(UTC)
            if getattr(tool, "id", None) is None:
                tool.id = uuid4()
            if getattr(tool, "created_at", None) is None:
                tool.created_at = now
            if getattr(tool, "updated_at", None) is None:
                tool.updated_at = now
            self.exposed_tools[(tool.workspace_id, tool.tool_fqn)] = tool
            await self.session.flush()
            return tool, True
        existing.mcp_tool_name = tool.mcp_tool_name
        existing.mcp_description = tool.mcp_description
        existing.mcp_input_schema = dict(tool.mcp_input_schema)
        existing.is_exposed = tool.is_exposed
        existing.created_by = tool.created_by
        existing.updated_at = datetime.now(UTC)
        await self.session.flush()
        return existing, False

    async def get_catalog_cache(self, server_id: UUID) -> MCPCatalogCache | None:
        return self.catalog_caches.get(server_id)

    async def upsert_catalog_cache(
        self,
        server_id: UUID,
        *,
        tools_catalog: list[dict[str, Any]],
        resources_catalog: list[dict[str, Any]] | None = None,
        prompts_catalog: list[dict[str, Any]] | None = None,
        fetched_at: datetime,
        version_snapshot: str | None,
        is_stale: bool,
        next_refresh_at: datetime,
    ) -> MCPCatalogCache:
        cache = self.catalog_caches.get(server_id)
        if cache is None:
            cache = build_catalog_cache(
                server_id=server_id,
                tools_catalog=tools_catalog,
                resources_catalog=resources_catalog or [],
                prompts_catalog=prompts_catalog or [],
                fetched_at=fetched_at,
                version_snapshot=version_snapshot,
                is_stale=is_stale,
                next_refresh_at=next_refresh_at,
            )
            self.catalog_caches[server_id] = cache
        else:
            cache.tools_catalog = list(tools_catalog)
            cache.resources_catalog = list(resources_catalog or [])
            cache.prompts_catalog = list(prompts_catalog or [])
            cache.fetched_at = fetched_at
            cache.version_snapshot = version_snapshot
            cache.is_stale = is_stale
            cache.next_refresh_at = next_refresh_at
        await self.session.flush()
        return cache

    async def create_audit_record(
        self,
        record: MCPInvocationAuditRecord,
    ) -> MCPInvocationAuditRecord:
        if getattr(record, "id", None) is None:
            record.id = uuid4()
        if getattr(record, "timestamp", None) is None:
            record.timestamp = datetime.now(UTC)
        self.audit_records.append(record)
        await self.session.flush()
        return record

    async def list_audit_records_by_agent(
        self,
        agent_id: UUID,
    ) -> list[MCPInvocationAuditRecord]:
        return [record for record in self.audit_records if record.agent_id == agent_id]

    async def list_due_catalog_refresh(
        self,
        now: datetime | None = None,
    ) -> list[MCPCatalogCache]:
        reference = now or datetime.now(UTC)
        return [
            cache
            for cache in self.catalog_caches.values()
            if cache.next_refresh_at <= reference
        ]

    async def mark_refresh_requested(
        self,
        server_id: UUID,
        when: datetime,
    ) -> MCPCatalogCache | None:
        cache = self.catalog_caches.get(server_id)
        if cache is None:
            return None
        cache.next_refresh_at = when
        await self.session.flush()
        return cache


def build_server(**overrides: Any) -> MCPServerRegistration:
    now = datetime.now(UTC)
    server = MCPServerRegistration(
        id=overrides.pop("id", uuid4()),
        workspace_id=overrides.pop("workspace_id", uuid4()),
        display_name=overrides.pop("display_name", "External MCP"),
        endpoint_url=overrides.pop("endpoint_url", "https://mcp.example.com"),
        auth_config=overrides.pop("auth_config", {"type": "api_key", "value": "secret"}),
        status=overrides.pop("status", MCPServerStatus.active),
        catalog_ttl_seconds=overrides.pop("catalog_ttl_seconds", 3600),
        last_catalog_fetched_at=overrides.pop("last_catalog_fetched_at", None),
        catalog_version_snapshot=overrides.pop("catalog_version_snapshot", None),
        created_by=overrides.pop("created_by", uuid4()),
        created_at=overrides.pop("created_at", now),
        updated_at=overrides.pop("updated_at", now),
    )
    for key, value in overrides.items():
        setattr(server, key, value)
    return server


def build_exposed_tool(**overrides: Any) -> MCPExposedTool:
    now = datetime.now(UTC)
    tool = MCPExposedTool(
        id=overrides.pop("id", uuid4()),
        workspace_id=overrides.pop("workspace_id", uuid4()),
        tool_fqn=overrides.pop("tool_fqn", "finance:lookup"),
        mcp_tool_name=overrides.pop("mcp_tool_name", "lookup"),
        mcp_description=overrides.pop("mcp_description", "Lookup a finance record"),
        mcp_input_schema=overrides.pop(
            "mcp_input_schema",
            {"type": "object", "properties": {"query": {"type": "string"}}},
        ),
        is_exposed=overrides.pop("is_exposed", True),
        created_by=overrides.pop("created_by", uuid4()),
        created_at=overrides.pop("created_at", now),
        updated_at=overrides.pop("updated_at", now),
    )
    for key, value in overrides.items():
        setattr(tool, key, value)
    return tool


def build_catalog_cache(**overrides: Any) -> MCPCatalogCache:
    now = datetime.now(UTC)
    cache = MCPCatalogCache(
        id=overrides.pop("id", uuid4()),
        server_id=overrides.pop("server_id", uuid4()),
        tools_catalog=overrides.pop(
            "tools_catalog",
            [
                {
                    "name": "search",
                    "description": "Search records",
                    "inputSchema": {"type": "object"},
                }
            ],
        ),
        resources_catalog=overrides.pop("resources_catalog", []),
        prompts_catalog=overrides.pop("prompts_catalog", []),
        fetched_at=overrides.pop("fetched_at", now),
        version_snapshot=overrides.pop("version_snapshot", "2024-11-05"),
        is_stale=overrides.pop("is_stale", False),
        next_refresh_at=overrides.pop("next_refresh_at", now + timedelta(hours=1)),
    )
    for key, value in overrides.items():
        setattr(cache, key, value)
    return cache


def build_agent_profile(**overrides: Any) -> Any:
    return SimpleNamespace(
        id=overrides.pop("id", uuid4()),
        workspace_id=overrides.pop("workspace_id", uuid4()),
        fqn=overrides.pop("fqn", "finance:analyst"),
        mcp_server_refs=overrides.pop("mcp_server_refs", []),
        mcp_servers=overrides.pop("mcp_servers", []),
        maturity_level=overrides.pop("maturity_level", 1),
        **overrides,
    )
