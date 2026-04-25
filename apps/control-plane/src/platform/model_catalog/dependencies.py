from __future__ import annotations

from platform.audit.dependencies import build_audit_chain_service
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.model_catalog.repository import ModelCatalogRepository
from platform.model_catalog.services.catalog_service import CatalogService
from platform.model_catalog.services.credential_service import CredentialService
from platform.model_catalog.services.fallback_service import FallbackPolicyService
from platform.model_catalog.services.injection_defense_service import InjectionDefenseService
from platform.model_catalog.services.model_card_service import ModelCardService
from platform.security_compliance.providers.rotatable_secret_provider import RotatableSecretProvider
from platform.security_compliance.repository import SecurityComplianceRepository
from platform.security_compliance.services.secret_rotation_service import SecretRotationService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _redis(request: Request) -> AsyncRedisClient | None:
    return cast(AsyncRedisClient | None, request.app.state.clients.get("redis"))


async def get_catalog_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> CatalogService:
    settings = _settings(request)
    return CatalogService(
        ModelCatalogRepository(session),
        producer=_producer(request),
        audit_chain=build_audit_chain_service(session, settings, _producer(request)),
    )


async def get_fallback_policy_service(
    session: AsyncSession = Depends(get_db),
) -> FallbackPolicyService:
    return FallbackPolicyService(ModelCatalogRepository(session))


async def get_model_card_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ModelCardService:
    return ModelCardService(ModelCatalogRepository(session), producer=_producer(request))


async def get_credential_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> CredentialService:
    settings = _settings(request)
    secret_provider = RotatableSecretProvider(settings, _redis(request))
    rotation_service = SecretRotationService(
        SecurityComplianceRepository(session),
        secret_provider,
        producer=_producer(request),
        audit_chain=build_audit_chain_service(session, settings, _producer(request)),
    )
    return CredentialService(
        ModelCatalogRepository(session),
        secret_reader=secret_provider,
        rotation_service=rotation_service,
    )


async def get_injection_defense_service(
    session: AsyncSession = Depends(get_db),
) -> InjectionDefenseService:
    return InjectionDefenseService(ModelCatalogRepository(session))
