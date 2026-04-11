from __future__ import annotations

from platform.main import create_app
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.accounts_support import build_test_clients, build_test_settings, issue_access_token
from tests.auth_support import RecordingProducer, role_claim


def _redis_url(redis_client) -> str:
    return redis_client._url or "redis://localhost:6379"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_can_approve_and_reject_pending_accounts(
    monkeypatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    del session_factory
    producer = RecordingProducer()
    sent_tokens: list[str] = []
    settings = build_test_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_url=_redis_url(redis_client),
        signup_mode="admin_approval",
    )
    admin_token = issue_access_token(settings, uuid4(), [role_claim("workspace_admin")])

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
            for email in ("approve@example.com", "reject@example.com"):
                await client.post(
                    "/api/v1/accounts/register",
                    json={
                        "email": email,
                        "display_name": email.split("@")[0],
                        "password": "StrongP@ssw0rd!",
                    },
                )

            first_verify = await client.post(
                "/api/v1/accounts/verify-email",
                json={"token": sent_tokens[0]},
            )
            second_verify = await client.post(
                "/api/v1/accounts/verify-email",
                json={"token": sent_tokens[1]},
            )
            pending = await client.get(
                "/api/v1/accounts/pending-approvals",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            approved = await client.post(
                f"/api/v1/accounts/{first_verify.json()['user_id']}/approve",
                json={"reason": "approved"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            rejected = await client.post(
                f"/api/v1/accounts/{second_verify.json()['user_id']}/reject",
                json={"reason": "rejected"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            double_approve = await client.post(
                f"/api/v1/accounts/{first_verify.json()['user_id']}/approve",
                json={"reason": "approved twice"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )

    assert first_verify.json()["status"] == "pending_approval"
    assert second_verify.json()["status"] == "pending_approval"
    assert pending.status_code == 200
    assert pending.json()["total"] == 2
    assert approved.status_code == 200
    assert approved.json()["status"] == "active"
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "archived"
    assert double_approve.status_code == 409
    assert double_approve.json()["error"]["code"] == "INVALID_TRANSITION"
    assert "accounts.user.approved" in [event["event_type"] for event in producer.events]
    assert "accounts.user.rejected" in [event["event_type"] for event in producer.events]
    assert "accounts.user.activated" in [event["event_type"] for event in producer.events]
