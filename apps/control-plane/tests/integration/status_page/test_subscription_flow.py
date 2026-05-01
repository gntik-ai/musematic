from __future__ import annotations

from datetime import UTC, datetime
from platform.notifications.deliverers.webhook_deliverer import WebhookDeliverer
from platform.notifications.models import DeliveryOutcome
from platform.status_page.dependencies import get_status_page_service
from platform.status_page.router import router
from platform.status_page.service import StatusPageService
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

pytestmark = pytest.mark.integration


class _InMemorySubscriptionRepo:
    def __init__(self) -> None:
        self.subscriptions: list[SimpleNamespace] = []
        self.dispatches: list[dict] = []

    async def create_subscription(self, **kwargs) -> SimpleNamespace:
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

    async def get_subscription_by_confirmation_hash(self, token_hash: bytes):
        return next(
            (
                subscription
                for subscription in self.subscriptions
                if subscription.confirmation_token_hash == token_hash
                and subscription.health == "pending"
            ),
            None,
        )

    async def get_subscription_by_unsubscribe_hash(self, token_hash: bytes):
        return next(
            (
                subscription
                for subscription in self.subscriptions
                if subscription.unsubscribe_token_hash == token_hash
                and subscription.health != "unsubscribed"
            ),
            None,
        )

    async def confirm_subscription(self, subscription):
        subscription.confirmed_at = datetime.now(UTC)
        subscription.health = "healthy"
        subscription.confirmation_token_hash = None
        return subscription

    async def mark_unsubscribed(self, subscription):
        subscription.health = "unsubscribed"
        return subscription

    async def rotate_unsubscribe_token(self, subscription, token_hash: bytes):
        subscription.unsubscribe_token_hash = token_hash
        return subscription

    async def list_confirmed_subscriptions_for_event(
        self,
        *,
        affected_components: list[str],
    ):
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

    async def insert_dispatch(self, **kwargs):
        self.dispatches.append(kwargs)
        return SimpleNamespace(id=uuid4(), **kwargs)


class _RecordingEmailDeliverer:
    def __init__(self) -> None:
        self.messages: list[tuple[object, str]] = []

    async def send(self, alert, email: str, smtp_settings: object) -> DeliveryOutcome:
        del smtp_settings
        self.messages.append((alert, email))
        return DeliveryOutcome.success


class _RecordingWebhookDeliverer(WebhookDeliverer):
    def __init__(self, *, response_status: int = 204) -> None:
        self.response_status = response_status
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
        return httpx.Response(self.response_status, text="ok")


def _build_app(service: StatusPageService) -> FastAPI:
    app = FastAPI()
    app.state.clients = {}
    app.include_router(router)
    app.dependency_overrides[get_status_page_service] = lambda: service
    return app


@pytest.mark.asyncio
async def test_email_confirm_opt_in() -> None:
    repo = _InMemorySubscriptionRepo()
    email = _RecordingEmailDeliverer()
    service = StatusPageService(repository=repo, email_deliverer=email)
    app = _build_app(service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        subscribe = await client.post(
            "/api/v1/public/subscribe/email",
            json={
                "email": "Dev@Example.COM",
                "scope_components": ["control-plane-api"],
            },
        )

        assert subscribe.status_code == 202
        assert subscribe.json()["message"].startswith("If the address is valid")
        assert repo.subscriptions[0].target == "dev@example.com"
        assert repo.subscriptions[0].health == "pending"
        assert repo.subscriptions[0].confirmed_at is None

        token = email.messages[0][0].body.splitlines()[2]
        confirm = await client.get(
            "/api/v1/public/subscribe/email/confirm",
            params={"token": token},
        )

    assert confirm.status_code == 200
    assert repo.subscriptions[0].health == "healthy"
    assert repo.subscriptions[0].confirmed_at is not None

    sent = await service.dispatch_event(
        "incident.created",
        {
            "incident_id": str(uuid4()),
            "title": "Control-plane incident",
            "components_affected": ["control-plane-api"],
            "public_status_base_url": "https://status.example.com",
        },
    )

    assert sent == 1
    assert repo.dispatches[0]["subscription_id"] == repo.subscriptions[0].id
    assert repo.dispatches[0]["event_kind"] == "incident.created"
    assert (
        "https://status.example.com/api/v1/public/subscribe/email/unsubscribe?token="
        in email.messages[-1][0].body
    )


@pytest.mark.asyncio
async def test_webhook_subscription_verifies_hmac_signed_test_ping() -> None:
    repo = _InMemorySubscriptionRepo()
    webhook = _RecordingWebhookDeliverer(response_status=204)
    service = StatusPageService(repository=repo, webhook_deliverer=webhook)
    app = _build_app(service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/public/subscribe/webhook",
            json={
                "url": "https://example.com/status-webhook",
                "contact_email": "ops@example.com",
                "scope_components": ["control-plane-api"],
            },
        )

    assert response.status_code == 202
    assert response.json()["verification_state"] == "healthy"
    assert repo.subscriptions[0].health == "healthy"
    assert repo.subscriptions[0].confirmed_at is not None
    assert webhook.calls[0][0] == "https://example.com/status-webhook"
    assert webhook.calls[0][1].startswith(b"{")
    assert webhook.calls[0][2]["X-Musematic-Signature"].startswith("sha256=")
    assert webhook.calls[0][2]["X-Musematic-Idempotency-Key"]


@pytest.mark.asyncio
async def test_webhook_subscription_failed_test_ping_is_not_confirmed() -> None:
    repo = _InMemorySubscriptionRepo()
    webhook = _RecordingWebhookDeliverer(response_status=410)
    service = StatusPageService(repository=repo, webhook_deliverer=webhook)
    app = _build_app(service)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/public/subscribe/webhook",
            json={
                "url": "https://example.com/status-webhook",
                "scope_components": ["control-plane-api"],
            },
        )

    assert response.status_code == 202
    assert response.json()["verification_state"] == "failed"
    assert repo.subscriptions[0].health == "unhealthy"
    assert repo.subscriptions[0].confirmed_at is None
