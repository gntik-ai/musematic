from __future__ import annotations

from datetime import datetime
from platform.composition.models import (
    AgentBlueprint,
    CompositionAuditEntry,
    CompositionRequest,
    CompositionValidation,
    FleetBlueprint,
)
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class CompositionRepository:
    """Provide async persistence helpers for composition."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_request(self, request: CompositionRequest) -> CompositionRequest:
        """Persist a composition request."""
        self.session.add(request)
        await self.session.flush()
        return request

    async def upsert_request_status(
        self,
        request_id: UUID,
        workspace_id: UUID,
        status: str,
        *,
        llm_model_used: str | None = None,
        generation_time_ms: int | None = None,
    ) -> CompositionRequest | None:
        """Update request status and optional generation metadata."""
        values: dict[str, Any] = {"status": status}
        if llm_model_used is not None:
            values["llm_model_used"] = llm_model_used
        if generation_time_ms is not None:
            values["generation_time_ms"] = generation_time_ms
        await self.session.execute(
            update(CompositionRequest)
            .where(
                CompositionRequest.id == request_id,
                CompositionRequest.workspace_id == workspace_id,
            )
            .values(**values)
        )
        await self.session.flush()
        return await self.get_request(request_id, workspace_id)

    async def get_request(
        self,
        request_id: UUID,
        workspace_id: UUID,
    ) -> CompositionRequest | None:
        """Return a composition request by id and workspace."""
        result = await self.session.execute(
            select(CompositionRequest).where(
                CompositionRequest.id == request_id,
                CompositionRequest.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_requests(
        self,
        workspace_id: UUID,
        *,
        request_type: str | None = None,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[CompositionRequest], str | None]:
        """Return requests in newest-first order using created_at cursor pagination."""
        query = select(CompositionRequest).where(CompositionRequest.workspace_id == workspace_id)
        if request_type is not None:
            query = query.where(CompositionRequest.request_type == request_type)
        if status is not None:
            query = query.where(CompositionRequest.status == status)
        if cursor is not None:
            query = query.where(CompositionRequest.created_at < _parse_cursor(cursor))
        query = query.order_by(
            CompositionRequest.created_at.desc(),
            CompositionRequest.id.desc(),
        ).limit(limit + 1)
        result = await self.session.execute(query)
        items = list(result.scalars().all())
        next_cursor = None
        if len(items) > limit:
            next_cursor = items[limit - 1].created_at.isoformat()
            items = items[:limit]
        return items, next_cursor

    async def create_agent_blueprint(self, blueprint: AgentBlueprint) -> AgentBlueprint:
        """Persist an agent blueprint."""
        self.session.add(blueprint)
        await self.session.flush()
        await self.session.refresh(blueprint, attribute_names=["request"])
        return blueprint

    async def create_fleet_blueprint(self, blueprint: FleetBlueprint) -> FleetBlueprint:
        """Persist a fleet blueprint."""
        self.session.add(blueprint)
        await self.session.flush()
        await self.session.refresh(blueprint, attribute_names=["request"])
        return blueprint

    async def get_agent_blueprint(
        self,
        blueprint_id: UUID,
        workspace_id: UUID,
    ) -> AgentBlueprint | None:
        """Return an agent blueprint by id and workspace."""
        result = await self.session.execute(
            select(AgentBlueprint)
            .options(selectinload(AgentBlueprint.request))
            .where(
                AgentBlueprint.id == blueprint_id,
                AgentBlueprint.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_fleet_blueprint(
        self,
        blueprint_id: UUID,
        workspace_id: UUID,
    ) -> FleetBlueprint | None:
        """Return a fleet blueprint by id and workspace."""
        result = await self.session.execute(
            select(FleetBlueprint)
            .options(selectinload(FleetBlueprint.request))
            .where(
                FleetBlueprint.id == blueprint_id,
                FleetBlueprint.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_agent_blueprint(
        self,
        request_id: UUID,
        workspace_id: UUID,
    ) -> AgentBlueprint | None:
        """Return the latest agent blueprint version for a request."""
        result = await self.session.execute(
            select(AgentBlueprint)
            .options(selectinload(AgentBlueprint.request))
            .where(
                AgentBlueprint.request_id == request_id,
                AgentBlueprint.workspace_id == workspace_id,
            )
            .order_by(AgentBlueprint.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_fleet_blueprint(
        self,
        request_id: UUID,
        workspace_id: UUID,
    ) -> FleetBlueprint | None:
        """Return the latest fleet blueprint version for a request."""
        result = await self.session.execute(
            select(FleetBlueprint)
            .options(selectinload(FleetBlueprint.request))
            .where(
                FleetBlueprint.request_id == request_id,
                FleetBlueprint.workspace_id == workspace_id,
            )
            .order_by(FleetBlueprint.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def insert_validation(
        self,
        validation: CompositionValidation,
    ) -> CompositionValidation:
        """Persist a composition validation."""
        self.session.add(validation)
        await self.session.flush()
        return validation

    async def insert_audit_entry(
        self,
        audit_entry: CompositionAuditEntry,
    ) -> CompositionAuditEntry:
        """Insert an append-only audit entry.

        This repository intentionally exposes no update/delete audit-entry methods.
        """
        self.session.add(audit_entry)
        await self.session.flush()
        return audit_entry

    async def get_audit_entries(
        self,
        request_id: UUID,
        workspace_id: UUID,
        *,
        event_type_filter: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[CompositionAuditEntry], str | None]:
        """Return audit entries in chronological order using created_at cursor pagination."""
        query = select(CompositionAuditEntry).where(
            CompositionAuditEntry.request_id == request_id,
            CompositionAuditEntry.workspace_id == workspace_id,
        )
        if event_type_filter is not None:
            query = query.where(CompositionAuditEntry.event_type == event_type_filter)
        if cursor is not None:
            query = query.where(CompositionAuditEntry.created_at > _parse_cursor(cursor))
        query = query.order_by(
            CompositionAuditEntry.created_at.asc(),
            CompositionAuditEntry.id.asc(),
        ).limit(limit + 1)
        result = await self.session.execute(query)
        items = list(result.scalars().all())
        next_cursor = None
        if len(items) > limit:
            next_cursor = items[limit - 1].created_at.isoformat()
            items = items[:limit]
        return items, next_cursor

    async def request_exists(self, request_id: UUID, workspace_id: UUID) -> bool:
        """Return whether a request exists in a workspace."""
        count = await self.session.scalar(
            select(func.count())
            .select_from(CompositionRequest)
            .where(
                CompositionRequest.id == request_id,
                CompositionRequest.workspace_id == workspace_id,
            )
        )
        return bool(count)


def apply_cursor(query: Select[tuple[Any]], column: Any, cursor: str | None) -> Select[tuple[Any]]:
    """Apply a simple datetime cursor to a select query."""
    if cursor is None:
        return query
    return query.where(column < _parse_cursor(cursor))


def _parse_cursor(cursor: str) -> datetime:
    return datetime.fromisoformat(cursor)
