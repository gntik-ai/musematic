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
    max_workspaces: int = 0,
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
                max_workspaces=max_workspaces,
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
async def test_workspace_crud_visibility_settings_and_isolation(
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
    other_id = uuid4()
    await _seed_user(
        session_factory,
        user_id=owner_id,
        email="owner@example.com",
        display_name="Owner",
        max_workspaces=2,
    )
    await _seed_user(
        session_factory,
        user_id=other_id,
        email="other@example.com",
        display_name="Other",
    )
    owner_token = issue_access_token(settings, owner_id, [role_claim("workspace_admin")])
    other_token = issue_access_token(settings, other_id, [role_claim("viewer")])

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
                json={"name": "Finance", "description": "Q4 planning"},
            )
            workspace_id = created.json()["id"]
            fleet_id = str(uuid4())
            policy_id = str(uuid4())
            connector_id = str(uuid4())
            set_visibility = await client.put(
                f"/api/v1/workspaces/{workspace_id}/visibility",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={
                    "visibility_agents": ["finance:*"],
                    "visibility_tools": ["tools:csv-reader"],
                },
            )
            get_visibility = await client.get(
                f"/api/v1/workspaces/{workspace_id}/visibility",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            update_settings = await client.patch(
                f"/api/v1/workspaces/{workspace_id}/settings",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={
                    "subscribed_agents": ["planner:*"],
                    "subscribed_fleets": [fleet_id],
                    "subscribed_policies": [policy_id],
                    "subscribed_connectors": [connector_id],
                },
            )
            get_settings = await client.get(
                f"/api/v1/workspaces/{workspace_id}/settings",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            fetched = await client.get(
                f"/api/v1/workspaces/{workspace_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            isolated = await client.get(
                f"/api/v1/workspaces/{workspace_id}",
                headers={"Authorization": f"Bearer {other_token}"},
            )
            updated = await client.patch(
                f"/api/v1/workspaces/{workspace_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"name": "Finance Ops"},
            )
            listed_active = await client.get(
                "/api/v1/workspaces",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            archived = await client.post(
                f"/api/v1/workspaces/{workspace_id}/archive",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            listed_archived = await client.get(
                "/api/v1/workspaces",
                headers={"Authorization": f"Bearer {owner_token}"},
                params={"status": "archived"},
            )
            restored = await client.post(
                f"/api/v1/workspaces/{workspace_id}/restore",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            rearchived = await client.post(
                f"/api/v1/workspaces/{workspace_id}/archive",
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            deleted = await client.delete(
                f"/api/v1/workspaces/{workspace_id}",
                headers={"Authorization": f"Bearer {owner_token}"},
            )

    assert created.status_code == 201
    assert set_visibility.status_code == 200
    assert get_visibility.json()["visibility_agents"] == ["finance:*"]
    assert update_settings.status_code == 200
    assert get_settings.json()["subscribed_agents"] == ["planner:*"]
    assert fetched.status_code == 200
    assert isolated.status_code == 404
    assert updated.json()["name"] == "Finance Ops"
    assert listed_active.json()["total"] == 1
    assert archived.json()["status"] == "archived"
    assert listed_archived.json()["total"] == 1
    assert restored.json()["status"] == "active"
    assert rearchived.json()["status"] == "archived"
    assert deleted.status_code == 202
    assert {event["event_type"] for event in producer.events} >= {
        "workspaces.workspace.created",
        "workspaces.workspace.updated",
        "workspaces.workspace.archived",
        "workspaces.workspace.restored",
        "workspaces.workspace.deleted",
        "workspaces.visibility_grant.updated",
    }
