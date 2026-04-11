from __future__ import annotations

from datetime import UTC, datetime
from platform.connectors.models import (
    ConnectorCredentialRef,
    ConnectorInstance,
    ConnectorInstanceStatus,
    ConnectorRoute,
    ConnectorType,
    DeadLetterEntry,
    DeadLetterResolution,
    DeliveryStatus,
    OutboundDelivery,
)
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class ConnectorsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_connector_types(self) -> list[ConnectorType]:
        result = await self.session.execute(
            select(ConnectorType).order_by(ConnectorType.slug.asc())
        )
        return list(result.scalars().all())

    async def get_connector_type(self, type_slug: str) -> ConnectorType | None:
        result = await self.session.execute(
            select(ConnectorType).where(ConnectorType.slug == type_slug)
        )
        return result.scalar_one_or_none()

    async def create_connector_instance(
        self,
        *,
        workspace_id: UUID,
        connector_type_id: UUID,
        name: str,
        config: dict[str, Any],
        status: Any,
    ) -> ConnectorInstance:
        instance = ConnectorInstance(
            workspace_id=workspace_id,
            connector_type_id=connector_type_id,
            name=name,
            config_json=dict(config),
            status=status,
        )
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def get_connector_instance(
        self,
        connector_id: UUID,
        workspace_id: UUID,
    ) -> ConnectorInstance | None:
        result = await self.session.execute(
            select(ConnectorInstance)
            .options(
                selectinload(ConnectorInstance.connector_type),
                selectinload(ConnectorInstance.credential_refs),
            )
            .where(
                ConnectorInstance.id == connector_id,
                ConnectorInstance.workspace_id == workspace_id,
                ConnectorInstance.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_connector_instance_public(self, connector_id: UUID) -> ConnectorInstance | None:
        result = await self.session.execute(
            select(ConnectorInstance)
            .options(
                selectinload(ConnectorInstance.connector_type),
                selectinload(ConnectorInstance.credential_refs),
            )
            .where(
                ConnectorInstance.id == connector_id,
                ConnectorInstance.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_connector_instances(
        self,
        workspace_id: UUID,
    ) -> tuple[list[ConnectorInstance], int]:
        filters = [
            ConnectorInstance.workspace_id == workspace_id,
            ConnectorInstance.deleted_at.is_(None),
        ]
        total = await self.session.scalar(
            select(func.count()).select_from(ConnectorInstance).where(*filters)
        )
        result = await self.session.execute(
            select(ConnectorInstance)
            .options(
                selectinload(ConnectorInstance.connector_type),
                selectinload(ConnectorInstance.credential_refs),
            )
            .where(*filters)
            .order_by(ConnectorInstance.created_at.asc(), ConnectorInstance.id.asc())
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_connector_instance(
        self,
        instance: ConnectorInstance,
        *,
        name: str | None = None,
        config: dict[str, Any] | None = None,
        status: Any | None = None,
        health_status: Any | None = None,
        health_check_error: str | None = None,
        last_health_check_at: datetime | None = None,
    ) -> ConnectorInstance:
        if name is not None:
            instance.name = name
        if config is not None:
            instance.config_json = dict(config)
        if status is not None:
            instance.status = status
        if health_status is not None:
            instance.health_status = health_status
        if health_check_error is not None or health_status is not None:
            instance.health_check_error = health_check_error
        if last_health_check_at is not None:
            instance.last_health_check_at = last_health_check_at
        await self.session.flush()
        return instance

    async def soft_delete_connector_instance(
        self,
        instance: ConnectorInstance,
    ) -> ConnectorInstance:
        instance.deleted_at = datetime.now(UTC)
        await self.session.flush()
        return instance

    async def upsert_credential_refs(
        self,
        connector_instance_id: UUID,
        workspace_id: UUID,
        credential_refs: dict[str, str],
    ) -> list[ConnectorCredentialRef]:
        await self.session.execute(
            delete(ConnectorCredentialRef).where(
                ConnectorCredentialRef.connector_instance_id == connector_instance_id
            )
        )
        items: list[ConnectorCredentialRef] = []
        for key, vault_path in sorted(credential_refs.items()):
            item = ConnectorCredentialRef(
                connector_instance_id=connector_instance_id,
                workspace_id=workspace_id,
                credential_key=key,
                vault_path=vault_path,
            )
            self.session.add(item)
            items.append(item)
        await self.session.flush()
        return items

    async def list_credential_refs(
        self,
        connector_instance_id: UUID,
        workspace_id: UUID,
    ) -> list[ConnectorCredentialRef]:
        result = await self.session.execute(
            select(ConnectorCredentialRef)
            .where(
                ConnectorCredentialRef.connector_instance_id == connector_instance_id,
                ConnectorCredentialRef.workspace_id == workspace_id,
            )
            .order_by(ConnectorCredentialRef.credential_key.asc())
        )
        return list(result.scalars().all())

    async def create_route(
        self,
        *,
        workspace_id: UUID,
        connector_instance_id: UUID,
        name: str,
        channel_pattern: str | None,
        sender_pattern: str | None,
        conditions: dict[str, Any],
        target_agent_fqn: str | None,
        target_workflow_id: UUID | None,
        priority: int,
        is_enabled: bool,
    ) -> ConnectorRoute:
        route = ConnectorRoute(
            workspace_id=workspace_id,
            connector_instance_id=connector_instance_id,
            name=name,
            channel_pattern=channel_pattern,
            sender_pattern=sender_pattern,
            conditions_json=dict(conditions),
            target_agent_fqn=target_agent_fqn,
            target_workflow_id=target_workflow_id,
            priority=priority,
            is_enabled=is_enabled,
        )
        self.session.add(route)
        await self.session.flush()
        return route

    async def get_route(self, route_id: UUID, workspace_id: UUID) -> ConnectorRoute | None:
        result = await self.session.execute(
            select(ConnectorRoute).where(
                ConnectorRoute.id == route_id,
                ConnectorRoute.workspace_id == workspace_id,
                ConnectorRoute.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_routes(
        self,
        workspace_id: UUID,
        connector_instance_id: UUID,
    ) -> tuple[list[ConnectorRoute], int]:
        filters = [
            ConnectorRoute.workspace_id == workspace_id,
            ConnectorRoute.connector_instance_id == connector_instance_id,
            ConnectorRoute.deleted_at.is_(None),
        ]
        total = await self.session.scalar(
            select(func.count()).select_from(ConnectorRoute).where(*filters)
        )
        result = await self.session.execute(
            select(ConnectorRoute)
            .where(*filters)
            .order_by(ConnectorRoute.priority.asc(), ConnectorRoute.created_at.asc())
        )
        return list(result.scalars().all()), int(total or 0)

    async def get_routes_for_instance(
        self,
        connector_instance_id: UUID,
        workspace_id: UUID,
    ) -> list[ConnectorRoute]:
        result = await self.session.execute(
            select(ConnectorRoute)
            .where(
                ConnectorRoute.connector_instance_id == connector_instance_id,
                ConnectorRoute.workspace_id == workspace_id,
                ConnectorRoute.deleted_at.is_(None),
            )
            .order_by(ConnectorRoute.priority.asc(), ConnectorRoute.created_at.asc())
        )
        return list(result.scalars().all())

    async def update_route(
        self,
        route: ConnectorRoute,
        *,
        name: str | None = None,
        channel_pattern: str | None = None,
        sender_pattern: str | None = None,
        conditions: dict[str, Any] | None = None,
        target_agent_fqn: str | None = None,
        target_workflow_id: UUID | None = None,
        priority: int | None = None,
        is_enabled: bool | None = None,
    ) -> ConnectorRoute:
        if name is not None:
            route.name = name
        if channel_pattern is not None:
            route.channel_pattern = channel_pattern
        if sender_pattern is not None:
            route.sender_pattern = sender_pattern
        if conditions is not None:
            route.conditions_json = dict(conditions)
        if target_agent_fqn is not None or target_workflow_id is not None:
            route.target_agent_fqn = target_agent_fqn
            route.target_workflow_id = target_workflow_id
        if priority is not None:
            route.priority = priority
        if is_enabled is not None:
            route.is_enabled = is_enabled
        await self.session.flush()
        return route

    async def delete_route(self, route: ConnectorRoute) -> ConnectorRoute:
        route.deleted_at = datetime.now(UTC)
        await self.session.flush()
        return route

    async def create_outbound_delivery(
        self,
        *,
        workspace_id: UUID,
        connector_instance_id: UUID,
        destination: str,
        content: dict[str, Any],
        priority: int,
        max_attempts: int,
        source_interaction_id: UUID | None,
        source_execution_id: UUID | None,
    ) -> OutboundDelivery:
        delivery = OutboundDelivery(
            workspace_id=workspace_id,
            connector_instance_id=connector_instance_id,
            destination=destination,
            content_json=dict(content),
            priority=priority,
            max_attempts=max_attempts,
            source_interaction_id=source_interaction_id,
            source_execution_id=source_execution_id,
        )
        self.session.add(delivery)
        await self.session.flush()
        return delivery

    async def get_outbound_delivery(
        self,
        delivery_id: UUID,
        workspace_id: UUID | None = None,
    ) -> OutboundDelivery | None:
        filters = [OutboundDelivery.id == delivery_id]
        if workspace_id is not None:
            filters.append(OutboundDelivery.workspace_id == workspace_id)
        result = await self.session.execute(
            select(OutboundDelivery)
            .options(selectinload(OutboundDelivery.dead_letter_entry))
            .where(*filters)
        )
        return result.scalar_one_or_none()

    async def list_outbound_deliveries(
        self,
        workspace_id: UUID,
        connector_instance_id: UUID | None = None,
    ) -> tuple[list[OutboundDelivery], int]:
        filters = [OutboundDelivery.workspace_id == workspace_id]
        if connector_instance_id is not None:
            filters.append(OutboundDelivery.connector_instance_id == connector_instance_id)
        total = await self.session.scalar(
            select(func.count()).select_from(OutboundDelivery).where(*filters)
        )
        result = await self.session.execute(
            select(OutboundDelivery)
            .where(*filters)
            .order_by(OutboundDelivery.created_at.desc(), OutboundDelivery.id.desc())
        )
        return list(result.scalars().all()), int(total or 0)

    async def update_delivery_status(
        self,
        delivery: OutboundDelivery,
        *,
        status: DeliveryStatus,
        attempt_count: int | None = None,
        next_retry_at: datetime | None = None,
        delivered_at: datetime | None = None,
    ) -> OutboundDelivery:
        delivery.status = status
        if attempt_count is not None:
            delivery.attempt_count = attempt_count
        delivery.next_retry_at = next_retry_at
        delivery.delivered_at = delivered_at
        await self.session.flush()
        return delivery

    async def append_error_history(
        self,
        delivery: OutboundDelivery,
        error_record: dict[str, Any],
    ) -> OutboundDelivery:
        delivery.error_history = [*delivery.error_history, dict(error_record)]
        await self.session.flush()
        return delivery

    async def get_pending_retries(self, *, limit: int) -> list[OutboundDelivery]:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(OutboundDelivery)
            .where(
                OutboundDelivery.status == DeliveryStatus.failed,
                OutboundDelivery.next_retry_at.is_not(None),
                OutboundDelivery.next_retry_at <= now,
            )
            .order_by(OutboundDelivery.next_retry_at.asc(), OutboundDelivery.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_dead_letter_entry(
        self,
        *,
        workspace_id: UUID,
        outbound_delivery_id: UUID,
        connector_instance_id: UUID,
        dead_lettered_at: datetime,
    ) -> DeadLetterEntry:
        entry = DeadLetterEntry(
            workspace_id=workspace_id,
            outbound_delivery_id=outbound_delivery_id,
            connector_instance_id=connector_instance_id,
            dead_lettered_at=dead_lettered_at,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def increment_connector_metrics(
        self,
        connector_instance_id: UUID,
        *,
        sent_delta: int = 0,
        failed_delta: int = 0,
        retried_delta: int = 0,
        dead_lettered_delta: int = 0,
    ) -> None:
        await self.session.execute(
            update(ConnectorInstance)
            .where(ConnectorInstance.id == connector_instance_id)
            .values(
                messages_sent=ConnectorInstance.messages_sent + sent_delta,
                messages_failed=ConnectorInstance.messages_failed + failed_delta,
                messages_retried=ConnectorInstance.messages_retried + retried_delta,
                messages_dead_lettered=ConnectorInstance.messages_dead_lettered
                + dead_lettered_delta,
            )
        )
        await self.session.flush()

    async def list_dead_letter_entries(
        self,
        workspace_id: UUID,
        *,
        connector_instance_id: UUID | None = None,
        resolution_status: DeadLetterResolution | None = None,
    ) -> tuple[list[DeadLetterEntry], int]:
        filters = [DeadLetterEntry.workspace_id == workspace_id]
        if connector_instance_id is not None:
            filters.append(DeadLetterEntry.connector_instance_id == connector_instance_id)
        if resolution_status is not None:
            filters.append(DeadLetterEntry.resolution_status == resolution_status)
        total = await self.session.scalar(
            select(func.count()).select_from(DeadLetterEntry).where(*filters)
        )
        result = await self.session.execute(
            select(DeadLetterEntry)
            .options(selectinload(DeadLetterEntry.outbound_delivery))
            .where(*filters)
            .order_by(DeadLetterEntry.dead_lettered_at.desc(), DeadLetterEntry.id.desc())
        )
        return list(result.scalars().all()), int(total or 0)

    async def get_dead_letter_entry(
        self,
        entry_id: UUID,
        workspace_id: UUID,
    ) -> DeadLetterEntry | None:
        result = await self.session.execute(
            select(DeadLetterEntry)
            .options(selectinload(DeadLetterEntry.outbound_delivery))
            .where(
                DeadLetterEntry.id == entry_id,
                DeadLetterEntry.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_dead_letter_resolution(
        self,
        entry: DeadLetterEntry,
        *,
        resolution_status: DeadLetterResolution,
        resolved_at: datetime,
        resolution_note: str | None,
        archive_path: str | None = None,
    ) -> DeadLetterEntry:
        entry.resolution_status = resolution_status
        entry.resolved_at = resolved_at
        entry.resolution_note = resolution_note
        entry.archive_path = archive_path
        await self.session.flush()
        return entry

    async def list_enabled_connector_instances_by_type(
        self,
        type_slug: str,
    ) -> list[ConnectorInstance]:
        result = await self.session.execute(
            select(ConnectorInstance)
            .join(ConnectorType, ConnectorType.id == ConnectorInstance.connector_type_id)
            .options(
                selectinload(ConnectorInstance.connector_type),
                selectinload(ConnectorInstance.credential_refs),
            )
            .where(
                ConnectorType.slug == type_slug,
                ConnectorInstance.status == ConnectorInstanceStatus.enabled,
                ConnectorInstance.deleted_at.is_(None),
            )
            .order_by(ConnectorInstance.created_at.asc())
        )
        return list(result.scalars().all())
