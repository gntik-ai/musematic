from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from platform.notifications.models import (
    AlertDeliveryOutcome,
    DeliveryMethod,
    NotificationChannelConfig,
    OutboundWebhook,
    UserAlert,
    UserAlertSettings,
    WebhookDelivery,
    WebhookDeliveryStatus,
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
        retry_cutoff = datetime.now(UTC).replace(tzinfo=None)
        result = await self.session.execute(
            select(AlertDeliveryOutcome)
            .join(UserAlert, UserAlert.id == AlertDeliveryOutcome.alert_id)
            .options(selectinload(AlertDeliveryOutcome.alert))
            .where(
                AlertDeliveryOutcome.delivery_method == DeliveryMethod.webhook,
                or_(
                    AlertDeliveryOutcome.outcome.is_(None),
                    AlertDeliveryOutcome.next_retry_at.is_(None),
                    AlertDeliveryOutcome.next_retry_at <= retry_cutoff,
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

    async def ensure_alert_delivery_outcome(
        self,
        alert_id: UUID,
        delivery_method: DeliveryMethod,
    ) -> AlertDeliveryOutcome:
        result = await self.session.execute(
            select(AlertDeliveryOutcome).where(AlertDeliveryOutcome.alert_id == alert_id)
        )
        outcome = result.scalar_one_or_none()
        if outcome is None:
            outcome = AlertDeliveryOutcome(
                alert_id=alert_id,
                delivery_method=delivery_method,
                attempt_count=1,
            )
            self.session.add(outcome)
        else:
            outcome.delivery_method = delivery_method
        await self.session.flush()
        return outcome

    async def delete_expired_alerts(self, retention_days: int) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await self.session.execute(delete(UserAlert).where(UserAlert.created_at < cutoff))
        rowcount = getattr(result, "rowcount", None)
        return int(rowcount or 0)

    async def list_enabled_channel_configs(
        self,
        user_id: UUID,
    ) -> list[NotificationChannelConfig]:
        result = await self.session.execute(
            select(NotificationChannelConfig)
            .where(
                NotificationChannelConfig.user_id == user_id,
                NotificationChannelConfig.enabled.is_(True),
                NotificationChannelConfig.verified_at.is_not(None),
            )
            .order_by(NotificationChannelConfig.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_user_channel_configs(
        self,
        user_id: UUID,
    ) -> list[NotificationChannelConfig]:
        result = await self.session.execute(
            select(NotificationChannelConfig)
            .where(NotificationChannelConfig.user_id == user_id)
            .order_by(
                NotificationChannelConfig.created_at.desc(),
                NotificationChannelConfig.id.desc(),
            )
        )
        return list(result.scalars().all())

    async def get_channel_config(
        self,
        channel_config_id: UUID,
        user_id: UUID | None = None,
    ) -> NotificationChannelConfig | None:
        query = select(NotificationChannelConfig).where(
            NotificationChannelConfig.id == channel_config_id
        )
        if user_id is not None:
            query = query.where(NotificationChannelConfig.user_id == user_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_channel_config(
        self,
        **fields: Any,
    ) -> NotificationChannelConfig:
        config = NotificationChannelConfig(**fields)
        self.session.add(config)
        await self.session.flush()
        return config

    async def update_channel_config(
        self,
        channel_config_id: UUID,
        **fields: Any,
    ) -> NotificationChannelConfig | None:
        config = await self.session.get(NotificationChannelConfig, channel_config_id)
        if config is None:
            return None
        for key, value in fields.items():
            setattr(config, key, value)
        await self.session.flush()
        return config

    async def delete_channel_config(self, channel_config_id: UUID) -> bool:
        config = await self.session.get(NotificationChannelConfig, channel_config_id)
        if config is None:
            return False
        await self.session.delete(config)
        await self.session.flush()
        return True

    async def expire_channel_verifications(self, now: datetime) -> list[NotificationChannelConfig]:
        result = await self.session.execute(
            select(NotificationChannelConfig).where(
                NotificationChannelConfig.verified_at.is_(None),
                NotificationChannelConfig.verification_expires_at < now,
                NotificationChannelConfig.enabled.is_(True),
            )
        )
        configs = list(result.scalars().all())
        for config in configs:
            config.enabled = False
            config.verification_token_hash = None
            config.verification_expires_at = None
        await self.session.flush()
        return configs

    async def get_channel_config_by_token_hash(
        self,
        token_hash: str,
    ) -> NotificationChannelConfig | None:
        result = await self.session.execute(
            select(NotificationChannelConfig).where(
                NotificationChannelConfig.verification_token_hash == token_hash
            )
        )
        return result.scalar_one_or_none()

    async def count_user_channels(
        self,
        user_id: UUID,
        channel_type: DeliveryMethod | None = None,
    ) -> int:
        query = select(func.count()).select_from(NotificationChannelConfig).where(
            NotificationChannelConfig.user_id == user_id
        )
        if channel_type is not None:
            query = query.where(NotificationChannelConfig.channel_type == channel_type)
        total = await self.session.scalar(query)
        return int(total or 0)

    async def list_outbound_webhooks(self, workspace_id: UUID) -> list[OutboundWebhook]:
        result = await self.session.execute(
            select(OutboundWebhook)
            .where(OutboundWebhook.workspace_id == workspace_id)
            .order_by(OutboundWebhook.created_at.desc(), OutboundWebhook.id.desc())
        )
        return list(result.scalars().all())

    async def list_active_outbound_webhooks(
        self,
        workspace_id: UUID,
        event_type: str,
    ) -> list[OutboundWebhook]:
        webhooks = await self.list_outbound_webhooks(workspace_id)
        return [
            webhook
            for webhook in webhooks
            if webhook.active and event_type in webhook.event_types
        ]

    async def create_outbound_webhook(self, **fields: Any) -> OutboundWebhook:
        webhook = OutboundWebhook(**fields)
        self.session.add(webhook)
        await self.session.flush()
        return webhook

    async def update_outbound_webhook(
        self,
        webhook_id: UUID,
        **fields: Any,
    ) -> OutboundWebhook | None:
        webhook = await self.session.get(OutboundWebhook, webhook_id)
        if webhook is None:
            return None
        for key, value in fields.items():
            setattr(webhook, key, value)
        await self.session.flush()
        return webhook

    async def get_outbound_webhook(self, webhook_id: UUID) -> OutboundWebhook | None:
        return await self.session.get(OutboundWebhook, webhook_id)

    async def get_webhook_delivery_by_idempotency(
        self,
        webhook_id: UUID,
        idempotency_key: UUID,
    ) -> WebhookDelivery | None:
        result = await self.session.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.webhook_id == webhook_id,
                WebhookDelivery.idempotency_key == idempotency_key,
                WebhookDelivery.replayed_from.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def count_active_webhooks(self, workspace_id: UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(OutboundWebhook)
            .where(
                OutboundWebhook.workspace_id == workspace_id,
                OutboundWebhook.active.is_(True),
            )
        )
        return int(total or 0)

    async def insert_delivery(self, **fields: Any) -> WebhookDelivery:
        delivery = WebhookDelivery(**fields)
        self.session.add(delivery)
        await self.session.flush()
        return delivery

    async def list_due_deliveries(
        self,
        now: datetime,
        limit: int,
    ) -> list[WebhookDelivery]:
        result = await self.session.execute(
            select(WebhookDelivery)
            .options(selectinload(WebhookDelivery.webhook))
            .where(
                WebhookDelivery.status.in_(
                    [WebhookDeliveryStatus.pending.value, WebhookDeliveryStatus.failed.value]
                ),
                or_(
                    WebhookDelivery.next_attempt_at.is_(None),
                    WebhookDelivery.next_attempt_at <= now,
                ),
            )
            .order_by(WebhookDelivery.next_attempt_at.asc().nullsfirst(), WebhookDelivery.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_delivery_status(
        self,
        delivery_id: UUID,
        **fields: Any,
    ) -> WebhookDelivery | None:
        delivery = await self.session.get(WebhookDelivery, delivery_id)
        if delivery is None:
            return None
        for key, value in fields.items():
            setattr(delivery, key, value)
        await self.session.flush()
        return delivery

    async def get_delivery(
        self,
        delivery_id: UUID,
        *,
        include_webhook: bool = False,
    ) -> WebhookDelivery | None:
        if not include_webhook:
            return await self.session.get(WebhookDelivery, delivery_id)
        result = await self.session.execute(
            select(WebhookDelivery)
            .options(selectinload(WebhookDelivery.webhook))
            .where(WebhookDelivery.id == delivery_id)
        )
        return result.scalar_one_or_none()

    async def list_dead_letters(
        self,
        workspace_id: UUID,
        filters: Mapping[str, Any] | None = None,
    ) -> list[WebhookDelivery]:
        filters = filters or {}
        query = (
            select(WebhookDelivery)
            .join(OutboundWebhook, OutboundWebhook.id == WebhookDelivery.webhook_id)
            .options(selectinload(WebhookDelivery.webhook))
            .where(
                OutboundWebhook.workspace_id == workspace_id,
                WebhookDelivery.status == WebhookDeliveryStatus.dead_letter.value,
                WebhookDelivery.resolved_at.is_(None),
            )
        )
        webhook_id = filters.get("webhook_id")
        if webhook_id is not None:
            query = query.where(WebhookDelivery.webhook_id == webhook_id)
        failure_reason = filters.get("failure_reason")
        if failure_reason is not None:
            query = query.where(WebhookDelivery.failure_reason == failure_reason)
        since = filters.get("since")
        if since is not None:
            query = query.where(WebhookDelivery.dead_lettered_at >= since)
        until = filters.get("until")
        if until is not None:
            query = query.where(WebhookDelivery.dead_lettered_at <= until)
        limit = int(filters.get("limit", 100))
        result = await self.session.execute(
            query.order_by(
                WebhookDelivery.dead_lettered_at.desc().nullslast(),
                WebhookDelivery.id.desc(),
            ).limit(limit)
        )
        return list(result.scalars().all())

    async def replay_dead_letter(
        self,
        original: WebhookDelivery,
        *,
        actor_id: UUID,
        now: datetime,
    ) -> WebhookDelivery:
        replay = WebhookDelivery(
            webhook_id=original.webhook_id,
            idempotency_key=original.idempotency_key,
            event_id=original.event_id,
            event_type=original.event_type,
            payload=original.payload,
            status=WebhookDeliveryStatus.pending.value,
            attempts=0,
            next_attempt_at=now,
            replayed_from=original.id,
            replayed_by=actor_id,
        )
        self.session.add(replay)
        await self.session.flush()
        return replay

    async def aggregate_dead_letter_depth_by_workspace(self) -> dict[UUID, int]:
        result = await self.session.execute(
            select(OutboundWebhook.workspace_id, func.count(WebhookDelivery.id))
            .join(WebhookDelivery, WebhookDelivery.webhook_id == OutboundWebhook.id)
            .where(
                WebhookDelivery.status == WebhookDeliveryStatus.dead_letter.value,
                WebhookDelivery.resolved_at.is_(None),
            )
            .group_by(OutboundWebhook.workspace_id)
        )
        return {workspace_id: int(count) for workspace_id, count in result.all()}

    async def delete_dead_letter_older_than(self, cutoff: datetime) -> int:
        result = await self.session.execute(
            delete(WebhookDelivery).where(
                WebhookDelivery.status == WebhookDeliveryStatus.dead_letter.value,
                WebhookDelivery.dead_lettered_at < cutoff,
            )
        )
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
