from __future__ import annotations

from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.clients.simulation_controller import SimulationControllerClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.evaluation.repository import EvaluationRepository
from platform.evaluation.service import FairnessEvaluationService
from platform.interactions.dependencies import get_interactions_service
from platform.interactions.service import InteractionsService
from platform.policies.dependencies import get_policy_service
from platform.policies.service import PolicyService
from platform.registry.dependencies import get_registry_service
from platform.registry.service import RegistryService
from platform.trust.ate_service import ATEService
from platform.trust.circuit_breaker import CircuitBreakerService
from platform.trust.contract_service import ContractService
from platform.trust.events import TrustEventPublisher
from platform.trust.guardrail_pipeline import GuardrailPipelineService
from platform.trust.oje_pipeline import OJEPipelineService
from platform.trust.prescreener import SafetyPreScreenerService
from platform.trust.privacy_assessment import PrivacyAssessmentService
from platform.trust.recertification import RecertificationService
from platform.trust.repository import TrustRepository
from platform.trust.service import CertificationService
from platform.trust.services.content_moderator import ContentModerator
from platform.trust.services.moderation_providers import ModerationProviderRegistry
from platform.trust.services.moderation_providers.anthropic_safety import AnthropicSafetyProvider
from platform.trust.services.moderation_providers.google_perspective import (
    GooglePerspectiveProvider,
)
from platform.trust.services.moderation_providers.openai_moderation import OpenAIModerationProvider
from platform.trust.services.moderation_providers.self_hosted_classifier import (
    SelfHostedClassifierProvider,
)
from platform.trust.surveillance_service import SurveillanceService
from platform.trust.trust_tier import TrustTierService
from typing import Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def _get_object_storage(request: Request) -> AsyncObjectStorageClient:
    return cast(AsyncObjectStorageClient, request.app.state.clients["object_storage"])


def _get_runtime_controller(request: Request) -> RuntimeControllerClient | None:
    return cast(RuntimeControllerClient | None, request.app.state.clients.get("runtime_controller"))


def _get_simulation_controller(request: Request) -> SimulationControllerClient | None:
    return cast(
        SimulationControllerClient | None,
        request.app.state.clients.get("simulation_controller"),
    )


class EmptySecretProvider:
    async def get_secret(self, path: str) -> dict[str, Any]:
        del path
        return {}

    async def read_secret(self, path: str) -> dict[str, Any]:
        return await self.get_secret(path)


class AllowAllResidencyService:
    async def allow_egress(self, *, workspace_id: object, provider: str) -> bool:
        del workspace_id, provider
        return True


def get_secret_provider() -> EmptySecretProvider:
    return EmptySecretProvider()


def get_residency_service() -> AllowAllResidencyService:
    return AllowAllResidencyService()


def get_audit_chain_service() -> None:
    return None


def build_moderation_provider_registry(
    *,
    settings: PlatformSettings,
    secret_provider: Any | None = None,
    model_router: Any | None = None,
) -> ModerationProviderRegistry:
    registry = ModerationProviderRegistry()
    timeout_ms = settings.content_moderation.default_per_call_timeout_ms
    registry.register(
        "openai",
        OpenAIModerationProvider(secret_provider=secret_provider, timeout_ms=timeout_ms),
    )
    registry.register(
        "anthropic",
        AnthropicSafetyProvider(
            model_router=model_router,
            secret_provider=secret_provider,
            timeout_ms=timeout_ms,
        ),
    )
    registry.register(
        "google_perspective",
        GooglePerspectiveProvider(secret_provider=secret_provider, timeout_ms=timeout_ms),
    )
    registry.register(
        "self_hosted",
        SelfHostedClassifierProvider(model_name=settings.content_moderation.self_hosted_model_name),
    )
    return registry


async def get_moderation_provider_registry(
    request: Request,
    secret_provider: EmptySecretProvider = Depends(get_secret_provider),
) -> ModerationProviderRegistry:
    return build_moderation_provider_registry(
        settings=_get_settings(request),
        secret_provider=secret_provider,
        model_router=request.app.state.clients.get("model_router"),
    )


def build_content_moderator(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    registry: ModerationProviderRegistry,
    residency_service: Any | None,
    secret_provider: Any | None,
    audit_chain: Any | None,
) -> ContentModerator:
    return ContentModerator(
        repository=TrustRepository(session),
        providers=registry,
        policy_engine=None,
        residency_service=residency_service,
        secrets=secret_provider,
        audit_chain=audit_chain,
        producer=producer,
        redis=redis_client,
        settings=settings,
    )


async def get_content_moderator(
    request: Request,
    session: AsyncSession = Depends(get_db),
    registry: ModerationProviderRegistry = Depends(get_moderation_provider_registry),
    residency_service: AllowAllResidencyService = Depends(get_residency_service),
    secret_provider: EmptySecretProvider = Depends(get_secret_provider),
    audit_chain: None = Depends(get_audit_chain_service),
) -> ContentModerator:
    return build_content_moderator(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
        registry=registry,
        residency_service=residency_service,
        secret_provider=secret_provider,
        audit_chain=audit_chain,
    )


