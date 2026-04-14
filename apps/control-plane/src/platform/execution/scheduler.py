from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from platform.execution.models import (
    ApprovalDecision,
    ApprovalTimeoutAction,
    Execution,
    ExecutionApprovalWait,
    ExecutionCheckpoint,
    ExecutionDispatchLease,
    ExecutionEventType,
    ExecutionStatus,
    ExecutionTaskPlanRecord,
)
from platform.execution.projector import ExecutionProjector
from platform.execution.repository import ExecutionRepository
from platform.execution.schemas import ExecutionStateResponse
from platform.execution.service import ExecutionService
from platform.workflows.ir import StepIR, WorkflowIR
from typing import Any, TypedDict
from uuid import uuid4

LOGGER = logging.getLogger(__name__)


class PriorityChange(TypedDict):
    """Represent the priority change."""
    step_id: str
    old_priority: float
    new_priority: float


class PriorityScorer:
    """Represent the priority scorer."""
    def compute(self, step: StepIR, execution_context: dict[str, Any]) -> float:
        """Handle compute."""
        now = execution_context["now"]
        execution: Execution = execution_context["execution"]
        urgency = 1.0 if execution.status == ExecutionStatus.running else 0.5
        importance = 1.0 if step.step_type == "approval_gate" else 0.6
        risk = 0.7 if step.retry_config is not None else 0.2
        severity = 1.0 if execution.status == ExecutionStatus.failed else 0.2
        sla_factor = 0.0
        if execution.sla_deadline is not None:
            remaining = (execution.sla_deadline - now).total_seconds()
            sla_factor = max(0.0, 1.0 - min(max(remaining, 0.0), 3600.0) / 3600.0)
        dependency_depth = float(execution_context["dependency_depth"].get(step.step_id, 0))
        reasoning_factor = 1.0 if step.context_budget_tokens else 0.5
        return (
            urgency * 0.35
            + importance * 0.20
            + risk * 0.15
            + severity * 0.10
            + sla_factor * 0.10
            + dependency_depth * 0.05
            + reasoning_factor * 0.05
        )


