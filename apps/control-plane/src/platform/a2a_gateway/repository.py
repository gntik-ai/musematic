from __future__ import annotations

from datetime import UTC, datetime
from platform.a2a_gateway.models import (
    A2AAuditRecord,
    A2AExternalEndpoint,
    A2ATask,
    A2ATaskState,
)
from platform.policies.models import PolicyBlockedActionRecord
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_UNSET = object()


class A2AGatewayRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_task(self, task: A2ATask) -> A2ATask:
        self.session.add(task)
        await self.session.flush()
        return task

    async def get_task_by_task_id(self, task_id: str) -> A2ATask | None:
        result = await self.session.execute(select(A2ATask).where(A2ATask.task_id == task_id))
        return result.scalar_one_or_none()

    async def get_task_by_id(self, task_db_id: UUID) -> A2ATask | None:
        result = await self.session.execute(select(A2ATask).where(A2ATask.id == task_db_id))
        return result.scalar_one_or_none()

    async def update_task_state(
        self,
        task: A2ATask,
        *,
        a2a_state: A2ATaskState | None = None,
        result_payload: dict[str, Any] | None | object = _UNSET,
        error_code: str | None | object = _UNSET,
        error_message: str | None | object = _UNSET,
        last_event_id: str | None | object = _UNSET,
        idle_timeout_at: datetime | None | object = _UNSET,
        cancellation_requested_at: datetime | None | object = _UNSET,
    ) -> A2ATask:
        if a2a_state is not None:
            task.a2a_state = a2a_state
        if result_payload is not _UNSET:
            task.result_payload = result_payload if isinstance(result_payload, dict) else None
        if error_code is not _UNSET:
            if isinstance(error_code, str) or error_code is None:
                task.error_code = error_code
        if error_message is not _UNSET:
            if isinstance(error_message, str) or error_message is None:
                task.error_message = error_message
        if last_event_id is not _UNSET:
            if isinstance(last_event_id, str) or last_event_id is None:
                task.last_event_id = last_event_id
        if idle_timeout_at is not _UNSET:
            if isinstance(idle_timeout_at, datetime) or idle_timeout_at is None:
                task.idle_timeout_at = idle_timeout_at
        if cancellation_requested_at is not _UNSET:
            if isinstance(cancellation_requested_at, datetime) or cancellation_requested_at is None:
                task.cancellation_requested_at = cancellation_requested_at
        task.updated_at = datetime.now(UTC)
        await self.session.flush()
        return task

    async def create_external_endpoint(
        self,
        endpoint: A2AExternalEndpoint,
    ) -> A2AExternalEndpoint:
        self.session.add(endpoint)
        await self.session.flush()
        return endpoint

    async def get_external_endpoint(
        self,
        endpoint_id: UUID,
        *,
        workspace_id: UUID | None = None,
        include_deleted: bool = False,
    ) -> A2AExternalEndpoint | None:
        filters = [A2AExternalEndpoint.id == endpoint_id]
        if workspace_id is not None:
            filters.append(A2AExternalEndpoint.workspace_id == workspace_id)
        if not include_deleted:
            filters.append(A2AExternalEndpoint.status != "deleted")
        result = await self.session.execute(select(A2AExternalEndpoint).where(*filters))
        return result.scalar_one_or_none()

    async def list_external_endpoints(
        self,
        workspace_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> list[A2AExternalEndpoint]:
        filters = [A2AExternalEndpoint.workspace_id == workspace_id]
        if not include_deleted:
            filters.append(A2AExternalEndpoint.status != "deleted")
        result = await self.session.execute(
            select(A2AExternalEndpoint)
            .where(*filters)
            .order_by(A2AExternalEndpoint.created_at.asc(), A2AExternalEndpoint.id.asc())
        )
        return list(result.scalars().all())

    async def update_external_endpoint_cache(
        self,
        endpoint: A2AExternalEndpoint,
        *,
        cached_agent_card: dict[str, Any] | None | object = _UNSET,
        card_cached_at: datetime | None | object = _UNSET,
        card_is_stale: bool | object = _UNSET,
        declared_version: str | None | object = _UNSET,
        status: str | object = _UNSET,
    ) -> A2AExternalEndpoint:
        if cached_agent_card is not _UNSET:
            endpoint.cached_agent_card = (
                cached_agent_card if isinstance(cached_agent_card, dict) else None
            )
        if card_cached_at is not _UNSET:
            if isinstance(card_cached_at, datetime) or card_cached_at is None:
                endpoint.card_cached_at = card_cached_at
        if card_is_stale is not _UNSET:
            endpoint.card_is_stale = bool(card_is_stale)
        if declared_version is not _UNSET:
            if isinstance(declared_version, str) or declared_version is None:
                endpoint.declared_version = declared_version
        if status is not _UNSET:
            endpoint.status = str(status)
        endpoint.updated_at = datetime.now(UTC)
        await self.session.flush()
        return endpoint

    async def delete_external_endpoint(
        self,
        endpoint: A2AExternalEndpoint,
    ) -> A2AExternalEndpoint:
        endpoint.status = "deleted"
        endpoint.updated_at = datetime.now(UTC)
        await self.session.flush()
        return endpoint

    async def create_audit_record(self, record: A2AAuditRecord) -> A2AAuditRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_task_events(self, task_db_id: UUID) -> list[A2AAuditRecord]:
        result = await self.session.execute(
            select(A2AAuditRecord)
            .where(A2AAuditRecord.task_id == task_db_id)
            .order_by(A2AAuditRecord.occurred_at.asc(), A2AAuditRecord.id.asc())
        )
        return list(result.scalars().all())

    async def list_tasks_idle_expired(
        self,
        now: datetime | None = None,
    ) -> list[A2ATask]:
        reference = now or datetime.now(UTC)
        result = await self.session.execute(
            select(A2ATask).where(
                A2ATask.a2a_state == A2ATaskState.input_required,
                A2ATask.idle_timeout_at.is_not(None),
                A2ATask.idle_timeout_at < reference,
            )
        )
        return list(result.scalars().all())

    async def create_policy_blocked_record(
        self,
        record: PolicyBlockedActionRecord,
    ) -> PolicyBlockedActionRecord:
        self.session.add(record)
        await self.session.flush()
        return record
