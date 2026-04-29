from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.reasoning_engine import ReasoningEngineClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import AuthorizationError, ObjectNotFoundError, ValidationError
from platform.common.logging import get_logger
from platform.execution.checkpoint_service import CheckpointService
from platform.execution.events import (
    ExecutionCreatedEvent,
    ExecutionReprioritizedEvent,
    ExecutionStatusChangedEvent,
    publish_execution_created,
    publish_execution_reprioritized,
    publish_execution_status_changed,
)
from platform.execution.exceptions import (
    ApprovalAlreadyDecidedError,
    ExecutionAlreadyRunningError,
    ExecutionNotFoundError,
    HotChangeIncompatibleError,
    TraceNotAvailableError,
    TraceNotFoundError,
)
from platform.execution.models import (
    ApprovalDecision,
    CompensationOutcome,
    Execution,
    ExecutionCompensationRecord,
    ExecutionEvent,
    ExecutionEventType,
    ExecutionStatus,
)
from platform.execution.projector import ExecutionProjector
from platform.execution.repository import ExecutionRepository
from platform.execution.schemas import (
    DEFAULT_CHECKPOINT_POLICY,
    ApprovalDecisionRequest,
    ApprovalWaitListResponse,
    ApprovalWaitResponse,
    ExecutionCreate,
    ExecutionEventListResponse,
    ExecutionEventResponse,
    ExecutionListResponse,
    ExecutionResponse,
    ExecutionStateResponse,
    HotChangeCompatibilityResult,
    ReasoningTraceResponse,
    RollbackResponse,
    TaskPlanFullResponse,
    TaskPlanRecordResponse,
    TracePaginationResponse,
    TraceStepResponse,
)
from platform.workflows.compiler import WorkflowCompiler
from platform.workflows.exceptions import WorkflowNotFoundError
from platform.workflows.ir import WorkflowIR
from platform.workflows.models import TriggerType
from platform.workflows.repository import WorkflowRepository
from typing import Any
from uuid import UUID, uuid4

LOGGER = get_logger(__name__)
COST_SIGNAL_KEYS = frozenset(
    {
        "model_id",
        "model",
        "tokens_in",
        "input_tokens",
        "prompt_tokens",
        "tokens_out",
        "output_tokens",
        "completion_tokens",
        "duration_ms",
        "latency_ms",
        "bytes_written",
        "storage_bytes",
        "model_cost_cents",
        "compute_cost_cents",
        "storage_cost_cents",
        "overhead_cost_cents",
    }
)


