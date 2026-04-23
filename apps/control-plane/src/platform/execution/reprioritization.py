from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from platform.common.exceptions import ValidationError
from platform.execution.exceptions import ReprioritizationTriggerNotFoundError
from platform.execution.models import Execution, ReprioritizationTrigger
from platform.execution.repository import ExecutionRepository
from platform.execution.schemas import ReprioritizationTriggerCreate, ReprioritizationTriggerUpdate
from time import monotonic
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class ReprioritizationFiring:
    execution_id: UUID
    trigger: ReprioritizationTrigger
    old_position: int
    new_position: int
    remaining_fraction: float


@dataclass(slots=True)
class ReprioritizationResult:
    ordered_executions: list[Execution]
    firings: list[ReprioritizationFiring]
    timed_out: bool = False


class ReprioritizationService:
    """Manage reprioritization triggers and per-cycle queue ordering."""

    def __init__(self, *, repository: ExecutionRepository) -> None:
        self.repository = repository

    async def create_trigger(
        self,
        data: ReprioritizationTriggerCreate,
        *,
        created_by: UUID | None,
    ) -> ReprioritizationTrigger:
        payload = self._validate_condition_config(data.trigger_type, data.condition_config)
        trigger = ReprioritizationTrigger(
            workspace_id=data.workspace_id,
            name=data.name,
            trigger_type=data.trigger_type,
            condition_config=payload,
            action=data.action,
            priority_rank=data.priority_rank,
            enabled=data.enabled,
            created_by=created_by,
        )
        self._validate_action(trigger.action)
        return await self.repository.create_reprioritization_trigger(trigger)

    async def list_triggers(
        self,
        workspace_id: UUID,
        *,
        enabled: bool | None = None,
        include_global: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ReprioritizationTrigger], int]:
        del include_global
        return await self.repository.list_reprioritization_triggers(
            workspace_id=workspace_id,
            enabled=enabled,
            offset=(page - 1) * page_size,
            limit=page_size,
        )

    async def get_trigger(
        self,
        trigger_id: UUID,
        workspace_id: UUID | None = None,
    ) -> ReprioritizationTrigger:
        trigger = await self.repository.get_reprioritization_trigger(trigger_id)
        if trigger is None:
            raise ReprioritizationTriggerNotFoundError(trigger_id)
        if workspace_id is not None and trigger.workspace_id != workspace_id:
            raise ReprioritizationTriggerNotFoundError(trigger_id)
        return trigger

    async def update_trigger(
        self,
        trigger_id: UUID,
        data: ReprioritizationTriggerUpdate,
        *,
        workspace_id: UUID | None = None,
    ) -> ReprioritizationTrigger:
        trigger = await self.get_trigger(trigger_id, workspace_id)
        fields: dict[str, Any] = {}
        if data.name is not None:
            fields["name"] = data.name
        if data.condition_config is not None:
            fields["condition_config"] = self._validate_condition_config(
                trigger.trigger_type,
                data.condition_config,
            )
        if data.action is not None:
            self._validate_action(data.action)
            fields["action"] = data.action
        if data.priority_rank is not None:
            fields["priority_rank"] = data.priority_rank
        if data.enabled is not None:
            fields["enabled"] = data.enabled
        return await self.repository.update_reprioritization_trigger(trigger, **fields)

    async def delete_trigger(
        self,
        trigger_id: UUID,
        *,
        workspace_id: UUID | None = None,
    ) -> None:
        trigger = await self.get_trigger(trigger_id, workspace_id)
        await self.repository.delete_reprioritization_trigger(trigger)

    async def evaluate_for_dispatch_cycle(
        self,
        executions: list[Execution],
        workspace_id: UUID,
        cycle_budget_ms: int,
    ) -> ReprioritizationResult:
        if not executions:
            return ReprioritizationResult(ordered_executions=[], firings=[])

        triggers = await self.repository.list_enabled_reprioritization_triggers(workspace_id)
        if not triggers:
            return ReprioritizationResult(ordered_executions=list(executions), firings=[])

        started = monotonic()
        original_order = list(executions)
        original_positions = {item.id: index + 1 for index, item in enumerate(original_order)}
        winners: dict[UUID, tuple[ReprioritizationTrigger, float, int]] = {}

        for trigger in triggers:
            for index, execution in enumerate(original_order):
                if cycle_budget_ms >= 0 and (monotonic() - started) * 1000.0 > cycle_budget_ms:
                    return ReprioritizationResult(
                        ordered_executions=original_order,
                        firings=[],
                        timed_out=True,
                    )
                if execution.id in winners:
                    continue
                score = self._evaluate_execution(execution, trigger)
                if score is None:
                    continue
                winners[execution.id] = (trigger, score, index)

        if not winners:
            return ReprioritizationResult(ordered_executions=original_order, firings=[])

        def sort_key(execution: Execution) -> tuple[int, int, float, int]:
            winner = winners.get(execution.id)
            if winner is None:
                return (1, 0, 0.0, original_positions[execution.id])
            trigger, score, original_index = winner
            return (0, trigger.priority_rank, score, original_index)

        ordered = sorted(original_order, key=sort_key)
        firings: list[ReprioritizationFiring] = []
        for new_index, execution in enumerate(ordered, start=1):
            winner = winners.get(execution.id)
            if winner is None:
                continue
            old_position = original_positions[execution.id]
            if old_position == new_index:
                continue
            firings.append(
                ReprioritizationFiring(
                    execution_id=execution.id,
                    trigger=winner[0],
                    old_position=old_position,
                    new_position=new_index,
                    remaining_fraction=winner[1],
                )
            )
        return ReprioritizationResult(ordered_executions=ordered, firings=firings)

    def _validate_condition_config(
        self,
        trigger_type: str,
        condition_config: dict[str, Any],
    ) -> dict[str, Any]:
        if trigger_type != "sla_approach":
            raise ValidationError(
                "REPRIORITIZATION_TRIGGER_UNSUPPORTED",
                f"trigger_type '{trigger_type}' is not supported in this release",
            )
        threshold = condition_config.get("threshold_fraction")
        if threshold is None:
            raise ValidationError(
                "REPRIORITIZATION_TRIGGER_INVALID",
                "threshold_fraction is required for sla_approach triggers",
            )
        value = float(threshold)
        if not 0.0 <= value <= 1.0:
            raise ValidationError(
                "REPRIORITIZATION_TRIGGER_INVALID",
                "threshold_fraction must be between 0.0 and 1.0",
            )
        return {"threshold_fraction": value}

    def _validate_action(self, action: str) -> None:
        if action != "promote_to_front":
            raise ValidationError(
                "REPRIORITIZATION_TRIGGER_ACTION_INVALID",
                f"action '{action}' is not supported in this release",
            )

    def _evaluate_execution(
        self,
        execution: Execution,
        trigger: ReprioritizationTrigger,
    ) -> float | None:
        if trigger.trigger_type != "sla_approach":
            return None
        return self._evaluate_sla_approach(execution, trigger.condition_config)

    def _evaluate_sla_approach(
        self,
        execution: Execution,
        config: dict[str, Any],
    ) -> float | None:
        if execution.sla_deadline is None:
            return None
        total_window = (execution.sla_deadline - execution.created_at).total_seconds()
        if total_window <= 0:
            return 0.0
        remaining = (execution.sla_deadline - datetime.now(UTC)).total_seconds()
        remaining_fraction = max(0.0, remaining) / total_window
        threshold = float(config.get("threshold_fraction", 0.0))
        if remaining_fraction < threshold:
            return remaining_fraction
        return None
