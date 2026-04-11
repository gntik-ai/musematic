from __future__ import annotations

from datetime import UTC, datetime
from platform.accounts.models import SignupSource, User, UserStatus
from platform.common.models.user import User as PlatformUser
from platform.main import create_app
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.accounts_support import build_test_clients, build_test_settings, issue_access_token
from tests.auth_support import RecordingProducer, role_claim


def _redis_url(redis_client) -> str:
    return redis_client._url or "redis://localhost:6379"


async def _seed_inviter(session_factory: async_sessionmaker, inviter_id: UUID) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add(
            User(
                id=inviter_id,
                email="provisioner@example.com",
                display_name="Provisioner",
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
                id=inviter_id,
                email="provisioner@example.com",
                display_name="Provisioner",
                status="active",
            )
        )
        await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_activation_event_is_emitted_once_per_first_activation_path(
    monkeypatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    verification_tokens: list[str] = []
    invitation_tokens: list[str] = []
    open_producer = RecordingProducer()
    open_settings = build_test_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_url=_redis_url(redis_client),
        signup_mode="open",
    )
    admin_token = issue_access_token(open_settings, uuid4(), [role_claim("workspace_admin")])

    async def capture_verification_email(
        user_id, email: str, token: str, display_name: str, notification_client=None
    ) -> None:
        del user_id, email, display_name, notification_client
        verification_tokens.append(token)

    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, open_producer),
    )
    monkeypatch.setattr(
        "platform.accounts.email.send_verification_email",
        capture_verification_email,
    )
    app = create_app(settings=open_settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            register = await client.post(
                "/api/v1/accounts/register",
                json={
                    "email": "provision-open@example.com",
                    "display_name": "Open User",
                    "password": "StrongP@ssw0rd!",
                },
            )
            verify = await client.post(
                "/api/v1/accounts/verify-email",
                json={"token": verification_tokens[0]},
            )
            suspend = await client.post(
                f"/api/v1/accounts/{verify.json()['user_id']}/suspend",
                json={"reason": "paused"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            reactivate = await client.post(
                f"/api/v1/accounts/{verify.json()['user_id']}/reactivate",
                json={"reason": "restored"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )

    activation_events = [
        event for event in open_producer.events if event["event_type"] == "accounts.user.activated"
    ]
    assert register.status_code == 202
    assert verify.status_code == 200
    assert suspend.status_code == 200
    assert reactivate.status_code == 200
    assert len(activation_events) == 1
    assert activation_events[0]["payload"]["email"] == "provision-open@example.com"

    approval_tokens: list[str] = []
    approval_producer = RecordingProducer()
    approval_settings = build_test_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_url=_redis_url(redis_client),
        signup_mode="admin_approval",
    )
    approval_admin = issue_access_token(
        approval_settings,
        uuid4(),
        [role_claim("workspace_admin")],
    )

    async def capture_approval_email(
        user_id, email: str, token: str, display_name: str, notification_client=None
    ) -> None:
        del user_id, email, display_name, notification_client
        approval_tokens.append(token)

    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, approval_producer),
    )
    monkeypatch.setattr(
        "platform.accounts.email.send_verification_email",
        capture_approval_email,
    )
    approval_app = create_app(settings=approval_settings)

    async with approval_app.router.lifespan_context(approval_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=approval_app),
            base_url="http://testserver",
        ) as client:
            await client.post(
                "/api/v1/accounts/register",
                json={
                    "email": "provision-approval@example.com",
                    "display_name": "Approval User",
                    "password": "StrongP@ssw0rd!",
                },
            )
            verified = await client.post(
                "/api/v1/accounts/verify-email",
                json={"token": approval_tokens[0]},
            )
            approved = await client.post(
                f"/api/v1/accounts/{verified.json()['user_id']}/approve",
                json={"reason": "approved"},
                headers={"Authorization": f"Bearer {approval_admin}"},
            )

    assert verified.json()["status"] == "pending_approval"
    assert approved.json()["status"] == "active"
    assert [
        event["event_type"]
        for event in approval_producer.events
        if event["event_type"] == "accounts.user.activated"
    ] == ["accounts.user.activated"]

    inviter_id = uuid4()
    await _seed_inviter(session_factory, inviter_id)
    invitation_producer = RecordingProducer()
    invitation_settings = build_test_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_url=_redis_url(redis_client),
    )
    invitation_admin = issue_access_token(
        invitation_settings,
        inviter_id,
        [role_claim("workspace_admin")],
    )

    async def capture_invitation_email(
        invitation_id, email: str, token: str, inviter_id, message, notification_client=None
    ) -> None:
        del invitation_id, email, inviter_id, message, notification_client
        invitation_tokens.append(token)

    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, invitation_producer),
    )
    monkeypatch.setattr(
        "platform.accounts.email.send_invitation_email",
        capture_invitation_email,
    )
    invitation_app = create_app(settings=invitation_settings)

    async with invitation_app.router.lifespan_context(invitation_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=invitation_app),
            base_url="http://testserver",
        ) as client:
            created = await client.post(
                "/api/v1/accounts/invitations",
                json={"email": "provision-invite@example.com", "roles": ["viewer"]},
                headers={"Authorization": f"Bearer {invitation_admin}"},
            )
            accepted = await client.post(
                f"/api/v1/accounts/invitations/{invitation_tokens[0]}/accept",
                json={
                    "token": invitation_tokens[0],
                    "display_name": "Invitee User",
                    "password": "StrongP@ssw0rd!",
                },
            )

    assert created.status_code == 201
    assert accepted.status_code == 201
    assert [
        event["event_type"]
        for event in invitation_producer.events
        if event["event_type"] == "accounts.user.activated"
    ] == ["accounts.user.activated"]
