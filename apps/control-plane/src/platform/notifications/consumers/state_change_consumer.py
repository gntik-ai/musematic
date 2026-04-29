from __future__ import annotations

from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from platform.interactions.events import InteractionsEventType, InteractionStateChangedPayload
from platform.notifications.dependencies import build_notifications_service
from platform.workspaces.dependencies import build_workspaces_service
from uuid import UUID

LOGGER = get_logger(__name__)

_ALLOWED_STATES = {
    "initializing",
    "ready",
    "running",
    "waiting",
    "paused",
    "completed",
    "failed",
    "canceled",
}


class StateChangeConsumer:
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
            "interaction.events",
            f"{self.settings.KAFKA_CONSUMER_GROUP_ID}.notifications-state-change",
            self.handle_event,
        )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        if envelope.event_type != InteractionsEventType.state_changed.value:
            return
        payload = InteractionStateChangedPayload.model_validate(envelope.payload)
        if payload.from_state not in _ALLOWED_STATES or payload.to_state not in _ALLOWED_STATES:
            LOGGER.warning(
                "Skipping interaction.state_changed with unrecognized states",
                extra={"from_state": payload.from_state, "to_state": payload.to_state},
            )
            return
        workspace_id = payload.workspace_id
        async with database.AsyncSessionLocal() as session:
            workspaces_service = build_workspaces_service(
                session=session,
                settings=self.settings,
                producer=self.producer,
                accounts_service=None,
            )
            service = build_notifications_service(
                session=session,
                settings=self.settings,
                redis_client=self.redis_client,
                producer=self.producer,
                workspaces_service=workspaces_service,
            )
            try:
                await service.process_state_change(payload, UUID(str(workspace_id)))
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Failed to process interaction.state_changed event")
