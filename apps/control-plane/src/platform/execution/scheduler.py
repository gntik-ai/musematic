from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.common.events.envelope import CorrelationContext
from platform.common.exceptions import PolicySecretLeakError
from platform.common.llm.mock_provider import MockLLMProvider
from platform.common.logging import get_logger
from platform.execution.checkpoint_service import CheckpointService
from platform.execution.events import (
    ExecutionDomainEventType,
    PromptSecretDetectedEvent,
    publish_prompt_secret_detected,
)
from platform.execution.models import (
    ApprovalDecision,
    ApprovalTimeoutAction,
    Execution,
    ExecutionApprovalWait,
    ExecutionCheckpoint,
    ExecutionDispatchLease,
    ExecutionEventType,
    ExecutionReasoningTraceRecord,
    ExecutionStatus,
    ExecutionTaskPlanRecord,
)
from platform.execution.projector import ExecutionProjector
from platform.execution.repository import ExecutionRepository
from platform.execution.reprioritization import ReprioritizationResult, ReprioritizationService
from platform.execution.schemas import DEFAULT_CHECKPOINT_POLICY, ExecutionStateResponse
from platform.execution.service import ExecutionService
from platform.interactions.events import MessageReceivedPayload, publish_message_received
from platform.interactions.models import MessageType
from platform.interactions.repository import InteractionsRepository
from platform.policies.models import EnforcementComponent, PolicyBlockedActionRecord
from platform.policies.repository import PolicyRepository
from platform.policies.sanitizer import OutputSanitizer
from platform.workflows.ir import StepIR, WorkflowIR
from typing import Any, TypedDict
from uuid import NAMESPACE_URL, uuid4, uuid5

