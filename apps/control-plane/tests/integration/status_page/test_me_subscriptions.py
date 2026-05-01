from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.notifications.deliverers.webhook_deliverer import WebhookDeliverer
from platform.notifications.dependencies import get_audit_chain_service
from platform.status_page.dependencies import get_status_page_service
from platform.status_page.me_router import router
from platform.status_page.service import StatusPageService
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

pytestmark = pytest.mark.integration


class _InMemoryMeSubscriptionRepo:
    def __init__(self) -> None:
        self.subscriptions: list[SimpleNamespace] = []
        self.dispatches: list[dict[str, Any]] = []

    async def list_user_subscriptions(
        self,
        *,
        user_id: UUID,
        workspace_id: UUID | None = None,
    ) -> list[SimpleNamespace]:
        return [
            subscription
            for subscription in self.subscriptions
            if subscription.user_id == user_id
            and (workspace_id is None or subscription.workspace_id == workspace_id)
        ]

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
            workspace_id=kwargs.get("workspace_id"),
            user_id=kwargs.get("user_id"),
            webhook_id=kwargs.get("webhook_id"),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.subscriptions.append(subscription)
        return subscription

    async def get_user_subscription(
        self,
        *,
        subscription_id: UUID,
        user_id: UUID,
    ) -> SimpleNamespace | None:
        return next(
            (
                subscription
                for subscription in self.subscriptions
                if subscription.id == subscription_id and subscription.user_id == user_id
            ),
            None,
        )

    async def get_subscription(self, subscription_id: UUID) -> SimpleNamespace | None:
        return next(
            (
                subscription
                for subscription in self.subscriptions
                if subscription.id == subscription_id
            ),
            None,
        )

    async def update_user_subscription(
        self,
        *,
        subscription_id: UUID,
        user_id: UUID,
        values: dict[str, Any],
    ) -> SimpleNamespace | None:
        subscription = await self.get_user_subscription(
            subscription_id=subscription_id,
            user_id=user_id,
        )
        if subscription is None:
            return None
        for key, value in values.items():
            setattr(subscription, key, value)
        subscription.updated_at = datetime.now(UTC)
        return subscription

    async def mark_unsubscribed(self, subscription: SimpleNamespace) -> SimpleNamespace:
        subscription.health = "unsubscribed"
        subscription.updated_at = datetime.now(UTC)
        return subscription

    async def list_confirmed_subscriptions_for_event(
        self,
        *,
        affected_components: list[str],
    ) -> list[SimpleNamespace]:
        affected = set(affected_components)
        return [
            subscription
            for subscription in self.subscriptions
            if subscription.confirmed_at is not None
            and subscription.health == "healthy"
            and (
                not affected
                or not subscription.scope_components
                or affected.intersection(subscription.scope_components)
            )
        ]

    async def insert_dispatch(self, **kwargs: Any) -> SimpleNamespace:
        self.dispatches.append(kwargs)
        return SimpleNamespace(id=uuid4(), **kwargs)


class _RecordingWebhookDeliverer(WebhookDeliverer):
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, dict[str, str]]] = []

    async def _post_signed(
        self,
        webhook_url: str,
        body: bytes,
        headers: dict[str, str],
        *,
        redirects_remaining: int = 3,
    ) -> httpx.Response:
        del redirects_remaining
        self.calls.append((webhook_url, body, headers))
        return httpx.Response(204, text="ok")


class _RecordingAuditChain:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    async def append(self, payload: dict[str, Any]) -> None:
        self.entries.append(payload)


def _build_app(
    service: StatusPageService,
    audit_chain: _RecordingAuditChain,
    current_user: dict[str, Any],
) -> tuple[FastAPI, dict[str, dict[str, Any]]]:
    state = {"current_user": current_user}
    app = FastAPI()
    app.state.clients = {}
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_status_page_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: state["current_user"]
    app.dependency_overrides[get_audit_chain_service] = lambda: audit_chain
    return app, state


@pytest.mark.asyncio
async def test_me_status_subscription_crud_webhook_ping_and_dispatch_stop() -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    repo = _InMemoryMeSubscriptionRepo()
    webhook = _RecordingWebhookDeliverer()
    audit_chain = _RecordingAuditChain()
    service = StatusPageService(repository=repo, webhook_deliverer=webhook)
    app, _state = _build_app(
        service,
        audit_chain,
        {
            "sub": str(user_id),
            "workspace_id": str(workspace_id),
        },
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        listed = await client.get("/api/v1/me/status-subscriptions")
        created = await client.post(
            "/api/v1/me/status-subscriptions",
            json={
                "channel": "webhook",
                "target": "https://example.com/status-webhook",
                "scope_components": ["control-plane-api"],
            },
        )
        patched = await client.patch(
            f"/api/v1/me/status-subscriptions/{created.json()['id']}",
            json={
                "target": "https://example.com/status-webhook-v2",
                "scope_components": ["reasoning-engine"],
            },
        )

    assert listed.status_code == 200
    assert listed.json() == {"items": []}
    assert created.status_code == 201
    created_body = created.json()
    assert created_body["health"] == "healthy"
    assert created_body["confirmed_at"] is not None
    assert len(webhook.calls) == 1
    assert webhook.calls[0][0] == "https://example.com/status-webhook"
    assert patched.status_code == 200
    assert patched.json()["target"] == "https://example.com/status-webhook-v2"
    assert patched.json()["scope_components"] == ["reasoning-engine"]

    sent = await service.dispatch_event(
        "incident.created",
        {
            "incident_id": str(uuid4()),
            "components_affected": ["reasoning-engine"],
        },
    )
    assert sent == 1
    assert len(repo.dispatches) == 1

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        deleted = await client.delete(f"/api/v1/me/status-subscriptions/{created_body['id']}")

    assert deleted.status_code == 200
    assert deleted.json()["status"] == "unsubscribed"

    sent_after_delete = await service.dispatch_event(
        "incident.created",
        {
            "incident_id": str(uuid4()),
            "components_affected": ["reasoning-engine"],
        },
    )
    assert sent_after_delete == 0
    assert [entry["event"] for entry in audit_chain.entries] == [
        "status.subscription.created",
        "status.subscription.updated",
        "status.subscription.unsubscribed",
    ]


@pytest.mark.asyncio
async def test_me_status_subscription_cross_user_attempts_return_403() -> None:
    owner_id = uuid4()
    other_user_id = uuid4()
    workspace_id = uuid4()
    repo = _InMemoryMeSubscriptionRepo()
    subscription = await repo.create_subscription(
        channel="email",
        target="owner@example.com",
        scope_components=[],
        confirmed_at=datetime.now(UTC),
        health="healthy",
        workspace_id=workspace_id,
        user_id=owner_id,
    )
    service = StatusPageService(repository=repo)
    app, _state = _build_app(
        service,
        _RecordingAuditChain(),
        {
            "sub": str(other_user_id),
            "workspace_id": str(workspace_id),
        },
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        patch = await client.patch(
            f"/api/v1/me/status-subscriptions/{subscription.id}",
            json={"scope_components": ["control-plane-api"]},
        )
        delete = await client.delete(f"/api/v1/me/status-subscriptions/{subscription.id}")

    assert patch.status_code == 403
    assert patch.json()["error"]["code"] == "status.subscription.forbidden"
    assert delete.status_code == 403
    assert delete.json()["error"]["code"] == "status.subscription.forbidden"
    assert subscription.health == "healthy"
