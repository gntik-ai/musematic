"""Marketplace Kafka consumer for fan-out notifications (UPD-049 FR-027).

Subscribes to ``marketplace.events`` and reacts to
``marketplace.source_updated`` by finding all forks of the source agent
(via the ``forked_from_agent_id`` self-FK on ``registry_agent_profiles``)
and delivering a notification to each fork's owner.

Reads cross-tenant via the platform-staff (BYPASSRLS) session because the
fan-out spans tenants — fork rows can live anywhere a consumer has
write access, including Enterprise tenants.

Gated by ``MARKETPLACE_FORK_NOTIFY_SOURCE_OWNERS`` (default ``True``).
"""

from __future__ import annotations

from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.common.logging import get_logger
from platform.marketplace.notifications import MarketplaceNotificationService
from platform.notifications.dependencies import build_notifications_service
from platform.registry.events import (
    MarketplaceEventType,
    MarketplaceSourceUpdatedPayload,
)
from typing import Any
from uuid import UUID

from sqlalchemy import text

LOGGER = get_logger(__name__)


class MarketplaceFanoutConsumer:
    """Cross-tenant fan-out for ``marketplace.source_updated`` events."""

    def __init__(
        self,
        *,
        settings: PlatformSettings,
        redis_client: AsyncRedisClient,
    ) -> None:
        self.settings = settings
        self.redis_client = redis_client

    def register(self, manager: EventConsumerManager) -> None:
        manager.subscribe(
            "marketplace.events",
            f"{self.settings.KAFKA_CONSUMER_GROUP_ID}.marketplace-fanout",
            self.handle_event,
        )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        if envelope.event_type != MarketplaceEventType.source_updated.value:
            return
        if not self.settings.MARKETPLACE_FORK_NOTIFY_SOURCE_OWNERS:
            LOGGER.debug(
                "marketplace fork-owner notifications disabled by setting; "
                "skipping source_updated fan-out",
                extra={"source_agent_id": envelope.payload.get("source_agent_id")},
            )
            return
        payload = MarketplaceSourceUpdatedPayload.model_validate(envelope.payload)
        source_id = UUID(payload.source_agent_id)
        async with database.PlatformStaffAsyncSessionLocal() as session:
            forks = await self._find_forks(session, source_id)
            if not forks:
                return
            source_fqn = await self._lookup_source_fqn(session, source_id)
            alert_service = build_notifications_service(
                session=session,
                settings=self.settings,
                redis_client=self.redis_client,
                producer=None,
                workspaces_service=None,
            )
            notifier = MarketplaceNotificationService(alert_service)
            for fork in forks:
                try:
                    await notifier.notify_source_updated(
                        fork_owner_user_id=fork["owner_user_id"],
                        source_agent_id=source_id,
                        source_fqn=source_fqn or "(unknown)",
                        new_version_id=UUID(payload.new_version_id),
                        diff_summary_hash=payload.diff_summary_hash,
                    )
                except Exception:
                    LOGGER.exception(
                        "Failed to deliver marketplace.source_updated notification",
                        extra={
                            "source_agent_id": str(source_id),
                            "fork_agent_id": str(fork["agent_id"]),
                            "fork_owner_user_id": str(fork["owner_user_id"]),
                        },
                    )

    async def _find_forks(
        self,
        session: Any,
        source_id: UUID,
    ) -> list[dict[str, UUID]]:
        result = await session.execute(
            text(
                """
                SELECT id AS agent_id, created_by AS owner_user_id
                  FROM registry_agent_profiles
                 WHERE forked_from_agent_id = :source_id
                """
            ),
            {"source_id": str(source_id)},
        )
        return [
            {"agent_id": row["agent_id"], "owner_user_id": row["owner_user_id"]}
            for row in result.mappings().all()
        ]

    async def _lookup_source_fqn(self, session: Any, source_id: UUID) -> str | None:
        result = await session.execute(
            text("SELECT fqn FROM registry_agent_profiles WHERE id = :source_id"),
            {"source_id": str(source_id)},
        )
        row = result.mappings().first()
        return row["fqn"] if row else None
