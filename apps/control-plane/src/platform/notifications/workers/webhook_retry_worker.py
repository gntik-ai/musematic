from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.notifications.deliverers.webhook_deliverer import WebhookDeliverer
from platform.notifications.events import (
    DeliveryDeadLetteredPayload,
    publish_delivery_dead_lettered,
)
from platform.notifications.models import DeliveryOutcome, WebhookDelivery, WebhookDeliveryStatus
from platform.notifications.repository import NotificationsRepository
from typing import Any, cast
from uuid import uuid4


async def run_webhook_retry_scan(
    *,
    repo: NotificationsRepository,
    redis: object,
    secrets: object,
    deliverer: WebhookDeliverer,
    settings: PlatformSettings,
    producer: EventProducer | None = None,
    limit: int = 200,
) -> int:
    count = 0
    for delivery in await repo.list_due_deliveries(datetime.now(UTC), limit):
        if not await _acquire_lease(redis, delivery.id):
            continue
        try:
            await _dispatch_delivery(
                repo=repo,
                secrets=secrets,
                deliverer=deliverer,
                settings=settings,
                producer=producer,
                delivery=delivery,
            )
            count += 1
        finally:
            await _release_lease(redis, delivery.id)
    return count


async def _dispatch_delivery(
    *,
    repo: NotificationsRepository,
    secrets: object,
    deliverer: WebhookDeliverer,
    settings: PlatformSettings,
    producer: EventProducer | None,
    delivery: WebhookDelivery,
) -> None:
    now = datetime.now(UTC)
    retry_policy = delivery.webhook.retry_policy
    backoff = list(
        retry_policy.get(
            "backoff_seconds",
            settings.notifications.webhook_default_backoff_seconds,
        )
    )
    max_retries = int(retry_policy.get("max_retries", len(backoff)))
    total_window = int(
        retry_policy.get(
            "total_window_seconds",
            settings.notifications.webhook_max_retry_window_seconds,
        )
    )
    retry_window_exhausted = (now - delivery.created_at).total_seconds() > total_window
    if delivery.attempts >= max_retries or retry_window_exhausted:
        await _dead_letter(repo, producer, delivery, "retry_window_exhausted")
        return
    if not delivery.webhook.active:
        await _dead_letter(repo, producer, delivery, "webhook_inactive")
        return

    secret_payload = await _read_secret(secrets, delivery.webhook.signing_secret_ref)
    secret = str(secret_payload.get("hmac_secret", ""))
    outcome, error_detail, _idempotency_key = await deliverer.send_signed(
        webhook_id=delivery.webhook_id,
        event_id=delivery.event_id,
        webhook_url=delivery.webhook.url,
        payload=delivery.payload,
        secret=secret,
        platform_version=settings.profile,
    )
    attempts = delivery.attempts + 1
    if outcome == DeliveryOutcome.success:
        await repo.update_delivery_status(
            delivery.id,
            status=WebhookDeliveryStatus.delivered.value,
            attempts=attempts,
            last_attempt_at=now,
            next_attempt_at=None,
            failure_reason=None,
        )
        return
    if outcome == DeliveryOutcome.failed:
        await _dead_letter(
            repo,
            producer,
            delivery,
            error_detail or "4xx_permanent",
            attempts=attempts,
        )
        return

    next_attempt_at = now + timedelta(
        seconds=_next_retry_delay(error_detail, backoff, attempts)
    )
    await repo.update_delivery_status(
        delivery.id,
        status=WebhookDeliveryStatus.failed.value,
        attempts=attempts,
        last_attempt_at=now,
        next_attempt_at=next_attempt_at,
        failure_reason=error_detail,
    )


async def _dead_letter(
    repo: NotificationsRepository,
    producer: EventProducer | None,
    delivery: WebhookDelivery,
    reason: str,
    *,
    attempts: int | None = None,
) -> None:
    attempts = delivery.attempts if attempts is None else attempts
    await repo.update_delivery_status(
        delivery.id,
        status=WebhookDeliveryStatus.dead_letter.value,
        attempts=attempts,
        failure_reason=reason,
        next_attempt_at=None,
        dead_lettered_at=datetime.now(UTC),
    )
    await publish_delivery_dead_lettered(
        producer,
        DeliveryDeadLetteredPayload(
            delivery_id=delivery.id,
            webhook_id=delivery.webhook_id,
            workspace_id=delivery.webhook.workspace_id,
            failure_reason=reason,
            attempts=attempts,
            occurred_at=datetime.now(UTC),
        ),
        CorrelationContext(correlation_id=uuid4(), workspace_id=delivery.webhook.workspace_id),
    )


def _next_backoff(backoff: list[int], attempts: int) -> int:
    if not backoff:
        return 60
    return backoff[min(attempts - 1, len(backoff) - 1)]


def _next_retry_delay(error_detail: str | None, backoff: list[int], attempts: int) -> int:
    retry_after_prefix = "retry_after="
    if error_detail:
        for segment in error_detail.split(";"):
            segment = segment.strip()
            if segment.startswith(retry_after_prefix):
                try:
                    return max(0, int(segment.removeprefix(retry_after_prefix)))
                except ValueError:
                    break
    return _next_backoff(backoff, attempts)


async def _read_secret(secrets: object, path: str) -> dict[str, Any]:
    read_secret = cast(Any, secrets).read_secret
    value = await read_secret(path)
    return value if isinstance(value, dict) else {}


async def _acquire_lease(redis: object, delivery_id: object) -> bool:
    key = f"notifications:webhook_lease:{delivery_id}"
    client = getattr(redis, "client", None)
    if client is None and callable(getattr(redis, "_get_client", None)):
        client = await cast(Any, redis)._get_client()
    raw_set = getattr(client, "set", None)
    if callable(raw_set):
        result = await raw_set(key, "1", ex=60, nx=True)
        return bool(result)

    set_method = getattr(redis, "set", None)
    if not callable(set_method):
        return True
    try:
        result = await set_method(key, "1", ex=60, nx=True)
    except TypeError:
        await set_method(key, b"1", ttl=60)
        return True
    return bool(result)


async def _release_lease(redis: object, delivery_id: object) -> None:
    delete_method = getattr(redis, "delete", None)
    if callable(delete_method):
        await delete_method(f"notifications:webhook_lease:{delivery_id}")


def build_webhook_retry_scheduler(run_once: Any, *, seconds: int = 30) -> Any | None:
    try:
        scheduler_module = __import__(
            "apscheduler.schedulers.asyncio",
            fromlist=["AsyncIOScheduler"],
        )
    except Exception:
        return None
    scheduler = scheduler_module.AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(run_once, "interval", seconds=seconds, id="notifications-webhook-retry-v2")
    return scheduler
