"""Status page repository for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.incident_response.models import Incident
from platform.multi_region_ops.models import MaintenanceWindow
from platform.status_page.models import (
    PlatformStatusSnapshot,
    StatusSubscription,
    SubscriptionDispatch,
)
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession


class StatusPageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_current_snapshot(self) -> PlatformStatusSnapshot | None:
        result = await self.session.execute(
            select(PlatformStatusSnapshot)
            .order_by(desc(PlatformStatusSnapshot.generated_at), desc(PlatformStatusSnapshot.id))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def insert_snapshot(
        self,
        *,
        generated_at: datetime,
        overall_state: str,
        payload: dict[str, Any],
        source_kind: str,
        created_by: UUID | None = None,
    ) -> PlatformStatusSnapshot:
        snapshot = PlatformStatusSnapshot(
            generated_at=generated_at,
            overall_state=overall_state,
            payload=payload,
            source_kind=source_kind,
            created_by=created_by,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def list_components(self) -> list[dict[str, Any]]:
        snapshot = await self.get_current_snapshot()
        if snapshot is None:
            return []
        components = snapshot.payload.get("components", [])
        return list(components) if isinstance(components, list) else []

    async def get_component_history(
        self,
        component_id: str,
        *,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        since = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            select(PlatformStatusSnapshot)
            .where(PlatformStatusSnapshot.generated_at >= since)
            .order_by(PlatformStatusSnapshot.generated_at.asc())
        )
        history: list[dict[str, Any]] = []
        for snapshot in result.scalars().all():
            components = snapshot.payload.get("components", [])
            if not isinstance(components, list):
                continue
            match = next(
                (
                    component
                    for component in components
                    if isinstance(component, dict) and component.get("id") == component_id
                ),
                None,
            )
            if match is None:
                continue
            history.append(
                {
                    "at": snapshot.generated_at,
                    "state": str(match.get("state", "operational")),
                }
            )
        return history

    async def list_active_incidents(self) -> list[Incident]:
        result = await self.session.execute(
            select(Incident)
            .where(Incident.status.in_(("open", "acknowledged")))
            .order_by(desc(Incident.triggered_at), desc(Incident.id))
        )
        return list(result.scalars().all())

    async def list_recent_resolved_incidents(self, *, days: int = 7) -> list[Incident]:
        since = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            select(Incident)
            .where(
                Incident.status.in_(("resolved", "auto_resolved")),
                Incident.resolved_at.is_not(None),
                Incident.resolved_at >= since,
            )
            .order_by(desc(Incident.resolved_at), desc(Incident.id))
        )
        return list(result.scalars().all())

    async def list_active_maintenance(self) -> list[MaintenanceWindow]:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(MaintenanceWindow)
            .where(
                MaintenanceWindow.status == "active",
                MaintenanceWindow.starts_at <= now,
                MaintenanceWindow.ends_at >= now,
            )
            .order_by(MaintenanceWindow.starts_at.asc(), MaintenanceWindow.id.asc())
        )
        return list(result.scalars().all())

    async def list_scheduled_maintenance(self, *, days: int = 30) -> list[MaintenanceWindow]:
        now = datetime.now(UTC)
        until = now + timedelta(days=days)
        result = await self.session.execute(
            select(MaintenanceWindow)
            .where(
                MaintenanceWindow.status.in_(("scheduled", "active")),
                MaintenanceWindow.ends_at >= now,
                MaintenanceWindow.starts_at <= until,
            )
            .order_by(MaintenanceWindow.starts_at.asc(), MaintenanceWindow.id.asc())
        )
        return list(result.scalars().all())

    async def get_uptime_30d(self) -> dict[str, Any]:
        snapshot = await self.get_current_snapshot()
        if snapshot is None:
            return {}
        uptime = snapshot.payload.get("uptime_30d", {})
        return dict(uptime) if isinstance(uptime, dict) else {}

    async def list_confirmed_subscriptions_for_event(
        self,
        *,
        affected_components: list[str],
    ) -> list[StatusSubscription]:
        statement = select(StatusSubscription).where(
            StatusSubscription.confirmed_at.is_not(None),
            StatusSubscription.health == "healthy",
        )
        result = await self.session.execute(statement)
        subscriptions = list(result.scalars().all())
        if not affected_components:
            return subscriptions
        affected = set(affected_components)
        return [
            subscription
            for subscription in subscriptions
            if (
                not subscription.scope_components
                or affected.intersection(subscription.scope_components)
            )
        ]

    async def create_subscription(
        self,
        *,
        channel: str,
        target: str,
        scope_components: list[str],
        confirmation_token_hash: bytes | None = None,
        unsubscribe_token_hash: bytes | None = None,
        confirmed_at: datetime | None = None,
        health: str = "pending",
        workspace_id: UUID | None = None,
        user_id: UUID | None = None,
        webhook_id: UUID | None = None,
    ) -> StatusSubscription:
        subscription = StatusSubscription(
            channel=channel,
            target=target,
            scope_components=scope_components,
            confirmation_token_hash=confirmation_token_hash,
            unsubscribe_token_hash=unsubscribe_token_hash,
            confirmed_at=confirmed_at,
            health=health,
            workspace_id=workspace_id,
            user_id=user_id,
            webhook_id=webhook_id,
        )
        self.session.add(subscription)
        await self.session.flush()
        return subscription

    async def get_subscription_by_confirmation_hash(
        self,
        token_hash: bytes,
    ) -> StatusSubscription | None:
        result = await self.session.execute(
            select(StatusSubscription).where(
                StatusSubscription.confirmation_token_hash == token_hash,
                StatusSubscription.health == "pending",
            )
        )
        return result.scalar_one_or_none()

    async def get_subscription_by_unsubscribe_hash(
        self,
        token_hash: bytes,
    ) -> StatusSubscription | None:
        result = await self.session.execute(
            select(StatusSubscription).where(
                StatusSubscription.unsubscribe_token_hash == token_hash,
                StatusSubscription.health != "unsubscribed",
            )
        )
        return result.scalar_one_or_none()

    async def get_subscription(self, subscription_id: UUID) -> StatusSubscription | None:
        result = await self.session.execute(
            select(StatusSubscription).where(StatusSubscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def confirm_subscription(self, subscription: StatusSubscription) -> StatusSubscription:
        subscription.confirmed_at = datetime.now(UTC)
        subscription.health = "healthy"
        subscription.confirmation_token_hash = None
        await self.session.flush()
        return subscription

    async def mark_unsubscribed(self, subscription: StatusSubscription) -> StatusSubscription:
        subscription.health = "unsubscribed"
        await self.session.flush()
        return subscription

    async def rotate_unsubscribe_token(
        self,
        subscription: StatusSubscription,
        token_hash: bytes,
    ) -> StatusSubscription:
        subscription.unsubscribe_token_hash = token_hash
        await self.session.flush()
        return subscription

    async def list_user_subscriptions(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID | None = None,
    ) -> list[StatusSubscription]:
        statement = select(StatusSubscription).where(StatusSubscription.user_id == user_id)
        if workspace_id is not None:
            statement = statement.where(StatusSubscription.workspace_id == workspace_id)
        statement = statement.order_by(
            desc(StatusSubscription.created_at),
            desc(StatusSubscription.id),
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_user_subscription(
        self,
        *,
        subscription_id: UUID,
        user_id: UUID,
    ) -> StatusSubscription | None:
        result = await self.session.execute(
            select(StatusSubscription).where(
                StatusSubscription.id == subscription_id,
                StatusSubscription.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_user_subscription(
        self,
        *,
        subscription_id: UUID,
        user_id: UUID,
        values: dict[str, Any],
    ) -> StatusSubscription | None:
        if not values:
            return await self.get_user_subscription(
                subscription_id=subscription_id,
                user_id=user_id,
            )
        await self.session.execute(
            update(StatusSubscription)
            .where(
                StatusSubscription.id == subscription_id,
                StatusSubscription.user_id == user_id,
            )
            .values(**values)
        )
        await self.session.flush()
        return await self.get_user_subscription(subscription_id=subscription_id, user_id=user_id)

    async def insert_dispatch(
        self,
        *,
        subscription_id: UUID,
        event_kind: str,
        event_id: UUID,
        outcome: str,
        webhook_signature_kid: str | None = None,
        error_summary: str | None = None,
    ) -> SubscriptionDispatch:
        dispatch = SubscriptionDispatch(
            subscription_id=subscription_id,
            event_kind=event_kind,
            event_id=event_id,
            outcome=outcome,
            webhook_signature_kid=webhook_signature_kid,
            error_summary=error_summary,
            dispatched_at=datetime.now(UTC),
        )
        self.session.add(dispatch)
        await self.session.flush()
        return dispatch
