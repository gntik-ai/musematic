from __future__ import annotations

from datetime import datetime
from platform.execution.models import (
    ApprovalDecision,
    Execution,
    ExecutionApprovalWait,
    ExecutionCheckpoint,
    ExecutionCompensationRecord,
    ExecutionDispatchLease,
    ExecutionEvent,
    ExecutionEventType,
    ExecutionRollbackAction,
    ExecutionStatus,
    ExecutionTaskPlanRecord,
    ReprioritizationTrigger,
)
from platform.workflows.models import TriggerType
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class ExecutionRepository:
    """Provide persistence helpers for execution."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_execution(self, execution: Execution) -> Execution:
        """Create execution."""
        self.session.add(execution)
        await self.session.flush()
        return execution

    async def get_execution_by_id(self, execution_id: UUID) -> Execution | None:
        """Return execution by id."""
        result = await self.session.execute(select(Execution).where(Execution.id == execution_id))
        return result.scalar_one_or_none()

    async def list_executions(
        self,
        *,
        workspace_id: UUID,
        workflow_id: UUID | None,
        status: ExecutionStatus | None,
        trigger_type: TriggerType | None,
        goal_id: UUID | None,
        since: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[list[Execution], int]:
        """List executions."""
        query = select(Execution).where(Execution.workspace_id == workspace_id)
        count_query = (
            select(func.count())
            .select_from(Execution)
            .where(Execution.workspace_id == workspace_id)
        )
        if workflow_id is not None:
            query = query.where(Execution.workflow_definition_id == workflow_id)
            count_query = count_query.where(Execution.workflow_definition_id == workflow_id)
        if status is not None:
            query = query.where(Execution.status == status)
            count_query = count_query.where(Execution.status == status)
        if trigger_type is not None:
            query = query.where(Execution.trigger_type == trigger_type)
            count_query = count_query.where(Execution.trigger_type == trigger_type)
        if goal_id is not None:
            query = query.where(Execution.correlation_goal_id == goal_id)
            count_query = count_query.where(Execution.correlation_goal_id == goal_id)
        if since is not None:
            query = query.where(Execution.created_at >= since)
            count_query = count_query.where(Execution.created_at >= since)
        total = await self.session.scalar(count_query)
        result = await self.session.execute(
            query.order_by(Execution.created_at.desc(), Execution.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def list_by_statuses(self, statuses: list[ExecutionStatus]) -> list[Execution]:
        """List by statuses."""
        result = await self.session.execute(
            select(Execution)
            .where(Execution.status.in_(statuses))
            .order_by(Execution.created_at.asc(), Execution.id.asc())
        )
        return list(result.scalars().all())

    async def count_active_for_trigger(self, trigger_id: UUID) -> int:
        """Count active for trigger."""
        total = await self.session.scalar(
            select(func.count())
            .select_from(Execution)
            .where(
                Execution.trigger_id == trigger_id,
                Execution.status.in_(
                    [
                        ExecutionStatus.queued,
                        ExecutionStatus.running,
                        ExecutionStatus.waiting_for_approval,
                        ExecutionStatus.compensating,
                    ]
                ),
            )
        )
        return int(total or 0)

    async def update_execution_status(
        self,
        execution: Execution,
        status: ExecutionStatus,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> Execution:
        """Update execution status."""
        execution.status = status
        if started_at is not None:
            execution.started_at = started_at
        if completed_at is not None:
            execution.completed_at = completed_at
        await self.session.flush()
        return execution

    async def append_event(
        self,
        *,
        execution_id: UUID,
        event_type: ExecutionEventType,
        step_id: str | None,
        agent_fqn: str | None,
        payload: dict[str, Any],
        correlation_workspace_id: UUID,
        correlation_execution_id: UUID,
        correlation_conversation_id: UUID | None = None,
        correlation_interaction_id: UUID | None = None,
        correlation_goal_id: UUID | None = None,
        correlation_fleet_id: UUID | None = None,
    ) -> ExecutionEvent:
        """Handle append event."""
        next_sequence = int(await self.count_events(execution_id)) + 1
        event = ExecutionEvent(
            execution_id=execution_id,
            sequence=next_sequence,
            event_type=event_type,
            step_id=step_id,
            agent_fqn=agent_fqn,
            payload=payload,
            correlation_workspace_id=correlation_workspace_id,
            correlation_conversation_id=correlation_conversation_id,
            correlation_interaction_id=correlation_interaction_id,
            correlation_goal_id=correlation_goal_id,
            correlation_fleet_id=correlation_fleet_id,
            correlation_execution_id=correlation_execution_id,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_events(
        self,
        execution_id: UUID,
        *,
        since_sequence: int | None = None,
        event_type: ExecutionEventType | None = None,
    ) -> list[ExecutionEvent]:
        """Return events."""
        query = select(ExecutionEvent).where(ExecutionEvent.execution_id == execution_id)
        if since_sequence is not None:
            query = query.where(ExecutionEvent.sequence > since_sequence)
        if event_type is not None:
            query = query.where(ExecutionEvent.event_type == event_type)
        result = await self.session.execute(query.order_by(ExecutionEvent.sequence.asc()))
        return list(result.scalars().all())

    async def count_events(self, execution_id: UUID) -> int:
        """Count events."""
        total = await self.session.scalar(
            select(func.count())
            .select_from(ExecutionEvent)
            .where(ExecutionEvent.execution_id == execution_id)
        )
        return int(total or 0)

    async def create_checkpoint(self, checkpoint: ExecutionCheckpoint) -> ExecutionCheckpoint:
        """Create checkpoint."""
        self.session.add(checkpoint)
        await self.session.flush()
        return checkpoint

    async def get_next_checkpoint_number(self, execution_id: UUID) -> int:
        """Return next checkpoint number for an execution."""
        total = await self.session.scalar(
            select(func.max(ExecutionCheckpoint.checkpoint_number)).where(
                ExecutionCheckpoint.execution_id == execution_id
            )
        )
        return int(total or 0) + 1

    async def list_checkpoints(
        self,
        execution_id: UUID,
        *,
        include_superseded: bool,
        offset: int,
        limit: int,
    ) -> tuple[list[ExecutionCheckpoint], int]:
        """List checkpoints for an execution."""
        query = select(ExecutionCheckpoint).where(ExecutionCheckpoint.execution_id == execution_id)
        count_query = (
            select(func.count())
            .select_from(ExecutionCheckpoint)
            .where(ExecutionCheckpoint.execution_id == execution_id)
        )
        if not include_superseded:
            query = query.where(ExecutionCheckpoint.superseded.is_(False))
            count_query = count_query.where(ExecutionCheckpoint.superseded.is_(False))
        total = await self.session.scalar(count_query)
        result = await self.session.execute(
            query.order_by(ExecutionCheckpoint.checkpoint_number.asc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def get_checkpoint_by_number(
        self,
        execution_id: UUID,
        checkpoint_number: int,
        *,
        include_superseded: bool = True,
    ) -> ExecutionCheckpoint | None:
        """Return a checkpoint by execution and checkpoint number."""
        query = select(ExecutionCheckpoint).where(
            ExecutionCheckpoint.execution_id == execution_id,
            ExecutionCheckpoint.checkpoint_number == checkpoint_number,
        )
        if not include_superseded:
            query = query.where(ExecutionCheckpoint.superseded.is_(False))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_latest_checkpoint(
        self,
        execution_id: UUID,
        *,
        include_superseded: bool = False,
    ) -> ExecutionCheckpoint | None:
        """Return latest checkpoint."""
        query = select(ExecutionCheckpoint).where(ExecutionCheckpoint.execution_id == execution_id)
        if not include_superseded:
            query = query.where(ExecutionCheckpoint.superseded.is_(False))
        result = await self.session.execute(
            query.order_by(
                ExecutionCheckpoint.checkpoint_number.desc(),
                ExecutionCheckpoint.created_at.desc(),
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_superseded_after(
        self,
        execution_id: UUID,
        checkpoint_number: int,
    ) -> list[ExecutionCheckpoint]:
        """Mark checkpoints after the target as superseded."""
        result = await self.session.execute(
            select(ExecutionCheckpoint)
            .where(ExecutionCheckpoint.execution_id == execution_id)
            .order_by(ExecutionCheckpoint.checkpoint_number.asc())
        )
        items = list(result.scalars().all())
        for item in items:
            item.superseded = item.checkpoint_number > checkpoint_number
        await self.session.flush()
        return items

    async def create_rollback_action(
        self,
        action: ExecutionRollbackAction,
    ) -> ExecutionRollbackAction:
        """Create rollback action."""
        self.session.add(action)
        await self.session.flush()
        return action

    async def list_enabled_reprioritization_triggers(
        self,
        workspace_id: UUID,
    ) -> list[ReprioritizationTrigger]:
        """List enabled reprioritization triggers for a workspace."""
        result = await self.session.execute(
            select(ReprioritizationTrigger)
            .where(
                ReprioritizationTrigger.workspace_id == workspace_id,
                ReprioritizationTrigger.enabled.is_(True),
            )
            .order_by(
                ReprioritizationTrigger.priority_rank.asc(),
                ReprioritizationTrigger.created_at.asc(),
            )
        )
        return list(result.scalars().all())

    async def create_reprioritization_trigger(
        self,
        trigger: ReprioritizationTrigger,
    ) -> ReprioritizationTrigger:
        """Create reprioritization trigger."""
        self.session.add(trigger)
        await self.session.flush()
        return trigger

    async def list_reprioritization_triggers(
        self,
        *,
        workspace_id: UUID,
        enabled: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ReprioritizationTrigger], int]:
        """List reprioritization triggers for a workspace."""
        query = select(ReprioritizationTrigger).where(
            ReprioritizationTrigger.workspace_id == workspace_id
        )
        count_query = (
            select(func.count())
            .select_from(ReprioritizationTrigger)
            .where(ReprioritizationTrigger.workspace_id == workspace_id)
        )
        if enabled is not None:
            query = query.where(ReprioritizationTrigger.enabled.is_(enabled))
            count_query = count_query.where(ReprioritizationTrigger.enabled.is_(enabled))
        total = await self.session.scalar(count_query)
        result = await self.session.execute(
            query.order_by(
                ReprioritizationTrigger.priority_rank.asc(),
                ReprioritizationTrigger.created_at.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)

    async def get_reprioritization_trigger(
        self,
        trigger_id: UUID,
    ) -> ReprioritizationTrigger | None:
        """Return reprioritization trigger."""
        result = await self.session.execute(
            select(ReprioritizationTrigger).where(ReprioritizationTrigger.id == trigger_id)
        )
        return result.scalar_one_or_none()

    async def update_reprioritization_trigger(
        self,
        trigger: ReprioritizationTrigger,
        **fields: Any,
    ) -> ReprioritizationTrigger:
        """Update reprioritization trigger."""
        for key, value in fields.items():
            setattr(trigger, key, value)
        await self.session.flush()
        return trigger

    async def delete_reprioritization_trigger(self, trigger: ReprioritizationTrigger) -> None:
        """Delete reprioritization trigger."""
        await self.session.delete(trigger)
        await self.session.flush()

    async def create_dispatch_lease(
        self,
        lease: ExecutionDispatchLease,
    ) -> ExecutionDispatchLease:
        """Create dispatch lease."""
        self.session.add(lease)
        await self.session.flush()
        return lease

    async def get_active_dispatch_lease(
        self,
        execution_id: UUID,
        step_id: str,
    ) -> ExecutionDispatchLease | None:
        """Return active dispatch lease."""
        result = await self.session.execute(
            select(ExecutionDispatchLease)
            .where(
                ExecutionDispatchLease.execution_id == execution_id,
                ExecutionDispatchLease.step_id == step_id,
                ExecutionDispatchLease.released_at.is_(None),
            )
            .order_by(ExecutionDispatchLease.acquired_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def release_dispatch_lease(
        self,
        lease: ExecutionDispatchLease,
        *,
        released_at: datetime,
        expired: bool = False,
    ) -> ExecutionDispatchLease:
        """Handle release dispatch lease."""
        lease.released_at = released_at
        lease.expired = expired
        await self.session.flush()
        return lease

    async def upsert_task_plan_record(
        self,
        record: ExecutionTaskPlanRecord,
    ) -> ExecutionTaskPlanRecord:
        """Handle upsert task plan record."""
        existing = await self.get_task_plan_record(record.execution_id, record.step_id)
        if existing is None:
            self.session.add(record)
            await self.session.flush()
            return record
        for field in (
            "selected_agent_fqn",
            "selected_tool_fqn",
            "rationale_summary",
            "considered_agents_count",
            "considered_tools_count",
            "rejected_alternatives_count",
            "parameter_sources",
            "storage_key",
            "storage_size_bytes",
        ):
            setattr(existing, field, getattr(record, field))
        await self.session.flush()
        return existing

    async def list_task_plan_records(self, execution_id: UUID) -> list[ExecutionTaskPlanRecord]:
        """List task plan records."""
        result = await self.session.execute(
            select(ExecutionTaskPlanRecord)
            .where(ExecutionTaskPlanRecord.execution_id == execution_id)
            .order_by(ExecutionTaskPlanRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_task_plan_record(
        self,
        execution_id: UUID,
        step_id: str,
    ) -> ExecutionTaskPlanRecord | None:
        """Return task plan record."""
        result = await self.session.execute(
            select(ExecutionTaskPlanRecord).where(
                ExecutionTaskPlanRecord.execution_id == execution_id,
                ExecutionTaskPlanRecord.step_id == step_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_approval_wait(
        self,
        approval_wait: ExecutionApprovalWait,
    ) -> ExecutionApprovalWait:
        """Create approval wait."""
        self.session.add(approval_wait)
        await self.session.flush()
        return approval_wait

    async def get_approval_wait(
        self,
        execution_id: UUID,
        step_id: str,
    ) -> ExecutionApprovalWait | None:
        """Return approval wait."""
        result = await self.session.execute(
            select(ExecutionApprovalWait).where(
                ExecutionApprovalWait.execution_id == execution_id,
                ExecutionApprovalWait.step_id == step_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_approval_waits(self, execution_id: UUID) -> list[ExecutionApprovalWait]:
        """List approval waits."""
        result = await self.session.execute(
            select(ExecutionApprovalWait)
            .where(ExecutionApprovalWait.execution_id == execution_id)
            .order_by(ExecutionApprovalWait.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_pending_approval_waits(self, now: datetime) -> list[ExecutionApprovalWait]:
        """List pending approval waits."""
        result = await self.session.execute(
            select(ExecutionApprovalWait).where(
                ExecutionApprovalWait.timeout_at < now,
                ExecutionApprovalWait.decision.is_(None),
            )
        )
        return list(result.scalars().all())

    async def update_approval_wait(
        self,
        approval_wait: ExecutionApprovalWait,
        *,
        decision: ApprovalDecision,
        decided_by: str | None,
        decided_at: datetime,
    ) -> ExecutionApprovalWait:
        """Update approval wait."""
        approval_wait.decision = decision
        approval_wait.decided_by = decided_by
        approval_wait.decided_at = decided_at
        await self.session.flush()
        return approval_wait

    async def create_compensation_record(
        self,
        record: ExecutionCompensationRecord,
    ) -> ExecutionCompensationRecord:
        """Create compensation record."""
        self.session.add(record)
        await self.session.flush()
        return record
