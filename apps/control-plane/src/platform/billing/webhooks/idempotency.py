"""UPD-052 — Stripe webhook idempotency.

Two-layer dedupe (research R3):

1. **Redis short-lived lock** ``billing:webhook_lock:{event_id}`` — SET NX EX 60.
   Compresses the in-flight race window to "post-commit." If the lock cannot
   be acquired, the request returns ``already_processing`` immediately.
2. **PostgreSQL durable record** ``processed_webhooks`` (composite PK on
   ``(provider, event_id)``). Inserted AFTER successful handler completion;
   the row guarantees correctness even if the Redis lock expired mid-flight.
"""

from __future__ import annotations

from dataclasses import dataclass
from platform.billing.webhooks.models import ProcessedWebhook
from platform.common.clients.redis import AsyncRedisClient
from platform.common.logging import get_logger
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)


def webhook_lock_key(event_id: str) -> str:
    return f"billing:webhook_lock:{event_id}"


@dataclass(frozen=True)
class IdempotencyDecision:
    """Outcome of the idempotency check."""

    proceed: bool
    reason: str  # "fresh" | "already_processed" | "already_processing"


class WebhookIdempotency:
    """Two-layer idempotency guard for Stripe webhook events.

    Caller protocol:

    1. ``decision = await guard.acquire(event_id)``.
    2. If ``decision.proceed`` is ``False``: return the ``decision.reason`` to
       the caller (Stripe sees an HTTP 200; no handler runs).
    3. Otherwise: run the handler in the same transaction and call
       ``await guard.mark_processed(session, event_id, event_type)`` before
       commit.
    """

    def __init__(
        self,
        *,
        redis: AsyncRedisClient,
        provider: str = "stripe",
        lock_ttl_seconds: int = 60,
    ) -> None:
        self._redis = redis
        self._provider = provider
        self._lock_ttl_seconds = lock_ttl_seconds

    async def acquire(self, session: AsyncSession, event_id: str) -> IdempotencyDecision:
        """Acquire the lock and check the durable record.

        Returns a decision describing whether the caller may proceed.
        """
        if not event_id:
            return IdempotencyDecision(proceed=False, reason="missing_event_id")

        # Durable check first: if the row exists, we have already processed
        # this event in a prior delivery and the in-flight lock check is
        # redundant.
        already_processed = await session.execute(
            select(ProcessedWebhook).where(
                ProcessedWebhook.provider == self._provider,
                ProcessedWebhook.event_id == event_id,
            )
        )
        if already_processed.scalar_one_or_none() is not None:
            return IdempotencyDecision(proceed=False, reason="already_processed")

        # In-flight short lock so concurrent retries don't both run handlers.
        # The platform's AsyncRedisClient does not expose nx/ex directly, so
        # call the underlying redis-py client when the wrapper is in use, and
        # fall back to the wrapper's set(... nx=True, ex=...) shape used by
        # the test stubs (matching the pattern in
        # ``notifications/workers/webhook_retry_worker.py``).
        lock_acquired = await self._set_nx_with_ttl(
            webhook_lock_key(event_id),
            "1",
            ex=self._lock_ttl_seconds,
        )
        if not lock_acquired:
            return IdempotencyDecision(proceed=False, reason="already_processing")

        return IdempotencyDecision(proceed=True, reason="fresh")

    async def _set_nx_with_ttl(
        self,
        key: str,
        value: str,
        *,
        ex: int,
    ) -> bool:
        """Best-effort SET NX EX bridging the wrapper and the raw redis-py client."""
        client = getattr(self._redis, "client", None)
        if client is None and callable(getattr(self._redis, "_get_client", None)):
            client = await cast(Any, self._redis)._get_client()
        raw_set = getattr(client, "set", None)
        if callable(raw_set):
            result = await raw_set(key, value, ex=ex, nx=True)
            return bool(result)
        # Test-double path: the wrapper itself accepts nx/ex.
        set_method = getattr(self._redis, "set", None)
        if not callable(set_method):
            return True
        try:
            result = await set_method(key, value, ex=ex, nx=True)
        except TypeError:
            # Fallback to the wrapper's typed signature (no NX support).
            await set_method(key, value.encode("utf-8"), ttl=ex)
            return True
        return bool(result)

    async def mark_processed(
        self,
        session: AsyncSession,
        event_id: str,
        event_type: str,
    ) -> None:
        """Persist the durable idempotency record.

        Caller MUST invoke this inside the handler's transaction so the row
        commits atomically with the handler's side effects. PK conflicts are
        treated as "another worker won the race" and silently ignored.
        """
        record = ProcessedWebhook(
            provider=self._provider,
            event_id=event_id,
            event_type=event_type,
        )
        session.add(record)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            LOGGER.info(
                "billing.webhook_already_processed_race",
                event_id=event_id,
                event_type=event_type,
            )

    async def release_lock(self, event_id: str) -> None:
        """Release the in-flight lock.

        Called on handler exception so a retry isn't blocked for 60s. The
        durable record is intentionally NOT inserted on exception — Stripe
        will retry and the next delivery proceeds normally.
        """
        try:
            await self._redis.delete(webhook_lock_key(event_id))
        except Exception:  # pragma: no cover - best-effort cleanup
            LOGGER.warning("billing.webhook_lock_release_failed", event_id=event_id)
