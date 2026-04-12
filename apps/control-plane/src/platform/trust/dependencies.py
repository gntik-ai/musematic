from __future__ import annotations

from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.clients.simulation_controller import SimulationControllerClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.interactions.dependencies import get_interactions_service
from platform.interactions.service import InteractionsService
from platform.policies.dependencies import get_policy_service
from platform.policies.service import PolicyService
from platform.registry.dependencies import get_registry_service
from platform.registry.service import RegistryService
from platform.trust.ate_service import ATEService
from platform.trust.circuit_breaker import CircuitBreakerService
from platform.trust.guardrail_pipeline import GuardrailPipelineService
from platform.trust.oje_pipeline import OJEPipelineService
from platform.trust.prescreener import SafetyPreScreenerService
from platform.trust.privacy_assessment import PrivacyAssessmentService
from platform.trust.recertification import RecertificationService
from platform.trust.repository import TrustRepository
from platform.trust.service import CertificationService
from platform.trust.trust_tier import TrustTierService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def _get_object_storage(request: Request) -> AsyncObjectStorageClient:
    return cast(AsyncObjectStorageClient, request.app.state.clients["minio"])


def _get_runtime_controller(request: Request) -> RuntimeControllerClient | None:
    return cast(RuntimeControllerClient | None, request.app.state.clients.get("runtime_controller"))


def _get_simulation_controller(request: Request) -> SimulationControllerClient | None:
    return cast(
        SimulationControllerClient | None,
        request.app.state.clients.get("simulation_controller"),
    )


def build_certification_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
) -> CertificationService:
    return CertificationService(
        repository=TrustRepository(session),
        settings=settings,
        producer=producer,
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
) -> GuardrailPipelineService:
    return GuardrailPipelineService(
        repository=TrustRepository(session),
        settings=settings,
        producer=producer,
        policy_engine=policy_engine,
    )


async def get_guardrail_pipeline_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    policy_service: PolicyService = Depends(get_policy_service),
) -> GuardrailPipelineService:
    return build_guardrail_pipeline_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        policy_engine=policy_service,
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
