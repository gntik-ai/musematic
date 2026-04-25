from __future__ import annotations

from platform.model_catalog import dependencies
from platform.model_catalog.services.catalog_service import CatalogService
from platform.model_catalog.services.credential_service import CredentialService
from platform.model_catalog.services.fallback_service import FallbackPolicyService
from platform.model_catalog.services.injection_defense_service import InjectionDefenseService
from platform.model_catalog.services.model_card_service import ModelCardService
from types import SimpleNamespace

import pytest


class RepositoryMarker:
    def __init__(self, session: object) -> None:
        self.session = session


class SecretProviderMarker:
    def __init__(self, settings: object, redis_client: object | None) -> None:
        self.settings = settings
        self.redis_client = redis_client


class SecurityRepositoryMarker:
    def __init__(self, session: object) -> None:
        self.session = session


class RotationServiceMarker:
    def __init__(
        self,
        repository: SecurityRepositoryMarker,
        secret_provider: SecretProviderMarker,
        *,
        producer: object | None,
        audit_chain: object,
    ) -> None:
        self.repository = repository
        self.secret_provider = secret_provider
        self.producer = producer
        self.audit_chain = audit_chain


@pytest.mark.asyncio
async def test_model_catalog_dependency_factories_wire_request_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = object()
    kafka = object()
    redis = object()
    audit_chain = object()
    session = object()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=settings, clients={"kafka": kafka, "redis": redis})
        )
    )

    monkeypatch.setattr(dependencies, "ModelCatalogRepository", RepositoryMarker)
    monkeypatch.setattr(dependencies, "RotatableSecretProvider", SecretProviderMarker)
    monkeypatch.setattr(dependencies, "SecurityComplianceRepository", SecurityRepositoryMarker)
    monkeypatch.setattr(dependencies, "SecretRotationService", RotationServiceMarker)
    monkeypatch.setattr(
        dependencies,
        "build_audit_chain_service",
        lambda built_session, built_settings, built_producer: (
            audit_chain,
            built_session,
            built_settings,
            built_producer,
        ),
    )

    assert dependencies._settings(request) is settings  # type: ignore[arg-type]
    assert dependencies._producer(request) is kafka  # type: ignore[arg-type]
    assert dependencies._redis(request) is redis  # type: ignore[arg-type]

    catalog = await dependencies.get_catalog_service(request, session)  # type: ignore[arg-type]
    fallback = await dependencies.get_fallback_policy_service(session)  # type: ignore[arg-type]
    card = await dependencies.get_model_card_service(request, session)  # type: ignore[arg-type]
    credential = await dependencies.get_credential_service(request, session)  # type: ignore[arg-type]
    injection = await dependencies.get_injection_defense_service(session)  # type: ignore[arg-type]

    assert isinstance(catalog, CatalogService)
    assert isinstance(fallback, FallbackPolicyService)
    assert isinstance(card, ModelCardService)
    assert isinstance(credential, CredentialService)
    assert isinstance(injection, InjectionDefenseService)
    assert catalog.repository.session is session
    assert catalog.producer is kafka
    assert catalog.audit_chain[0] is audit_chain  # type: ignore[index]
    assert fallback.repository.session is session
    assert card.producer is kafka
    assert credential.repository.session is session
    assert credential.secret_reader.settings is settings  # type: ignore[attr-defined]
    assert credential.secret_reader.redis_client is redis  # type: ignore[attr-defined]
    assert credential.rotation_service.repository.session is session  # type: ignore[attr-defined]
    assert credential.rotation_service.producer is kafka  # type: ignore[attr-defined]
    assert credential.rotation_service.audit_chain[0] is audit_chain  # type: ignore[attr-defined,index]
    assert injection.repository.session is session
