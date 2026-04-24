from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from platform.accounts.models import SignupSource, UserStatus
from platform.accounts.repository import AccountsRepository
from platform.common import database
from platform.common.auth_middleware import AuthMiddleware
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.debug_logging.capture import DebugCaptureMiddleware
from platform.common.debug_logging.events import register_debug_logging_event_types
from platform.common.debug_logging.models import DebugLoggingCapture, DebugLoggingSession
from platform.common.debug_logging.router import router as debug_logging_router
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from fastapi import FastAPI, Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class RecordingProducer:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def publish(
        self,
        topic: str,
        key: str,
        event_type: str,
        payload: dict[str, object],
        correlation_ctx,
        source: str,
    ) -> None:
        self.events.append(
            {
                "topic": topic,
                "key": key,
                "event_type": event_type,
                "payload": payload,
                "correlation_id": str(correlation_ctx.correlation_id),
                "source": source,
            }
        )


class _FrozenDateTime(datetime):
    current: datetime = datetime.now(UTC)

    @classmethod
    def now(cls, tz: UTC | None = None) -> datetime:
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)


def _redis_url(redis_client: AsyncRedisClient) -> str:
    return redis_client._url or "redis://localhost:6379"


def _settings(
    auth_settings, *, database_url: str, redis_client: AsyncRedisClient
) -> PlatformSettings:
    return auth_settings.model_copy(
        update={
            "db": auth_settings.db.model_copy(update={"dsn": database_url}),
            "redis": auth_settings.redis.model_copy(
                update={"url": _redis_url(redis_client), "test_mode": "standalone"}
            ),
            "auth": auth_settings.auth.model_copy(
                update={
                    "jwt_secret_key": "d" * 32,
                    "jwt_private_key": "",
                    "jwt_public_key": "",
                    "jwt_algorithm": "HS256",
                }
            ),
        }
    )


def _token(secret: str, sub: str, *, roles: list[str]) -> str:
    return jwt.encode(
        {
            "sub": sub,
            "principal_id": sub,
            "type": "access",
            "roles": [{"role": role, "workspace_id": None} for role in roles],
        },
        secret,
        algorithm="HS256",
    )


def _auth_headers(
    settings: PlatformSettings,
    sub: str,
    roles: list[str],
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": (f"Bearer {_token(settings.auth.signing_key, sub, roles=roles)}")
    }
    if extra is not None:
        headers.update(extra)
    return headers


def _build_app(
    settings: PlatformSettings,
    redis_client: AsyncRedisClient,
    producer: RecordingProducer,
) -> FastAPI:
    database.configure_database(settings)
    register_debug_logging_event_types()
    app = FastAPI()
    app.state.settings = settings
    app.state.clients = {"redis": redis_client, "kafka": producer}
    app.add_middleware(DebugCaptureMiddleware)
    app.add_middleware(AuthMiddleware)
    app.include_router(debug_logging_router)

    @app.get("/api/v1/workspaces")
    async def list_workspaces(request: Request) -> dict[str, str | None]:
        return {"workspace_id": request.headers.get("X-Workspace-ID")}

    return app


