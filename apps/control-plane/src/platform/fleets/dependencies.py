from __future__ import annotations

from platform.common.clients.redis import AsyncRedisClient
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.fleets.governance import FleetGovernanceChainService
from platform.fleets.health import FleetHealthProjectionService
from platform.fleets.repository import (
    FleetGovernanceChainRepository,
    FleetMemberRepository,
    FleetOrchestrationRulesRepository,
    FleetPolicyBindingRepository,
    FleetRepository,
    FleetTopologyVersionRepository,
    ObserverAssignmentRepository,
)
from platform.fleets.service import FleetOrchestrationModifierService, FleetService
from platform.registry.dependencies import get_registry_service
from platform.registry.service import RegistryService
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def _get_runtime_controller(request: Request) -> RuntimeControllerClient | None:
    return cast(RuntimeControllerClient | None, request.app.state.clients.get("runtime_controller"))


def build_orchestration_modifier_service(
    *,
    session: AsyncSession,
) -> FleetOrchestrationModifierService:
    from platform.fleet_learning.personality import FleetPersonalityProfileService
    from platform.fleet_learning.repository import FleetPersonalityProfileRepository

    return FleetOrchestrationModifierService(
        personality_service=FleetPersonalityProfileService(
            repository=FleetPersonalityProfileRepository(session)
        )
    )


def build_health_service(
    *,
    session: AsyncSession,
    redis_client: AsyncRedisClient,
    producer: EventProducer | None,
) -> FleetHealthProjectionService:
    return FleetHealthProjectionService(
        fleet_repo=FleetRepository(session),
        member_repo=FleetMemberRepository(session),
        redis_client=redis_client,
        producer=producer,
    )


async def get_health_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> FleetHealthProjectionService:
    return build_health_service(
        session=session,
        redis_client=_get_redis(request),
        producer=_get_producer(request),
    )


def build_governance_service(
    *,
    session: AsyncSession,
    producer: EventProducer | None,
    oje_service: object | None = None,
    pipeline_config: object | None = None,
) -> FleetGovernanceChainService:
    return FleetGovernanceChainService(
        fleet_repo=FleetRepository(session),
        governance_repo=FleetGovernanceChainRepository(session),
        producer=producer,
        oje_service=oje_service,
        pipeline_config=pipeline_config,
    )


async def get_governance_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    registry_service: RegistryService = Depends(get_registry_service),
    oje_service: object | None = None,
    pipeline_config: object | None = None,
) -> FleetGovernanceChainService:
    from platform.governance.dependencies import (
        build_judge_service,
        build_pipeline_config_service,
    )

    settings = _get_settings(request)
    producer = _get_producer(request)
    if oje_service is None:
        oje_service = build_judge_service(
            session=session,
            settings=settings,
            producer=producer,
            redis_client=_get_redis(request),
            registry_service=registry_service,
        )
    if pipeline_config is None:
        pipeline_config = build_pipeline_config_service(
            session=session,
            registry_service=registry_service,
        )
    return build_governance_service(
        session=session,
        producer=producer,
        oje_service=oje_service,
        pipeline_config=pipeline_config,
    )


def build_fleet_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    registry_service: RegistryService | None,
    modifier_service: FleetOrchestrationModifierService | None = None,
    health_service: FleetHealthProjectionService | None = None,
    runtime_controller: RuntimeControllerClient | None = None,
    tag_service: object | None = None,
    label_service: object | None = None,
    tagging_service: object | None = None,
) -> FleetService:
    return FleetService(
        fleet_repo=FleetRepository(session),
        member_repo=FleetMemberRepository(session),
        topology_repo=FleetTopologyVersionRepository(session),
        policy_repo=FleetPolicyBindingRepository(session),
        observer_repo=ObserverAssignmentRepository(session),
        governance_repo=FleetGovernanceChainRepository(session),
        rules_repo=FleetOrchestrationRulesRepository(session),
        settings=settings,
        producer=producer,
        registry_service=registry_service,
        modifier_service=modifier_service,
        health_service=health_service,
        runtime_controller=runtime_controller,
        tag_service=tag_service,
        label_service=label_service,
        tagging_service=tagging_service,
    )


async def get_fleet_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    registry_service: RegistryService = Depends(get_registry_service),
    health_service: FleetHealthProjectionService = Depends(get_health_service),
) -> FleetService:
    from platform.common.tagging.dependencies import (
        get_label_service,
        get_tag_service,
        get_tagging_service,
    )

    return build_fleet_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        registry_service=registry_service,
        modifier_service=build_orchestration_modifier_service(session=session),
        health_service=health_service,
        runtime_controller=_get_runtime_controller(request),
        tag_service=await get_tag_service(request, session),
        label_service=await get_label_service(request, session),
        tagging_service=await get_tagging_service(request, session),
    )
