from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import AuthSettings
from typing import Any, cast
from uuid import UUID


class RedisSessionStore:
    def __init__(self, redis_client: AsyncRedisClient, settings: AuthSettings) -> None:
        self.redis_client = redis_client
        self.settings = settings

    async def create_session(
        self,
        user_id: UUID,
        session_id: UUID,
        email: str,
        roles: list[dict[str, Any]],
        ip: str,
        device: str,
        refresh_jti: str,
    ) -> None:
        client = await self.redis_client._get_client()
        now = datetime.now(UTC).isoformat()
        session_key = self._session_key(user_id, session_id)
        user_sessions_key = self._user_sessions_key(user_id)
        mapping = {
            "user_id": str(user_id),
            "email": email,
            "roles_json": json.dumps(roles),
            "device_info": device,
            "ip_address": ip,
            "created_at": now,
            "last_activity": now,
            "refresh_jti": refresh_jti,
        }
        await cast(Any, client.hset(session_key, mapping=mapping))
        await cast(Any, client.expire(session_key, self.settings.session_ttl))
        await cast(Any, client.sadd(user_sessions_key, str(session_id)))
        await cast(Any, client.expire(user_sessions_key, self.settings.session_ttl))

    async def get_session(self, user_id: UUID, session_id: UUID) -> dict[str, Any] | None:
        client = await self.redis_client._get_client()
        raw = await cast(Any, client.hgetall(self._session_key(user_id, session_id)))
        if not raw:
            return None
        return {
            "user_id": raw["user_id"],
            "email": raw["email"],
            "roles": json.loads(raw["roles_json"]),
            "device_info": raw["device_info"],
            "ip_address": raw["ip_address"],
            "created_at": raw["created_at"],
            "last_activity": raw["last_activity"],
            "refresh_jti": raw["refresh_jti"],
        }

    async def list_sessions_by_user(self, user_id: UUID) -> list[dict[str, Any]]:
        client = await self.redis_client._get_client()
        raw_session_ids = await cast(Any, client.smembers(self._user_sessions_key(user_id)))
        sessions: list[dict[str, Any]] = []
        for raw_session_id in raw_session_ids:
            session_id = UUID(self._decode_redis_value(raw_session_id))
            session = await self.get_session(user_id, session_id)
            if session is None:
                await cast(Any, client.srem(self._user_sessions_key(user_id), str(session_id)))
                continue
            sessions.append({"session_id": str(session_id), **session})
        return sorted(
            sessions,
            key=lambda session: str(session.get("last_activity") or ""),
            reverse=True,
        )

    async def delete_session(self, user_id: UUID, session_id: UUID) -> None:
        client = await self.redis_client._get_client()
        await client.delete(self._session_key(user_id, session_id))
        await cast(Any, client.srem(self._user_sessions_key(user_id), str(session_id)))

    async def delete_all_sessions(self, user_id: UUID) -> int:
        client = await self.redis_client._get_client()
        sessions_key = self._user_sessions_key(user_id)
        session_ids = await cast(Any, client.smembers(sessions_key))
        if not session_ids:
            return 0
        deleted = 0
        for raw_session_id in session_ids:
            session_id = UUID(str(raw_session_id))
            await client.delete(self._session_key(user_id, session_id))
            deleted += 1
        await client.delete(sessions_key)
        return deleted

    @staticmethod
    def _session_key(user_id: UUID, session_id: UUID) -> str:
        return f"session:{user_id}:{session_id}"

    @staticmethod
    def _user_sessions_key(user_id: UUID) -> str:
        return f"user_sessions:{user_id}"

    @staticmethod
    def _decode_redis_value(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode()
        return str(value)