def build_certification_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
) -> CertificationService:
    fairness_gate = FairnessEvaluationService(
        repository=EvaluationRepository(session),
        settings=settings,
        producer=producer,
    )
    return CertificationService(
        repository=TrustRepository(session),
        settings=settings,
        producer=producer,
        fairness_gate=fairness_gate,
    )


def build_contract_service(
    *,
    session: AsyncSession,
    producer: EventProducer | None,
) -> ContractService:
    return ContractService(
        repository=TrustRepository(session),
        publisher=TrustEventPublisher(producer),
    )


def build_surveillance_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
) -> SurveillanceService:
    return SurveillanceService(
        repository=TrustRepository(session),
        publisher=TrustEventPublisher(producer),
        settings=settings,
    )


async def get_contract_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ContractService:
    return build_contract_service(
        session=session,
        producer=_get_producer(request),
    )


async def get_surveillance_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> SurveillanceService:
    return build_surveillance_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
    )


async def get_certification_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> CertificationService:
    return build_certification_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
    )


def build_trust_tier_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
) -> TrustTierService:
    return TrustTierService(
        repository=TrustRepository(session),
        settings=settings,
        producer=producer,
    )


async def get_trust_tier_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TrustTierService:
    return build_trust_tier_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
    )


def build_guardrail_pipeline_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    policy_engine: PolicyService | None,
    pre_screener: SafetyPreScreenerService | None = None,
    content_moderator: ContentModerator | None = None,
) -> GuardrailPipelineService:
    return GuardrailPipelineService(
        repository=TrustRepository(session),
        settings=settings,
        producer=producer,
        policy_engine=policy_engine,
        pre_screener=pre_screener,
        content_moderator=content_moderator,
    )


async def get_guardrail_pipeline_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    policy_service: PolicyService = Depends(get_policy_service),
    content_moderator: ContentModerator = Depends(get_content_moderator),
) -> GuardrailPipelineService:
    prescreener_service = await get_prescreener_service(request=request, session=session)
    return build_guardrail_pipeline_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        policy_engine=policy_service,
        pre_screener=prescreener_service,
        content_moderator=content_moderator,
    )


def build_prescreener_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    object_storage: AsyncObjectStorageClient,
) -> SafetyPreScreenerService:
    return SafetyPreScreenerService(
        repository=TrustRepository(session),
        settings=settings,
        redis_client=redis_client,
        object_storage=object_storage,
        producer=producer,
    )


async def get_prescreener_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> SafetyPreScreenerService:
    return build_prescreener_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
        object_storage=_get_object_storage(request),
    )


def build_oje_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    registry_service: RegistryService | None,
    interactions_service: InteractionsService | None,
    runtime_controller: RuntimeControllerClient | None,
) -> OJEPipelineService:
    return OJEPipelineService(
        repository=TrustRepository(session),
        settings=settings,
        producer=producer,
        registry_service=registry_service,
        interactions_service=interactions_service,
        runtime_controller=runtime_controller,
    )


async def get_oje_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    registry_service: RegistryService = Depends(get_registry_service),
    interactions_service: InteractionsService = Depends(get_interactions_service),
) -> OJEPipelineService:
    return build_oje_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        registry_service=registry_service,
        interactions_service=interactions_service,
        runtime_controller=_get_runtime_controller(request),
    )


def build_recertification_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
) -> RecertificationService:
    return RecertificationService(
        repository=TrustRepository(session),
        settings=settings,
        producer=producer,
    )


async def get_recertification_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> RecertificationService:
    return build_recertification_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
    )


def build_circuit_breaker_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    runtime_controller: RuntimeControllerClient | None,
) -> CircuitBreakerService:
    return CircuitBreakerService(
        repository=TrustRepository(session),
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        runtime_controller=runtime_controller,
    )


async def get_circuit_breaker_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> CircuitBreakerService:
    return build_circuit_breaker_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
        runtime_controller=_get_runtime_controller(request),
    )


def build_ate_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    object_storage: AsyncObjectStorageClient,
    simulation_controller: SimulationControllerClient | None,
    redis_client: AsyncRedisClient,
) -> ATEService:
    return ATEService(
        repository=TrustRepository(session),
        settings=settings,
        object_storage=object_storage,
        simulation_controller=simulation_controller,
        redis_client=redis_client,
    )


async def get_ate_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ATEService:
    return build_ate_service(
        session=session,
        settings=_get_settings(request),
        object_storage=_get_object_storage(request),
        simulation_controller=_get_simulation_controller(request),
        redis_client=_get_redis(request),
    )


def build_privacy_assessment_service(
    *,
    policy_engine: PolicyService | None,
) -> PrivacyAssessmentService:
    return PrivacyAssessmentService(policy_engine=policy_engine)


async def get_privacy_assessment_service(
    policy_service: PolicyService = Depends(get_policy_service),
) -> PrivacyAssessmentService:
    return build_privacy_assessment_service(policy_engine=policy_service)
