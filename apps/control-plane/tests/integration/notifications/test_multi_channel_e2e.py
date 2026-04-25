from __future__ import annotations

import hashlib
import hmac
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from platform.accounts.models import SignupSource, User, UserStatus
from platform.accounts.repository import AccountsRepository
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.models.workspace import Workspace
from platform.interactions.events import AttentionRequestedPayload
from platform.notifications.channel_router import ChannelDelivererRegistry, ChannelRouter
from platform.notifications.deliverers.email_deliverer import EmailDeliverer
from platform.notifications.deliverers.webhook_deliverer import WebhookDeliverer
from platform.notifications.models import DeliveryMethod, DeliveryOutcome, WebhookDelivery
from platform.notifications.repository import NotificationsRepository
from platform.notifications.schemas import (
    ChannelConfigCreate,
    ChannelConfigUpdate,
    OutboundWebhookCreate,
    QuietHoursConfig,
)
from platform.notifications.service import AlertService
from platform.notifications.webhooks_service import OutboundWebhookService
from platform.notifications.workers.webhook_retry_worker import run_webhook_retry_scan
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.auth_support import RecordingProducer


class _RecordingEmailDeliverer(EmailDeliverer):
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send(self, alert, recipient_email, smtp_settings=None):
        self.calls.append(
            {
                "alert": alert,
                "recipient_email": recipient_email,
                "smtp_settings": smtp_settings,
            }
        )
        return DeliveryOutcome.success


class _AllowDlp:
    async def scan_outbound(self, **kwargs: Any) -> dict[str, str]:
        del kwargs
        return {"action": "allow"}


class _AllowResidency:
    async def resolve_region_for_url(self, url: str) -> str | None:
        del url
        return None

    async def check_egress(self, workspace_id: UUID, region: str | None) -> bool:
        del workspace_id, region
        return True


class _SecretProvider:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, str]] = {}

    async def write_secret(self, path: str, payload: dict[str, Any]) -> None:
        self.values[path] = {key: str(value) for key, value in payload.items()}

    async def read_secret(self, path: str) -> dict[str, str]:
        return self.values[path]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_us1_email_channel_with_quiet_hours(
    auth_settings: PlatformSettings,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: AsyncRedisClient,
) -> None:
    settings = _settings(auth_settings, multi_channel=True)
    email = _RecordingEmailDeliverer()

    async with session_factory() as session:
        user = await _create_user(session, email="multi-channel@example.com")
        service = _alert_service(session, settings, redis_client, email)
        channel = await service.create_channel_config(
            user.id,
            ChannelConfigCreate(
                channel_type=DeliveryMethod.email,
                target=user.email,
                display_name="Primary email",
                alert_type_filter=["attention_request"],
                quiet_hours=QuietHoursConfig(start="00:00", end="23:59", timezone="UTC"),
            ),
        )
        token = str(email.calls[-1]["alert"].body).rsplit(": ", 1)[1]
        verified = await service.verify_channel_config(user.id, channel.id, token)

        await service.process_attention_request(_attention(user.email, "medium"))
        await service.update_channel_config(
            user.id,
            verified.id,
            ChannelConfigUpdate(quiet_hours=None),
        )
        await service.process_attention_request(_attention(user.email, "medium"))
        await service.update_channel_config(
            user.id,
            verified.id,
            ChannelConfigUpdate(
                quiet_hours=QuietHoursConfig(start="00:00", end="23:59", timezone="UTC")
            ),
        )
        await service.process_attention_request(_attention(user.email, "critical"))

    delivered_alerts = [
        call["alert"]
        for call in email.calls
        if call["alert"].alert_type == "attention_request"
    ]
    assert [alert.urgency for alert in delivered_alerts] == ["medium", "critical"]
    assert all(call["recipient_email"] == user.email for call in email.calls)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_idempotency_hmac_and_retry_round_trip(
    auth_settings: PlatformSettings,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: AsyncRedisClient,
) -> None:
    settings = _settings(auth_settings, allow_http=True)
    secrets = _SecretProvider()

    async with session_factory() as session:
        user = await _create_user(session, email="webhook-admin@example.com")
        workspace = await _create_workspace(session, user.id)
        repo = NotificationsRepository(session)
        webhook_service = OutboundWebhookService(
            repo=repo,
            settings=settings,
            secrets=secrets,
            residency_service=_AllowResidency(),
            dlp_service=_AllowDlp(),
            deliverer=WebhookDeliverer(),
        )
        router = ChannelRouter(
            repo=repo,
            accounts_repo=AccountsRepository(session),
            workspaces_service=None,
            dlp_service=_AllowDlp(),
            residency_service=_AllowResidency(),
            secrets=secrets,
            audit_chain=SimpleNamespace(),
            producer=None,
            settings=settings,
            deliverers=ChannelDelivererRegistry(
                email=EmailDeliverer(),
                webhook=WebhookDeliverer(),
            ),
        )

        async with _receiver([204, 204, 204, 204]) as first_receiver:
            webhook = await webhook_service.create(
                OutboundWebhookCreate(
                    workspace_id=workspace.id,
                    name="Primary receiver",
                    url=first_receiver.url,
                    event_types=["execution.failed"],
                ),
                actor_id=user.id,
            )
            unique_event_ids = [uuid4() for _ in range(4)]
            first_result = await router.route_workspace_event(
                {"event_id": unique_event_ids[0], "event_type": "execution.failed"},
                workspace.id,
            )
            for event_id in unique_event_ids[1:]:
                await router.route_workspace_event(
                    {"event_id": event_id, "event_type": "execution.failed"},
                    workspace.id,
                )
            duplicate_result = await router.route_workspace_event(
                {"event_id": unique_event_ids[0], "event_type": "execution.failed"},
                workspace.id,
            )

            assert first_result[0].delivery_id == duplicate_result[0].delivery_id
            assert len(first_receiver.requests) == 4
            assert _all_signatures_valid(first_receiver.requests, webhook.signing_secret)
            assert len({request["idempotency_key"] for request in first_receiver.requests}) == 4

        async with _receiver([503, 503, 204]) as retry_receiver:
            retry_webhook = await webhook_service.create(
                OutboundWebhookCreate(
                    workspace_id=workspace.id,
                    name="Retry receiver",
                    url=retry_receiver.url,
                    event_types=["execution.retry"],
                    retry_policy={
                        "max_retries": 3,
                        "backoff_seconds": [0, 0, 0],
                        "total_window_seconds": 86_400,
                    },
                ),
                actor_id=user.id,
            )
            retry_result = await router.route_workspace_event(
                {"event_id": uuid4(), "event_type": "execution.retry"},
                workspace.id,
            )
            await run_webhook_retry_scan(
                repo=repo,
                redis=redis_client,
                secrets=secrets,
                deliverer=WebhookDeliverer(),
                settings=settings,
            )
            await run_webhook_retry_scan(
                repo=repo,
                redis=redis_client,
                secrets=secrets,
                deliverer=WebhookDeliverer(),
                settings=settings,
            )
            delivery = await session.get(WebhookDelivery, retry_result[0].delivery_id)
            assert delivery is not None
            assert delivery.status == "delivered"
            assert delivery.attempts == 3
            assert [request["status"] for request in retry_receiver.requests] == [503, 503, 204]
            assert _all_signatures_valid(retry_receiver.requests, retry_webhook.signing_secret)
            assert len({request["idempotency_key"] for request in retry_receiver.requests}) == 1


