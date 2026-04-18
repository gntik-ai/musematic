from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from platform.notifications.models import (
    AlertDeliveryOutcome,
    DeliveryMethod,
    UserAlert,
    UserAlertSettings,
)
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class NotificationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_settings(self, user_id: UUID) -> UserAlertSettings | None:
        result = await self.session.execute(
            select(UserAlertSettings).where(UserAlertSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert_settings(
        self,
        user_id: UUID,
        data: dict[str, Any],
    ) -> UserAlertSettings:
        settings = await self.get_settings(user_id)
        if settings is None:
            settings = UserAlertSettings(user_id=user_id, **data)
            self.session.add(settings)
        else:
            for key, value in data.items():
                setattr(settings, key, value)
        await self.session.flush()
        return settings

    async def create_alert(
        self,
        *,
        user_id: UUID,
        interaction_id: UUID | None,
        source_reference: dict[str, Any] | None,
        alert_type: str,
        title: str,
        body: str | None,
        urgency: str,
        delivery_method: DeliveryMethod | None = None,
    ) -> UserAlert:
        alert = UserAlert(
            user_id=user_id,
            interaction_id=interaction_id,
            source_reference=source_reference,
            alert_type=alert_type,
            title=title,
            body=body,
            urgency=urgency,
            read=False,
        )
        self.session.add(alert)
        await self.session.flush()
        if delivery_method is not None and delivery_method != DeliveryMethod.in_app:
            outcome = AlertDeliveryOutcome(
                alert_id=alert.id,
                delivery_method=delivery_method,
                attempt_count=1,
            )
            self.session.add(outcome)
            await self.session.flush()
            alert.delivery_outcome = outcome
        return alert

    async def list_alerts(
        self,
        user_id: UUID,
        read_filter: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[UserAlert], str | None, int]:
        unread_total = await self.get_unread_count(user_id)
        query = (
            select(UserAlert)
            .where(UserAlert.user_id == user_id)
            .order_by(UserAlert.created_at.desc(), UserAlert.id.desc())
            .options(selectinload(UserAlert.delivery_outcome))
        )
        if read_filter == "read":
            query = query.where(UserAlert.read.is_(True))
        elif read_filter == "unread":
            query = query.where(UserAlert.read.is_(False))
        query = _apply_cursor(query, cursor).limit(limit + 1)
        items = list((await self.session.execute(query)).scalars().all())
        page, next_cursor = _items_with_cursor(items, limit)
        return page, next_cursor, unread_total

    async def get_alert(self, alert_id: UUID, user_id: UUID) -> UserAlert | None:
        result = await self.session.execute(
            select(UserAlert)
            .options(selectinload(UserAlert.delivery_outcome))
            .where(
                UserAlert.id == alert_id,
                UserAlert.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_alert_by_id(self, alert_id: UUID) -> UserAlert | None:
        result = await self.session.execute(
            select(UserAlert)
            .options(selectinload(UserAlert.delivery_outcome))
            .where(UserAlert.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def mark_read(self, alert_id: UUID, user_id: UUID) -> UserAlert | None:
        alert = await self.get_alert(alert_id, user_id)
        if alert is None:
            return None
        if not alert.read:
            alert.read = True
            await self.session.flush()
        return alert

    async def get_unread_count(self, user_id: UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(UserAlert)
            .where(
                UserAlert.user_id == user_id,
                UserAlert.read.is_(False),
            )
        )
        return int(total or 0)

    async def get_pending_webhook_deliveries(self) -> list[AlertDeliveryOutcome]:
        result = await self.session.execute(
            select(AlertDeliveryOutcome)
            .join(UserAlert, UserAlert.id == AlertDeliveryOutcome.alert_id)
            .options(selectinload(AlertDeliveryOutcome.alert))
            .where(
                AlertDeliveryOutcome.delivery_method == DeliveryMethod.webhook,
                or_(
                    AlertDeliveryOutcome.outcome.is_(None),
                    AlertDeliveryOutcome.next_retry_at.is_(None),
                    AlertDeliveryOutcome.next_retry_at <= datetime.now(UTC),
                ),
            )
            .order_by(AlertDeliveryOutcome.created_at.asc())
        )
        return list(result.scalars().all())

    async def update_delivery_outcome(
        self,
        outcome_id: UUID,
        **fields: Any,
    ) -> AlertDeliveryOutcome | None:
        outcome = await self.session.get(AlertDeliveryOutcome, outcome_id)
        if outcome is None:
            return None
        for key, value in fields.items():
            setattr(outcome, key, value)
        await self.session.flush()
        return outcome

    async def delete_expired_alerts(self, retention_days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await self.session.execute(delete(UserAlert).where(UserAlert.created_at < cutoff))
        rowcount = getattr(result, "rowcount", None)
        return int(rowcount or 0)


def _apply_cursor(query: Any, cursor: str | None) -> Any:
    if not cursor:
        return query
    created_at, item_id = _decode_cursor(cursor)
    return query.where(
        or_(
            UserAlert.created_at < created_at,
            (UserAlert.created_at == created_at) & (UserAlert.id < item_id),
        )
    )


def _items_with_cursor(
    items: Sequence[UserAlert],
    limit: int,
) -> tuple[list[UserAlert], str | None]:
    page = list(items[:limit])
    next_cursor = None
    if len(items) > limit and page:
        next_cursor = _encode_cursor(page[-1].created_at, page[-1].id)
    return page, next_cursor


def _encode_cursor(created_at: datetime, item_id: UUID) -> str:
    payload = json.dumps({"created_at": created_at.isoformat(), "id": str(item_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    return datetime.fromisoformat(payload["created_at"]), UUID(payload["id"])