class ExecutionService:
    """Provide execution operations."""

    def __init__(
        self,
        *,
        repository: ExecutionRepository,
        settings: PlatformSettings,
        producer: EventProducer | None,
        redis_client: AsyncRedisClient,
        object_storage: AsyncObjectStorageClient,
        runtime_controller: RuntimeControllerClient | Any | None,
        reasoning_engine: ReasoningEngineClient | Any | None,
        context_engineering_service: Any | None,
        projector: ExecutionProjector,
        compiler: WorkflowCompiler | None = None,
        checkpoint_service: CheckpointService | None = None,
        attribution_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.redis_client = redis_client
        self.object_storage = object_storage
        self.runtime_controller = runtime_controller
        self.reasoning_engine = reasoning_engine
        self.context_engineering_service = context_engineering_service
        self.projector = projector
        self.compiler = compiler or WorkflowCompiler()
        self.checkpoint_service = checkpoint_service
        self.attribution_service = attribution_service
        self.workflow_repository = WorkflowRepository(repository.session)
        self.task_plan_bucket = "execution-task-plans"
        self.reasoning_trace_bucket = "reasoning-traces"

    async def create_execution(
        self,
        data: ExecutionCreate,
        *,
        created_by: UUID | None = None,
        parent_execution_id: UUID | None = None,
        rerun_of_execution_id: UUID | None = None,
        precompleted_step_ids: list[str] | None = None,
        step_results: dict[str, Any] | None = None,
    ) -> ExecutionResponse:
        """Create execution."""
        definition = await self.workflow_repository.get_definition_by_id(
            data.workflow_definition_id
        )
        if definition is None:
            raise WorkflowNotFoundError(data.workflow_definition_id)

        version = await self._resolve_workflow_version(definition.id, data.workflow_version_id)
        trigger = None
        if data.trigger_id is not None:
            trigger = await self.workflow_repository.get_trigger_by_id(data.trigger_id)
            if trigger is None:
                raise ValidationError("TRIGGER_NOT_FOUND", "Trigger does not exist")
            if trigger.max_concurrent_executions is not None:
                current = await self.repository.count_active_for_trigger(trigger.id)
                if current >= trigger.max_concurrent_executions:
                    raise ValidationError(
                        "TRIGGER_CONCURRENCY_LIMIT",
                        "Trigger concurrency limit reached",
                    )

        execution = await self.repository.create_execution(
            Execution(
                workflow_version_id=version.id,
                workflow_definition_id=definition.id,
                trigger_id=data.trigger_id,
                trigger_type=data.trigger_type,
                status=ExecutionStatus.queued,
                input_parameters=dict(data.input_parameters),
                workspace_id=data.workspace_id,
                correlation_workspace_id=data.workspace_id,
                correlation_conversation_id=data.correlation_conversation_id,
                correlation_interaction_id=data.correlation_interaction_id,
                correlation_fleet_id=data.correlation_fleet_id,
                correlation_goal_id=data.correlation_goal_id,
                parent_execution_id=parent_execution_id,
                rerun_of_execution_id=rerun_of_execution_id,
                sla_deadline=data.sla_deadline,
                created_by=created_by,
                checkpoint_policy_snapshot=dict(
                    version.checkpoint_policy or DEFAULT_CHECKPOINT_POLICY
                ),
            )
        )
        ir = WorkflowIR.from_dict(version.compiled_ir)
        await self.repository.append_event(
            execution_id=execution.id,
            event_type=ExecutionEventType.created,
            step_id=None,
            agent_fqn=None,
            payload={
                "workflow_definition_id": str(definition.id),
                "workflow_version_id": str(version.id),
                "all_step_ids": [step.step_id for step in ir.steps],
                "precompleted_step_ids": list(precompleted_step_ids or []),
                "step_results": dict(step_results or {}),
                "input_parameters": dict(data.input_parameters),
            },
            correlation_workspace_id=execution.workspace_id,
            correlation_execution_id=execution.id,
            correlation_conversation_id=execution.correlation_conversation_id,
            correlation_interaction_id=execution.correlation_interaction_id,
            correlation_goal_id=execution.correlation_goal_id,
            correlation_fleet_id=execution.correlation_fleet_id,
        )
        await publish_execution_created(
            self.producer,
            ExecutionCreatedEvent(
                execution_id=execution.id,
                workflow_definition_id=definition.id,
                workflow_version_id=version.id,
                workspace_id=execution.workspace_id,
            ),
            self._correlation(execution),
        )
        return ExecutionResponse.model_validate(execution)

    async def get_execution(self, execution_id: UUID) -> ExecutionResponse:
        """Return execution."""
        execution = await self._get_execution_or_raise(execution_id)
        return ExecutionResponse.model_validate(execution)

    async def list_executions(
        self,
        *,
        workspace_id: UUID,
        workflow_id: UUID | None,
        status: ExecutionStatus | None,
        trigger_type: TriggerType | None,
        goal_id: UUID | None,
        since: datetime | None,
        page: int,
        page_size: int,
    ) -> ExecutionListResponse:
        """List executions."""
        items, total = await self.repository.list_executions(
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            status=status,
            trigger_type=trigger_type,
            goal_id=goal_id,
            since=since,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return ExecutionListResponse(
            items=[ExecutionResponse.model_validate(item) for item in items],
            total=total,
        )

    async def cancel_execution(self, execution_id: UUID) -> ExecutionResponse:
        """Cancel execution."""
        execution = await self._get_execution_or_raise(execution_id)
        if execution.status in {
            ExecutionStatus.completed,
            ExecutionStatus.failed,
            ExecutionStatus.canceled,
        }:
            raise ValidationError("EXECUTION_NOT_CANCELABLE", "Execution cannot be canceled")
        await self.repository.update_execution_status(
            execution,
            ExecutionStatus.canceled,
            completed_at=datetime.now(UTC),
        )
        await self._append_domain_event(
            execution,
            ExecutionEventType.canceled,
            payload={"reason": "user_requested"},
        )
        return ExecutionResponse.model_validate(execution)

    async def get_execution_state(self, execution_id: UUID) -> ExecutionStateResponse:
        """Return execution state."""
        cache_key = self._state_cache_key(execution_id)
        cached = await self.redis_client.get(cache_key)
        if cached is not None:
            return ExecutionStateResponse.model_validate(json.loads(cached.decode("utf-8")))
        execution = await self._get_execution_or_raise(execution_id)
        checkpoint = await self.repository.get_latest_checkpoint(execution_id)
        events = await self.repository.get_events(
            execution_id,
            since_sequence=checkpoint.last_event_sequence if checkpoint is not None else None,
        )
        state = self.projector.project_state(events, checkpoint)
        state.workflow_version_id = execution.workflow_version_id
        state.status = execution.status
        await self.redis_client.set(
            cache_key,
            state.model_dump_json().encode("utf-8"),
            ttl=30,
        )
        return state

    async def get_journal(
        self,
        execution_id: UUID,
        *,
        since_sequence: int | None = None,
        event_type: ExecutionEventType | None = None,
    ) -> ExecutionEventListResponse:
        """Return journal."""
        await self._get_execution_or_raise(execution_id)
        events = await self.repository.get_events(
            execution_id,
            since_sequence=since_sequence,
            event_type=event_type,
        )
        return ExecutionEventListResponse(
            items=[ExecutionEventResponse.model_validate(event) for event in events],
            total=len(events),
        )

    async def get_journal_in_window(
        self,
        execution_ids: list[UUID],
        start_ts: datetime,
        end_ts: datetime,
    ) -> list[ExecutionEvent]:
        """Return execution journal rows across executions for timeline assembly."""
        return await self.repository.list_journal_in_window(execution_ids, start_ts, end_ts)

    async def replay_execution(self, execution_id: UUID) -> ExecutionStateResponse:
        """Replay execution."""
        execution = await self._get_execution_or_raise(execution_id)
        events = await self.repository.get_events(execution_id)
        state = self.projector.project_state(events)
        state.workflow_version_id = execution.workflow_version_id
        state.status = execution.status
        return state

    async def resume_execution(self, execution_id: UUID) -> ExecutionResponse:
        """Resume execution."""
        execution = await self._get_execution_or_raise(execution_id)
        if execution.status in {
            ExecutionStatus.queued,
            ExecutionStatus.running,
            ExecutionStatus.waiting_for_approval,
            ExecutionStatus.compensating,
        }:
            raise ExecutionAlreadyRunningError(execution_id)
        checkpoint = await self.repository.get_latest_checkpoint(execution_id)
        state = await self.replay_execution(execution_id)
        payload = ExecutionCreate(
            workflow_definition_id=execution.workflow_definition_id,
            workflow_version_id=execution.workflow_version_id,
            trigger_type=TriggerType.manual,
            input_parameters=dict(execution.input_parameters),
            workspace_id=execution.workspace_id,
            correlation_conversation_id=execution.correlation_conversation_id,
            correlation_interaction_id=execution.correlation_interaction_id,
            correlation_fleet_id=execution.correlation_fleet_id,
            correlation_goal_id=execution.correlation_goal_id,
            sla_deadline=execution.sla_deadline,
        )
        resumed = await self.create_execution(
            payload,
            created_by=execution.created_by,
            parent_execution_id=execution.id,
            precompleted_step_ids=list(
                checkpoint.completed_step_ids
                if checkpoint is not None
                else state.completed_step_ids
            ),
            step_results=dict(
                checkpoint.step_results if checkpoint is not None else state.step_results
            ),
        )
        new_execution = await self._get_execution_or_raise(resumed.id)
        await self._append_domain_event(
            new_execution,
            ExecutionEventType.resumed,
            payload={"parent_execution_id": str(execution.id)},
        )
        return resumed

    async def rerun_execution(
        self,
        execution_id: UUID,
        input_overrides: dict[str, Any] | None,
    ) -> ExecutionResponse:
        """Rerun execution."""
        execution = await self._get_execution_or_raise(execution_id)
        merged_input = dict(execution.input_parameters)
        merged_input.update(input_overrides or {})
        return await self.create_execution(
            ExecutionCreate(
                workflow_definition_id=execution.workflow_definition_id,
                workflow_version_id=execution.workflow_version_id,
                trigger_type=TriggerType.manual,
                input_parameters=merged_input,
                workspace_id=execution.workspace_id,
                correlation_conversation_id=execution.correlation_conversation_id,
                correlation_interaction_id=execution.correlation_interaction_id,
                correlation_fleet_id=execution.correlation_fleet_id,
                correlation_goal_id=execution.correlation_goal_id,
                sla_deadline=execution.sla_deadline,
            ),
            created_by=execution.created_by,
            rerun_of_execution_id=execution.id,
        )

    async def pause_execution(self, execution_id: UUID) -> ExecutionResponse:
        """Pause a queued or running execution."""
        execution = await self._get_execution_or_raise(execution_id)
        if execution.status not in {ExecutionStatus.queued, ExecutionStatus.running}:
            raise ValidationError(
                "EXECUTION_NOT_PAUSABLE",
                "Only queued or running executions can be paused",
            )
        await self.repository.update_execution_status(execution, ExecutionStatus.paused)
        await self._invalidate_state_cache(execution.id)
        return ExecutionResponse.model_validate(execution)

    async def rollback_execution(
        self,
        execution_id: UUID,
        checkpoint_number: int,
        *,
        initiated_by: UUID | None,
        reason: str | None = None,
        authorized: bool = True,
    ) -> RollbackResponse:
        """Rollback an execution to a checkpoint."""
        if not authorized:
            raise AuthorizationError(
                "PERMISSION_DENIED",
                "Permission 'execution.rollback' required",
            )
        checkpoint_service = self.checkpoint_service or CheckpointService(
            repository=self.repository,
            settings=self.settings,
            producer=self.producer,
            projector=self.projector,
        )
        self.checkpoint_service = checkpoint_service
        return await checkpoint_service.rollback(
            execution_id,
            checkpoint_number,
            initiated_by=initiated_by,
            reason=reason,
        )

    async def validate_hot_change(
        self,
        execution_id: UUID,
        new_version_id: UUID,
    ) -> HotChangeCompatibilityResult:
        """Validate hot change."""
        execution = await self._get_execution_or_raise(execution_id)
        state = await self.get_execution_state(execution_id)
        old_version = await self._resolve_workflow_version(
            execution.workflow_definition_id, execution.workflow_version_id
        )
        new_version = await self.workflow_repository.get_version_by_id(new_version_id)
        if new_version is None:
            raise WorkflowNotFoundError(new_version_id)
        old_ir = WorkflowIR.from_dict(old_version.compiled_ir)
        new_ir = WorkflowIR.from_dict(new_version.compiled_ir)
        return self.compiler.validate_compatibility(
            old_ir,
            new_ir,
            list(state.active_step_ids),
        )

    async def apply_hot_change(
        self,
        execution_id: UUID,
        new_version_id: UUID,
    ) -> ExecutionResponse:
        """Apply hot change."""
        result = await self.validate_hot_change(execution_id, new_version_id)
        if not result.compatible:
            raise HotChangeIncompatibleError(result.issues)
        execution = await self._get_execution_or_raise(execution_id)
        old_version_id = execution.workflow_version_id
        execution.workflow_version_id = new_version_id
        await self.repository.session.flush()
        await self._append_domain_event(
            execution,
            ExecutionEventType.hot_changed,
            payload={
                "old_version_id": str(old_version_id),
                "new_version_id": str(new_version_id),
            },
        )
        await self._invalidate_state_cache(execution.id)
        return ExecutionResponse.model_validate(execution)

    async def list_approvals(self, execution_id: UUID) -> ApprovalWaitListResponse:
        """List approvals."""
        await self._get_execution_or_raise(execution_id)
        waits = await self.repository.list_approval_waits(execution_id)
        return ApprovalWaitListResponse(
            items=[ApprovalWaitResponse.model_validate(item) for item in waits],
            total=len(waits),
        )

    async def record_approval_decision(
        self,
        execution_id: UUID,
        step_id: str,
        request: ApprovalDecisionRequest,
        *,
        decided_by: UUID,
    ) -> ApprovalWaitResponse:
        """Record approval decision."""
        execution = await self._get_execution_or_raise(execution_id)
        approval_wait = await self.repository.get_approval_wait(execution_id, step_id)
        if approval_wait is None:
            raise ValidationError("APPROVAL_NOT_FOUND", "Approval wait does not exist")
        if approval_wait.decision is not None:
            raise ApprovalAlreadyDecidedError(execution_id, step_id)
        now = datetime.now(UTC)
        updated = await self.repository.update_approval_wait(
            approval_wait,
            decision=request.decision,
            decided_by=str(decided_by),
            decided_at=now,
        )
        event_type = (
            ExecutionEventType.approved
            if request.decision == ApprovalDecision.approved
            else ExecutionEventType.rejected
        )
        next_status = (
            ExecutionStatus.running
            if request.decision == ApprovalDecision.approved
            else ExecutionStatus.failed
        )
        await self.repository.update_execution_status(execution, next_status)
        await self._append_domain_event(
            execution,
            event_type,
            step_id=step_id,
            payload={"comment": request.comment},
        )
        if request.decision == ApprovalDecision.approved:
            await self.repository.update_execution_status(execution, ExecutionStatus.queued)
            await self._append_domain_event(
                execution,
                ExecutionEventType.resumed,
                step_id=step_id,
                payload={"reason": "approval_granted"},
            )
        return ApprovalWaitResponse.model_validate(updated)

    async def trigger_compensation(
        self,
        execution_id: UUID,
        step_id: str,
        *,
        triggered_by: str,
    ) -> None:
        """Trigger compensation."""
        execution = await self._get_execution_or_raise(execution_id)
        state = await self.get_execution_state(execution_id)
        if step_id not in state.completed_step_ids:
            raise ValidationError("STEP_NOT_COMPLETED", "Only completed steps can be compensated")
        version = await self._resolve_workflow_version(
            execution.workflow_definition_id, execution.workflow_version_id
        )
        ir = WorkflowIR.from_dict(version.compiled_ir)
        step = next((item for item in ir.steps if item.step_id == step_id), None)
        if step is None:
            raise ValidationError("STEP_NOT_FOUND", f"Step '{step_id}' does not exist")
        handler = step.compensation_handler or "not_available"
        record = await self.repository.create_compensation_record(
            ExecutionCompensationRecord(
                execution_id=execution.id,
                step_id=step_id,
                compensation_handler=handler,
                triggered_by=triggered_by,
                outcome=(
                    CompensationOutcome.completed
                    if step.compensation_handler is not None
                    else CompensationOutcome.not_available
                ),
                error_detail=None,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
        )
        await self._append_domain_event(
            execution,
            (
                ExecutionEventType.compensated
                if record.outcome == CompensationOutcome.completed
                else ExecutionEventType.compensation_failed
            ),
            step_id=step_id,
            payload={"compensation_handler": handler, "outcome": record.outcome.value},
        )

    async def get_task_plan(
        self,
        execution_id: UUID,
        step_id: str | None,
    ) -> TaskPlanFullResponse | list[TaskPlanRecordResponse]:
        """Return task plan."""
        await self._get_execution_or_raise(execution_id)
        if step_id is None:
            records = await self.repository.list_task_plan_records(execution_id)
            return [TaskPlanRecordResponse.model_validate(item) for item in records]
        record = await self.repository.get_task_plan_record(execution_id, step_id)
        if record is None:
            raise ValidationError("TASK_PLAN_NOT_FOUND", "Task plan does not exist")
        payload: dict[str, Any] = {}
        try:
            raw = await self.object_storage.download_object(
                self.task_plan_bucket, record.storage_key
            )
            payload = json.loads(raw.decode("utf-8"))
        except ObjectNotFoundError:
            payload = {}
        return TaskPlanFullResponse(
            **TaskPlanRecordResponse.model_validate(record).model_dump(),
            considered_agents=list(payload.get("considered_agents", [])),
            considered_tools=list(payload.get("considered_tools", [])),
            parameters=dict(payload.get("parameters", {})),
            rejected_alternatives=list(payload.get("rejected_alternatives", [])),
        )

    async def get_reasoning_trace(
        self,
        execution_id: UUID,
        step_id: str | None = None,
        *,
        page: int = 1,
        page_size: int = 100,
        requester_workspace_id: UUID | None = None,
    ) -> ReasoningTraceResponse:
        """Return the structured reasoning trace for an execution."""
        execution = await self._get_execution_or_raise(execution_id)
        if requester_workspace_id is not None and execution.workspace_id != requester_workspace_id:
            raise AuthorizationError("AUTHORIZATION_ERROR", "Not authorized")

        record = await self.repository.get_reasoning_trace_record(execution_id, step_id)
        if record is None:
            raise TraceNotFoundError(execution_id, step_id)
        if record.status == "expired":
            raise TraceNotAvailableError(execution_id, record.storage_key)

        try:
            raw = await self.object_storage.download_object(
                self.reasoning_trace_bucket,
                record.storage_key,
            )
        except ObjectNotFoundError as exc:
            raise TraceNotAvailableError(execution_id, record.storage_key) from exc

        payload = json.loads(raw.decode("utf-8")) if raw else {}
        all_steps = list(payload.get("steps", []))
        total_steps = len(all_steps)
        start = max(page - 1, 0) * page_size
        end = start + page_size
        page_items = all_steps[start:end]
        steps = [TraceStepResponse.model_validate(item) for item in page_items]

        total_tokens = int(
            payload.get("total_tokens")
            or sum(int(item.get("tokens_used", 0)) for item in all_steps if isinstance(item, dict))
        )
        pagination = TracePaginationResponse(
            page=page,
            page_size=page_size,
            total_steps=total_steps,
            has_more=end < total_steps,
        )
        compute_budget_value = payload.get("compute_budget_used")
        compute_budget_used = (
            float(compute_budget_value)
            if compute_budget_value is not None
            else float(record.compute_budget_used or 0.0)
        )
        effective_budget_scope = (
            payload.get("effective_budget_scope") or record.effective_budget_scope
        )
        return ReasoningTraceResponse(
            execution_id=execution.id,
            technique=record.technique,
            schema_version=str(payload.get("schema_version", "1.0")),
            status=record.status,
            steps=steps,
            total_tokens=total_tokens,
            compute_budget_used=compute_budget_used,
            effective_budget_scope=(
                str(effective_budget_scope) if effective_budget_scope else None
            ),
            compute_budget_exhausted=bool(
                payload.get("compute_budget_exhausted", record.compute_budget_exhausted)
            ),
            consensus_reached=(
                payload.get("consensus_reached")
                if payload.get("consensus_reached") is not None
                else record.consensus_reached
            ),
            stabilized=(
                payload.get("stabilized")
                if payload.get("stabilized") is not None
                else record.stabilized
            ),
            degradation_detected=(
                payload.get("degradation_detected")
                if payload.get("degradation_detected") is not None
                else record.degradation_detected
            ),
            last_updated_at=(
                (payload.get("last_updated_at") or record.updated_at)
                if record.status != "complete"
                else None
            ),
            pagination=pagination,
        )

    async def get_reasoning_traces(
        self,
        execution_id: UUID,
        step_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return reasoning trace steps for legacy adapter compatibility."""
        trace = await self.get_reasoning_trace(
            execution_id,
            step_id,
            page=1,
            page_size=500,
        )
        return [item.model_dump(mode="json") for item in trace.steps]

    async def record_runtime_event(
        self,
        execution_id: UUID,
        *,
        step_id: str | None,
        event_type: ExecutionEventType,
        payload: dict[str, Any],
        status: ExecutionStatus | None = None,
    ) -> None:
        """Record runtime event."""
        execution = await self._get_execution_or_raise(execution_id)
        if status is not None:
            await self.repository.update_execution_status(execution, status)
        await self._append_domain_event(execution, event_type, step_id=step_id, payload=payload)
        await self._record_cost_attribution(execution, step_id=step_id, payload=payload)

    async def _resolve_workflow_version(
        self,
        workflow_id: UUID,
        version_id: UUID | None,
    ) -> Any:
        if version_id is not None:
            version = await self.workflow_repository.get_version_by_id(version_id)
            if version is None:
                raise WorkflowNotFoundError(version_id)
            return version
        definition = await self.workflow_repository.get_definition_by_id(workflow_id)
        if definition is None or definition.current_version is None:
            raise WorkflowNotFoundError(workflow_id)
        return definition.current_version

    async def _get_execution_or_raise(self, execution_id: UUID) -> Execution:
        execution = await self.repository.get_execution_by_id(execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        return execution

    async def _append_domain_event(
        self,
        execution: Execution,
        event_type: ExecutionEventType,
        *,
        step_id: str | None = None,
        agent_fqn: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await self.repository.append_event(
            execution_id=execution.id,
            event_type=event_type,
            step_id=step_id,
            agent_fqn=agent_fqn,
            payload=dict(payload or {}),
            correlation_workspace_id=execution.workspace_id,
            correlation_execution_id=execution.id,
            correlation_conversation_id=execution.correlation_conversation_id,
            correlation_interaction_id=execution.correlation_interaction_id,
            correlation_goal_id=execution.correlation_goal_id,
            correlation_fleet_id=execution.correlation_fleet_id,
        )
        await self._invalidate_state_cache(execution.id)
        await publish_execution_status_changed(
            self.producer,
            ExecutionStatusChangedEvent(
                execution_id=execution.id,
                status=execution.status.value,
                step_id=step_id,
            ),
            self._correlation(execution),
        )

    async def publish_reprioritization(
        self,
        execution: Execution,
        *,
        trigger_reason: str,
        steps_affected: list[str],
        trigger_id: UUID | None = None,
        trigger_name: str | None = None,
        new_queue_order: list[dict[str, Any]] | None = None,
    ) -> None:
        """Publish reprioritization."""
        await publish_execution_reprioritized(
            self.producer,
            ExecutionReprioritizedEvent(
                execution_id=execution.id,
                trigger_reason=trigger_reason,
                steps_affected=steps_affected,
                trigger_id=trigger_id,
                trigger_name=trigger_name,
                new_queue_order=new_queue_order,
            ),
            self._correlation(execution),
        )

    async def _invalidate_state_cache(self, execution_id: UUID) -> None:
        await self.redis_client.delete(self._state_cache_key(execution_id))

    async def _record_cost_attribution(
        self,
        execution: Execution,
        *,
        step_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        if not any(key in payload for key in COST_SIGNAL_KEYS):
            return
        service = self.attribution_service
        if service is None:
            from platform.cost_governance.repository import CostGovernanceRepository
            from platform.cost_governance.services.attribution_service import AttributionService

            service = AttributionService(
                repository=CostGovernanceRepository(self.repository.session),
                settings=self.settings,
                kafka_producer=self.producer,
                fail_open=self.settings.cost_governance.attribution_fail_open,
            )
        try:
            await service.record_step_cost(
                execution_id=execution.id,
                step_id=step_id,
                workspace_id=execution.workspace_id,
                agent_id=_uuid_or_none(payload.get("agent_id") or payload.get("agent_profile_id")),
                user_id=execution.created_by,
                payload=payload,
                correlation_ctx=self._correlation(execution),
            )
        except Exception:
            if not getattr(service, "fail_open", True):
                raise
            LOGGER.warning(
                "Cost attribution hook failed open",
                exc_info=True,
                extra={
                    "workspace_id": str(execution.workspace_id),
                    "execution_id": str(execution.id),
                },
            )

    @staticmethod
    def _state_cache_key(execution_id: UUID) -> str:
        return f"exec:state:{execution_id}"

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


def _uuid_or_none(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None
