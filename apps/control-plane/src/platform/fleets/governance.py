from __future__ import annotations

from platform.common.events.envelope import CorrelationContext
from platform.fleets.events import (
    FleetEventType,
    FleetGovernanceChainUpdatedPayload,
    publish_fleet_event,
)
from platform.fleets.exceptions import FleetNotFoundError, FleetStateError
from platform.fleets.models import FleetGovernanceChain
from platform.fleets.repository import FleetGovernanceChainRepository, FleetRepository
from platform.fleets.schemas import (
    FleetGovernanceChainListResponse,
    FleetGovernanceChainResponse,
    FleetGovernanceChainUpdate,
)
from typing import Any
from uuid import UUID, uuid4


def _correlation(workspace_id: UUID, fleet_id: UUID) -> CorrelationContext:
    return CorrelationContext(workspace_id=workspace_id, fleet_id=fleet_id, correlation_id=uuid4())


class FleetGovernanceChainService:
    def __init__(
        self,
        *,
        fleet_repo: FleetRepository,
        governance_repo: FleetGovernanceChainRepository,
        producer: Any | None,
        oje_service: Any | None = None,
        pipeline_config: Any | None = None,
    ) -> None:
        self.fleet_repo = fleet_repo
        self.governance_repo = governance_repo
        self.producer = producer
        self.oje_service = oje_service
        self.pipeline_config = pipeline_config

    async def get_chain(self, fleet_id: UUID, workspace_id: UUID) -> FleetGovernanceChainResponse:
        await self._require_fleet(fleet_id, workspace_id)
        chain = await self.governance_repo.get_current(fleet_id)
        if chain is None:
            raise FleetStateError(
                "Fleet governance chain was not found", code="FLEET_GOVERNANCE_NOT_FOUND"
            )
        return FleetGovernanceChainResponse.model_validate(chain)

    async def update_chain(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        request: FleetGovernanceChainUpdate,
    ) -> FleetGovernanceChainResponse:
        await self._require_fleet(fleet_id, workspace_id)
        if self.pipeline_config is not None:
            await self.pipeline_config.validate_chain_update(
                request.observer_fqns,
                request.judge_fqns,
                request.enforcer_fqns,
                workspace_id=workspace_id,
            )
        current = await self.governance_repo.get_current(fleet_id)
        version_number = 1 if current is None else current.version + 1
        chain = await self.governance_repo.create_version(
            FleetGovernanceChain(
                fleet_id=fleet_id,
                workspace_id=workspace_id,
                version=version_number,
                observer_fqns=request.observer_fqns,
                judge_fqns=request.judge_fqns,
                enforcer_fqns=request.enforcer_fqns,
                policy_binding_ids=[str(item) for item in request.policy_binding_ids],
                verdict_to_action_mapping=request.verdict_to_action_mapping,
                is_current=True,
                is_default=False,
            )
        )
        await publish_fleet_event(
            self.producer,
            FleetEventType.fleet_governance_chain_updated,
            FleetGovernanceChainUpdatedPayload(
                fleet_id=fleet_id,
                workspace_id=workspace_id,
                version=chain.version,
                is_default=chain.is_default,
            ),
            _correlation(workspace_id, fleet_id),
        )
        return FleetGovernanceChainResponse.model_validate(chain)

    async def get_chain_history(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
    ) -> FleetGovernanceChainListResponse:
        await self._require_fleet(fleet_id, workspace_id)
        items = await self.governance_repo.list_history(fleet_id)
        return FleetGovernanceChainListResponse(
            items=[FleetGovernanceChainResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def create_default_chain(
        self, fleet_id: UUID, workspace_id: UUID
    ) -> FleetGovernanceChainResponse:
        chain = await self.governance_repo.create_version(
            FleetGovernanceChain(
                fleet_id=fleet_id,
                workspace_id=workspace_id,
                version=1,
                observer_fqns=["platform:default-observer"],
                judge_fqns=["platform:default-judge"],
                enforcer_fqns=["platform:default-enforcer"],
                policy_binding_ids=[],
                verdict_to_action_mapping={},
                is_current=True,
                is_default=True,
            )
        )
        return FleetGovernanceChainResponse.model_validate(chain)

    async def trigger_oje_pipeline(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        signal: dict[str, object],
    ) -> object:
        chain = await self.get_chain(fleet_id, workspace_id)
        processor = getattr(self.oje_service, "process_fleet_anomaly_signal", None)
        if processor is None:
            return {
                "fleet_id": str(fleet_id),
                "workspace_id": str(workspace_id),
                "status": "skipped",
                "reason": "OJE pipeline interface unavailable",
                "signal": signal,
            }
        return await processor(fleet_id, chain, signal)

    async def _require_fleet(self, fleet_id: UUID, workspace_id: UUID) -> None:
        if await self.fleet_repo.get_by_id(fleet_id, workspace_id) is None:
            raise FleetNotFoundError(fleet_id)