LOGGER = get_logger(__name__)


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
        reprioritization_service: ReprioritizationService | None = None,
        checkpoint_service: CheckpointService | None = None,
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
        self.reprioritization_service = reprioritization_service
        self.checkpoint_service = checkpoint_service
        self.worker_id = f"worker-{uuid4()}"

    async def tick(self) -> None:
        """Handle tick."""
        executions = await self.repository.list_by_statuses(
            [ExecutionStatus.queued, ExecutionStatus.running]
        )
        queued = [item for item in executions if item.status == ExecutionStatus.queued]
        running = [item for item in executions if item.status != ExecutionStatus.queued]
        running.sort(key=self._execution_priority_key)

        reordered_queued: list[Execution] = []
        if queued and self.reprioritization_service is not None:
            by_workspace: dict[Any, list[Execution]] = {}
            for execution in queued:
                by_workspace.setdefault(execution.workspace_id, []).append(execution)
            for workspace_id, workspace_executions in by_workspace.items():
                result = await self.reprioritization_service.evaluate_for_dispatch_cycle(
                    workspace_executions,
                    workspace_id,
                    cycle_budget_ms=25,
                )
                reordered_queued.extend(result.ordered_executions)
                if result.firings:
                    await self._emit_queue_reprioritization(result)
        else:
            reordered_queued = sorted(queued, key=self._execution_priority_key)

        for execution in [*running, *reordered_queued]:
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
            if not await self._capture_pre_dispatch_checkpoint(execution, step, state):
                return
            if step.step_type == "approval_gate":
                await self._handle_approval_gate(execution, step)
                continue
            if not await self._acquire_lease(execution.id, step.step_id):
                continue
            try:
                task_plan_payload = await self._persist_task_plan(execution, step)
            except PolicySecretLeakError as exc:
                LOGGER.warning(
                    "Prompt preflight blocked runtime dispatch",
                    extra={
                        "execution_id": str(execution.id),
                        "step_id": step.step_id,
                        "secret_type": exc.secret_type,
                    },
                )
                lease = await self.repository.get_active_dispatch_lease(execution.id, step.step_id)
                if lease is not None:
                    await self.repository.release_dispatch_lease(
                        lease,
                        released_at=datetime.now(UTC),
                        expired=False,
                    )
                await self.repository.update_execution_status(
                    execution,
                    ExecutionStatus.failed,
                    completed_at=datetime.now(UTC),
                )
                await self.execution_service.record_runtime_event(
                    execution.id,
                    step_id=step.step_id,
                    event_type=ExecutionEventType.failed,
                    payload={"step_type": step.step_type, "secret_type": exc.secret_type},
                    status=ExecutionStatus.failed,
                )
                return
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
            await self._dispatch_to_runtime(
                execution,
                ir,
                step,
                task_plan_payload=task_plan_payload,
            )
            await self._maybe_checkpoint(execution.id)

    async def _emit_queue_reprioritization(self, result: ReprioritizationResult) -> None:
        queue_order = [
            {"execution_id": str(item.id), "position": index + 1}
            for index, item in enumerate(result.ordered_executions)
        ]
        for firing in result.firings:
            execution = next(
                item for item in result.ordered_executions if item.id == firing.execution_id
            )
            payload = {
                "trigger_reason": firing.trigger.trigger_type,
                "trigger_id": str(firing.trigger.id),
                "trigger_name": firing.trigger.name,
                "new_queue_order": queue_order,
                "priority_changes": [
                    {
                        "execution_id": str(firing.execution_id),
                        "old_position": firing.old_position,
                        "new_position": firing.new_position,
                    }
                ],
                "steps_affected": [],
            }
            await self.execution_service.record_runtime_event(
                execution.id,
                step_id=None,
                event_type=ExecutionEventType.reprioritized,
                payload=payload,
            )
            await self.execution_service.publish_reprioritization(
                execution,
                trigger_reason=firing.trigger.trigger_type,
                steps_affected=[],
                trigger_id=firing.trigger.id,
                trigger_name=firing.trigger.name,
                new_queue_order=queue_order,
            )

    async def _capture_pre_dispatch_checkpoint(
        self,
        execution: Execution,
        step: StepIR,
        state: ExecutionStateResponse,
    ) -> bool:
        if self.checkpoint_service is None:
            return True
        policy = dict(execution.checkpoint_policy_snapshot or DEFAULT_CHECKPOINT_POLICY)
        if not self.checkpoint_service.should_capture(step, policy):
            return True
        try:
            await self.checkpoint_service.capture(
                execution=execution,
                step_id=step.step_id,
                state=state,
                policy_snapshot=policy,
            )
        except Exception as exc:
            LOGGER.warning(
                "Checkpoint capture paused execution",
                extra={
                    "execution_id": str(execution.id),
                    "step_id": step.step_id,
                    "error": str(exc),
                },
            )
            await self.repository.update_execution_status(execution, ExecutionStatus.paused)
            await self.execution_service.record_runtime_event(
                execution.id,
                step_id=step.step_id,
                event_type=ExecutionEventType.failed,
                payload={
                    "step_type": step.step_type,
                    "failure_kind": "checkpoint_capture",
                    "recoverable": True,
                    "error": str(exc),
                },
                status=ExecutionStatus.paused,
            )
            return False
        return True

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

    async def _persist_task_plan(
        self,
        execution: Execution,
        step: StepIR,
    ) -> dict[str, Any]:
        payload = await self._build_task_plan_payload(execution, step)
        encoded = self._runtime_json_dumps(payload).encode("utf-8")
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
        return payload

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
                    await self._prompt_secret_preflight(payload, execution=execution, step=step)
                    return payload
        parameter_sources = []
        parameters = {}
        for key, value in (step.input_bindings or {}).items():
            provenance = "prev_step_output" if value.startswith("$.steps.") else "user_input"
            parameter_sources.append(provenance)
            parameters[key] = {"value": value, "provenance": provenance}
        payload = {
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
        await self._prompt_secret_preflight(payload, execution=execution, step=step)
        return payload

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

    async def _dispatch_to_runtime(
        self,
        execution: Execution,
        ir: WorkflowIR,
        step: StepIR,
        *,
        task_plan_payload: dict[str, Any] | None = None,
    ) -> None:
        compute_budget, effective_budget_scope = self._resolve_effective_compute_budget(ir, step)
        payload: dict[str, object] = {
            "execution_id": str(execution.id),
            "workflow_version_id": str(execution.workflow_version_id),
            "step_id": step.step_id,
            "step_type": step.step_type,
            "agent_fqn": step.agent_fqn,
            "tool_fqn": step.tool_fqn,
            "input_bindings": dict(step.input_bindings or {}),
        }
        if step.reasoning_mode is not None:
            payload["reasoning_mode"] = step.reasoning_mode
        if compute_budget is not None:
            payload["compute_budget"] = compute_budget
            payload["effective_budget_scope"] = effective_budget_scope
        if task_plan_payload is None:
            task_plan_payload = await self._build_task_plan_payload(execution, step)
        if self._e2e_runtime_simulation_enabled():
            await self._simulate_e2e_runtime_completion(
                execution,
                step,
                task_plan_payload,
                compute_budget=compute_budget,
                effective_budget_scope=effective_budget_scope,
            )
            return
        contract = self._runtime_contract_payload(
            execution,
            step,
            task_plan_payload,
            compute_budget=compute_budget,
            effective_budget_scope=effective_budget_scope,
        )
        launch = getattr(self.runtime_controller, "launch_runtime", None)
        fallback = getattr(self.runtime_controller, "dispatch", None)
        if not callable(fallback) and getattr(self.runtime_controller, "stub", None) is not None:
            fallback = getattr(self.runtime_controller.stub, "dispatch", None)
        if callable(launch):
            try:
                result = launch(contract, prefer_warm=True)
                if hasattr(result, "__await__"):
                    await result
                return
            except Exception:
                if not callable(fallback):
                    raise
        if callable(fallback):
            result = fallback(payload)
            if hasattr(result, "__await__"):
                await result

    def _e2e_runtime_simulation_enabled(self) -> bool:
        return bool(getattr(self.settings, "feature_e2e_mode", False))

    async def _simulate_e2e_runtime_completion(
        self,
        execution: Execution,
        step: StepIR,
        task_plan_payload: dict[str, Any],
        *,
        compute_budget: float | None,
        effective_budget_scope: str | None,
    ) -> None:
        response_text = await self._generate_e2e_agent_response(execution, step, task_plan_payload)
        now = datetime.now(UTC)
        tokens_used = max(1, len(response_text.split()))
        trace_steps = [
            {
                "step_number": 1,
                "type": "thought",
                "agent_fqn": step.agent_fqn,
                "content": f"E2E runtime selected {step.step_id} for deterministic execution.",
                "tokens_used": 0,
                "timestamp": now.isoformat(),
            },
            {
                "step_number": 2,
                "type": "final",
                "agent_fqn": step.agent_fqn,
                "content": response_text,
                "tokens_used": tokens_used,
                "timestamp": now.isoformat(),
            },
        ]
        trace_key = f"e2e/{execution.id}/{step.step_id}/trace.json"
        trace_payload = {
            "schema_version": "1.0",
            "steps": trace_steps,
            "total_tokens": tokens_used,
            "compute_budget_used": float(compute_budget or 0.0),
            "effective_budget_scope": effective_budget_scope,
            "compute_budget_exhausted": False,
            "consensus_reached": True,
            "stabilized": True,
            "degradation_detected": False,
            "last_updated_at": now.isoformat(),
        }
        await self.object_storage.create_bucket_if_not_exists(
            self.execution_service.reasoning_trace_bucket
        )
        await self.object_storage.upload_object(
            self.execution_service.reasoning_trace_bucket,
            trace_key,
            json.dumps(trace_payload, sort_keys=True).encode("utf-8"),
            content_type="application/json",
            metadata={"execution_id": str(execution.id), "step_id": step.step_id},
        )
        await self.repository.upsert_reasoning_trace_record(
            ExecutionReasoningTraceRecord(
                execution_id=execution.id,
                step_id=step.step_id,
                technique="e2e_mock_agent",
                storage_key=trace_key,
                step_count=len(trace_steps),
                status="complete",
                compute_budget_used=float(compute_budget or 0.0),
                consensus_reached=True,
                stabilized=True,
                degradation_detected=False,
                compute_budget_exhausted=False,
                effective_budget_scope=effective_budget_scope,
            )
        )
        await self.execution_service.record_runtime_event(
            execution.id,
            step_id=step.step_id,
            event_type=ExecutionEventType.reasoning_trace_emitted,
            payload={
                "technique": "e2e_mock_agent",
                "storage_key": trace_key,
                "step_count": len(trace_steps),
            },
            status=ExecutionStatus.running,
        )
        await self._publish_e2e_reasoning_event(execution, step, trace_key)
        await self._append_e2e_agent_message(execution, step, response_text)
        await self.execution_service.record_runtime_event(
            execution.id,
            step_id=step.step_id,
            event_type=ExecutionEventType.completed,
            payload={
                "step_type": step.step_type,
                "output": {"content": response_text},
            },
            status=ExecutionStatus.running,
        )
        await self._release_step_dispatch_lease(execution.id, step.step_id)

    async def _generate_e2e_agent_response(
        self,
        execution: Execution,
        step: StepIR,
        task_plan_payload: dict[str, Any],
    ) -> str:
        provider = MockLLMProvider(self.redis_client)
        prompt = json.dumps(
            {
                "execution_id": str(execution.id),
                "step_id": step.step_id,
                "task_plan": task_plan_payload,
            },
            default=self._runtime_json_default,
            sort_keys=True,
        )
        try:
            return await provider.generate(
                "agent_response",
                prompt,
                model="e2e-mock-runtime",
                temperature=0.0,
                max_tokens=1024,
                correlation_context=self._runtime_correlation_payload(execution, step),
            )
        except Exception:
            LOGGER.warning(
                "E2E mock LLM response lookup failed; using deterministic fallback",
                exc_info=True,
                extra={"execution_id": str(execution.id), "step_id": step.step_id},
            )
            return f"E2E runtime completed step {step.step_id}."

    async def _publish_e2e_reasoning_event(
        self,
        execution: Execution,
        step: StepIR,
        storage_key: str,
    ) -> None:
        if self.producer is None:
            return
        await self.producer.publish(
            topic="runtime.reasoning",
            key=str(execution.id),
            event_type=ExecutionDomainEventType.reasoning_trace_emitted.value,
            payload={
                "execution_id": str(execution.id),
                "step_id": step.step_id,
                "technique": "e2e_mock_agent",
                "status": "complete",
                "storage_key": storage_key,
            },
            correlation_ctx=self._correlation_context(execution, step),
            source="platform.execution.e2e",
        )

    async def _append_e2e_agent_message(
        self,
        execution: Execution,
        step: StepIR,
        response_text: str,
    ) -> None:
        if (
            execution.correlation_interaction_id is None
            or execution.correlation_conversation_id is None
        ):
            return
        repository = InteractionsRepository(self.repository.session)
        interaction = await repository.get_interaction(
            execution.correlation_interaction_id,
            execution.workspace_id,
        )
        if interaction is None:
            return
        latest_agent_message = await repository.get_latest_agent_message(interaction.id)
        if (
            latest_agent_message is not None
            and latest_agent_message.metadata_json.get("execution_id") == str(execution.id)
        ):
            return
        limit = int(getattr(self.settings.interactions, "max_messages_per_conversation", 500))
        incremented = await repository.increment_message_count(
            conversation_id=interaction.conversation_id,
            workspace_id=execution.workspace_id,
            limit=limit,
        )
        if incremented is None:
            return
        message = await repository.create_message(
            interaction_id=interaction.id,
            parent_message_id=None,
            sender_identity=step.agent_fqn or "e2e-runtime",
            message_type=MessageType.agent,
            content=response_text,
            metadata={
                "execution_id": str(execution.id),
                "step_id": step.step_id,
                "source": "e2e_runtime_simulator",
            },
        )
        await publish_message_received(
            self.producer,
            MessageReceivedPayload(
                message_id=message.id,
                interaction_id=interaction.id,
                conversation_id=interaction.conversation_id,
                workspace_id=execution.workspace_id,
                sender_identity=message.sender_identity,
                message_type=message.message_type,
            ),
            CorrelationContext(
                correlation_id=uuid4(),
                workspace_id=execution.workspace_id,
                conversation_id=interaction.conversation_id,
                interaction_id=interaction.id,
                goal_id=interaction.goal_id,
                execution_id=execution.id,
                agent_fqn=step.agent_fqn,
            ),
        )

    async def _release_step_dispatch_lease(self, execution_id: Any, step_id: str) -> None:
        lease = await self.repository.get_active_dispatch_lease(execution_id, step_id)
        if lease is not None:
            await self.repository.release_dispatch_lease(
                lease,
                released_at=datetime.now(UTC),
                expired=False,
            )
        client = await self.redis_client._get_client()
        delete = getattr(client, "delete", None)
        if callable(delete):
            result = delete(f"exec:lease:{execution_id}:{step_id}")
            if hasattr(result, "__await__"):
                await result

    def _runtime_contract_payload(
        self,
        execution: Execution,
        step: StepIR,
        task_plan_payload: dict[str, Any],
        *,
        compute_budget: float | None,
        effective_budget_scope: str | None,
    ) -> dict[str, Any]:
        raw_contract_snapshot = getattr(execution, "contract_snapshot", None)
        contract_snapshot = raw_contract_snapshot if isinstance(raw_contract_snapshot, dict) else {}
        model_binding = contract_snapshot.get("model_binding")
        if isinstance(model_binding, str) and model_binding.strip():
            model_binding_json = model_binding
        elif model_binding is not None:
            model_binding_json = self._runtime_json_dumps(model_binding)
        else:
            model_binding_json = "{}"

        policy_ids = (
            contract_snapshot.get("policy_ids") or contract_snapshot.get("source_policy_ids") or []
        )
        policy_id_values = [str(item) for item in policy_ids if item is not None]

        contract: dict[str, Any] = {
            "agent_revision": self._runtime_agent_revision(execution, step),
            "model_binding": model_binding_json,
            "policy_ids": policy_id_values,
            "correlation_context": self._runtime_correlation_payload(execution, step),
            "resource_limits": {},
            "secret_refs": [],
            "env_vars": {
                "WORKFLOW_VERSION_ID": str(execution.workflow_version_id),
                "STEP_TYPE": step.step_type,
            },
            "task_plan_json": self._runtime_json_dumps(task_plan_payload),
            "step_id": step.step_id,
        }
        if step.agent_fqn is not None:
            contract["env_vars"]["AGENT_FQN"] = step.agent_fqn
        if step.tool_fqn is not None:
            contract["env_vars"]["TOOL_FQN"] = step.tool_fqn
        if step.reasoning_mode is not None:
            contract["reasoning_config_json"] = self._runtime_json_dumps(
                {"reasoning_mode": step.reasoning_mode}
            )
        if compute_budget is not None:
            contract["reasoning_budget_envelope_json"] = self._runtime_json_dumps(
                {
                    "compute_budget": compute_budget,
                    "effective_budget_scope": effective_budget_scope,
                }
            )
        context_profile_id = (
            task_plan_payload.get("context_engineering_profile_id")
            if isinstance(task_plan_payload, dict)
            else None
        )
        if context_profile_id:
            contract["context_engineering_profile_id"] = str(context_profile_id)
        return contract

    def _runtime_agent_revision(self, execution: Execution, step: StepIR) -> str:
        raw_contract_snapshot = getattr(execution, "contract_snapshot", None)
        contract_snapshot = raw_contract_snapshot if isinstance(raw_contract_snapshot, dict) else {}
        for key in ("agent_revision_id", "revision_id", "agent_revision"):
            value = contract_snapshot.get(key)
            if value is not None and str(value).strip():
                return str(value)
        return str(step.agent_fqn or step.tool_fqn or step.step_id)

    def _runtime_correlation_payload(
        self,
        execution: Execution,
        step: StepIR,
    ) -> dict[str, str]:
        workspace_id = getattr(execution, "correlation_workspace_id", None)
        if workspace_id is None:
            workspace_id = execution.workspace_id
        conversation_id = getattr(execution, "correlation_conversation_id", None)
        interaction_id = getattr(execution, "correlation_interaction_id", None)
        fleet_id = getattr(execution, "correlation_fleet_id", None)
        goal_id = getattr(execution, "correlation_goal_id", None)
        trace_id = str(uuid5(NAMESPACE_URL, f"{execution.id}:{step.step_id}"))
        payload = {
            "workspace_id": str(workspace_id),
            "execution_id": str(execution.id),
            "trace_id": trace_id,
        }
        if conversation_id is not None:
            payload["conversation_id"] = str(conversation_id)
        if interaction_id is not None:
            payload["interaction_id"] = str(interaction_id)
        if fleet_id is not None:
            payload["fleet_id"] = str(fleet_id)
        if goal_id is not None:
            payload["goal_id"] = str(goal_id)
        return payload

    @staticmethod
    def _runtime_json_dumps(payload: Any) -> str:
        return json.dumps(payload, default=SchedulerService._runtime_json_default, sort_keys=True)

    @staticmethod
    def _runtime_json_default(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def _resolve_effective_compute_budget(
        self,
        ir: WorkflowIR,
        step: StepIR,
    ) -> tuple[float | None, str | None]:
        workflow_budget = (
            ir.metadata.get("compute_budget") if isinstance(ir.metadata, dict) else None
        )
        step_budget = step.compute_budget
        if not self._is_valid_compute_budget(step_budget):
            step_budget = None
        if not self._is_valid_compute_budget(workflow_budget):
            workflow_budget = None
        workflow_budget_value = float(workflow_budget) if workflow_budget is not None else None
        step_budget_value = float(step_budget) if step_budget is not None else None
        if step_budget_value is None and workflow_budget_value is None:
            return None, None
        if step_budget_value is None:
            return workflow_budget_value, "workflow"
        if workflow_budget_value is None:
            return step_budget_value, "step"
        if step_budget_value <= workflow_budget_value:
            return step_budget_value, "step"
        return workflow_budget_value, "workflow"

    @staticmethod
    def _is_valid_compute_budget(value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and 0.0 < float(value) <= 1.0
        )

    async def _prompt_secret_preflight(
        self,
        payload: dict[str, Any],
        *,
        execution: Execution,
        step: StepIR,
    ) -> None:
        prompt_payload = json.dumps(payload, sort_keys=True)
        for secret_type, pattern in OutputSanitizer.SECRET_PATTERNS.items():
            if pattern.search(prompt_payload) is None:
                continue
            agent_fqn = step.agent_fqn or "unknown-agent"
            agent_id = uuid5(NAMESPACE_URL, agent_fqn)
            repository = PolicyRepository(self.repository.session)
            await repository.create_blocked_action_record(
                PolicyBlockedActionRecord(
                    agent_id=agent_id,
                    agent_fqn=agent_fqn,
                    enforcement_component=EnforcementComponent.sanitizer,
                    action_type="prompt_preflight_block",
                    target=secret_type,
                    block_reason=f"prompt_secret_detected:{secret_type}",
                    policy_rule_ref={"step_id": step.step_id},
                    execution_id=execution.id,
                    workspace_id=execution.workspace_id,
                )
            )
            await publish_prompt_secret_detected(
                self.producer,
                PromptSecretDetectedEvent(
                    execution_id=execution.id,
                    workspace_id=execution.workspace_id,
                    agent_fqn=agent_fqn,
                    step_id=step.step_id,
                    secret_type=secret_type,
                ),
                self._correlation_context(execution, step),
            )
            raise PolicySecretLeakError(secret_type)

    def _correlation_context(self, execution: Execution, step: StepIR) -> CorrelationContext:
        return CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=execution.workspace_id,
            execution_id=execution.id,
            conversation_id=execution.correlation_conversation_id,
            interaction_id=execution.correlation_interaction_id,
            fleet_id=execution.correlation_fleet_id,
            goal_id=execution.correlation_goal_id,
            agent_fqn=step.agent_fqn,
        )

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