class SchedulerService:
    """Provide scheduler operations."""
    def __init__(
        self,
        *,
        repository: ExecutionRepository,
        execution_service: ExecutionService,
        projector: ExecutionProjector,
        settings: Any,
        producer: Any | None,
        redis_client: Any,
        object_storage: Any,
        runtime_controller: Any,
        reasoning_engine: Any,
        context_engineering_service: Any | None,
        interactions_service: Any | None,
        priority_scorer: PriorityScorer | None = None,
    ) -> None:
        self.repository = repository
        self.execution_service = execution_service
        self.projector = projector
        self.settings = settings
        self.producer = producer
        self.redis_client = redis_client
        self.object_storage = object_storage
        self.runtime_controller = runtime_controller
        self.reasoning_engine = reasoning_engine
        self.context_engineering_service = context_engineering_service
        self.interactions_service = interactions_service
        self.priority_scorer = priority_scorer or PriorityScorer()
        self.worker_id = f"worker-{uuid4()}"

    async def tick(self) -> None:
        """Handle tick."""
        executions = await self.repository.list_by_statuses(
            [ExecutionStatus.queued, ExecutionStatus.running]
        )
        executions.sort(key=self._execution_priority_key)
        for execution in executions:
            await self._process_execution(execution)

    async def handle_reprioritization_trigger(
        self,
        trigger_reason: str,
        execution_id: Any,
    ) -> None:
        """Handle reprioritization trigger."""
        execution = await self.repository.get_execution_by_id(execution_id)
        if execution is None:
            return
        state = await self.execution_service.get_execution_state(execution.id)
        version = await self.execution_service._resolve_workflow_version(
            execution.workflow_definition_id,
            execution.workflow_version_id,
        )
        ir = WorkflowIR.from_dict(version.compiled_ir)
        runnable = self._runnable_steps(ir, state)
        dependency_depth = self._dependency_depths(ir)
        priorities: list[PriorityChange] = []
        now = datetime.now(UTC)
        for step in runnable:
            priorities.append(
                {
                    "step_id": step.step_id,
                    "old_priority": 0.0,
                    "new_priority": self.priority_scorer.compute(
                        step,
                        {
                            "execution": execution,
                            "state": state,
                            "now": now,
                            "dependency_depth": dependency_depth,
                        },
                    ),
                }
            )
        priorities.sort(key=lambda item: item["new_priority"], reverse=True)
        await self.execution_service.record_runtime_event(
            execution.id,
            step_id=None,
            event_type=ExecutionEventType.reprioritized,
            payload={
                "trigger_reason": trigger_reason,
                "steps_affected": [str(item["step_id"]) for item in priorities],
                "priority_changes": priorities,
            },
        )
        await self.execution_service.publish_reprioritization(
            execution,
            trigger_reason=trigger_reason,
            steps_affected=[str(item["step_id"]) for item in priorities],
        )

    async def scan_approval_timeouts(self) -> None:
        """Scan approval timeouts."""
        overdue = await self.repository.list_pending_approval_waits(datetime.now(UTC))
        for approval_wait in overdue:
            request = (
                ApprovalDecision.approved
                if approval_wait.timeout_action == ApprovalTimeoutAction.skip
                else ApprovalDecision.timed_out
            )
            await self.repository.update_approval_wait(
                approval_wait,
                decision=request,
                decided_by="system",
                decided_at=datetime.now(UTC),
            )
            event_type = ExecutionEventType.approval_timed_out
            execution = await self.repository.get_execution_by_id(approval_wait.execution_id)
            if execution is None:
                continue
            new_status = (
                ExecutionStatus.failed
                if approval_wait.timeout_action.value == "fail"
                else ExecutionStatus.running
            )
            await self.repository.update_execution_status(execution, new_status)
            await self.execution_service.record_runtime_event(
                execution.id,
                step_id=approval_wait.step_id,
                event_type=event_type,
                payload={"timeout_action": approval_wait.timeout_action.value},
                status=new_status,
            )

    async def _process_execution(self, execution: Execution) -> None:
        state = await self.execution_service.get_execution_state(execution.id)
        version = await self.execution_service._resolve_workflow_version(
            execution.workflow_definition_id,
            execution.workflow_version_id,
        )
        ir = WorkflowIR.from_dict(version.compiled_ir)

        journal = await self.repository.get_events(execution.id)
        if len(journal) == 1 and journal[0].event_type == ExecutionEventType.created:
            await self.execution_service.record_runtime_event(
                execution.id,
                step_id=None,
                event_type=ExecutionEventType.queued,
                payload={},
            )
            state = await self.execution_service.get_execution_state(execution.id)

        if execution.sla_deadline is not None:
            total_window = execution.sla_deadline - execution.created_at
            consumed = datetime.now(UTC) - execution.created_at
            if total_window.total_seconds() > 0 and consumed / total_window >= 0.8:
                await self.handle_reprioritization_trigger("sla_deadline_approaching", execution.id)

        runnable = self._runnable_steps(ir, state)
        retryable = await self._collect_retryable_steps(execution, ir, state)
        retryable_ids = {step.step_id for step in retryable}
        if retryable:
            combined = {step.step_id: step for step in runnable}
            combined.update({step.step_id: step for step in retryable})
            runnable = list(combined.values())
        if not runnable:
            if (
                len(state.completed_step_ids) == len(ir.steps)
                and execution.status != ExecutionStatus.completed
            ):
                await self.repository.update_execution_status(
                    execution,
                    ExecutionStatus.completed,
                    completed_at=datetime.now(UTC),
                )
                await self.execution_service.record_runtime_event(
                    execution.id,
                    step_id=None,
                    event_type=ExecutionEventType.completed,
                    payload={"execution_completed": True},
                    status=ExecutionStatus.completed,
                )
            return

        dependency_depth = self._dependency_depths(ir)
        scored = sorted(
            runnable,
            key=lambda step: self.priority_scorer.compute(
                step,
                {
                    "execution": execution,
                    "state": state,
                    "now": datetime.now(UTC),
                    "dependency_depth": dependency_depth,
                },
            ),
            reverse=True,
        )

        for step in scored:
            if step.step_type == "approval_gate":
                await self._handle_approval_gate(execution, step)
                continue
            if not await self._acquire_lease(execution.id, step.step_id):
                continue
            await self._persist_task_plan(execution, step)
            await self.repository.update_execution_status(
                execution,
                ExecutionStatus.running,
                started_at=execution.started_at or datetime.now(UTC),
            )
            await self.execution_service.record_runtime_event(
                execution.id,
                step_id=step.step_id,
                event_type=(
                    ExecutionEventType.retried
                    if step.step_id in retryable_ids
                    else ExecutionEventType.dispatched
                ),
                payload={"step_type": step.step_type},
                status=ExecutionStatus.running,
            )
            await self._dispatch_to_runtime(execution, step)
            await self._maybe_checkpoint(execution.id)

    async def _handle_approval_gate(self, execution: Execution, step: StepIR) -> None:
        existing = await self.repository.get_approval_wait(execution.id, step.step_id)
        if existing is not None:
            return
        if step.approval_config is None:
            return
        timeout_at = datetime.now(UTC) + timedelta(seconds=step.approval_config.timeout_seconds)
        await self.repository.create_approval_wait(
            ExecutionApprovalWait(
                execution_id=execution.id,
                step_id=step.step_id,
                required_approvers=list(step.approval_config.required_approvers),
                timeout_at=timeout_at,
                timeout_action=ApprovalTimeoutAction(step.approval_config.timeout_action),
                decision=None,
                decided_by=None,
                decided_at=None,
                interaction_message_id=None,
            )
        )
        await self.repository.update_execution_status(
            execution, ExecutionStatus.waiting_for_approval
        )
        await self.execution_service.record_runtime_event(
            execution.id,
            step_id=step.step_id,
            event_type=ExecutionEventType.waiting_for_approval,
            payload={"required_approvers": list(step.approval_config.required_approvers)},
            status=ExecutionStatus.waiting_for_approval,
        )
        if self.interactions_service is not None:
            create_request = getattr(self.interactions_service, "create_approval_request", None)
            if callable(create_request):
                result = create_request(
                    execution_id=execution.id,
                    step_id=step.step_id,
                    required_approvers=list(step.approval_config.required_approvers),
                )
                if hasattr(result, "__await__"):
                    await result

    async def _persist_task_plan(self, execution: Execution, step: StepIR) -> None:
        payload = await self._build_task_plan_payload(execution, step)
        encoded = json.dumps(payload).encode("utf-8")
        storage_key = f"{execution.id}/{step.step_id}/task-plan.json"
        try:
            await self.object_storage.create_bucket_if_not_exists(
                self.execution_service.task_plan_bucket
            )
            await self.object_storage.upload_object(
                self.execution_service.task_plan_bucket,
                storage_key,
                encoded,
                content_type="application/json",
            )
        except Exception:
            LOGGER.exception(
                "Failed to persist task plan payload",
                extra={"execution_id": str(execution.id), "step_id": step.step_id},
            )
        await self.repository.upsert_task_plan_record(
            ExecutionTaskPlanRecord(
                execution_id=execution.id,
                step_id=step.step_id,
                selected_agent_fqn=step.agent_fqn,
                selected_tool_fqn=step.tool_fqn,
                rationale_summary=str(payload.get("rationale_summary") or "")[:500] or None,
                considered_agents_count=len(payload.get("considered_agents", [])),
                considered_tools_count=len(payload.get("considered_tools", [])),
                rejected_alternatives_count=len(payload.get("rejected_alternatives", [])),
                parameter_sources=list(payload.get("parameter_sources", [])),
                storage_key=storage_key,
                storage_size_bytes=len(encoded),
            )
        )

    async def _build_task_plan_payload(self, execution: Execution, step: StepIR) -> dict[str, Any]:
        if self.context_engineering_service is not None:
            getter = getattr(self.context_engineering_service, "get_plan_context", None)
            if callable(getter):
                result = getter(execution_id=execution.id, step_id=step.step_id)
                if hasattr(result, "__await__"):
                    payload = await result
                else:
                    payload = result
                if isinstance(payload, dict):
                    return payload
        parameter_sources = []
        parameters = {}
        for key, value in (step.input_bindings or {}).items():
            provenance = "prev_step_output" if value.startswith("$.steps.") else "user_input"
            parameter_sources.append(provenance)
            parameters[key] = {"value": value, "provenance": provenance}
        return {
            "execution_id": str(execution.id),
            "step_id": step.step_id,
            "selected_agent_fqn": step.agent_fqn,
            "selected_tool_fqn": step.tool_fqn,
            "rationale_summary": f"Selected primary target for {step.step_type}",
            "considered_agents": (
                [{"fqn": step.agent_fqn, "capabilities": [], "selection_score": 1.0}]
                if step.agent_fqn
                else []
            ),
            "considered_tools": (
                [{"fqn": step.tool_fqn, "selection_score": 1.0}] if step.tool_fqn else []
            ),
            "parameters": parameters,
            "parameter_sources": list(dict.fromkeys(parameter_sources)),
            "rejected_alternatives": [],
        }

    async def _acquire_lease(self, execution_id: Any, step_id: str) -> bool:
        client = await self.redis_client._get_client()
        token = str(uuid4())
        key = f"exec:lease:{execution_id}:{step_id}"
        acquired = await client.set(key, token, ex=300, nx=True)
        if not acquired:
            return False
        now = datetime.now(UTC)
        await self.repository.create_dispatch_lease(
            ExecutionDispatchLease(
                execution_id=execution_id,
                step_id=step_id,
                scheduler_worker_id=self.worker_id,
                acquired_at=now,
                expires_at=now + timedelta(minutes=5),
                released_at=None,
                expired=False,
            )
        )
        return True

    async def _dispatch_to_runtime(self, execution: Execution, step: StepIR) -> None:
        payload = {
            "execution_id": str(execution.id),
            "workflow_version_id": str(execution.workflow_version_id),
            "step_id": step.step_id,
            "step_type": step.step_type,
            "agent_fqn": step.agent_fqn,
            "tool_fqn": step.tool_fqn,
            "input_bindings": dict(step.input_bindings or {}),
        }
        target = getattr(self.runtime_controller, "dispatch", None)
        if not callable(target) and getattr(self.runtime_controller, "stub", None) is not None:
            target = getattr(self.runtime_controller.stub, "dispatch", None)
        if callable(target):
            result = target(payload)
            if hasattr(result, "__await__"):
                await result

    async def _maybe_checkpoint(self, execution_id: Any) -> None:
        event_count = await self.repository.count_events(execution_id)
        if event_count % 100 != 0:
            return
        state = await self.execution_service.get_execution_state(execution_id)
        await self.repository.create_checkpoint(
            ExecutionCheckpoint(
                execution_id=execution_id,
                last_event_sequence=state.last_event_sequence,
                step_results=dict(state.step_results),
                completed_step_ids=list(state.completed_step_ids),
                pending_step_ids=list(state.pending_step_ids),
                active_step_ids=list(state.active_step_ids),
                execution_data=dict(state.step_results.get("_execution_data", {})),
            )
        )

    @staticmethod
    def _runnable_steps(ir: WorkflowIR, state: ExecutionStateResponse) -> list[StepIR]:
        dependencies: dict[str, set[str]] = {step.step_id: set() for step in ir.steps}
        for source, target in ir.dag_edges:
            dependencies.setdefault(target, set()).add(source)
        completed = set(state.completed_step_ids)
        active = set(state.active_step_ids)
        runnable: list[StepIR] = []
        for step in ir.steps:
            if step.step_id in completed or step.step_id in active:
                continue
            if dependencies.get(step.step_id, set()).issubset(completed):
                runnable.append(step)
        return runnable

    @staticmethod
    def _dependency_depths(ir: WorkflowIR) -> dict[str, float]:
        parents: dict[str, list[str]] = {step.step_id: [] for step in ir.steps}
        for source, target in ir.dag_edges:
            parents.setdefault(target, []).append(source)
        cache: dict[str, float] = {}

        def depth(step_id: str) -> float:
            """Handle depth."""
            if step_id in cache:
                return cache[step_id]
            if not parents.get(step_id):
                cache[step_id] = 0.0
                return 0.0
            value = 1.0 + max(depth(parent) for parent in parents[step_id])
            cache[step_id] = value
            return value

        return {step.step_id: depth(step.step_id) for step in ir.steps}

    async def _collect_retryable_steps(
        self,
        execution: Execution,
        ir: WorkflowIR,
        state: ExecutionStateResponse,
    ) -> list[StepIR]:
        if not state.active_step_ids:
            return []

        client = await self.redis_client._get_client()
        retryable: list[StepIR] = []
        now = datetime.now(UTC)
        for step_id in list(state.active_step_ids):
            lease = await self.repository.get_active_dispatch_lease(execution.id, step_id)
            if lease is None:
                continue
            key = f"exec:lease:{execution.id}:{step_id}"
            redis_exists = bool(await client.exists(key))
            if lease.expires_at > now and redis_exists:
                continue
            await client.delete(key)
            await self.repository.release_dispatch_lease(
                lease,
                released_at=now,
                expired=True,
            )
            step = next((item for item in ir.steps if item.step_id == step_id), None)
            if step is not None:
                retryable.append(step)
        return retryable

    @staticmethod
    def _execution_priority_key(execution: Execution) -> tuple[datetime, datetime]:
        deadline = execution.sla_deadline or datetime.max.replace(tzinfo=UTC)
        return (deadline, execution.created_at)
