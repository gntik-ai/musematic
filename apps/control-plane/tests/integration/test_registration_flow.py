from __future__ import annotations

from platform.accounts.models import User, UserStatus
from platform.main import create_app

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.accounts_support import build_test_clients, build_test_settings
from tests.auth_support import RecordingProducer


def _redis_url(redis_client) -> str:
    return redis_client._url or "redis://localhost:6379"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_open_signup_registration_verify_and_resend_rate_limit(
    monkeypatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    sent_tokens: list[str] = []
    settings = build_test_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_url=_redis_url(redis_client),
        signup_mode="open",
    )

    async def capture_verification_email(
        user_id, email: str, token: str, display_name: str, notification_client=None
    ) -> None:
        del user_id, email, display_name, notification_client
        sent_tokens.append(token)

    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    monkeypatch.setattr(
        "platform.accounts.email.send_verification_email",
        capture_verification_email,
    )
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            register = await client.post(
                "/api/v1/accounts/register",
                json={
                    "email": "user@example.com",
                    "display_name": "Jane Smith",
                    "password": "StrongP@ssw0rd!",
                },
            )
            assert register.status_code == 202
            assert len(sent_tokens) == 1

            for _ in range(3):
                response = await client.post(
                    "/api/v1/accounts/resend-verification",
                    json={"email": "user@example.com"},
                )
                assert response.status_code == 202

            rate_limited = await client.post(
                "/api/v1/accounts/resend-verification",
                json={"email": "user@example.com"},
            )
            verify = await client.post(
                "/api/v1/accounts/verify-email",
                json={"token": sent_tokens[0]},
            )

    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == "user@example.com"))

    assert rate_limited.status_code == 429
    assert rate_limited.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert verify.status_code == 200
    assert verify.json()["status"] == UserStatus.active.value
    assert user is not None
    assert user.status == UserStatus.active
    assert user.email_verified_at is not None
    assert user.activated_at is not None
    assert [event["event_type"] for event in producer.events] == [
        "accounts.user.registered",
        "accounts.user.email_verified",
        "accounts.user.activated",
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_approval_mode_stops_after_email_verification(
    monkeypatch,
    auth_settings,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    sent_tokens: list[str] = []
    settings = build_test_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_url=_redis_url(redis_client),
        signup_mode="admin_approval",
    )

    async def capture_verification_email(
        user_id, email: str, token: str, display_name: str, notification_client=None
    ) -> None:
        del user_id, email, display_name, notification_client
        sent_tokens.append(token)

    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    monkeypatch.setattr(
        "platform.accounts.email.send_verification_email",
        capture_verification_email,
    )
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            register = await client.post(
                "/api/v1/accounts/register",
                json={
                    "email": "approval@example.com",
                    "display_name": "Approval User",
                    "password": "StrongP@ssw0rd!",
                },
            )
            verify = await client.post(
                "/api/v1/accounts/verify-email",
                json={"token": sent_tokens[0]},
            )

    assert register.status_code == 202
    assert verify.status_code == 200
    assert verify.json()["status"] == UserStatus.pending_approval.value
    assert [event["event_type"] for event in producer.events] == [
        "accounts.user.registered",
        "accounts.user.email_verified",
    ]
