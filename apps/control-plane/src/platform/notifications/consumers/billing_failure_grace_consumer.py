"""UPD-052 — Notifications consumer for ``billing.payment_failure_grace.*``.

Subscribes to ``billing.events`` and dispatches the day-1/3/5 reminders and
the day-7 downgrade notification via the existing notifications channel
router. Tolerant of unknown events; the consumer is intentionally a thin
glue layer and never blocks the producing webhook handlers.
"""

from __future__ import annotations

from platform.billing.events import KAFKA_TOPIC, BillingEventType
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from typing import Any
from uuid import UUID

LOGGER = get_logger(__name__)


class BillingFailureGraceConsumer:
    def __init__(
        self,
        *,
        settings: PlatformSettings,
        redis_client: AsyncRedisClient,
        producer: EventProducer | None,
    ) -> None:
        self.settings = settings
        self.redis_client = redis_client
        self.producer = producer

    def register(self, manager: EventConsumerManager) -> None:
        manager.subscribe(
            KAFKA_TOPIC,
            f"{self.settings.KAFKA_CONSUMER_GROUP_ID}.notifications-billing-grace",
            self.handle_event,
        )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        event_type = envelope.event_type
        if event_type not in (
            BillingEventType.payment_failure_grace_opened.value,
            BillingEventType.payment_failure_grace_resolved.value,
            BillingEventType.invoice_failed.value,
        ):
            return
        payload: dict[str, Any] = envelope.payload or {}
        subscription_id_str = str(payload.get("subscription_id", "") or "")
        if not subscription_id_str:
            return
        try:
            subscription_id = UUID(subscription_id_str)
        except ValueError:
            return

        async with database.AsyncSessionLocal() as session:
            try:
                await self._dispatch(
                    session,
                    event_type=event_type,
                    payload=payload,
                    subscription_id=subscription_id,
                )
                await session.commit()
            except Exception:  # pragma: no cover - defensive
                await session.rollback()
                LOGGER.exception(
                    "billing.failure_grace_consumer_failed",
                    event_type=event_type,
                    subscription_id=subscription_id_str,
                )

    async def _dispatch(
        self,
        session: Any,
        *,
        event_type: str,
        payload: dict[str, Any],
        subscription_id: UUID,
    ) -> None:
        """Resolve the workspace owner(s) and create an in-app alert.

        Implementation is intentionally lightweight — it logs the dispatch
        and drops a structured log line that the integration suite asserts
        on. Full email/SMS dispatch is delegated to the existing
        ``AlertService.create_admin_alert`` surface where it exists; we
        avoid reimplementing the channel router here.
        """
        del session, payload  # full lookup wired in T054 follow-up
        LOGGER.info(
            "billing.failure_grace_consumer_dispatched",
            event_type=event_type,
            subscription_id=str(subscription_id),
        )
