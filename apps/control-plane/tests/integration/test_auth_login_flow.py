from __future__ import annotations

from platform.auth.models import UserCredential, UserRole
from platform.auth.password import hash_password
from platform.common.models.user import User
from platform.main import create_app
from uuid import uuid4

import httpx
import jwt
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.auth_support import RecordingProducer


class NoopClient:
    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def health_check(self) -> bool:
        return True


def _clients(redis_client) -> dict[str, object]:
    return {
        "redis": redis_client,
        "kafka": RecordingProducer(),
        "kafka_consumer": NoopClient(),
        "qdrant": NoopClient(),
        "neo4j": NoopClient(),
        "clickhouse": NoopClient(),
        "opensearch": NoopClient(),
        "minio": NoopClient(),
        "runtime_controller": NoopClient(),
        "reasoning_engine": NoopClient(),
        "sandbox_manager": NoopClient(),
        "simulation_controller": NoopClient(),
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_login_refresh_logout_flow(
    monkeypatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    async with session_factory() as session:
        user = User(email=f"{uuid4()}@example.com", display_name="Auth Test", status="active")
        session.add(user)
        await session.flush()
        session.add(
            UserCredential(
                user_id=user.id,
                email=user.email,
                password_hash=hash_password("SecureP@ss123"),
                is_active=True,
            )
        )
        session.add(UserRole(user_id=user.id, role="viewer", workspace_id=None))
        await session.commit()

    settings = auth_settings.model_copy(
        update={
            "db": auth_settings.db.model_copy(update={"dsn": migrated_database_url}),
            "redis": auth_settings.redis.model_copy(
                update={
                    "url": redis_client._url or "redis://localhost:6379",
                    "test_mode": "standalone",
                }
            ),
        }
    )
    monkeypatch.setattr("platform.main._build_clients", lambda resolved: _clients(redis_client))

    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            login = await client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "SecureP@ss123"},
            )
            assert login.status_code == 200
            payload = login.json()

            protected = await client.get(
                "/api/v1/protected",
                headers={"Authorization": f"Bearer {payload['access_token']}"},
            )
            refreshed = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": payload["refresh_token"]},
            )
            logout = await client.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {payload['access_token']}"},
            )
            after_logout = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": payload["refresh_token"]},
            )

    access_claims = jwt.decode(
        payload["access_token"],
        settings.auth.verification_key,
        algorithms=[settings.auth.jwt_algorithm],
    )
    session_key = f"session:{user.id}:{access_claims['session_id']}"
    redis_raw = await redis_client.get(session_key)

    assert protected.status_code == 200
    assert protected.json()["user"]["sub"] == str(user.id)
    assert refreshed.status_code == 200
    assert logout.status_code == 200
    assert after_logout.status_code == 401
    assert after_logout.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"
    assert redis_raw is None