def _settings(
    auth_settings: PlatformSettings,
    *,
    multi_channel: bool = False,
    allow_http: bool = False,
) -> PlatformSettings:
    return auth_settings.model_copy(
        update={
            "notifications": auth_settings.notifications.model_copy(
                update={
                    "multi_channel_enabled": multi_channel,
                    "allow_http_webhooks": allow_http,
                    "webhook_default_backoff_seconds": [0, 0, 0],
                }
            )
        }
    )


def _alert_service(
    session: AsyncSession,
    settings: PlatformSettings,
    redis_client: AsyncRedisClient,
    email: _RecordingEmailDeliverer,
) -> AlertService:
    repo = NotificationsRepository(session)
    return AlertService(
        repo=repo,
        accounts_repo=AccountsRepository(session),
        workspaces_service=SimpleNamespace(),
        redis=redis_client,
        producer=RecordingProducer(),
        settings=settings,
        email_deliverer=email,
        webhook_deliverer=WebhookDeliverer(),
        channel_router=ChannelRouter(
            repo=repo,
            accounts_repo=AccountsRepository(session),
            workspaces_service=None,
            dlp_service=_AllowDlp(),
            residency_service=_AllowResidency(),
            secrets=_SecretProvider(),
            audit_chain=SimpleNamespace(),
            producer=RecordingProducer(),
            settings=settings,
            deliverers=ChannelDelivererRegistry(email=email, webhook=WebhookDeliverer()),
        ),
    )


async def _create_user(session: AsyncSession, *, email: str) -> User:
    user = await AccountsRepository(session).create_user(
        email=email,
        display_name=email.split("@", 1)[0],
        status=UserStatus.active,
        signup_source=SignupSource.self_registration,
    )
    await session.flush()
    return user


async def _create_workspace(session: AsyncSession, owner_id: UUID) -> Workspace:
    workspace = Workspace(
        id=uuid4(),
        name=f"notifications-{uuid4().hex}",
        owner_id=owner_id,
        settings={},
    )
    session.add(workspace)
    await session.flush()
    return workspace


def _attention(target_identity: str, urgency: str) -> AttentionRequestedPayload:
    return AttentionRequestedPayload(
        request_id=uuid4(),
        workspace_id=uuid4(),
        source_agent_fqn="notifications:test-agent",
        target_identity=target_identity,
        urgency=urgency,
        related_interaction_id=None,
        related_goal_id=None,
        context_summary=f"{urgency} attention request",
    )


@asynccontextmanager
async def _receiver(statuses: list[int]) -> AsyncIterator[SimpleNamespace]:
    requests: list[dict[str, Any]] = []

    async def _handle(request: web.Request) -> web.Response:
        body = await request.read()
        status = statuses.pop(0)
        requests.append(
            {
                "body": body,
                "headers": dict(request.headers),
                "status": status,
                "idempotency_key": request.headers["X-Musematic-Idempotency-Key"],
            }
        )
        return web.Response(status=status, text=f"status={status}")

    app = web.Application()
    app.router.add_post("/events", _handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = _free_port()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        yield SimpleNamespace(url=f"http://127.0.0.1:{port}/events", requests=requests)
    finally:
        await runner.cleanup()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _all_signatures_valid(requests: list[dict[str, Any]], secret: str) -> bool:
    return all(
        _signature_valid(request["headers"], request["body"], secret)
        for request in requests
    )


def _signature_valid(headers: dict[str, str], body: bytes, secret: str) -> bool:
    timestamp = headers["X-Musematic-Timestamp"]
    signed = f"{timestamp}.".encode("ascii") + body
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(headers["X-Musematic-Signature"], f"sha256={expected}")
