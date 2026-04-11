from __future__ import annotations

from datetime import UTC, datetime
from platform.accounts.events import AccountsEventType
from platform.accounts.models import SignupSource, User, UserStatus
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.common.models.user import User as PlatformUser
from platform.main import create_app
from platform.workspaces.consumer import WorkspacesConsumer
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.accounts_support import build_test_clients, build_test_settings, issue_access_token
from tests.auth_support import RecordingProducer, role_claim


def _redis_url(redis_client) -> str:
    return redis_client._url or "redis://localhost:6379"


async def _seed_user(
    session_factory: async_sessionmaker,
    *,
    user_id: UUID,
    email: str,
    display_name: str,
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add(
            User(
                id=user_id,
                email=email,
                display_name=display_name,
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
                email=email,
                display_name=display_name,
                status="active",
            )
        )
        await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_default_workspace_provisioning_is_idempotent(
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
    user_id = uuid4()
    await _seed_user(
        session_factory,
        user_id=user_id,
        email="activated@example.com",
        display_name="Activated User",
    )

    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    app = create_app(settings=settings)
    consumer = WorkspacesConsumer(
        settings=settings,
        redis_client=redis_client,
        producer=producer,
    )
    envelope = EventEnvelope(
        event_type=AccountsEventType.user_activated.value,
        source="platform.accounts",
        correlation_context=CorrelationContext(correlation_id=uuid4()),
        payload={
            "user_id": str(user_id),
            "email": "activated@example.com",
            "display_name": "Activated User",
            "signup_source": SignupSource.self_registration.value,
        },
    )
    token = issue_access_token(settings, user_id, [role_claim("workspace_admin")])

    async with app.router.lifespan_context(app):
        await consumer.handle_event(envelope)
        await consumer.handle_event(envelope)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            listed = await client.get(
                "/api/v1/workspaces",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["is_default"] is True
    assert listed.json()["items"][0]["name"] == "Activated User's Workspace"
