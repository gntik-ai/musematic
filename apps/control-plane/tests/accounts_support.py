from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from uuid import UUID, uuid4

import jwt

from tests.auth_support import RecordingProducer


class NoopClient:
    async def connect(self) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def health_check(self) -> bool:
        return True


def build_test_clients(
    redis_client, producer: RecordingProducer | None = None
) -> dict[str, object]:
    return {
        "redis": redis_client,
        "kafka": producer or RecordingProducer(),
        "kafka_consumer": NoopClient(),
        "qdrant": NoopClient(),
        "neo4j": NoopClient(),
        "clickhouse": NoopClient(),
        "opensearch": NoopClient(),
        "object_storage": NoopClient(),
        "runtime_controller": NoopClient(),
        "reasoning_engine": NoopClient(),
        "sandbox_manager": NoopClient(),
        "simulation_controller": NoopClient(),
    }


def build_test_settings(
    settings: PlatformSettings,
    *,
    database_url: str,
    redis_url: str,
    signup_mode: str = "open",
) -> PlatformSettings:
    return settings.model_copy(
        update={
            "db": settings.db.model_copy(update={"dsn": database_url}),
            "redis": settings.redis.model_copy(
                update={"url": redis_url, "test_mode": "standalone"}
            ),
            "accounts": settings.accounts.model_copy(update={"signup_mode": signup_mode}),
        }
    )


def issue_access_token(
    settings: PlatformSettings,
    user_id: UUID,
    roles: list[dict[str, str | None]],
    *,
    extra_claims: dict[str, object] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": str(user_id),
        "type": "access",
        "roles": roles,
        "session_id": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.auth.access_token_ttl)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        settings.auth.signing_key,
        algorithm=settings.auth.jwt_algorithm,
    )
