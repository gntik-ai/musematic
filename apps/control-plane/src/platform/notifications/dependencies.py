from __future__ import annotations

from platform.accounts.repository import AccountsRepository
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.common.secret_provider import HealthStatus, SecretProvider
from platform.notifications.channel_router import (
    AuditChainService,
    ChannelDelivererRegistry,
    ChannelRouter,
    DlpService,
    ResidencyService,
)
from platform.notifications.deliverers.email_deliverer import EmailDeliverer
from platform.notifications.deliverers.slack_deliverer import SlackDeliverer
from platform.notifications.deliverers.sms_deliverer import SmsDeliverer
from platform.notifications.deliverers.teams_deliverer import TeamsDeliverer
from platform.notifications.deliverers.webhook_deliverer import WebhookDeliverer
from platform.notifications.models import DeliveryMethod
from platform.notifications.repository import NotificationsRepository
from platform.notifications.service import AlertService
from platform.notifications.webhooks_service import OutboundWebhookService
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.service import WorkspacesService
from typing import Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


class NoopAuditChainService:
    async def append(self, payload: dict[str, Any]) -> None:
        del payload


class AllowAllDlpService:
    async def scan_outbound(
        self,
        *,
        payload: dict[str, Any],
        workspace_id: object | None,
        channel_type: str,
    ) -> object:
        del payload, workspace_id, channel_type
        return {"action": "allow"}


class AllowAllResidencyService:
    async def resolve_region_for_url(self, url: str) -> str | None:
        del url
        return None

    async def check_egress(self, workspace_id: object, region: str | None) -> bool:
        del workspace_id, region
        return True


class InMemorySecretProvider:
    def __init__(self) -> None:
        self._values: dict[str, dict[str, str]] = {}

    async def get(self, path: str, key: str = "value") -> str:
        return self._values.get(path, {}).get(key, "")

    async def put(self, path: str, values: dict[str, str]) -> None:
        self._values[path] = dict(values)

    async def flush_cache(self, path: str | None = None) -> None:
        del path

    async def delete_version(self, path: str, version: int) -> None:
        del path, version

    async def list_versions(self, path: str) -> list[int]:
        del path
        return [1]

    async def health_check(self) -> HealthStatus:
        return HealthStatus(status="green", auth_method="memory")

    async def read_secret(self, path: str) -> dict[str, Any]:
        return dict(self._values.get(path, {}))

    async def write_secret(self, path: str, payload: dict[str, Any]) -> None:
        self._values[path] = {key: str(value) for key, value in payload.items()}


def build_notifications_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    redis_client: AsyncRedisClient,
    producer: EventProducer | None,
    workspaces_service: WorkspacesService | None,
    channel_router: ChannelRouter | None = None,
    secret_provider: SecretProvider | None = None,
) -> AlertService:
    return AlertService(
        repo=NotificationsRepository(session),
        accounts_repo=AccountsRepository(session),
        workspaces_service=workspaces_service,
        redis=redis_client,
        producer=producer,
        settings=settings,
        email_deliverer=EmailDeliverer(),
        webhook_deliverer=WebhookDeliverer(),
        channel_router=channel_router,
        sms_deliverer=SmsDeliverer(
            redis=redis_client,
            secrets=secret_provider or InMemorySecretProvider(),
            settings=settings,
        ),
    )


def get_audit_chain_service(request: Request) -> AuditChainService:
    return cast(
        AuditChainService,
        getattr(request.app.state, "audit_chain_service", None) or NoopAuditChainService(),
    )


def get_dlp_service(request: Request) -> DlpService:
    return cast(
        DlpService,
        getattr(request.app.state, "dlp_service", None) or AllowAllDlpService(),
    )


def get_residency_service(request: Request) -> ResidencyService:
    return cast(
        ResidencyService,
        getattr(request.app.state, "residency_service", None) or AllowAllResidencyService(),
    )


def get_secret_provider(request: Request) -> SecretProvider:
    return cast(
        SecretProvider,
        getattr(request.app.state, "secret_provider", None) or InMemorySecretProvider(),
    )


def get_deliverer_registry(
    request: Request,
    secret_provider: SecretProvider = Depends(get_secret_provider),
) -> ChannelDelivererRegistry:
    settings = _get_settings(request)
    redis_client = _get_redis(request)
    return ChannelDelivererRegistry(
        email=EmailDeliverer(),
        webhook=WebhookDeliverer(),
        extras={
            DeliveryMethod.slack: SlackDeliverer(),
            DeliveryMethod.teams: TeamsDeliverer(),
            DeliveryMethod.sms: SmsDeliverer(
                redis=redis_client,
                secrets=secret_provider,
                settings=settings,
            ),
        },
    )


async def get_channel_router(
    request: Request,
    session: AsyncSession = Depends(get_db),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
    dlp_service: DlpService = Depends(get_dlp_service),
    residency_service: ResidencyService = Depends(get_residency_service),
    secret_provider: SecretProvider = Depends(get_secret_provider),
    deliverers: ChannelDelivererRegistry = Depends(get_deliverer_registry),
) -> ChannelRouter:
    return ChannelRouter(
        repo=NotificationsRepository(session),
        accounts_repo=AccountsRepository(session),
        workspaces_service=workspaces_service,
        dlp_service=dlp_service,
        residency_service=residency_service,
        secrets=secret_provider,
        audit_chain=audit_chain,
        producer=_get_producer(request),
        settings=_get_settings(request),
        deliverers=deliverers,
    )


async def get_outbound_webhook_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    dlp_service: DlpService = Depends(get_dlp_service),
    residency_service: ResidencyService = Depends(get_residency_service),
    secret_provider: SecretProvider = Depends(get_secret_provider),
) -> OutboundWebhookService:
    return OutboundWebhookService(
        repo=NotificationsRepository(session),
        settings=_get_settings(request),
        secrets=secret_provider,
        residency_service=residency_service,
        dlp_service=dlp_service,
        deliverer=WebhookDeliverer(),
    )


async def get_notifications_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
    channel_router: ChannelRouter = Depends(get_channel_router),
    secret_provider: SecretProvider = Depends(get_secret_provider),
) -> AlertService:
    return build_notifications_service(
        session=session,
        settings=_get_settings(request),
        redis_client=_get_redis(request),
        producer=_get_producer(request),
        workspaces_service=workspaces_service,
        channel_router=channel_router,
        secret_provider=secret_provider,
    )
