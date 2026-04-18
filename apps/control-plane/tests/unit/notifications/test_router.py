from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.notifications.dependencies import get_notifications_service
from platform.notifications.exceptions import AlertAuthorizationError, AlertNotFoundError
from platform.notifications.models import DeliveryMethod
from platform.notifications.router import router as notifications_router
from platform.notifications.schemas import (
    AlertListResponse,
    UnreadCountResponse,
    UserAlertDetail,
    UserAlertRead,
    UserAlertSettingsRead,
)
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI


class AlertServiceStub:
    def __init__(self, user_id: UUID) -> None:
        now = datetime.now(UTC)
        self.user_id = user_id
        self.settings = UserAlertSettingsRead(
            id=uuid4(),
            user_id=user_id,
            state_transitions=["any_to_failed"],
            delivery_method=DeliveryMethod.in_app,
            webhook_url=None,
            created_at=now,
            updated_at=now,
        )
        self.alert = UserAlertRead(
            id=uuid4(),
            alert_type="attention_request",
            title="Attention requested",
            body="Review needed",
            urgency="high",
            read=False,
            interaction_id=None,
            source_reference={"type": "attention_request", "id": str(uuid4())},
            created_at=now,
            updated_at=now,
        )
        self.calls: list[tuple[str, object]] = []
        self.detail_error: Exception | None = None

    async def get_or_default_settings(self, user_id: UUID) -> UserAlertSettingsRead:
        self.calls.append(("get_settings", user_id))
        return self.settings

    async def upsert_settings(self, user_id: UUID, data) -> UserAlertSettingsRead:
        self.calls.append(("upsert_settings", (user_id, data.delivery_method)))
        return self.settings.model_copy(
            update={
                "delivery_method": data.delivery_method,
                "webhook_url": str(data.webhook_url) if data.webhook_url else None,
            }
        )

    async def list_alerts(
        self, user_id: UUID, *, read_filter: str, cursor: str | None, limit: int
    ) -> AlertListResponse:
        self.calls.append(("list_alerts", (user_id, read_filter, cursor, limit)))
        return AlertListResponse(items=[self.alert], next_cursor="cursor-1", total_unread=1)

    async def get_unread_count(self, user_id: UUID) -> UnreadCountResponse:
        self.calls.append(("get_unread_count", user_id))
        return UnreadCountResponse(count=1)

    async def mark_alert_read(self, alert_id: UUID, user_id: UUID) -> UserAlertRead:
        self.calls.append(("mark_alert_read", (alert_id, user_id)))
        return self.alert.model_copy(update={"id": alert_id, "read": True})

    async def get_alert(self, alert_id: UUID, user_id: UUID) -> UserAlertDetail:
        self.calls.append(("get_alert", (alert_id, user_id)))
        if self.detail_error is not None:
            raise self.detail_error
        return UserAlertDetail(
            **self.alert.model_dump(exclude={"id"}),
            id=alert_id,
            delivery_outcome=None,
        )


def build_app(service: AlertServiceStub, current_user: dict[str, object]) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)

    async def _current_user() -> dict[str, object]:
        return current_user

    async def _service() -> AlertServiceStub:
        return service

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_notifications_service] = _service
    app.include_router(notifications_router, prefix="/api/v1")
    return app


@pytest.mark.asyncio
async def test_notifications_router_exposes_settings_and_alert_endpoints() -> None:
    user_id = uuid4()
    service = AlertServiceStub(user_id)
    app = build_app(service, {"sub": str(user_id)})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        get_settings = await client.get("/api/v1/me/alert-settings")
        put_settings = await client.put(
            "/api/v1/me/alert-settings",
            json={
                "state_transitions": ["any_to_failed"],
                "delivery_method": "email",
                "webhook_url": None,
            },
        )
        list_alerts = await client.get("/api/v1/me/alerts", params={"read": "unread", "limit": 5})
        unread = await client.get("/api/v1/me/alerts/unread-count")
        mark_read = await client.patch(f"/api/v1/me/alerts/{service.alert.id}/read")
        detail = await client.get(f"/api/v1/me/alerts/{service.alert.id}")

    assert get_settings.status_code == 200
    assert put_settings.status_code == 200
    assert put_settings.json()["delivery_method"] == "email"
    assert list_alerts.status_code == 200
    assert list_alerts.json()["next_cursor"] == "cursor-1"
    assert unread.json() == {"count": 1}
    assert mark_read.json()["read"] is True
    assert detail.json()["id"] == str(service.alert.id)
    assert [name for name, _ in service.calls] == [
        "get_settings",
        "upsert_settings",
        "list_alerts",
        "get_unread_count",
        "mark_alert_read",
        "get_alert",
    ]


@pytest.mark.asyncio
async def test_notifications_router_surfaces_domain_errors() -> None:
    user_id = uuid4()
    service = AlertServiceStub(user_id)
    service.detail_error = AlertAuthorizationError()
    app = build_app(service, {"sub": str(user_id)})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        forbidden = await client.get(f"/api/v1/me/alerts/{service.alert.id}")

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "ALERT_FORBIDDEN"

    service.detail_error = AlertNotFoundError(service.alert.id)
    app = build_app(service, {"sub": str(user_id)})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        missing = await client.get(f"/api/v1/me/alerts/{service.alert.id}")

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "ALERT_NOT_FOUND"
