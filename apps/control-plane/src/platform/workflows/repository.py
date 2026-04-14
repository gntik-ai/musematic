from __future__ import annotations

from platform.workflows.models import (
    TriggerType,
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowTriggerDefinition,
    WorkflowVersion,
)
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class WorkflowRepository:
    """Provide persistence helpers for workflow."""
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """Create definition."""
        self.session.add(definition)
        await self.session.flush()
        return definition

    async def get_definition_by_id(self, workflow_id: UUID) -> WorkflowDefinition | None:
        """Return definition by id."""
        result = await self.session.execute(
            select(WorkflowDefinition)
            .options(
                selectinload(WorkflowDefinition.current_version),
                selectinload(WorkflowDefinition.versions),
                selectinload(WorkflowDefinition.trigger_definitions),
            )
            .where(WorkflowDefinition.id == workflow_id)
        )
        return result.scalar_one_or_none()

    async def get_definition_by_name(
        self,
        *,
        workspace_id: UUID,
        name: str,
    ) -> WorkflowDefinition | None:
        """Return definition by name."""
        result = await self.session.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.workspace_id == workspace_id,
                WorkflowDefinition.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def list_definitions(
        self,
        *,
        workspace_id: UUID,
        status: WorkflowStatus | None,
        tags: list[str] | None,
        offset: int,
        limit: int,
    ) -> tuple[list[WorkflowDefinition], int]:
        """List definitions."""
        query = select(WorkflowDefinition).where(WorkflowDefinition.workspace_id == workspace_id)
        count_query = (
            select(func.count())
            .select_from(WorkflowDefinition)
            .where(WorkflowDefinition.workspace_id == workspace_id)
        )
        if status is not None:
            query = query.where(WorkflowDefinition.status == status)
            count_query = count_query.where(WorkflowDefinition.status == status)
        if tags:
            query = query.where(WorkflowDefinition.tags.overlap(tags))
            count_query = count_query.where(WorkflowDefinition.tags.overlap(tags))
        total = await self.session.scalar(count_query)
        result = await self.session.execute(
            query.options(selectinload(WorkflowDefinition.current_version))
            .order_by(WorkflowDefinition.created_at.desc(), WorkflowDefinition.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def create_version(self, version: WorkflowVersion) -> WorkflowVersion:
        """Create version."""
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_version_by_number(
        self,
        workflow_id: UUID,
        version_number: int,
    ) -> WorkflowVersion | None:
        """Return version by number."""
        result = await self.session.execute(
            select(WorkflowVersion).where(
                WorkflowVersion.definition_id == workflow_id,
                WorkflowVersion.version_number == version_number,
            )
        )
        return result.scalar_one_or_none()

    async def get_version_by_id(self, version_id: UUID) -> WorkflowVersion | None:
        """Return version by id."""
        result = await self.session.execute(
            select(WorkflowVersion).where(WorkflowVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def list_versions(self, workflow_id: UUID) -> list[WorkflowVersion]:
        """List versions."""
        result = await self.session.execute(
            select(WorkflowVersion)
            .where(WorkflowVersion.definition_id == workflow_id)
            .order_by(WorkflowVersion.version_number.asc())
        )
        return list(result.scalars().all())

    async def update_current_version_id(
        self,
        definition: WorkflowDefinition,
        version_id: UUID,
        *,
        schema_version: int,
    ) -> WorkflowDefinition:
        """Update current version id."""
        definition.current_version_id = version_id
        definition.schema_version = schema_version
        await self.session.flush()
        return definition

    async def create_trigger(
        self,
        trigger: WorkflowTriggerDefinition,
    ) -> WorkflowTriggerDefinition:
        """Create trigger."""
        self.session.add(trigger)
        await self.session.flush()
        return trigger

    async def get_trigger_by_id(self, trigger_id: UUID) -> WorkflowTriggerDefinition | None:
        """Return trigger by id."""
        result = await self.session.execute(
            select(WorkflowTriggerDefinition).where(WorkflowTriggerDefinition.id == trigger_id)
        )
        return result.scalar_one_or_none()

    async def list_triggers(self, workflow_id: UUID) -> list[WorkflowTriggerDefinition]:
        """List triggers."""
        result = await self.session.execute(
            select(WorkflowTriggerDefinition)
            .where(WorkflowTriggerDefinition.definition_id == workflow_id)
            .order_by(WorkflowTriggerDefinition.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_active_triggers_by_type(
        self,
        trigger_type: TriggerType,
    ) -> list[WorkflowTriggerDefinition]:
        """List active triggers by type."""
        result = await self.session.execute(
            select(WorkflowTriggerDefinition)
            .options(selectinload(WorkflowTriggerDefinition.definition))
            .where(
                WorkflowTriggerDefinition.trigger_type == trigger_type,
                WorkflowTriggerDefinition.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def update_trigger(
        self,
        trigger: WorkflowTriggerDefinition,
        **fields: Any,
    ) -> WorkflowTriggerDefinition:
        """Update trigger."""
        for key, value in fields.items():
            setattr(trigger, key, value)
        await self.session.flush()
        return trigger

    async def delete_trigger(self, trigger: WorkflowTriggerDefinition) -> None:
        """Delete trigger."""
        await self.session.delete(trigger)
        await self.session.flush()
