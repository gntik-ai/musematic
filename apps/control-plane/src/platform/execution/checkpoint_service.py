from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.execution.events import ExecutionRolledBackEvent, publish_execution_rolled_back
from platform.execution.exceptions import (
    CheckpointNotFoundError,
    CheckpointRetentionExpiredError,
    CheckpointSizeLimitExceededError,
    ExecutionNotFoundError,
    RollbackFailedError,
    RollbackNotEligibleError,
)
from platform.execution.models import (
    Execution,
    ExecutionCheckpoint,
    ExecutionEventType,
    ExecutionRollbackAction,
    ExecutionStatus,
    RollbackActionStatus,
)
from platform.execution.projector import ExecutionProjector
from platform.execution.repository import ExecutionRepository
from platform.execution.schemas import (
    DEFAULT_CHECKPOINT_POLICY,
    CheckpointDetailResponse,
    CheckpointListResponse,
    CheckpointSummaryResponse,
    ExecutionStateResponse,
    RollbackResponse,
)
from platform.workflows.ir import StepIR
from typing import Any, ClassVar
from uuid import UUID, uuid4

from sqlalchemy import and_, exists, select


class CheckpointService:
    """Manage policy-aware execution checkpoints and rollback."""

    ROLLBACK_ELIGIBLE_STATUSES: ClassVar[set[ExecutionStatus]] = {
        ExecutionStatus.paused,
        ExecutionStatus.waiting_for_approval,
        ExecutionStatus.failed,
        ExecutionStatus.rolled_back,
    }

    def __init__(
        self,
        *,
        repository: ExecutionRepository,
        settings: PlatformSettings,
        producer: EventProducer | None,
        projector: ExecutionProjector | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.projector = projector or ExecutionProjector()

    def should_capture(self, step: StepIR, policy_dict: dict[str, Any] | None) -> bool:
        """Return whether a checkpoint should be captured before a step."""
        policy = dict(policy_dict or DEFAULT_CHECKPOINT_POLICY)
        policy_type = str(policy.get("type", DEFAULT_CHECKPOINT_POLICY["type"]))
        if policy_type == "disabled":
            return False
        if policy_type == "before_every_step":
            return True
        if policy_type == "named_steps":
            return step.step_id in {str(item) for item in policy.get("step_ids", [])}
        return step.step_type == "tool_call"

    async def capture(
        self,
        *,
        execution: Execution,
        step_id: str,
        state: ExecutionStateResponse,
        policy_snapshot: dict[str, Any] | None,
    ) -> ExecutionCheckpoint:
        """Persist a checkpoint snapshot for an execution."""
        snapshot = self._snapshot_payload(state=state, policy_snapshot=policy_snapshot)
        encoded = json.dumps(snapshot, sort_keys=True, default=str).encode("utf-8")
        if len(encoded) > self.settings.checkpoint_max_size_bytes:
            raise CheckpointSizeLimitExceededError(
                size_bytes=len(encoded),
                limit_bytes=self.settings.checkpoint_max_size_bytes,
            )
        checkpoint = ExecutionCheckpoint(
            execution_id=execution.id,
            checkpoint_number=await self.repository.get_next_checkpoint_number(execution.id),
            last_event_sequence=state.last_event_sequence,
            step_results=dict(state.step_results),
            completed_step_ids=list(state.completed_step_ids),
            pending_step_ids=list(state.pending_step_ids),
            active_step_ids=list(state.active_step_ids),
            execution_data=dict(state.step_results.get("_execution_data", {})),
            current_context=dict(snapshot["current_context"]),
            accumulated_costs=dict(snapshot["accumulated_costs"]),
            superseded=False,
            policy_snapshot=dict(snapshot["policy_snapshot"]),
        )
        return await self.repository.create_checkpoint(checkpoint)

    async def list_checkpoints(
        self,
        execution_id: UUID,
        *,
        include_superseded: bool,
        page: int,
        page_size: int,
    ) -> CheckpointListResponse:
        execution = await self.repository.get_execution_by_id(execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        items, total = await self.repository.list_checkpoints(
            execution_id,
            include_superseded=include_superseded,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return CheckpointListResponse(
            items=[self._checkpoint_summary(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_checkpoint(
        self,
        execution_id: UUID,
        checkpoint_number: int,
    ) -> CheckpointDetailResponse:
        execution = await self.repository.get_execution_by_id(execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        checkpoint = await self.repository.get_checkpoint_by_number(
            execution_id,
            checkpoint_number,
            include_superseded=True,
        )
        if checkpoint is None:
            raise CheckpointNotFoundError(execution_id, checkpoint_number)
        return self._checkpoint_detail(checkpoint)

    async def rollback(
        self,
        execution_id: UUID,
        checkpoint_number: int,
        *,
        initiated_by: UUID | None,
        reason: str | None,
    ) -> RollbackResponse:
        execution = await self.repository.get_execution_by_id(execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        if execution.status not in self.ROLLBACK_ELIGIBLE_STATUSES:
            raise RollbackNotEligibleError(execution_id, execution.status)

        checkpoint = await self.repository.get_checkpoint_by_number(
            execution_id,
            checkpoint_number,
            include_superseded=True,
        )
        if checkpoint is None:
            raise CheckpointNotFoundError(execution_id, checkpoint_number)
        if checkpoint.created_at < datetime.now(UTC) - timedelta(
            days=self.settings.checkpoint_retention_days
        ):
            raise CheckpointRetentionExpiredError(execution_id, checkpoint_number)

        latest = await self.repository.get_latest_checkpoint(execution_id, include_superseded=True)
        cost_delta_reversed = self._compute_cost_delta(
            latest.accumulated_costs if latest is not None else {},
            checkpoint.accumulated_costs,
        )

        try:
            action = await self.repository.create_rollback_action(
                ExecutionRollbackAction(
                    execution_id=execution.id,
                    target_checkpoint_id=checkpoint.id,
                    target_checkpoint_number=checkpoint.checkpoint_number,
                    initiated_by=initiated_by,
                    cost_delta_reversed=cost_delta_reversed,
                    status=RollbackActionStatus.completed,
                    failure_reason=reason,
                )
            )
            await self.repository.mark_superseded_after(execution.id, checkpoint.checkpoint_number)
            await self.repository.update_execution_status(execution, ExecutionStatus.rolled_back)
            await self.repository.append_event(
                execution_id=execution.id,
                event_type=ExecutionEventType.rolled_back,
                step_id=None,
                agent_fqn=None,
                payload={
                    "rollback_action_id": str(action.id),
                    "target_checkpoint_number": checkpoint.checkpoint_number,
                    "completed_step_ids": list(checkpoint.completed_step_ids),
                    "pending_step_ids": list(checkpoint.pending_step_ids),
                    "active_step_ids": list(checkpoint.active_step_ids),
                    "step_results": dict(checkpoint.step_results),
                    "workflow_version_id": str(execution.workflow_version_id),
                    "reason": reason,
                },
                correlation_workspace_id=execution.workspace_id,
                correlation_execution_id=execution.id,
                correlation_conversation_id=execution.correlation_conversation_id,
                correlation_interaction_id=execution.correlation_interaction_id,
                correlation_goal_id=execution.correlation_goal_id,
                correlation_fleet_id=execution.correlation_fleet_id,
            )
            await publish_execution_rolled_back(
                self.producer,
                ExecutionRolledBackEvent(
                    execution_id=execution.id,
                    rollback_action_id=action.id,
                    target_checkpoint_number=checkpoint.checkpoint_number,
                    workspace_id=execution.workspace_id,
                ),
                self._correlation(execution),
            )
            return RollbackResponse(
                rollback_action_id=action.id,
                execution_id=execution.id,
                target_checkpoint_id=checkpoint.id,
                target_checkpoint_number=checkpoint.checkpoint_number,
                initiated_by=initiated_by,
                cost_delta_reversed=cost_delta_reversed,
                status=action.status.value,
                execution_status=execution.status,
                warning=(
                    "External side effects made after the rollback point must be "
                    "reconciled manually."
                ),
                created_at=action.created_at,
            )
        except Exception as exc:
            await self.repository.create_rollback_action(
                ExecutionRollbackAction(
                    execution_id=execution.id,
                    target_checkpoint_id=checkpoint.id,
                    target_checkpoint_number=checkpoint.checkpoint_number,
                    initiated_by=initiated_by,
                    cost_delta_reversed={},
                    status=RollbackActionStatus.failed,
                    failure_reason=str(exc),
                )
            )
            await self.repository.update_execution_status(
                execution, ExecutionStatus.rollback_failed
            )
            commit = getattr(self.repository.session, "commit", None)
            if callable(commit):
                result = commit()
                if hasattr(result, "__await__"):
                    await result
            raise RollbackFailedError(execution_id, checkpoint_number, str(exc)) from exc

    async def gc_expired(self, retention_days: int) -> int:
        """Delete expired checkpoints not pinned by rollback actions."""
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await self.repository.session.execute(
            select(ExecutionCheckpoint).where(
                ExecutionCheckpoint.created_at < cutoff,
                ~exists(
                    select(ExecutionRollbackAction.id).where(
                        and_(
                            ExecutionRollbackAction.target_checkpoint_id == ExecutionCheckpoint.id,
                            ExecutionRollbackAction.status != RollbackActionStatus.failed,
                        )
                    )
                ),
            )
        )
        items = list(result.scalars().all())
        for item in items:
            await self.repository.session.delete(item)
        await self.repository.session.flush()
        return len(items)

    def _snapshot_payload(
        self,
        *,
        state: ExecutionStateResponse,
        policy_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        current_context = dict(state.step_results.get("_execution_data", {}))
        accumulated_costs = dict(state.step_results.get("_accumulated_costs", {}))
        return {
            "last_event_sequence": state.last_event_sequence,
            "step_results": dict(state.step_results),
            "completed_step_ids": list(state.completed_step_ids),
            "pending_step_ids": list(state.pending_step_ids),
            "active_step_ids": list(state.active_step_ids),
            "current_context": current_context,
            "accumulated_costs": accumulated_costs,
            "policy_snapshot": dict(policy_snapshot or DEFAULT_CHECKPOINT_POLICY),
        }

    def _checkpoint_summary(self, checkpoint: ExecutionCheckpoint) -> CheckpointSummaryResponse:
        current_step_id = None
        if checkpoint.active_step_ids:
            current_step_id = checkpoint.active_step_ids[0]
        elif checkpoint.pending_step_ids:
            current_step_id = checkpoint.pending_step_ids[0]
        return CheckpointSummaryResponse(
            id=checkpoint.id,
            execution_id=checkpoint.execution_id,
            checkpoint_number=checkpoint.checkpoint_number,
            last_event_sequence=checkpoint.last_event_sequence,
            created_at=checkpoint.created_at,
            completed_step_count=len(checkpoint.completed_step_ids),
            current_step_id=current_step_id,
            accumulated_costs=dict(checkpoint.accumulated_costs),
            superseded=checkpoint.superseded,
            policy_snapshot=dict(checkpoint.policy_snapshot),
        )

    def _checkpoint_detail(self, checkpoint: ExecutionCheckpoint) -> CheckpointDetailResponse:
        return CheckpointDetailResponse(
            id=checkpoint.id,
            execution_id=checkpoint.execution_id,
            checkpoint_number=checkpoint.checkpoint_number,
            last_event_sequence=checkpoint.last_event_sequence,
            created_at=checkpoint.created_at,
            step_results=dict(checkpoint.step_results),
            completed_step_ids=list(checkpoint.completed_step_ids),
            pending_step_ids=list(checkpoint.pending_step_ids),
            active_step_ids=list(checkpoint.active_step_ids),
            current_context=dict(checkpoint.current_context),
            accumulated_costs=dict(checkpoint.accumulated_costs),
            execution_data=dict(checkpoint.execution_data),
            superseded=checkpoint.superseded,
            policy_snapshot=dict(checkpoint.policy_snapshot),
        )

    def _compute_cost_delta(
        self,
        latest_costs: dict[str, Any],
        target_costs: dict[str, Any],
    ) -> dict[str, Any]:
        reversed_costs: dict[str, Any] = {}
        keys = set(latest_costs) | set(target_costs)
        for key in keys:
            latest_value = latest_costs.get(key, 0)
            target_value = target_costs.get(key, 0)
            if isinstance(latest_value, (int, float)) and isinstance(target_value, (int, float)):
                reversed_costs[key] = latest_value - target_value
        return reversed_costs

    @staticmethod
    def _correlation(execution: Execution) -> CorrelationContext:
        return CorrelationContext(
            workspace_id=execution.workspace_id,
            conversation_id=execution.correlation_conversation_id,
            interaction_id=execution.correlation_interaction_id,
            execution_id=execution.id,
            fleet_id=execution.correlation_fleet_id,
            goal_id=execution.correlation_goal_id,
            correlation_id=uuid4(),
        )
