from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.auth.events import UserLockedPayload, publish_auth_event
from platform.common.clients.redis import AsyncRedisClient
from platform.common.events.producer import EventProducer
from uuid import UUID, uuid4


class LockoutManager:
    def __init__(
        self,
        redis_client: AsyncRedisClient,
        *,
        producer: EventProducer | None = None,
    ) -> None:
        self.redis_client = redis_client
        self.producer = producer

    async def is_locked(self, user_id: UUID) -> bool:
        client = await self.redis_client._get_client()
        value = await client.get(self._locked_key(user_id))
        return value is not None

    async def increment_failure(
        self,
        user_id: UUID,
        threshold: int,
        duration: int,
        *,
        correlation_id: UUID | None = None,
    ) -> int:
        client = await self.redis_client._get_client()
        counter_key = self._counter_key(user_id)
        attempts = int(await client.incr(counter_key))
        if attempts == 1:
            await client.expire(counter_key, duration)
        if attempts >= threshold:
            await self.lock_account(
                user_id,
                duration,
                attempt_count=attempts,
                correlation_id=correlation_id,
            )
        return attempts

    async def lock_account(
        self,
        user_id: UUID,
        duration: int,
        *,
        attempt_count: int | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        client = await self.redis_client._get_client()
        await client.set(self._locked_key(user_id), "1", ex=duration)
        await publish_auth_event(
            "auth.user.locked",
            UserLockedPayload(
                user_id=user_id,
                attempt_count=attempt_count or 0,
                locked_until=datetime.now(UTC) + timedelta(seconds=duration),
            ),
            correlation_id or uuid4(),
            self.producer,
        )

    async def reset_failure_counter(self, user_id: UUID) -> None:
        client = await self.redis_client._get_client()
        await client.delete(self._counter_key(user_id))
        await client.delete(self._locked_key(user_id))

    @staticmethod
    def _counter_key(user_id: UUID) -> str:
        return f"auth:lockout:{user_id}"

    @staticmethod
    def _locked_key(user_id: UUID) -> str:
        return f"auth:locked:{user_id}"
