from __future__ import annotations

from datetime import UTC, datetime
from platform.mcp.models import (
    MCPCatalogCache,
    MCPExposedTool,
    MCPInvocationAuditRecord,
    MCPServerRegistration,
    MCPServerStatus,
)
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

_UNSET = object()


class MCPRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_server(self, server: MCPServerRegistration) -> MCPServerRegistration:
        self.session.add(server)
        await self.session.flush()
        return server

    async def get_server(
        self,
        server_id: UUID,
        workspace_id: UUID | None = None,
    ) -> MCPServerRegistration | None:
        filters = [MCPServerRegistration.id == server_id]
        if workspace_id is not None:
            filters.append(MCPServerRegistration.workspace_id == workspace_id)
        result = await self.session.execute(select(MCPServerRegistration).where(*filters))
        return result.scalar_one_or_none()

    async def get_server_by_url(
        self,
        workspace_id: UUID,
        endpoint_url: str,
    ) -> MCPServerRegistration | None:
        result = await self.session.execute(
            select(MCPServerRegistration).where(
                MCPServerRegistration.workspace_id == workspace_id,
                MCPServerRegistration.endpoint_url == endpoint_url,
            )
        )
        return result.scalar_one_or_none()

    async def list_servers(
        self,
        workspace_id: UUID,
        *,
        status: MCPServerStatus | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[MCPServerRegistration], int]:
        filters = [MCPServerRegistration.workspace_id == workspace_id]
        if status is not None:
            filters.append(MCPServerRegistration.status == status)
        total_result = await self.session.execute(select(MCPServerRegistration).where(*filters))
        total = len(list(total_result.scalars().all()))
        result = await self.session.execute(
            select(MCPServerRegistration)
            .where(*filters)
            .order_by(MCPServerRegistration.created_at.asc(), MCPServerRegistration.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_servers_by_ids(
        self,
        workspace_id: UUID,
        server_ids: list[UUID],
    ) -> list[MCPServerRegistration]:
        if not server_ids:
            return []
        result = await self.session.execute(
            select(MCPServerRegistration)
            .where(
                MCPServerRegistration.workspace_id == workspace_id,
                MCPServerRegistration.id.in_(server_ids),
            )
            .order_by(MCPServerRegistration.created_at.asc(), MCPServerRegistration.id.asc())
        )
        return list(result.scalars().all())

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
        filters: list[Any] = []
        if workspace_id is not None:
            filters.append(
                or_(
                    MCPExposedTool.workspace_id == workspace_id,
                    MCPExposedTool.workspace_id.is_(None),
                )
            )
        if is_exposed is not None:
            filters.append(MCPExposedTool.is_exposed.is_(is_exposed))
        total_result = await self.session.execute(select(MCPExposedTool).where(*filters))
        total = len(list(total_result.scalars().all()))
        result = await self.session.execute(
            select(MCPExposedTool)
            .where(*filters)
            .order_by(MCPExposedTool.updated_at.desc(), MCPExposedTool.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def get_exposed_tool_by_fqn(
        self,
        tool_fqn: str,
        workspace_id: UUID | None,
    ) -> MCPExposedTool | None:
        filters = [MCPExposedTool.tool_fqn == tool_fqn]
        if workspace_id is None:
            filters.append(MCPExposedTool.workspace_id.is_(None))
        else:
            filters.append(
                or_(
                    MCPExposedTool.workspace_id == workspace_id,
                    MCPExposedTool.workspace_id.is_(None),
                )
            )
        result = await self.session.execute(select(MCPExposedTool).where(*filters))
        return result.scalars().first()

    async def get_exposed_tool_by_name(
        self,
        tool_name: str,
        workspace_id: UUID | None,
    ) -> MCPExposedTool | None:
        filters = [MCPExposedTool.mcp_tool_name == tool_name]
        if workspace_id is None:
            filters.append(MCPExposedTool.workspace_id.is_(None))
        else:
            filters.append(
                or_(
                    MCPExposedTool.workspace_id == workspace_id,
                    MCPExposedTool.workspace_id.is_(None),
                )
            )
        result = await self.session.execute(select(MCPExposedTool).where(*filters))
        return result.scalars().first()

    async def upsert_exposed_tool(self, tool: MCPExposedTool) -> tuple[MCPExposedTool, bool]:
        existing = await self.get_exposed_tool_by_fqn(tool.tool_fqn, tool.workspace_id)
        if existing is None or existing.tool_fqn != tool.tool_fqn:
            self.session.add(tool)
            await self.session.flush()
            return tool, True
        existing.mcp_tool_name = tool.mcp_tool_name
        existing.mcp_description = tool.mcp_description
        existing.mcp_input_schema = tool.mcp_input_schema
        existing.is_exposed = tool.is_exposed
        existing.created_by = tool.created_by
        existing.updated_at = datetime.now(UTC)
        await self.session.flush()
        return existing, False

    async def get_catalog_cache(self, server_id: UUID) -> MCPCatalogCache | None:
        result = await self.session.execute(
            select(MCPCatalogCache).where(MCPCatalogCache.server_id == server_id)
        )
        return result.scalar_one_or_none()

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
        existing = await self.get_catalog_cache(server_id)
        if existing is None:
            existing = MCPCatalogCache(
                server_id=server_id,
                tools_catalog=tools_catalog,
                resources_catalog=list(resources_catalog or []),
                prompts_catalog=list(prompts_catalog or []),
                fetched_at=fetched_at,
                version_snapshot=version_snapshot,
                is_stale=is_stale,
                next_refresh_at=next_refresh_at,
            )
            self.session.add(existing)
            await self.session.flush()
            return existing
        existing.tools_catalog = tools_catalog
        existing.resources_catalog = list(resources_catalog or [])
        existing.prompts_catalog = list(prompts_catalog or [])
        existing.fetched_at = fetched_at
        existing.version_snapshot = version_snapshot
        existing.is_stale = is_stale
        existing.next_refresh_at = next_refresh_at
        await self.session.flush()
        return existing

    async def create_audit_record(
        self,
        record: MCPInvocationAuditRecord,
    ) -> MCPInvocationAuditRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_audit_records_by_agent(
        self,
        agent_id: UUID,
    ) -> list[MCPInvocationAuditRecord]:
        result = await self.session.execute(
            select(MCPInvocationAuditRecord)
            .where(MCPInvocationAuditRecord.agent_id == agent_id)
            .order_by(MCPInvocationAuditRecord.timestamp.desc(), MCPInvocationAuditRecord.id.asc())
        )
        return list(result.scalars().all())

    async def list_due_catalog_refresh(self, now: datetime | None = None) -> list[MCPCatalogCache]:
        reference = now or datetime.now(UTC)
        result = await self.session.execute(
            select(MCPCatalogCache)
            .where(MCPCatalogCache.next_refresh_at <= reference)
            .order_by(MCPCatalogCache.next_refresh_at.asc(), MCPCatalogCache.id.asc())
        )
        return list(result.scalars().all())

    async def mark_refresh_requested(
        self,
        server_id: UUID,
        when: datetime,
    ) -> MCPCatalogCache | None:
        cache = await self.get_catalog_cache(server_id)
        if cache is None:
            return None
        cache.next_refresh_at = when
        await self.session.flush()
        return cache
