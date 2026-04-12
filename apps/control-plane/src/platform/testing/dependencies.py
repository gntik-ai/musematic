from __future__ import annotations

from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.reasoning_engine import ReasoningEngineClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.evaluation.repository import EvaluationRepository
from platform.evaluation.scorers.llm_judge import LLMJudgeScorer
from platform.execution.dependencies import build_execution_service
from platform.fleets.repository import FleetMemberRepository, FleetRepository
from platform.registry.dependencies import get_registry_service
from platform.registry.service import RegistryService
from platform.testing.adversarial_service import AdversarialGenerationService
from platform.testing.coordination_service import CoordinationTestService
from platform.testing.drift_service import DriftDetectionService
from platform.testing.repository import TestingRepository
from platform.testing.suite_generation_service import TestSuiteGenerationService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_object_storage(request: Request) -> AsyncObjectStorageClient:
    return cast(AsyncObjectStorageClient, request.app.state.clients["minio"])


def _get_clickhouse(request: Request) -> AsyncClickHouseClient:
    return cast(AsyncClickHouseClient, request.app.state.clients["clickhouse"])


def build_adversarial_generation_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    registry_service: RegistryService | None,
) -> AdversarialGenerationService:
    return AdversarialGenerationService(
        repository=TestingRepository(session),
        settings=settings,
        registry_service=registry_service,
    )


async def get_adversarial_generation_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    registry_service: RegistryService = Depends(get_registry_service),
) -> AdversarialGenerationService:
    return build_adversarial_generation_service(
        session=session,
        settings=_get_settings(request),
        registry_service=registry_service,
    )


def build_test_suite_generation_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    object_storage: AsyncObjectStorageClient,
    registry_service: RegistryService | None,
) -> TestSuiteGenerationService:
    return TestSuiteGenerationService(
        repository=TestingRepository(session),
        evaluation_repository=EvaluationRepository(session),
        settings=settings,
        producer=producer,
        object_storage=object_storage,
        adversarial_service=build_adversarial_generation_service(
            session=session,
            settings=settings,
            registry_service=registry_service,
        ),
    )


async def get_test_suite_generation_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    registry_service: RegistryService = Depends(get_registry_service),
) -> TestSuiteGenerationService:
    return build_test_suite_generation_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        object_storage=_get_object_storage(request),
        registry_service=registry_service,
    )


def build_drift_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    clickhouse_client: AsyncClickHouseClient,
) -> DriftDetectionService:
    return DriftDetectionService(
        repository=TestingRepository(session),
        evaluation_repository=EvaluationRepository(session),
        clickhouse_client=clickhouse_client,
        settings=settings,
        producer=producer,
    )


async def get_drift_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> DriftDetectionService:
    return build_drift_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        clickhouse_client=_get_clickhouse(request),
    )


def build_coordination_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    object_storage: AsyncObjectStorageClient,
    runtime_controller: RuntimeControllerClient | None,
    reasoning_engine: ReasoningEngineClient | None,
) -> CoordinationTestService:
    execution_service = build_execution_service(
        session=session,
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        object_storage=object_storage,
        runtime_controller=runtime_controller,
        reasoning_engine=reasoning_engine,
        context_engineering_service=None,
    )
    return CoordinationTestService(
        repository=TestingRepository(session),
        fleet_repository=FleetRepository(session),
        member_repository=FleetMemberRepository(session),
        execution_query=execution_service,
        producer=producer,
        llm_judge=LLMJudgeScorer(settings=settings),
    )


async def get_coordination_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> CoordinationTestService:
    return build_coordination_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=cast(AsyncRedisClient, request.app.state.clients["redis"]),
        object_storage=_get_object_storage(request),
        runtime_controller=cast(
            RuntimeControllerClient | None,
            request.app.state.clients.get("runtime_controller"),
        ),
        reasoning_engine=cast(
            ReasoningEngineClient | None,
            request.app.state.clients.get("reasoning_engine"),
        ),
    )
