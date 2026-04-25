from __future__ import annotations

import logging
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.common.events.producer import EventProducer
from platform.interactions.events import AttentionRequestedPayload, InteractionsEventType
from platform.notifications.dependencies import build_notifications_service

LOGGER = logging.getLogger(__name__)


class AttentionConsumer:
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
            "interaction.attention",
            f"{self.settings.KAFKA_CONSUMER_GROUP_ID}.notifications-attention",
            self.handle_event,
        )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        if envelope.event_type != InteractionsEventType.attention_requested.value:
            return
        payload = AttentionRequestedPayload.model_validate(envelope.payload)
        if payload.alert_already_created:
            return
        async with database.AsyncSessionLocal() as session:
            service = build_notifications_service(
                session=session,
                settings=self.settings,
                redis_client=self.redis_client,
                producer=self.producer,
                workspaces_service=None,
            )
            try:
                await service.process_attention_request(payload)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Failed to process interaction attention event")
