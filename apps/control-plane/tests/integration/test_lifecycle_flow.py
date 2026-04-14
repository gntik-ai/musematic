from __future__ import annotations

from datetime import UTC, datetime
from platform.accounts.models import SignupSource, User, UserStatus
from platform.auth.models import MfaEnrollment, UserCredential
from platform.auth.password import hash_password
from platform.common.models.user import User as PlatformUser
from platform.main import create_app
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.accounts_support import build_test_clients, build_test_settings, issue_access_token
from tests.auth_support import RecordingProducer, role_claim


def _redis_url(redis_client) -> str:
    return redis_client._url or "redis://localhost:6379"


async def _seed_user_for_lifecycle(session_factory: async_sessionmaker) -> UUID:
    user_id = uuid4()
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add(
            User(
                id=user_id,
                email="lifecycle@example.com",
                display_name="Lifecycle User",
                status=UserStatus.active,
                signup_source=SignupSource.self_registration,
                email_verified_at=now,
                activated_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            PlatformUser(
                id=user_id,
                email="lifecycle@example.com",
                display_name="Lifecycle User",
                status="active",
            )
        )
        await session.flush()
        session.add(
            UserCredential(
                user_id=user_id,
                email="lifecycle@example.com",
                password_hash=hash_password("StrongP@ssw0rd!"),
                is_active=True,
            )
        )
        await session.flush()
        session.add(
            MfaEnrollment(
                user_id=user_id,
                encrypted_secret="encrypted",
                status="active",
                recovery_codes_hash=[],
                enrolled_at=now,
            )
        )
        await session.commit()
    return user_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_lifecycle_actions_update_state_and_auth_side_effects(
    monkeypatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    settings = build_test_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_url=_redis_url(redis_client),
    )
    admin_token = issue_access_token(settings, uuid4(), [role_claim("workspace_admin")])
    superadmin_token = issue_access_token(settings, uuid4(), [role_claim("superadmin")])
    user_id = await _seed_user_for_lifecycle(session_factory)
    redis_backend = await redis_client._get_client()
    await redis_backend.set(f"auth:lockout:{user_id}", "3", ex=900)
    await redis_backend.set(f"auth:locked:{user_id}", "1", ex=900)

    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            invalid_reactivate = await client.post(
                f"/api/v1/accounts/{user_id}/reactivate",
                json={"reason": "already active"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            suspended = await client.post(
                f"/api/v1/accounts/{user_id}/suspend",
                json={"reason": "paused"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            reactivated = await client.post(
                f"/api/v1/accounts/{user_id}/reactivate",
                json={"reason": "restored"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            reset_mfa = await client.post(
                f"/api/v1/accounts/{user_id}/reset-mfa",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            reset_password = await client.post(
                f"/api/v1/accounts/{user_id}/reset-password",
                json={"force_change_on_login": True},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            unlocked = await client.post(
                f"/api/v1/accounts/{user_id}/unlock",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            blocked = await client.post(
                f"/api/v1/accounts/{user_id}/block",
                json={"reason": "blocked"},
                headers={"Authorization": f"Bearer {superadmin_token}"},
            )
            unblocked = await client.post(
                f"/api/v1/accounts/{user_id}/unblock",
                json={"reason": "unblocked"},
                headers={"Authorization": f"Bearer {superadmin_token}"},
            )
            archived = await client.post(
                f"/api/v1/accounts/{user_id}/archive",
                json={"reason": "archived"},
                headers={"Authorization": f"Bearer {superadmin_token}"},
            )

    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.id == user_id))
        password_reset_rows = (
            (await session.execute(select(UserCredential).where(UserCredential.user_id == user_id)))
            .scalars()
            .all()
        )

    assert invalid_reactivate.status_code == 409
    assert suspended.json()["status"] == "suspended"
    assert reactivated.json()["status"] == "active"
    assert reset_mfa.json()["mfa_cleared"] is True
    assert reset_password.json()["password_reset_initiated"] is True
    assert unlocked.json()["unlocked"] is True
    assert blocked.json()["status"] == "blocked"
    assert unblocked.json()["status"] == "active"
    assert archived.json()["status"] == "archived"
    assert user is not None
    assert user.status == UserStatus.archived
    assert user.deleted_at is not None
    assert await redis_backend.get(f"auth:lockout:{user_id}") is None
    assert await redis_backend.get(f"auth:locked:{user_id}") is None
    assert len(password_reset_rows) == 1
    assert "accounts.user.suspended" in [event["event_type"] for event in producer.events]
    assert "accounts.user.reactivated" in [event["event_type"] for event in producer.events]
    assert "accounts.user.blocked" in [event["event_type"] for event in producer.events]
    assert "accounts.user.unblocked" in [event["event_type"] for event in producer.events]
    assert "accounts.user.archived" in [event["event_type"] for event in producer.events]
    assert "accounts.user.mfa_reset" in [event["event_type"] for event in producer.events]
    assert "accounts.user.password_reset_initiated" in [
        event["event_type"] for event in producer.events
    ]
