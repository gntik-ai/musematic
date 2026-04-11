from __future__ import annotations

from datetime import UTC, datetime
from platform.accounts.models import SignupSource, User, UserStatus
from platform.auth.models import UserRole
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


async def _seed_inviter(session_factory: async_sessionmaker) -> UUID:
    inviter_id = uuid4()
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add(
            User(
                id=inviter_id,
                email="admin@example.com",
                display_name="Admin User",
                status=UserStatus.active,
                signup_source=SignupSource.self_registration,
                activated_at=now,
                email_verified_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            PlatformUser(
                id=inviter_id,
                email="admin@example.com",
                display_name="Admin User",
                status="active",
            )
        )
        await session.commit()
    return inviter_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invitation_create_details_accept_and_role_assignment(
    monkeypatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    invitation_tokens: list[str] = []
    settings = build_test_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_url=_redis_url(redis_client),
    )
    inviter_id = await _seed_inviter(session_factory)
    admin_token = issue_access_token(settings, inviter_id, [role_claim("workspace_admin")])

    async def capture_invitation_email(
        invitation_id, email: str, token: str, inviter_id, message, notification_client=None
    ) -> None:
        del invitation_id, email, inviter_id, message, notification_client
        invitation_tokens.append(token)

    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    monkeypatch.setattr(
        "platform.accounts.email.send_invitation_email",
        capture_invitation_email,
    )
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            created = await client.post(
                "/api/v1/accounts/invitations",
                json={
                    "email": "invitee@example.com",
                    "roles": ["viewer"],
                    "message": "Welcome aboard",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            details = await client.get(f"/api/v1/accounts/invitations/{invitation_tokens[0]}")
            accepted = await client.post(
                f"/api/v1/accounts/invitations/{invitation_tokens[0]}/accept",
                json={
                    "token": invitation_tokens[0],
                    "display_name": "Invitee User",
                    "password": "StrongP@ssw0rd!",
                },
            )
            invitations = await client.get(
                "/api/v1/accounts/invitations",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

    async with session_factory() as session:
        accepted_user = await session.scalar(
            select(User).where(User.email == "invitee@example.com")
        )
        assigned_roles = (
            (
                await session.execute(
                    select(UserRole).where(UserRole.user_id == UUID(accepted.json()["user_id"]))
                )
            )
            .scalars()
            .all()
        )

    assert created.status_code == 201
    assert details.status_code == 200
    assert details.json()["inviter_display_name"] == "Admin User"
    assert accepted.status_code == 201
    assert accepted.json()["status"] == "active"
    assert invitations.status_code == 200
    assert invitations.json()["total"] == 1
    assert accepted_user is not None
    assert accepted_user.status == UserStatus.active
    assert [role.role for role in assigned_roles] == ["viewer"]
    assert "accounts.invitation.created" in [event["event_type"] for event in producer.events]
    assert "accounts.invitation.accepted" in [event["event_type"] for event in producer.events]
    assert "accounts.user.activated" in [event["event_type"] for event in producer.events]
