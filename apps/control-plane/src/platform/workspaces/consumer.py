from __future__ import annotations

import logging
from platform.accounts.events import AccountsEventType, UserActivatedPayload
from platform.accounts.repository import AccountsRepository
from platform.accounts.service import AccountsService
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.common.events.producer import EventProducer
from platform.workspaces.dependencies import build_workspaces_service
from typing import Any, cast

LOGGER = logging.getLogger(__name__)


class _ConsumerAuthStub:
    pass


class WorkspacesConsumer:
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
            "accounts.events",
            f"{self.settings.KAFKA_CONSUMER_GROUP_ID}.workspaces",
            self.handle_event,
        )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        if envelope.event_type != AccountsEventType.user_activated.value:
            return

        payload = UserActivatedPayload.model_validate(envelope.payload)
        async with database.AsyncSessionLocal() as session:
            accounts_service = AccountsService(
                repo=AccountsRepository(session),
                redis=self.redis_client,
                kafka_producer=self.producer,
                auth_service=cast(Any, _ConsumerAuthStub()),
                settings=self.settings,
            )
            service = build_workspaces_service(
                session=session,
                settings=self.settings,
                producer=self.producer,
                accounts_service=accounts_service,
            )
            try:
                await service.create_default_workspace(
                    payload.user_id,
                    payload.display_name,
                    correlation_ctx=envelope.correlation_context,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception(
                    "Failed to provision default workspace for activated user",
                    extra={"user_id": str(payload.user_id)},
                )
