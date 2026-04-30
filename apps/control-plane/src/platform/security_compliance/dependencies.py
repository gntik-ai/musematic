from __future__ import annotations

from platform.audit.dependencies import build_audit_chain_service
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.common.secret_provider import MockSecretProvider, SecretProvider
from platform.security_compliance.providers.rotatable_secret_provider import RotatableSecretProvider
from platform.security_compliance.repository import SecurityComplianceRepository
from platform.security_compliance.services.compliance_service import ComplianceService
from platform.security_compliance.services.jit_service import JitService
from platform.security_compliance.services.pentest_service import PentestService
from platform.security_compliance.services.sbom_service import SbomService
from platform.security_compliance.services.secret_rotation_service import SecretRotationService
from platform.security_compliance.services.vuln_scan_service import VulnScanService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _redis(request: Request) -> AsyncRedisClient | None:
    return cast(AsyncRedisClient | None, request.app.state.clients.get("redis"))


async def get_sbom_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> SbomService:
    return SbomService(
        SecurityComplianceRepository(session),
        producer=_producer(request),
        audit_chain=build_audit_chain_service(session, _settings(request), _producer(request)),
    )


async def get_vuln_scan_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> VulnScanService:
    return VulnScanService(
        SecurityComplianceRepository(session),
        producer=_producer(request),
        audit_chain=build_audit_chain_service(session, _settings(request), _producer(request)),
    )


async def get_rotation_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> SecretRotationService:
    settings = _settings(request)
    secret_provider = cast(
        SecretProvider,
        getattr(request.app.state, "secret_provider", None)
        or MockSecretProvider(settings, validate_paths=False),
    )
    return SecretRotationService(
        SecurityComplianceRepository(session),
        RotatableSecretProvider(settings, _redis(request), secret_provider),
        producer=_producer(request),
        audit_chain=build_audit_chain_service(session, settings, _producer(request)),
    )


async def get_jit_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> JitService:
    settings = _settings(request)
    return JitService(
        SecurityComplianceRepository(session),
        settings,
        redis_client=_redis(request),
        producer=_producer(request),
        audit_chain=build_audit_chain_service(session, settings, _producer(request)),
    )


async def get_pentest_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PentestService:
    return PentestService(
        SecurityComplianceRepository(session),
        producer=_producer(request),
        audit_chain=build_audit_chain_service(session, _settings(request), _producer(request)),
    )


async def get_compliance_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ComplianceService:
    settings = _settings(request)
    return ComplianceService(
        SecurityComplianceRepository(session),
        settings,
        object_storage=cast(
            AsyncObjectStorageClient | None,
            request.app.state.clients.get("object_storage"),
        ),
        audit_chain=build_audit_chain_service(session, settings, _producer(request)),
    )
