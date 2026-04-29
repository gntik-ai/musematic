from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any
from uuid import UUID


@dataclass
class MemoryRedis:
    strings: dict[str, Any] = field(default_factory=dict)
    hashes: dict[str, dict[str, str]] = field(default_factory=dict)
    sets: dict[str, set[str]] = field(default_factory=dict)
    expirations: dict[str, int] = field(default_factory=dict)

    async def hset(self, key: str, mapping: dict[str, Any]) -> int:
        bucket = self.hashes.setdefault(key, {})
        created = 0
        for name, value in mapping.items():
            if name not in bucket:
                created += 1
            bucket[name] = str(value)
        return created

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    async def exists(self, key: str) -> int:
        return int(key in self.strings or key in self.hashes or key in self.sets)

    async def expire(self, key: str, seconds: int) -> bool:
        self.expirations[key] = seconds
        return True

    async def sadd(self, key: str, *members: str) -> int:
        bucket = self.sets.setdefault(key, set())
        before = len(bucket)
        bucket.update(str(member) for member in members)
        return len(bucket) - before

    async def srem(self, key: str, *members: str) -> int:
        bucket = self.sets.setdefault(key, set())
        removed = 0
        for member in members:
            if str(member) in bucket:
                bucket.remove(str(member))
                removed += 1
        return removed

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    async def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        self.strings[key] = value
        if ex is not None:
            self.expirations[key] = ex
        return True

    async def get(self, key: str) -> Any | None:
        return self.strings.get(key)

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.strings:
                del self.strings[key]
                deleted += 1
            if key in self.hashes:
                del self.hashes[key]
                deleted += 1
            if key in self.sets:
                del self.sets[key]
                deleted += 1
            self.expirations.pop(key, None)
        return deleted

    async def incr(self, key: str) -> int:
        current = int(self.strings.get(key, 0)) + 1
        self.strings[key] = current
        return current

    async def ttl(self, key: str) -> int:
        return self.expirations.get(key, -1)

    async def ping(self) -> bool:
        return True

    async def scan(
        self,
        *,
        cursor: int = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[str]]:
        del cursor, count
        keys = list(self.strings.keys())
        if match is not None:
            keys = [key for key in keys if fnmatch(key, match)]
        return 0, keys


class FakeAsyncRedisClient:
    def __init__(self, client: MemoryRedis | None = None) -> None:
        self.client = client or MemoryRedis()

    async def _get_client(self) -> MemoryRedis:
        return self.client

    async def get(self, key: str) -> bytes | None:
        value = await self.client.get(key)
        if value is None:
            return None
        if isinstance(value, bytes):
            return value
        return str(value).encode()

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        await self.client.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def health_check(self) -> bool:
        return True


class RecordingProducer:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def publish(
        self,
        topic: str,
        key: str,
        event_type: str,
        payload: dict[str, Any],
        correlation_ctx: Any,
        source: str,
    ) -> None:
        self.events.append(
            {
                "topic": topic,
                "key": key,
                "event_type": event_type,
                "payload": payload,
                "correlation_ctx": correlation_ctx,
                "source": source,
            }
        )


def role_claim(role: str, workspace_id: UUID | None = None) -> dict[str, str | None]:
    return {
        "role": role,
        "workspace_id": str(workspace_id) if workspace_id is not None else None,
    }
