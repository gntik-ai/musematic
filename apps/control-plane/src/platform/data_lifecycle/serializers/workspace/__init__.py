"""Workspace-scope serializers for data export.

Each serializer is an async generator yielding ``(filepath, bytes)``
tuples that ExportService writes into the export ZIP. Serializers are
deliberately decoupled from the service so they can be tested in
isolation and so future serializers (e.g. raw artifact blobs from S3)
can opt into a streaming variant without touching the service layer.

The default serializer set is constructed by
:func:`build_default_workspace_serializers` and registered on
``ExportService`` at app construction time.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from platform.data_lifecycle.serializers.workspace.agents import (
    serialize_workspace_agents,
)
from platform.data_lifecycle.serializers.workspace.audit import (
    serialize_workspace_audit,
)
from platform.data_lifecycle.serializers.workspace.costs import (
    serialize_workspace_costs,
)
from platform.data_lifecycle.serializers.workspace.executions import (
    serialize_workspace_executions,
)
from platform.data_lifecycle.serializers.workspace.members import (
    serialize_workspace_members,
)
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

SerializerFn = Callable[..., AsyncIterator[tuple[str, bytes]]]


def build_default_workspace_serializers(
    *,
    session: AsyncSession,
) -> dict[str, SerializerFn]:
    """Wire the default 5 workspace serializers against an SQLAlchemy session."""

    async def _agents(
        *, scope_id: UUID, tenant_id: UUID
    ) -> AsyncIterator[tuple[str, bytes]]:
        async for entry in serialize_workspace_agents(
            session=session, workspace_id=scope_id, tenant_id=tenant_id
        ):
            yield entry

    async def _executions(
        *, scope_id: UUID, tenant_id: UUID
    ) -> AsyncIterator[tuple[str, bytes]]:
        async for entry in serialize_workspace_executions(
            session=session, workspace_id=scope_id, tenant_id=tenant_id
        ):
            yield entry

    async def _audit(
        *, scope_id: UUID, tenant_id: UUID
    ) -> AsyncIterator[tuple[str, bytes]]:
        async for entry in serialize_workspace_audit(
            session=session, workspace_id=scope_id, tenant_id=tenant_id
        ):
            yield entry

    async def _costs(
        *, scope_id: UUID, tenant_id: UUID
    ) -> AsyncIterator[tuple[str, bytes]]:
        async for entry in serialize_workspace_costs(
            session=session, workspace_id=scope_id, tenant_id=tenant_id
        ):
            yield entry

    async def _members(
        *, scope_id: UUID, tenant_id: UUID
    ) -> AsyncIterator[tuple[str, bytes]]:
        async for entry in serialize_workspace_members(
            session=session, workspace_id=scope_id, tenant_id=tenant_id
        ):
            yield entry

    return {
        "agents": _agents,
        "executions": _executions,
        "audit": _audit,
        "costs": _costs,
        "members": _members,
    }
