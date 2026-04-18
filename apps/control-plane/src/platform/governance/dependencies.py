from __future__ import annotations

from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.fleets.repository import (
    FleetGovernanceChainRepository,
    FleetPolicyBindingRepository,
)
from platform.governance.exceptions import VerdictNotFoundError
from platform.governance.repository import GovernanceRepository
from platform.governance.schemas import (
    EnforcementActionListQuery,
    EnforcementActionListResponse,
    EnforcementActionRead,
    GovernanceVerdictDetail,
    GovernanceVerdictRead,
    VerdictListQuery,
    VerdictListResponse,
)
from platform.governance.services.enforcer_service import EnforcerService
from platform.governance.services.judge_service import JudgeService
from platform.governance.services.pipeline_config import PipelineConfigService
from platform.policies.repository import PolicyRepository
from platform.registry.dependencies import get_registry_service
from platform.registry.service import RegistryService
from platform.trust.dependencies import build_certification_service
from platform.workspaces.governance import WorkspaceGovernanceChainRepository
from typing import cast
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


class GovernanceService:
    def __init__(self, repository: GovernanceRepository) -> None:
        self.repository = repository

    async def list_verdicts(self, query: VerdictListQuery) -> VerdictListResponse:
        items, total, next_cursor = await self.repository.list_verdicts(query)
        return VerdictListResponse(
            items=[GovernanceVerdictRead.model_validate(item) for item in items],
            total=total,
            next_cursor=next_cursor,
        )

    async def get_verdict(self, verdict_id: UUID) -> GovernanceVerdictDetail:
        verdict = await self.repository.get_verdict(verdict_id)
        if verdict is None:
            raise VerdictNotFoundError(verdict_id)
        action = verdict.enforcement_actions[0] if verdict.enforcement_actions else None
        return GovernanceVerdictDetail(
            **GovernanceVerdictRead.model_validate(verdict).model_dump(),
            evidence=verdict.evidence,
            enforcement_action=(EnforcementActionRead.model_validate(action) if action else None),
        )

    async def list_enforcement_actions(
        self, query: EnforcementActionListQuery
    ) -> EnforcementActionListResponse:
        items, total, next_cursor = await self.repository.list_enforcement_actions(query)
        return EnforcementActionListResponse(
            items=[EnforcementActionRead.model_validate(item) for item in items],
            total=total,
            next_cursor=next_cursor,
        )


def build_pipeline_config_service(
    *,
    session: AsyncSession,
    registry_service: RegistryService | None,
) -> PipelineConfigService:
    return PipelineConfigService(
        fleet_governance_repo=FleetGovernanceChainRepository(session),
        workspace_governance_repo=WorkspaceGovernanceChainRepository(session),
        registry_service=registry_service,
    )


async def get_pipeline_config_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    registry_service: RegistryService = Depends(get_registry_service),
) -> PipelineConfigService:
    del request
    return build_pipeline_config_service(session=session, registry_service=registry_service)


def build_judge_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    registry_service: RegistryService | None,
) -> JudgeService:
    return JudgeService(
        repository=GovernanceRepository(session),
        pipeline_config=build_pipeline_config_service(
            session=session,
            registry_service=registry_service,
        ),
        fleet_policy_repo=FleetPolicyBindingRepository(session),
        policy_repo=PolicyRepository(session),
        settings=settings,
        producer=producer,
        redis_client=redis_client,
    )


async def get_judge_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    registry_service: RegistryService = Depends(get_registry_service),
) -> JudgeService:
    return build_judge_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
        registry_service=registry_service,
    )


def build_enforcer_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
) -> EnforcerService:
    return EnforcerService(
        repository=GovernanceRepository(session),
        producer=producer,
        certification_service=build_certification_service(
            session=session,
            settings=settings,
            producer=producer,
        ),
    )


async def get_enforcer_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> EnforcerService:
    return build_enforcer_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
    )


def build_governance_service(*, session: AsyncSession) -> GovernanceService:
    return GovernanceService(GovernanceRepository(session))


async def get_governance_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> GovernanceService:
    del request
    return build_governance_service(session=session)
