from __future__ import annotations

import re
from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.notifications.dependencies import get_audit_chain_service
from platform.status_page.dependencies import enforce_subscribe_rate_limit, get_status_page_service
from platform.status_page.router import router
from platform.status_page.schemas import PlatformStatusSnapshotRead, SourceKind
from platform.status_page.service import StatusPageService
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

pytestmark = pytest.mark.integration


class _Repo:
    def __init__(self) -> None:
        self.subscriptions: list[SimpleNamespace] = []

    async def create_subscription(self, **kwargs: Any) -> SimpleNamespace:
        subscription = SimpleNamespace(
            id=uuid4(),
            channel=kwargs["channel"],
            target=kwargs["target"],
            scope_components=kwargs["scope_components"],
            confirmation_token_hash=kwargs.get("confirmation_token_hash"),
            unsubscribe_token_hash=kwargs.get("unsubscribe_token_hash"),
            confirmed_at=kwargs.get("confirmed_at"),
            health=kwargs.get("health", "pending"),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.subscriptions.append(subscription)
        return subscription

    async def get_subscription_by_confirmation_hash(self, token_hash: bytes):
        return next(
            (
                subscription
                for subscription in self.subscriptions
                if subscription.confirmation_token_hash == token_hash
            ),
            None,
        )

    async def get_subscription_by_unsubscribe_hash(self, token_hash: bytes):
        return next(
            (
                subscription
                for subscription in self.subscriptions
                if subscription.unsubscribe_token_hash == token_hash
            ),
            None,
        )

    async def confirm_subscription(self, subscription: SimpleNamespace) -> SimpleNamespace:
        subscription.confirmed_at = datetime.now(UTC)
        subscription.confirmation_token_hash = None
        subscription.health = "healthy"
        return subscription

    async def mark_unsubscribed(self, subscription: SimpleNamespace) -> SimpleNamespace:
        subscription.health = "unsubscribed"
        return subscription


class _Email:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, alert: Any, email: str, smtp_settings: object) -> None:
        del email, smtp_settings
        self.messages.append(str(alert.body))


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def append(self, payload: dict[str, Any]) -> None:
        self.entries.append(payload)


class _SnapshotService(StatusPageService):
    async def compose_current_snapshot(self) -> PlatformStatusSnapshotRead:
        return PlatformStatusSnapshotRead(
            generated_at=datetime.now(UTC),
            overall_state="operational",
            components=[],
            active_incidents=[],
            scheduled_maintenance=[],
            active_maintenance=None,
            recently_resolved_incidents=[],
            uptime_30d={},
            source_kind=SourceKind.manual,
            snapshot_id="manual-snapshot-1",
        )


def _build_app(service: StatusPageService, audit: _Audit) -> FastAPI:
    app = FastAPI()
    app.state.clients = {}
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[enforce_subscribe_rate_limit] = lambda: None
    app.dependency_overrides[get_status_page_service] = lambda: service
    app.dependency_overrides[get_audit_chain_service] = lambda: audit
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "superadmin-user",
        "roles": [{"role": "superadmin"}],
    }
    return app


def _tokens(body: str) -> tuple[str, str]:
    values = re.findall(r"^[A-Za-z0-9_-]{32,}$", body, flags=re.MULTILINE)
    assert len(values) >= 2
    return values[0], values[1]


@pytest.mark.asyncio
async def test_status_page_public_and_admin_actions_emit_audit_chain_entries() -> None:
    repo = _Repo()
    email = _Email()
    audit = _Audit()
    service = _SnapshotService(repository=repo, email_deliverer=email)
    app = _build_app(service, audit)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        subscribed = await client.post(
            "/api/v1/public/subscribe/email",
            json={"email": "audit@example.com", "scope_components": []},
        )
        confirmation_token, unsubscribe_token = _tokens(email.messages[0])
        confirmed = await client.get(
            "/api/v1/public/subscribe/email/confirm",
            params={"token": confirmation_token},
        )
        webhook = await client.post(
            "/api/v1/public/subscribe/webhook",
            json={
                "url": "https://receiver.example/status",
                "contact_email": "ops@example.com",
                "scope_components": ["control-plane-api"],
            },
        )
        unsubscribed = await client.get(
            "/api/v1/public/subscribe/email/unsubscribe",
            params={"token": unsubscribe_token},
        )
        regenerated = await client.post("/api/v1/internal/status_page/regenerate-fallback")

    assert subscribed.status_code == 202
    assert confirmed.status_code == 200
    assert webhook.status_code == 202
    assert unsubscribed.status_code == 200
    assert regenerated.status_code == 200
    assert [entry["event"] for entry in audit.entries] == [
        "status.subscription.confirmed",
        "status.subscription.webhook.rotated",
        "status.subscription.unsubscribed",
        "status.snapshot.manual_override",
    ]
