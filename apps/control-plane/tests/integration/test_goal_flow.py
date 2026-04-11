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
async def test_goal_flow_and_invalid_transition(
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
    owner_id = uuid4()
    await _seed_user(
        session_factory,
        user_id=owner_id,
        email="owner@example.com",
        display_name="Owner",
    )
    owner_token = issue_access_token(settings, owner_id, [role_claim("workspace_admin")])

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
            created = await client.post(
                "/api/v1/workspaces",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"name": "Goals Space"},
            )
            workspace_id = created.json()["id"]
            goal = await client.post(
                f"/api/v1/workspaces/{workspace_id}/goals",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"title": "Ship Q4 analysis", "description": "Run reports"},
            )
            goal_id = goal.json()["id"]
            listed = await client.get(
                f"/api/v1/workspaces/{workspace_id}/goals",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            fetched = await client.get(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            in_progress = await client.patch(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"status": "in_progress"},
            )
            completed = await client.patch(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"status": "completed"},
            )
            invalid = await client.patch(
                f"/api/v1/workspaces/{workspace_id}/goals/{goal_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"status": "in_progress"},
            )

    assert goal.status_code == 201
    assert listed.json()["total"] == 1
    assert fetched.status_code == 200
    assert in_progress.json()["status"] == "in_progress"
    assert completed.json()["status"] == "completed"
    assert invalid.status_code == 409
    assert {event["event_type"] for event in producer.events} >= {
        "workspaces.goal.created",
        "workspaces.goal.status_changed",
    }
