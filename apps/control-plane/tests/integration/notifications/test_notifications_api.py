from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.models.user import User as PlatformUser
from platform.main import create_app
from platform.notifications.models import UserAlert
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.accounts_support import build_test_clients, issue_access_token
from tests.auth_support import RecordingProducer


async def _create_platform_user(
    session_factory: async_sessionmaker,
    *,
    user_id: UUID,
    email: str,
    display_name: str,
) -> PlatformUser:
    async with session_factory() as session:
        user = PlatformUser(
            id=user_id, email=email.lower(), display_name=display_name, status="active"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _seed_alert(
    session_factory: async_sessionmaker,
    *,
    user_id: UUID,
    title: str,
    read: bool,
    created_at: datetime,
) -> UserAlert:
    async with session_factory() as session:
        alert = UserAlert(
            user_id=user_id,
            interaction_id=None,
            source_reference={"type": "attention_request", "id": str(uuid4())},
            alert_type="attention_request",
            title=title,
            body=f"Body for {title}",
            urgency="medium",
            read=read,
            created_at=created_at,
            updated_at=created_at,
        )
        session.add(alert)
        await session.commit()
        await session.refresh(alert)
        return alert


def _build_settings(auth_settings, *, database_url: str, redis_client) -> object:
    return auth_settings.model_copy(
        update={
            "db": auth_settings.db.model_copy(update={"dsn": database_url}),
            "redis": auth_settings.redis.model_copy(
                update={
                    "url": redis_client._url or "redis://localhost:6379",
                    "test_mode": "standalone",
                }
            ),
        }
    )


def _auth_headers(settings, user_id: UUID) -> dict[str, str]:
    token = issue_access_token(settings, user_id, [])
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_alert_settings_endpoints_support_defaults_and_updates(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    settings = _build_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_client=redis_client,
    )
    user_id = uuid4()
    await _create_platform_user(
        session_factory,
        user_id=user_id,
        email="alerts@example.com",
        display_name="Alerts User",
    )
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            default_response = await client.get(
                "/api/v1/me/alert-settings",
                headers=_auth_headers(settings, user_id),
            )
            invalid_response = await client.put(
                "/api/v1/me/alert-settings",
                headers=_auth_headers(settings, user_id),
                json={
                    "state_transitions": ["any_to_failed"],
                    "delivery_method": "webhook",
                    "webhook_url": None,
                },
            )
            update_response = await client.put(
                "/api/v1/me/alert-settings",
                headers=_auth_headers(settings, user_id),
                json={
                    "state_transitions": ["any_to_failed"],
                    "delivery_method": "webhook",
                    "webhook_url": "https://hooks.example.com/alerts",
                },
            )
            fetch_updated = await client.get(
                "/api/v1/me/alert-settings",
                headers=_auth_headers(settings, user_id),
            )

    assert default_response.status_code == 200
    assert default_response.json()["delivery_method"] == "in_app"
    assert invalid_response.status_code == 422
    assert update_response.status_code == 200
    assert update_response.json()["delivery_method"] == "webhook"
    assert update_response.json()["webhook_url"] == "https://hooks.example.com/alerts"
    assert fetch_updated.json()["state_transitions"] == ["any_to_failed"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_alert_history_endpoints_list_mark_read_and_forbid_cross_user(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings,
    session_factory: async_sessionmaker,
    redis_client,
    migrated_database_url: str,
) -> None:
    producer = RecordingProducer()
    monkeypatch.setattr(
        "platform.main._build_clients",
        lambda resolved: build_test_clients(redis_client, producer),
    )
    settings = _build_settings(
        auth_settings,
        database_url=migrated_database_url,
        redis_client=redis_client,
    )
    primary_user = uuid4()
    other_user = uuid4()
    await _create_platform_user(
        session_factory,
        user_id=primary_user,
        email="primary@example.com",
        display_name="Primary",
    )
    await _create_platform_user(
        session_factory,
        user_id=other_user,
        email="other@example.com",
        display_name="Other",
    )
    now = datetime.now(UTC)
    newest = await _seed_alert(
        session_factory,
        user_id=primary_user,
        title="Newest alert",
        read=False,
        created_at=now,
    )
    await _seed_alert(
        session_factory,
        user_id=primary_user,
        title="Read alert",
        read=True,
        created_at=now - timedelta(minutes=1),
    )
    unread_second = await _seed_alert(
        session_factory,
        user_id=primary_user,
        title="Older unread",
        read=False,
        created_at=now - timedelta(minutes=2),
    )
    other_alert = await _seed_alert(
        session_factory,
        user_id=other_user,
        title="Other user alert",
        read=False,
        created_at=now - timedelta(minutes=3),
    )
    app = create_app(settings=settings)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            list_response = await client.get(
                "/api/v1/me/alerts",
                headers=_auth_headers(settings, primary_user),
                params={"read": "all", "limit": 2},
            )
            unread_response = await client.get(
                "/api/v1/me/alerts/unread-count",
                headers=_auth_headers(settings, primary_user),
            )
            mark_read = await client.patch(
                f"/api/v1/me/alerts/{newest.id}/read",
                headers=_auth_headers(settings, primary_user),
            )
            detail = await client.get(
                f"/api/v1/me/alerts/{unread_second.id}",
                headers=_auth_headers(settings, primary_user),
            )
            forbidden = await client.get(
                f"/api/v1/me/alerts/{other_alert.id}",
                headers=_auth_headers(settings, primary_user),
            )
            unread_after = await client.get(
                "/api/v1/me/alerts/unread-count",
                headers=_auth_headers(settings, primary_user),
            )

    assert list_response.status_code == 200
    body = list_response.json()
    assert [item["title"] for item in body["items"]] == ["Newest alert", "Read alert"]
    assert body["next_cursor"] is not None
    assert body["total_unread"] == 2
    assert unread_response.json() == {"count": 2}
    assert mark_read.status_code == 200
    assert mark_read.json()["read"] is True
    assert detail.status_code == 200
    assert detail.json()["id"] == str(unread_second.id)
    assert forbidden.status_code == 403
    assert unread_after.json() == {"count": 1}
    assert producer.events[-1]["event_type"] == "notifications.alert_read"
