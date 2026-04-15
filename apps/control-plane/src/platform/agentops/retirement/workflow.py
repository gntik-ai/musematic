from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from platform.agentops.events import AgentOpsEventType, GovernanceEventPublisher
from platform.agentops.exceptions import RetirementConflictError
from platform.agentops.models import RetirementWorkflow, RetirementWorkflowStatus
from platform.agentops.repository import AgentOpsRepository
from platform.common.exceptions import NotFoundError, ValidationError
from typing import Any
from uuid import UUID


class RetirementManager:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        governance_publisher: GovernanceEventPublisher | None,
        workflow_service: Any | None,
        registry_service: Any | None,
        now_factory: Callable[[], datetime] | None = None,
        grace_period_days: int = 14,
    ) -> None:
        self.repository = repository
        self.governance_publisher = governance_publisher
        self.workflow_service = workflow_service
        self.registry_service = registry_service
        self._now_factory = now_factory or (lambda: datetime.now(UTC))
        self.grace_period_days = grace_period_days

    async def initiate(
        self,
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
        *,
        trigger_reason: str,
        triggered_by: UUID | None,
        operator_confirmed: bool = False,
    ) -> RetirementWorkflow:
        existing = await self.repository.get_active_retirement(agent_fqn, workspace_id)
        if existing is not None:
            raise RetirementConflictError(agent_fqn, workspace_id)

        dependent_workflows = await self._dependent_workflows(agent_fqn, workspace_id)
        now = self._now()
        workflow = await self.repository.create_retirement(
            RetirementWorkflow(
                workspace_id=workspace_id,
                agent_fqn=agent_fqn,
                revision_id=revision_id,
                trigger_reason=trigger_reason,
                trigger_detail={"reason": trigger_reason},
                status=RetirementWorkflowStatus.grace_period.value,
                dependent_workflows=dependent_workflows,
                high_impact_flag=bool(dependent_workflows),
                operator_confirmed=operator_confirmed,
                notifications_sent_at=now,
                grace_period_days=self.grace_period_days,
                grace_period_starts_at=now,
                grace_period_ends_at=now + timedelta(days=self.grace_period_days),
            )
        )
        await self._record_event(
            AgentOpsEventType.retirement_initiated.value,
            workflow,
            actor=triggered_by,
            payload={
                "workflow_id": str(workflow.id),
                "trigger_reason": trigger_reason,
                "dependent_workflow_count": len(dependent_workflows),
                "high_impact_flag": workflow.high_impact_flag,
            },
        )
        return workflow

    async def get(self, workflow_id: UUID) -> RetirementWorkflow:
        workflow = await self.repository.get_retirement(workflow_id)
        if workflow is None:
            raise NotFoundError("AGENTOPS_RETIREMENT_NOT_FOUND", "Retirement workflow not found")
        return workflow

    async def confirm(
        self,
        workflow_id: UUID,
        *,
        confirmed_by: UUID | None,
        reason: str,
    ) -> RetirementWorkflow:
        workflow = await self.get(workflow_id)
        workflow.operator_confirmed = True
        workflow.updated_at = self._now()
        updated = await self.repository.update_retirement(workflow)
        await self._record_event(
            AgentOpsEventType.retirement_initiated.value,
            updated,
            actor=confirmed_by,
            payload={
                "workflow_id": str(updated.id),
                "confirmation_reason": reason,
                "operator_confirmed": True,
            },
        )
        return updated

    async def retire_agent(self, workflow_id: UUID) -> RetirementWorkflow:
        workflow = await self.get(workflow_id)
        if workflow.high_impact_flag and not workflow.operator_confirmed:
            raise ValidationError(
                "AGENTOPS_RETIREMENT_CONFIRMATION_REQUIRED",
                "High-impact retirement requires operator confirmation",
            )
        if self.registry_service is not None and hasattr(
            self.registry_service,
            "set_marketplace_visibility",
        ):
            await self.registry_service.set_marketplace_visibility(
                workflow.agent_fqn,
                False,
                workflow.workspace_id,
            )
        workflow.status = RetirementWorkflowStatus.retired.value
        workflow.retired_at = self._now()
        updated = await self.repository.update_retirement(workflow)
        await self._record_event(
            AgentOpsEventType.retirement_completed.value,
            updated,
            actor=None,
            payload={
                "workflow_id": str(updated.id),
                "trigger_reason": updated.trigger_reason,
            },
        )
        return updated

    async def halt(
        self,
        workflow_id: UUID,
        *,
        reason: str,
        halted_by: UUID | None,
    ) -> RetirementWorkflow:
        workflow = await self.get(workflow_id)
        workflow.status = RetirementWorkflowStatus.halted.value
        workflow.halted_at = self._now()
        workflow.halted_by = halted_by
        workflow.halt_reason = reason
        updated = await self.repository.update_retirement(workflow)
        await self._record_event(
            AgentOpsEventType.retirement_completed.value,
            updated,
            actor=halted_by,
            payload={
                "workflow_id": str(updated.id),
                "halt_reason": reason,
                "status": updated.status,
            },
        )
        return updated

    async def _dependent_workflows(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> list[dict[str, Any]]:
        if self.workflow_service is None or not hasattr(
            self.workflow_service,
            "find_workflows_using_agent",
        ):
            return []
        return list(await self.workflow_service.find_workflows_using_agent(agent_fqn, workspace_id))

    async def _record_event(
        self,
        event_type: str,
        workflow: RetirementWorkflow,
        *,
        actor: UUID | None,
        payload: dict[str, Any],
    ) -> None:
        if self.governance_publisher is None:
            return
        await self.governance_publisher.record(
            event_type,
            workflow.agent_fqn,
            workflow.workspace_id,
            payload=payload,
            actor=actor,
            revision_id=workflow.revision_id,
        )

    def _now(self) -> datetime:
        return self._now_factory()
