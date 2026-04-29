from __future__ import annotations

from platform.audit.dependencies import get_audit_chain_service
from platform.audit.service import AuditChainService
from platform.common import database
from platform.common.clients.model_router import SecretProvider
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.execution.dependencies import get_execution_service
from platform.execution.service import ExecutionService
from platform.incident_response.repository import IncidentResponseRepository
from platform.incident_response.service import IncidentResponseService
from platform.incident_response.services.incident_service import IncidentService
from platform.incident_response.services.integration_service import IntegrationService
from platform.incident_response.services.kafka_replay import KafkaTimelineReplay
from platform.incident_response.services.post_mortem_service import PostMortemService
from platform.incident_response.services.providers.base import PagingProviderClient
from platform.incident_response.services.providers.opsgenie import OpsGenieClient
from platform.incident_response.services.providers.pagerduty import PagerDutyClient
from platform.incident_response.services.providers.victorops import VictorOpsClient
from platform.incident_response.services.runbook_service import RunbookService
from platform.incident_response.services.timeline_assembler import TimelineAssembler
from platform.notifications.dependencies import get_notifications_service
from platform.notifications.service import AlertService
from platform.security_compliance.providers.rotatable_secret_provider import RotatableSecretProvider
from typing import Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_redis(request: Request) -> AsyncRedisClient | None:
    return cast(AsyncRedisClient | None, request.app.state.clients.get("redis"))


def _get_object_storage(request: Request) -> AsyncObjectStorageClient | None:
    return cast(AsyncObjectStorageClient | None, request.app.state.clients.get("object_storage"))


def get_secret_provider(request: Request) -> SecretProvider:
    existing = getattr(request.app.state, "incident_response_secret_provider", None)
    if existing is not None:
        return cast(SecretProvider, existing)
    provider = RotatableSecretProvider(
        settings=_get_settings(request),
        redis_client=_get_redis(request),
    )
    request.app.state.incident_response_secret_provider = provider
    return provider


def get_paging_provider_clients(
    request: Request,
    secret_provider: SecretProvider = Depends(get_secret_provider),
) -> dict[str, PagingProviderClient]:
    timeout = _get_settings(request).incident_response.external_alert_request_timeout_seconds
    return {
        "pagerduty": PagerDutyClient(secret_provider=secret_provider, timeout_seconds=timeout),
        "opsgenie": OpsGenieClient(secret_provider=secret_provider, timeout_seconds=timeout),
        "victorops": VictorOpsClient(secret_provider=secret_provider, timeout_seconds=timeout),
    }


def build_runbook_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    audit_chain_service: Any | None = None,
) -> RunbookService:
    return RunbookService(
        repository=IncidentResponseRepository(session),
        settings=settings,
        audit_chain_service=audit_chain_service,
    )


def build_integration_service(
    *,
    session: AsyncSession,
    secret_provider: SecretProvider,
    audit_chain_service: Any | None = None,
) -> IntegrationService:
    return IntegrationService(
        repository=IncidentResponseRepository(session),
        secret_provider=secret_provider,
        audit_chain_service=audit_chain_service,
    )


def build_incident_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    redis_client: AsyncRedisClient | None,
    producer: EventProducer | None,
    provider_clients: dict[str, PagingProviderClient],
    runbook_service: RunbookService | None = None,
    audit_chain_service: Any | None = None,
    session_factory: Any | None = None,
) -> IncidentService:
    return IncidentService(
        repository=IncidentResponseRepository(session),
        settings=settings,
        redis_client=redis_client,
        producer=producer,
        provider_clients=provider_clients,
        runbook_service=runbook_service,
        audit_chain_service=audit_chain_service,
        session_factory=session_factory,
    )


def build_timeline_assembler(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    audit_chain_service: Any | None,
    execution_service: Any | None,
) -> TimelineAssembler:
    return TimelineAssembler(
        repository=IncidentResponseRepository(session),
        audit_chain_service=audit_chain_service,
        execution_service=execution_service,
        kafka_replay=KafkaTimelineReplay(settings=settings),
        kafka_topics=list(settings.incident_response.timeline_kafka_topics),
    )


def build_post_mortem_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    timeline_assembler: TimelineAssembler,
    object_storage: AsyncObjectStorageClient | None = None,
    alert_service: Any | None = None,
    audit_chain_service: Any | None = None,
) -> PostMortemService:
    return PostMortemService(
        repository=IncidentResponseRepository(session),
        settings=settings,
        timeline_assembler=timeline_assembler,
        object_storage=object_storage,
        alert_service=alert_service,
        audit_chain_service=audit_chain_service,
    )


async def get_runbook_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    audit_chain_service: AuditChainService = Depends(get_audit_chain_service),
) -> RunbookService:
    return build_runbook_service(
        session=session,
        settings=_get_settings(request),
        audit_chain_service=audit_chain_service,
    )


async def get_integration_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    secret_provider: SecretProvider = Depends(get_secret_provider),
    audit_chain_service: AuditChainService = Depends(get_audit_chain_service),
) -> IntegrationService:
    return build_integration_service(
        session=session,
        secret_provider=secret_provider,
        audit_chain_service=audit_chain_service,
    )


async def get_incident_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    provider_clients: dict[str, PagingProviderClient] = Depends(get_paging_provider_clients),
    runbook_service: RunbookService = Depends(get_runbook_service),
    audit_chain_service: AuditChainService = Depends(get_audit_chain_service),
) -> IncidentService:
    return build_incident_service(
        session=session,
        settings=_get_settings(request),
        redis_client=_get_redis(request),
        producer=_get_producer(request),
        provider_clients=provider_clients,
        runbook_service=runbook_service,
        audit_chain_service=audit_chain_service,
        session_factory=database.AsyncSessionLocal,
    )


async def get_timeline_assembler(
    request: Request,
    session: AsyncSession = Depends(get_db),
    audit_chain_service: AuditChainService = Depends(get_audit_chain_service),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> TimelineAssembler:
    return build_timeline_assembler(
        session=session,
        settings=_get_settings(request),
        audit_chain_service=audit_chain_service,
        execution_service=execution_service,
    )


async def get_post_mortem_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    timeline_assembler: TimelineAssembler = Depends(get_timeline_assembler),
    audit_chain_service: AuditChainService = Depends(get_audit_chain_service),
    alert_service: AlertService = Depends(get_notifications_service),
) -> PostMortemService:
    return build_post_mortem_service(
        session=session,
        settings=_get_settings(request),
        timeline_assembler=timeline_assembler,
        object_storage=_get_object_storage(request),
        alert_service=alert_service,
        audit_chain_service=audit_chain_service,
    )


async def get_incident_response_service(
    incident_service: IncidentService = Depends(get_incident_service),
    integration_service: IntegrationService = Depends(get_integration_service),
    runbook_service: RunbookService = Depends(get_runbook_service),
    post_mortem_service: PostMortemService = Depends(get_post_mortem_service),
    timeline_assembler: TimelineAssembler = Depends(get_timeline_assembler),
) -> IncidentResponseService:
    return IncidentResponseService(
        incident_service=incident_service,
        integration_service=integration_service,
        runbook_service=runbook_service,
        post_mortem_service=post_mortem_service,
        timeline_assembler=timeline_assembler,
    )
