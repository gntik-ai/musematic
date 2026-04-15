from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from platform.agentops.events import AgentOpsEventType, GovernanceEventPublisher
from platform.agentops.exceptions import CanaryConflictError, CanaryStateError
from platform.agentops.models import CanaryDeployment, CanaryDeploymentStatus, RegressionAlertStatus
from platform.agentops.repository import AgentOpsRepository
from platform.agentops.schemas import CanaryDeploymentCreateRequest
from typing import Any
from uuid import UUID


class CanaryManager:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        governance_publisher: GovernanceEventPublisher | None,
        redis_client: Any | None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.governance_publisher = governance_publisher
        self.redis_client = redis_client
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    async def start(
        self,
        agent_fqn: str,
        request: CanaryDeploymentCreateRequest,
        *,
        initiated_by: UUID,
    ) -> CanaryDeployment:
        existing = await self.repository.get_active_canary(agent_fqn, request.workspace_id)
        if existing is not None:
            raise CanaryConflictError(agent_fqn, request.workspace_id)

        started_at = self._now()
        observation_ends_at = started_at + timedelta(hours=request.observation_window_hours)
        deployment = await self.repository.create_canary(
            CanaryDeployment(
                agent_fqn=agent_fqn,
                workspace_id=request.workspace_id,
                production_revision_id=request.production_revision_id,
                canary_revision_id=request.canary_revision_id,
                initiated_by=initiated_by,
                traffic_percentage=request.traffic_percentage,
                observation_window_hours=request.observation_window_hours,
                quality_tolerance_pct=request.quality_tolerance_pct,
                latency_tolerance_pct=request.latency_tolerance_pct,
                error_rate_tolerance_pct=request.error_rate_tolerance_pct,
                cost_tolerance_pct=request.cost_tolerance_pct,
                status=CanaryDeploymentStatus.active.value,
                started_at=started_at,
                observation_ends_at=observation_ends_at,
            )
        )
        await self._write_routing_key(deployment)
        await self._record_event(
            AgentOpsEventType.canary_started.value,
            deployment,
            actor=initiated_by,
            payload={
                "deployment_id": str(deployment.id),
                "production_revision_id": str(deployment.production_revision_id),
                "canary_revision_id": str(deployment.canary_revision_id),
                "traffic_percentage": deployment.traffic_percentage,
                "observation_ends_at": deployment.observation_ends_at.isoformat(),
            },
        )
        return deployment

    async def promote(
        self,
        canary_id: UUID,
        *,
        manual: bool,
        reason: str | None = None,
        actor: UUID | None = None,
    ) -> CanaryDeployment:
        deployment = await self._get_active_canary(canary_id)
        await self._clear_routing_key(deployment)
        now = self._now()
        deployment.status = (
            CanaryDeploymentStatus.manually_promoted.value
            if manual
            else CanaryDeploymentStatus.auto_promoted.value
        )
        deployment.promoted_at = now
        deployment.completed_at = now
        if manual:
            deployment.manual_override_by = actor
            deployment.manual_override_reason = reason
        updated = await self.repository.update_canary(deployment)
        await self._record_event(
            AgentOpsEventType.canary_promoted.value,
            updated,
            actor=actor,
            payload={
                "deployment_id": str(updated.id),
                "manual": manual,
                "reason": reason,
            },
        )
        return updated

    async def rollback(
        self,
        canary_id: UUID,
        *,
        reason: str,
        manual: bool,
        actor: UUID | None = None,
    ) -> CanaryDeployment:
        deployment = await self._get_active_canary(canary_id)
        await self._clear_routing_key(deployment)
        now = self._now()
        deployment.status = (
            CanaryDeploymentStatus.manually_rolled_back.value
            if manual
            else CanaryDeploymentStatus.auto_rolled_back.value
        )
        deployment.rollback_reason = reason
        deployment.rolled_back_at = now
        deployment.completed_at = now
        if manual:
            deployment.manual_override_by = actor
            deployment.manual_override_reason = reason
        updated = await self.repository.update_canary(deployment)
        await self._mark_related_regression_alerts(updated)
        await self._record_event(
            AgentOpsEventType.canary_rolled_back.value,
            updated,
            actor=actor,
            payload={
                "deployment_id": str(updated.id),
                "manual": manual,
                "reason": reason,
            },
        )
        return updated

    async def _mark_related_regression_alerts(self, deployment: CanaryDeployment) -> None:
        alerts, _ = await self.repository.list_regression_alerts(
            deployment.agent_fqn,
            deployment.workspace_id,
            status=RegressionAlertStatus.active.value,
            new_revision_id=deployment.canary_revision_id,
            limit=100,
        )
        for alert in alerts:
            alert.triggered_rollback = True
            await self.repository.update_regression_alert(alert)

    async def _get_active_canary(self, canary_id: UUID) -> CanaryDeployment:
        deployment = await self.repository.get_canary(canary_id)
        if deployment is None:
            raise CanaryStateError(canary_id, "missing")
        if deployment.status != CanaryDeploymentStatus.active.value:
            raise CanaryStateError(canary_id, deployment.status)
        return deployment

    async def _write_routing_key(self, deployment: CanaryDeployment) -> None:
        if self.redis_client is None:
            return
        payload = {
            "deployment_id": str(deployment.id),
            "canary_revision_id": str(deployment.canary_revision_id),
            "production_revision_id": str(deployment.production_revision_id),
            "traffic_percentage": deployment.traffic_percentage,
            "observation_window_end": deployment.observation_ends_at.isoformat(),
        }
        ttl_seconds = self._ttl_seconds(deployment.observation_ends_at)
        await self.redis_client.set(
            self._routing_key(deployment.workspace_id, deployment.agent_fqn),
            json.dumps(payload).encode(),
            ttl=ttl_seconds,
        )

    async def _clear_routing_key(self, deployment: CanaryDeployment) -> None:
        if self.redis_client is None:
            return
        await self.redis_client.delete(
            self._routing_key(deployment.workspace_id, deployment.agent_fqn)
        )

    async def _record_event(
        self,
        event_type: str,
        deployment: CanaryDeployment,
        *,
        actor: UUID | None,
        payload: dict[str, Any],
    ) -> None:
        if self.governance_publisher is None:
            return
        await self.governance_publisher.record(
            event_type,
            deployment.agent_fqn,
            deployment.workspace_id,
            payload=payload,
            actor=actor,
            revision_id=deployment.canary_revision_id,
        )

    def _ttl_seconds(self, observation_ends_at: datetime) -> int:
        remaining = int((observation_ends_at - self._now()).total_seconds())
        return max(1, remaining + 3600)

    def _now(self) -> datetime:
        return self._now_factory()

    @staticmethod
    def _routing_key(workspace_id: UUID, agent_fqn: str) -> str:
        return f"canary:{workspace_id}:{agent_fqn}"
