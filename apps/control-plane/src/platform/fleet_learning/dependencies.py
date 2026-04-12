from __future__ import annotations

from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.fleet_learning.adaptation import FleetAdaptationEngineService
from platform.fleet_learning.performance import FleetPerformanceProfileService
from platform.fleet_learning.personality import FleetPersonalityProfileService
from platform.fleet_learning.repository import (
    CrossFleetTransferRepository,
    FleetAdaptationLogRepository,
    FleetAdaptationRuleRepository,
    FleetPerformanceProfileRepository,
    FleetPersonalityProfileRepository,
)
from platform.fleet_learning.service import FleetLearningService
from platform.fleet_learning.transfer import CrossFleetTransferService
from platform.fleets.dependencies import get_fleet_service
from platform.fleets.repository import (
    FleetOrchestrationRulesRepository,
    FleetTopologyVersionRepository,
)
from platform.fleets.service import FleetService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_clickhouse(request: Request) -> AsyncClickHouseClient:
    return cast(AsyncClickHouseClient, request.app.state.clients["clickhouse"])


def _get_object_storage(request: Request) -> AsyncObjectStorageClient:
    return cast(AsyncObjectStorageClient, request.app.state.clients["minio"])


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def build_personality_service(
    *,
    session: AsyncSession,
) -> FleetPersonalityProfileService:
    return FleetPersonalityProfileService(repository=FleetPersonalityProfileRepository(session))


async def get_personality_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> FleetPersonalityProfileService:
    del request
    return build_personality_service(session=session)


def build_performance_service(
    *,
    session: AsyncSession,
    clickhouse: AsyncClickHouseClient,
    fleet_service: FleetService,
) -> FleetPerformanceProfileService:
    return FleetPerformanceProfileService(
        repository=FleetPerformanceProfileRepository(session),
        clickhouse=clickhouse,
        fleet_service=fleet_service,
    )


async def get_performance_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetPerformanceProfileService:
    return build_performance_service(
        session=session,
        clickhouse=_get_clickhouse(request),
        fleet_service=fleet_service,
    )


def build_adaptation_service(
    *,
    session: AsyncSession,
    fleet_service: FleetService,
    producer: EventProducer | None,
) -> FleetAdaptationEngineService:
    return FleetAdaptationEngineService(
        rule_repo=FleetAdaptationRuleRepository(session),
        log_repo=FleetAdaptationLogRepository(session),
        profile_repo=FleetPerformanceProfileRepository(session),
        rules_repo=FleetOrchestrationRulesRepository(session),
        fleet_service=fleet_service,
        producer=producer,
    )


async def get_adaptation_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetAdaptationEngineService:
    return build_adaptation_service(
        session=session,
        fleet_service=fleet_service,
        producer=_get_producer(request),
    )


def build_transfer_service(
    *,
    session: AsyncSession,
    object_storage: AsyncObjectStorageClient,
    fleet_service: FleetService,
    producer: EventProducer | None,
) -> CrossFleetTransferService:
    return CrossFleetTransferService(
        repository=CrossFleetTransferRepository(session),
        rules_repo=FleetOrchestrationRulesRepository(session),
        topology_repo=FleetTopologyVersionRepository(session),
        object_storage=object_storage,
        fleet_service=fleet_service,
        producer=producer,
    )


async def get_transfer_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> CrossFleetTransferService:
    return build_transfer_service(
        session=session,
        object_storage=_get_object_storage(request),
        fleet_service=fleet_service,
        producer=_get_producer(request),
    )


def build_fleet_learning_service(
    *,
    session: AsyncSession,
    clickhouse: AsyncClickHouseClient,
    object_storage: AsyncObjectStorageClient,
    fleet_service: FleetService,
    producer: EventProducer | None,
) -> FleetLearningService:
    personality_service = build_personality_service(session=session)
    return FleetLearningService(
        performance_service=build_performance_service(
            session=session,
            clickhouse=clickhouse,
            fleet_service=fleet_service,
        ),
        adaptation_service=build_adaptation_service(
            session=session,
            fleet_service=fleet_service,
            producer=producer,
        ),
        transfer_service=build_transfer_service(
            session=session,
            object_storage=object_storage,
            fleet_service=fleet_service,
            producer=producer,
        ),
        personality_service=personality_service,
    )


async def get_fleet_learning_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    fleet_service: FleetService = Depends(get_fleet_service),
) -> FleetLearningService:
    return build_fleet_learning_service(
        session=session,
        clickhouse=_get_clickhouse(request),
        object_storage=_get_object_storage(request),
        fleet_service=fleet_service,
        producer=_get_producer(request),
    )
