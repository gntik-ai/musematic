from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.notifications.events import (
    DlqDepthThresholdReachedPayload,
    publish_dlq_depth_threshold_reached,
)
from platform.notifications.repository import NotificationsRepository
from typing import Any, cast
from uuid import UUID, uuid4


async def run_dead_letter_threshold_scan(
    *,
    repo: NotificationsRepository,
    redis: object,
    settings: PlatformSettings,
    producer: EventProducer | None,
) -> int:
    emitted = 0
    depths = await repo.aggregate_dead_letter_depth_by_workspace()
    for workspace_id, depth in depths.items():
        if depth < settings.notifications.dead_letter_warning_threshold:
            continue
        if not await _acquire_cooldown(redis, workspace_id):
            continue
        await publish_dlq_depth_threshold_reached(
            producer,
            DlqDepthThresholdReachedPayload(
                workspace_id=workspace_id,
                depth=depth,
                threshold=settings.notifications.dead_letter_warning_threshold,
                occurred_at=datetime.now(UTC),
            ),
            CorrelationContext(correlation_id=uuid4(), workspace_id=workspace_id),
        )
        emitted += 1
    return emitted


async def _acquire_cooldown(redis: object, workspace_id: UUID) -> bool:
    key = f"notifications:dlq_threshold:{workspace_id}"
    client = getattr(redis, "client", None)
    if client is None and callable(getattr(redis, "_get_client", None)):
        client = await cast(Any, redis)._get_client()
    raw_set = getattr(client, "set", None)
    if callable(raw_set):
        return bool(await raw_set(key, "1", ex=3600, nx=True))
    set_method = getattr(redis, "set", None)
    if not callable(set_method):
        return True
    try:
        return bool(await set_method(key, "1", ex=3600, nx=True))
    except TypeError:
        exists = getattr(redis, "get", None)
        if callable(exists) and await exists(key):
            return False
        await set_method(key, b"1", ttl=3600)
        return True


def build_dead_letter_threshold_scheduler(run_once: Any, *, seconds: int = 60) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(run_once, "interval", seconds=seconds, id="notifications-dlq-threshold")
    return scheduler
