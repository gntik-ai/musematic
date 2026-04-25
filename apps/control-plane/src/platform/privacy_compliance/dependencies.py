from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user, get_db
from platform.common.events.producer import EventProducer
from platform.privacy_compliance.cascade_adapters.clickhouse_adapter import ClickHouseCascadeAdapter
from platform.privacy_compliance.cascade_adapters.neo4j_adapter import Neo4jCascadeAdapter
from platform.privacy_compliance.cascade_adapters.opensearch_adapter import OpenSearchCascadeAdapter
from platform.privacy_compliance.cascade_adapters.postgresql_adapter import PostgreSQLCascadeAdapter
from platform.privacy_compliance.cascade_adapters.qdrant_adapter import QdrantCascadeAdapter
from platform.privacy_compliance.cascade_adapters.s3_adapter import S3CascadeAdapter
from platform.privacy_compliance.events import PrivacyEventPublisher
from platform.privacy_compliance.repository import PrivacyComplianceRepository
from platform.privacy_compliance.services.cascade_orchestrator import CascadeOrchestrator
from platform.privacy_compliance.services.consent_service import ConsentService
from platform.privacy_compliance.services.dlp_service import DLPService
from platform.privacy_compliance.services.dsr_service import DSRService
from platform.privacy_compliance.services.pia_service import PIAService
from platform.privacy_compliance.services.residency_service import ResidencyService
from platform.privacy_compliance.services.salt_history import SaltHistoryProvider
from platform.privacy_compliance.services.tombstone_signer import TombstoneSigner
from typing import Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

ADMIN_ROLES = {"privacy_officer", "platform_admin", "superadmin"}
READ_ROLES = ADMIN_ROLES | {"auditor", "compliance_officer"}


def _settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _has_role(user: dict[str, Any], allowed: set[str]) -> bool:
    role = user.get("role")
    if isinstance(role, str) and role in allowed:
        return True
    roles = user.get("roles") or []
    for item in roles:
        if isinstance(item, str) and item in allowed:
            return True
        if isinstance(item, dict) and item.get("role") in allowed:
            return True
    return False


async def require_privacy_admin(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if not _has_role(current_user, ADMIN_ROLES | {"service_account"}):
        from platform.common.exceptions import AuthorizationError

        raise AuthorizationError("PRIVACY_ADMIN_REQUIRED", "Privacy admin role required")
    return current_user


async def require_privacy_reader(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if not _has_role(current_user, READ_ROLES | {"service_account"}):
        from platform.common.exceptions import AuthorizationError

        raise AuthorizationError("PRIVACY_READER_REQUIRED", "Privacy read role required")
    return current_user


def build_privacy_repository(session: AsyncSession) -> PrivacyComplianceRepository:
    return PrivacyComplianceRepository(session)


def build_consent_service(
    *,
    session: AsyncSession,
    producer: EventProducer | None,
) -> ConsentService:
    return ConsentService(
        repository=build_privacy_repository(session),
        event_publisher=PrivacyEventPublisher(producer),
    )


def build_pia_service(
    *,
    session: AsyncSession,
    producer: EventProducer | None,
) -> PIAService:
    return PIAService(
        repository=build_privacy_repository(session),
        event_publisher=PrivacyEventPublisher(producer),
    )


def build_dlp_service(
    *,
    session: AsyncSession,
    producer: EventProducer | None,
) -> DLPService:
    return DLPService(
        repository=build_privacy_repository(session),
        event_publisher=PrivacyEventPublisher(producer),
    )


def build_residency_service(
    *,
    session: AsyncSession,
    producer: EventProducer | None,
    redis_client: object | None = None,
) -> ResidencyService:
    return ResidencyService(
        repository=build_privacy_repository(session),
        event_publisher=PrivacyEventPublisher(producer),
        redis_client=redis_client,
    )


def build_dsr_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    clients: dict[str, Any] | None = None,
) -> DSRService:
    clients = clients or {}
    repository = build_privacy_repository(session)
    buckets = [
        settings.registry.package_bucket,
        getattr(settings.connectors, "dead_letter_bucket", "connector-dead-letters"),
    ]
    orchestrator = CascadeOrchestrator(
        repository=repository,
        adapters=[
            PostgreSQLCascadeAdapter(session),
            QdrantCascadeAdapter(clients.get("qdrant")),
            OpenSearchCascadeAdapter(clients.get("opensearch")),
            S3CascadeAdapter(clients.get("object_storage"), buckets),
            ClickHouseCascadeAdapter(
                clients.get("clickhouse"),
                settings.privacy_compliance.clickhouse_pii_tables,
            ),
            Neo4jCascadeAdapter(session),
        ],
        signer=TombstoneSigner(clients.get("audit_signer")),
        salt_provider=SaltHistoryProvider(vault_path=settings.privacy_compliance.salt_vault_path),
        audit_chain=clients.get("audit_chain"),
    )
    return DSRService(
        repository=repository,
        event_publisher=PrivacyEventPublisher(producer),
        orchestrator=orchestrator,
        audit_chain=clients.get("audit_chain"),
    )


async def get_dsr_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> DSRService:
    return build_dsr_service(
        session=session,
        settings=_settings(request),
        producer=_producer(request),
        clients=request.app.state.clients,
    )


async def get_consent_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ConsentService:
    return build_consent_service(session=session, producer=_producer(request))


async def get_pia_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PIAService:
    return build_pia_service(session=session, producer=_producer(request))


async def get_dlp_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> DLPService:
    return build_dlp_service(session=session, producer=_producer(request))


async def get_residency_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ResidencyService:
    return build_residency_service(
        session=session,
        producer=_producer(request),
        redis_client=request.app.state.clients.get("redis"),
    )