async def _create_admin_user(session: AsyncSession) -> str:
    repository = AccountsRepository(session)
    user = await repository.create_user(
        email=f"admin-{uuid4().hex}@e2e.test",
        display_name="Platform Admin",
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    await session.commit()
    return str(user.id)


async def _drain_events() -> None:
    await asyncio.sleep(0.05)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_scoped_session_captures_only_target_user_requests(
    auth_settings,
    redis_client: AsyncRedisClient,
    migrated_database_url: str,
    integration_session: AsyncSession,
) -> None:
    producer = RecordingProducer()
    settings = _settings(
        auth_settings, database_url=migrated_database_url, redis_client=redis_client
    )
    app = _build_app(settings, redis_client, producer)
    admin_id = await _create_admin_user(integration_session)
    target_user_id = str(uuid4())
    other_user_id = str(uuid4())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        create = await client.post(
            "/api/v1/admin/debug-logging/sessions",
            headers=_auth_headers(settings, admin_id, ["platform_admin"]),
            json={
                "target_type": "user",
                "target_id": target_user_id,
                "justification": "investigating reported login issue",
                "duration_minutes": 30,
            },
        )
        create.raise_for_status()
        session_id = create.json()["session_id"]

        for _ in range(3):
            response = await client.get(
                "/api/v1/workspaces",
                headers=_auth_headers(settings, target_user_id, ["workspace_member"]),
            )
            response.raise_for_status()
        other = await client.get(
            "/api/v1/workspaces",
            headers=_auth_headers(settings, other_user_id, ["workspace_member"]),
        )
        other.raise_for_status()
        await _drain_events()

        captures = await client.get(
            f"/api/v1/admin/debug-logging/sessions/{session_id}/captures",
            headers=_auth_headers(settings, admin_id, ["platform_admin"]),
        )
        captures.raise_for_status()
        session = await client.get(
            f"/api/v1/admin/debug-logging/sessions/{session_id}",
            headers=_auth_headers(settings, admin_id, ["platform_admin"]),
        )
        session.raise_for_status()

    assert len(captures.json()["items"]) == 3
    assert session.json()["capture_count"] == 3
    assert {event["event_type"] for event in producer.events} >= {
        "debug_logging.session.created",
        "debug_logging.capture.written",
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_workspace_scoped_session_captures_matching_workspace_requests(
    auth_settings,
    redis_client: AsyncRedisClient,
    migrated_database_url: str,
    integration_session: AsyncSession,
) -> None:
    producer = RecordingProducer()
    settings = _settings(
        auth_settings, database_url=migrated_database_url, redis_client=redis_client
    )
    app = _build_app(settings, redis_client, producer)
    admin_id = await _create_admin_user(integration_session)
    workspace_id = str(uuid4())
    other_workspace_id = str(uuid4())
    actor_id = str(uuid4())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        create = await client.post(
            "/api/v1/admin/debug-logging/sessions",
            headers=_auth_headers(settings, admin_id, ["platform_admin"]),
            json={
                "target_type": "workspace",
                "target_id": workspace_id,
                "justification": "investigating workspace behaviour",
                "duration_minutes": 30,
            },
        )
        create.raise_for_status()
        session_id = create.json()["session_id"]

        matching = await client.get(
            "/api/v1/workspaces",
            headers=_auth_headers(
                settings,
                actor_id,
                ["workspace_member"],
                {"X-Workspace-ID": workspace_id},
            ),
        )
        non_matching = await client.get(
            "/api/v1/workspaces",
            headers=_auth_headers(
                settings,
                actor_id,
                ["workspace_member"],
                {"X-Workspace-ID": other_workspace_id},
            ),
        )
        matching.raise_for_status()
        non_matching.raise_for_status()
        await _drain_events()

        captures = await client.get(
            f"/api/v1/admin/debug-logging/sessions/{session_id}/captures",
            headers=_auth_headers(settings, admin_id, ["platform_admin"]),
        )
        captures.raise_for_status()

    assert len(captures.json()["items"]) == 1
    assert captures.json()["items"][0]["path"] == "/api/v1/workspaces"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_expired_and_terminated_sessions_stop_future_capture(
    auth_settings,
    redis_client: AsyncRedisClient,
    migrated_database_url: str,
    integration_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    producer = RecordingProducer()
    settings = _settings(
        auth_settings, database_url=migrated_database_url, redis_client=redis_client
    )
    app = _build_app(settings, redis_client, producer)
    admin_id = await _create_admin_user(integration_session)
    target_user_id = str(uuid4())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        create = await client.post(
            "/api/v1/admin/debug-logging/sessions",
            headers=_auth_headers(settings, admin_id, ["platform_admin"]),
            json={
                "target_type": "user",
                "target_id": target_user_id,
                "justification": "investigating temporary user issue",
                "duration_minutes": 1,
            },
        )
        create.raise_for_status()
        session_id = create.json()["session_id"]
        expires_at = datetime.fromisoformat(create.json()["expires_at"])

        monkeypatch.setattr(
            "platform.common.debug_logging.service.datetime",
            _FrozenDateTime,
        )
        _FrozenDateTime.current = expires_at + timedelta(minutes=1)

        response = await client.get(
            "/api/v1/workspaces",
            headers=_auth_headers(settings, target_user_id, ["workspace_member"]),
        )
        response.raise_for_status()
        await _drain_events()

        expired_captures = await client.get(
            f"/api/v1/admin/debug-logging/sessions/{session_id}/captures",
            headers=_auth_headers(settings, admin_id, ["platform_admin"]),
        )
        expired_captures.raise_for_status()
        assert expired_captures.json()["items"] == []

        monkeypatch.undo()

        create_active = await client.post(
            "/api/v1/admin/debug-logging/sessions",
            headers=_auth_headers(settings, admin_id, ["platform_admin"]),
            json={
                "target_type": "user",
                "target_id": target_user_id,
                "justification": "investigating active user issue",
                "duration_minutes": 30,
            },
        )
        create_active.raise_for_status()
        active_session_id = create_active.json()["session_id"]
        terminated = await client.delete(
            f"/api/v1/admin/debug-logging/sessions/{active_session_id}",
            headers=_auth_headers(settings, admin_id, ["platform_admin"]),
        )
        assert terminated.status_code == 204

        after_close = await client.get(
            "/api/v1/workspaces",
            headers=_auth_headers(settings, target_user_id, ["workspace_member"]),
        )
        after_close.raise_for_status()
        await _drain_events()

        closed_captures = await client.get(
            f"/api/v1/admin/debug-logging/sessions/{active_session_id}/captures",
            headers=_auth_headers(settings, admin_id, ["platform_admin"]),
        )
        closed_captures.raise_for_status()

    assert closed_captures.json()["items"] == []
    assert {event["event_type"] for event in producer.events} >= {
        "debug_logging.session.created",
        "debug_logging.session.expired",
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_delete_cascades_to_captures(
    auth_settings,
    redis_client: AsyncRedisClient,
    migrated_database_url: str,
    integration_session: AsyncSession,
) -> None:
    producer = RecordingProducer()
    settings = _settings(
        auth_settings, database_url=migrated_database_url, redis_client=redis_client
    )
    app = _build_app(settings, redis_client, producer)
    admin_id = await _create_admin_user(integration_session)
    target_user_id = str(uuid4())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        create = await client.post(
            "/api/v1/admin/debug-logging/sessions",
            headers=_auth_headers(settings, admin_id, ["platform_admin"]),
            json={
                "target_type": "user",
                "target_id": target_user_id,
                "justification": "investigating RTBF-style cleanup",
                "duration_minutes": 30,
            },
        )
        create.raise_for_status()
        session_id = UUID(create.json()["session_id"])
        request_response = await client.get(
            "/api/v1/workspaces",
            headers=_auth_headers(settings, target_user_id, ["workspace_member"]),
        )
        request_response.raise_for_status()
        await _drain_events()

    async with database.AsyncSessionLocal() as session:
        capture_count = await session.scalar(
            select(func.count())
            .select_from(DebugLoggingCapture)
            .where(DebugLoggingCapture.session_id == session_id)
        )
        assert int(capture_count or 0) == 1
        await session.execute(
            delete(DebugLoggingSession).where(DebugLoggingSession.id == session_id)
        )
        await session.commit()

    async with database.AsyncSessionLocal() as session:
        remaining = await session.scalar(
            select(func.count())
            .select_from(DebugLoggingCapture)
            .where(DebugLoggingCapture.session_id == session_id)
        )

    assert int(remaining or 0) == 0
