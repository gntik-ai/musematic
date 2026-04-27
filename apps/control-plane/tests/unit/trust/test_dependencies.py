from __future__ import annotations

import platform.trust as trust_package
from platform.trust.ate_service import ATEService
from platform.trust.circuit_breaker import CircuitBreakerService
from platform.trust.contract_service import ContractService
from platform.trust.dependencies import (
    build_ate_service,
    build_certification_service,
    build_circuit_breaker_service,
    build_content_moderator,
    build_contract_service,
    build_guardrail_pipeline_service,
    build_moderation_provider_registry,
    build_oje_service,
    build_prescreener_service,
    build_privacy_assessment_service,
    build_recertification_service,
    build_surveillance_service,
    build_trust_tier_service,
    get_ate_service,
    get_audit_chain_service,
    get_certification_service,
    get_circuit_breaker_service,
    get_content_moderator,
    get_contract_service,
    get_guardrail_pipeline_service,
    get_moderation_provider_registry,
    get_oje_service,
    get_prescreener_service,
    get_privacy_assessment_service,
    get_recertification_service,
    get_residency_service,
    get_secret_provider,
    get_surveillance_service,
    get_trust_tier_service,
)
from platform.trust.guardrail_pipeline import GuardrailPipelineService
from platform.trust.oje_pipeline import OJEPipelineService
from platform.trust.prescreener import SafetyPreScreenerService
from platform.trust.privacy_assessment import PrivacyAssessmentService
from platform.trust.recertification import RecertificationService
from platform.trust.service import CertificationService
from platform.trust.services.content_moderator import ContentModerator
from platform.trust.services.moderation_providers import ModerationProviderRegistry
from platform.trust.surveillance_service import SurveillanceService
from platform.trust.trust_tier import TrustTierService
from types import SimpleNamespace

import pytest

from tests.trust_support import build_trust_bundle


@pytest.mark.asyncio
async def test_trust_dependencies_build_services() -> None:
    bundle = build_trust_bundle()
    session = bundle.repository.session

    assert isinstance(
        build_certification_service(
            session=session,
            settings=bundle.settings,
            producer=bundle.producer,
        ),
        CertificationService,
    )
    assert isinstance(
        build_contract_service(
            session=session,
            producer=bundle.producer,
        ),
        ContractService,
    )
    registry = build_moderation_provider_registry(settings=bundle.settings)
    assert registry.registered_names() == [
        "anthropic",
        "google_perspective",
        "openai",
        "self_hosted",
    ]
    assert isinstance(
        build_content_moderator(
            session=session,
            settings=bundle.settings,
            producer=bundle.producer,
            redis_client=bundle.redis,
            registry=registry,
            residency_service=get_residency_service(),
            secret_provider=get_secret_provider(),
            audit_chain=get_audit_chain_service(),
        ),
        ContentModerator,
    )
    assert isinstance(
        build_surveillance_service(
            session=session,
            settings=bundle.settings,
            producer=bundle.producer,
        ),
        SurveillanceService,
    )
    assert isinstance(
        build_trust_tier_service(
            session=session,
            settings=bundle.settings,
            producer=bundle.producer,
        ),
        TrustTierService,
    )
    assert isinstance(
        build_guardrail_pipeline_service(
            session=session,
            settings=bundle.settings,
            producer=bundle.producer,
            policy_engine=bundle.policy_engine,
        ),
        GuardrailPipelineService,
    )
    assert isinstance(
        build_prescreener_service(
            session=session,
            settings=bundle.settings,
            producer=bundle.producer,
            redis_client=bundle.redis,
            object_storage=bundle.object_storage,
        ),
        SafetyPreScreenerService,
    )
    assert isinstance(
        build_oje_service(
            session=session,
            settings=bundle.settings,
            producer=bundle.producer,
            registry_service=bundle.registry_service,
            interactions_service=bundle.interactions_service,
            runtime_controller=bundle.runtime_controller,
        ),
        OJEPipelineService,
    )
    assert isinstance(
        build_recertification_service(
            session=session,
            settings=bundle.settings,
            producer=bundle.producer,
        ),
        RecertificationService,
    )
    assert isinstance(
        build_circuit_breaker_service(
            session=session,
            settings=bundle.settings,
            producer=bundle.producer,
            redis_client=bundle.redis,
            runtime_controller=bundle.runtime_controller,
        ),
        CircuitBreakerService,
    )
    assert isinstance(
        build_ate_service(
            session=session,
            settings=bundle.settings,
            object_storage=bundle.object_storage,
            simulation_controller=bundle.simulation_controller,
            redis_client=bundle.redis,
        ),
        ATEService,
    )
    assert isinstance(
        build_privacy_assessment_service(policy_engine=bundle.policy_engine),
        PrivacyAssessmentService,
    )
    assert callable(trust_package.get_ate_service)


@pytest.mark.asyncio
async def test_trust_dependency_getters_resolve_from_request_state() -> None:
    bundle = build_trust_bundle()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=bundle.settings,
                clients={
                    "kafka": bundle.producer,
                    "redis": bundle.redis,
                    "object_storage": bundle.object_storage,
                    "runtime_controller": bundle.runtime_controller,
                    "simulation_controller": bundle.simulation_controller,
                    "model_router": None,
                },
            )
        )
    )
    session = bundle.repository.session
    registry = await get_moderation_provider_registry(request=request)

    assert isinstance(registry, ModerationProviderRegistry)
    assert await get_secret_provider().read_secret("trust/provider") == {}
    assert await get_residency_service().allow_egress(workspace_id=object(), provider="openai")
    assert get_audit_chain_service() is None
    assert isinstance(
        await get_content_moderator(
            request=request,
            session=session,
            registry=registry,
            residency_service=get_residency_service(),
            secret_provider=get_secret_provider(),
            audit_chain=get_audit_chain_service(),
        ),
        ContentModerator,
    )

    assert isinstance(
        await get_guardrail_pipeline_service(
            request=request,
            session=session,
            policy_service=bundle.policy_engine,
        ),
        GuardrailPipelineService,
    )
    assert isinstance(
        await get_prescreener_service(request=request, session=session),
        SafetyPreScreenerService,
    )
    assert isinstance(
        await get_oje_service(
            request=request,
            session=session,
            registry_service=bundle.registry_service,
            interactions_service=bundle.interactions_service,
        ),
        OJEPipelineService,
    )
    assert isinstance(
        await get_certification_service(request=request, session=session),
        CertificationService,
    )
    assert isinstance(
        await get_contract_service(request=request, session=session),
        ContractService,
    )
    assert isinstance(
        await get_surveillance_service(request=request, session=session),
        SurveillanceService,
    )
    assert isinstance(
        await get_trust_tier_service(request=request, session=session),
        TrustTierService,
    )
    assert isinstance(
        await get_circuit_breaker_service(request=request, session=session),
        CircuitBreakerService,
    )
    assert isinstance(await get_ate_service(request=request, session=session), ATEService)
    assert isinstance(
        await get_recertification_service(request=request, session=session),
        RecertificationService,
    )
    assert isinstance(
        await get_privacy_assessment_service(policy_service=bundle.policy_engine),
        PrivacyAssessmentService,
    )
