from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.notifications.events import (
    ChannelConfigChangedPayload,
    publish_channel_config_changed,
)
from platform.notifications.repository import NotificationsRepository
from typing import Any
from uuid import uuid4


async def expire_unverified_channels(
    repo: NotificationsRepository,
    producer: EventProducer | None = None,
) -> int:
    expired = await repo.expire_channel_verifications(datetime.now(UTC))
    for config in expired:
        await publish_channel_config_changed(
            producer,
            ChannelConfigChangedPayload(
                channel_config_id=config.id,
                user_id=config.user_id,
                channel_type=config.channel_type.value,
                action="verification_expired",
                actor_id=config.user_id,
                occurred_at=datetime.now(UTC),
            ),
            CorrelationContext(correlation_id=uuid4()),
        )
    return len(expired)


def build_channel_verification_scheduler(run_once: Any) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(run_once, "interval", hours=1, id="notifications-channel-verification")
    return scheduler
