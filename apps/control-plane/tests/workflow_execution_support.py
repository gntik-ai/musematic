from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.execution.models import (
    Execution,
    ExecutionApprovalWait,
    ExecutionCheckpoint,
    ExecutionCompensationRecord,
    ExecutionDispatchLease,
    ExecutionEvent,
    ExecutionStatus,
    ExecutionTaskPlanRecord,
)
from platform.workflows.models import (
    TriggerType,
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowTriggerDefinition,
    WorkflowVersion,
)
from typing import Any
from uuid import UUID, uuid4


class FakeSession:
    async def flush(self) -> None:
        return

    async def commit(self) -> None:
        return

    async def rollback(self) -> None:
        return

    def add(self, instance: Any) -> None:
        del instance

    async def delete(self, instance: Any) -> None:
        del instance


class FakeProducer:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def publish(self, **payload: Any) -> None:
        self.messages.append(payload)


class FakeRedisClient:
    def __init__(self) -> None:
        self.storage: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self.storage.get(key)

    async def delete(self, key: str) -> None:
        self.storage.pop(key, None)

    async def _get_client(self) -> FakeRedisClient:
        return self

    async def set_with_options(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        del ex
        if nx and key in self.storage:
            return False
        self.storage[key] = value.encode("utf-8")
        return True

    async def set(
        self,
        key: str,
        value: str | bytes,
        ex: int | None = None,
        nx: bool = False,
        ttl: int | None = None,
    ) -> bool | None:
        if ttl is not None and ex is None:
            ex = ttl
        if isinstance(value, bytes):
            if nx and key in self.storage:
                return False
            del ex
            self.storage[key] = value
            return True
        return await self.set_with_options(key, value, ex=ex, nx=nx)


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.buckets: set[str] = set()

    async def create_bucket_if_not_exists(self, bucket: str) -> None:
        self.buckets.add(bucket)

    async def upload_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        del content_type, metadata
        self.objects[(bucket, key)] = data

    async def download_object(self, bucket: str, key: str) -> bytes:
        return self.objects[(bucket, key)]


class FakeRuntimeController:
    def __init__(self) -> None:
        self.dispatch_calls: list[dict[str, Any]] = []

    async def dispatch(self, payload: dict[str, Any]) -> None:
        self.dispatch_calls.append(payload)


class FakeWorkflowRepository:
    def __init__(self) -> None:
        self.session = FakeSession()
        self.definitions: dict[UUID, WorkflowDefinition] = {}
        self.versions: dict[UUID, WorkflowVersion] = {}
        self.triggers: dict[UUID, WorkflowTriggerDefinition] = {}

    async def create_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        definition.id = getattr(definition, "id", None) or uuid4()
        definition.created_at = datetime.now(UTC)
        definition.updated_at = definition.created_at
        definition.status = definition.status or WorkflowStatus.active
        definition.versions = []
        definition.trigger_definitions = []
        self.definitions[definition.id] = definition
        return definition

    async def get_definition_by_id(self, workflow_id: UUID) -> WorkflowDefinition | None:
        return self.definitions.get(workflow_id)

    async def get_definition_by_name(
        self,
        *,
        workspace_id: UUID,
        name: str,
    ) -> WorkflowDefinition | None:
        for definition in self.definitions.values():
            if definition.workspace_id == workspace_id and definition.name == name:
                return definition
        return None

    async def list_definitions(
        self,
        *,
        workspace_id: UUID,
        status: WorkflowStatus | None,
        tags: list[str] | None,
        offset: int,
        limit: int,
    ) -> tuple[list[WorkflowDefinition], int]:
        items = [
            item
            for item in self.definitions.values()
            if item.workspace_id == workspace_id
            and (status is None or item.status == status)
            and (not tags or set(tags).intersection(item.tags))
        ]
        return items[offset : offset + limit], len(items)

    async def create_version(self, version: WorkflowVersion) -> WorkflowVersion:
        version.id = getattr(version, "id", None) or uuid4()
        version.created_at = datetime.now(UTC)
        version.updated_at = version.created_at
        self.versions[version.id] = version
        definition = self.definitions[version.definition_id]
        definition.versions.append(version)
        return version

    async def get_version_by_number(
        self,
        workflow_id: UUID,
        version_number: int,
    ) -> WorkflowVersion | None:
        for version in self.versions.values():
            if version.definition_id == workflow_id and version.version_number == version_number:
                return version
        return None

    async def get_version_by_id(self, version_id: UUID) -> WorkflowVersion | None:
        return self.versions.get(version_id)

    async def list_versions(self, workflow_id: UUID) -> list[WorkflowVersion]:
        return sorted(
            [item for item in self.versions.values() if item.definition_id == workflow_id],
            key=lambda item: item.version_number,
        )

    async def update_current_version_id(
        self,
        definition: WorkflowDefinition,
        version_id: UUID,
        *,
        schema_version: int,
    ) -> WorkflowDefinition:
        definition.current_version_id = version_id
        definition.current_version = self.versions[version_id]
        definition.schema_version = schema_version
        return definition

    async def create_trigger(self, trigger: WorkflowTriggerDefinition) -> WorkflowTriggerDefinition:
        trigger.id = getattr(trigger, "id", None) or uuid4()
        trigger.created_at = datetime.now(UTC)
        trigger.updated_at = trigger.created_at
        self.triggers[trigger.id] = trigger
        self.definitions[trigger.definition_id].trigger_definitions.append(trigger)
        return trigger

    async def get_trigger_by_id(self, trigger_id: UUID) -> WorkflowTriggerDefinition | None:
        return self.triggers.get(trigger_id)

    async def list_triggers(self, workflow_id: UUID) -> list[WorkflowTriggerDefinition]:
        return [item for item in self.triggers.values() if item.definition_id == workflow_id]

    async def list_active_triggers_by_type(
        self,
        trigger_type: TriggerType,
    ) -> list[WorkflowTriggerDefinition]:
        return [
            item
            for item in self.triggers.values()
            if item.trigger_type == trigger_type and item.is_active
        ]

    async def update_trigger(
        self,
        trigger: WorkflowTriggerDefinition,
        **fields: Any,
    ) -> WorkflowTriggerDefinition:
        for key, value in fields.items():
            setattr(trigger, key, value)
        trigger.updated_at = datetime.now(UTC)
        return trigger

    async def delete_trigger(self, trigger: WorkflowTriggerDefinition) -> None:
        self.triggers.pop(trigger.id, None)
        definition = self.definitions[trigger.definition_id]
        definition.trigger_definitions = [
            item for item in definition.trigger_definitions if item.id != trigger.id
        ]


class FakeExecutionRepository:
    def __init__(self) -> None:
        self.session = FakeSession()
        self.executions: dict[UUID, Execution] = {}
        self.events: dict[UUID, list[ExecutionEvent]] = defaultdict(list)
        self.checkpoints: dict[UUID, list[ExecutionCheckpoint]] = defaultdict(list)
        self.leases: list[ExecutionDispatchLease] = []
        self.task_plan_records: dict[tuple[UUID, str], ExecutionTaskPlanRecord] = {}
        self.approval_waits: dict[tuple[UUID, str], ExecutionApprovalWait] = {}
        self.compensations: list[ExecutionCompensationRecord] = []

    async def create_execution(self, execution: Execution) -> Execution:
        execution.id = getattr(execution, "id", None) or uuid4()
        execution.created_at = datetime.now(UTC)
        execution.updated_at = execution.created_at
        self.executions[execution.id] = execution
        return execution

    async def get_execution_by_id(self, execution_id: UUID) -> Execution | None:
        return self.executions.get(execution_id)

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
        items = [
            item
            for item in self.executions.values()
            if item.workspace_id == workspace_id
            and (workflow_id is None or item.workflow_definition_id == workflow_id)
            and (status is None or item.status == status)
            and (trigger_type is None or item.trigger_type == trigger_type)
            and (goal_id is None or item.correlation_goal_id == goal_id)
            and (since is None or item.created_at >= since)
        ]
        return items[offset : offset + limit], len(items)

    async def list_by_statuses(self, statuses: list[ExecutionStatus]) -> list[Execution]:
        return [item for item in self.executions.values() if item.status in statuses]

    async def count_active_for_trigger(self, trigger_id: UUID) -> int:
        return sum(
            1
            for item in self.executions.values()
            if item.trigger_id == trigger_id
            and item.status
            in {
                ExecutionStatus.queued,
                ExecutionStatus.running,
                ExecutionStatus.waiting_for_approval,
                ExecutionStatus.compensating,
            }
        )

    async def update_execution_status(
        self,
        execution: Execution,
        status: ExecutionStatus,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> Execution:
        execution.status = status
        if started_at is not None:
            execution.started_at = started_at
        if completed_at is not None:
            execution.completed_at = completed_at
        execution.updated_at = datetime.now(UTC)
        return execution

    async def append_event(self, **payload: Any) -> ExecutionEvent:
        execution_id = payload["execution_id"]
        event = ExecutionEvent(
            id=uuid4(),
            execution_id=execution_id,
            sequence=len(self.events[execution_id]) + 1,
            event_type=payload["event_type"],
            step_id=payload.get("step_id"),
            agent_fqn=payload.get("agent_fqn"),
            payload=dict(payload.get("payload", {})),
            correlation_workspace_id=payload["correlation_workspace_id"],
            correlation_conversation_id=payload.get("correlation_conversation_id"),
            correlation_interaction_id=payload.get("correlation_interaction_id"),
            correlation_goal_id=payload.get("correlation_goal_id"),
            correlation_fleet_id=payload.get("correlation_fleet_id"),
            correlation_execution_id=payload["correlation_execution_id"],
            created_at=datetime.now(UTC),
        )
        self.events[execution_id].append(event)
        return event

    async def get_events(
        self,
        execution_id: UUID,
        *,
        since_sequence: int | None = None,
        event_type: Any | None = None,
    ) -> list[ExecutionEvent]:
        items = list(self.events[execution_id])
        if since_sequence is not None:
            items = [item for item in items if item.sequence > since_sequence]
        if event_type is not None:
            items = [item for item in items if item.event_type == event_type]
        return items

    async def count_events(self, execution_id: UUID) -> int:
        return len(self.events[execution_id])

    async def create_checkpoint(self, checkpoint: ExecutionCheckpoint) -> ExecutionCheckpoint:
        checkpoint.id = getattr(checkpoint, "id", None) or uuid4()
        checkpoint.created_at = datetime.now(UTC)
        checkpoint.updated_at = checkpoint.created_at
        self.checkpoints[checkpoint.execution_id].append(checkpoint)
        return checkpoint

    async def get_latest_checkpoint(self, execution_id: UUID) -> ExecutionCheckpoint | None:
        if not self.checkpoints[execution_id]:
            return None
        return self.checkpoints[execution_id][-1]

    async def create_dispatch_lease(
        self,
        lease: ExecutionDispatchLease,
    ) -> ExecutionDispatchLease:
        lease.id = getattr(lease, "id", None) or uuid4()
        lease.created_at = datetime.now(UTC)
        lease.updated_at = lease.created_at
        self.leases.append(lease)
        return lease

    async def get_active_dispatch_lease(
        self,
        execution_id: UUID,
        step_id: str,
    ) -> ExecutionDispatchLease | None:
        for lease in reversed(self.leases):
            if (
                lease.execution_id == execution_id
                and lease.step_id == step_id
                and lease.released_at is None
            ):
                return lease
        return None

    async def release_dispatch_lease(
        self,
        lease: ExecutionDispatchLease,
        *,
        released_at: datetime,
        expired: bool = False,
    ) -> ExecutionDispatchLease:
        lease.released_at = released_at
        lease.expired = expired
        return lease

    async def upsert_task_plan_record(
        self,
        record: ExecutionTaskPlanRecord,
    ) -> ExecutionTaskPlanRecord:
        record.id = getattr(record, "id", None) or uuid4()
        record.created_at = datetime.now(UTC)
        record.updated_at = record.created_at
        self.task_plan_records[(record.execution_id, record.step_id)] = record
        return record

    async def list_task_plan_records(self, execution_id: UUID) -> list[ExecutionTaskPlanRecord]:
        return [
            item
            for (stored_execution_id, _), item in self.task_plan_records.items()
            if stored_execution_id == execution_id
        ]

    async def get_task_plan_record(
        self,
        execution_id: UUID,
        step_id: str,
    ) -> ExecutionTaskPlanRecord | None:
        return self.task_plan_records.get((execution_id, step_id))

    async def create_approval_wait(
        self,
        approval_wait: ExecutionApprovalWait,
    ) -> ExecutionApprovalWait:
        approval_wait.id = getattr(approval_wait, "id", None) or uuid4()
        approval_wait.created_at = datetime.now(UTC)
        approval_wait.updated_at = approval_wait.created_at
        self.approval_waits[(approval_wait.execution_id, approval_wait.step_id)] = approval_wait
        return approval_wait

    async def get_approval_wait(
        self,
        execution_id: UUID,
        step_id: str,
    ) -> ExecutionApprovalWait | None:
        return self.approval_waits.get((execution_id, step_id))

    async def list_approval_waits(self, execution_id: UUID) -> list[ExecutionApprovalWait]:
        return [
            item
            for (stored_execution_id, _), item in self.approval_waits.items()
            if stored_execution_id == execution_id
        ]

    async def list_pending_approval_waits(self, now: datetime) -> list[ExecutionApprovalWait]:
        return [
            item
            for item in self.approval_waits.values()
            if item.decision is None and item.timeout_at < now
        ]

    async def update_approval_wait(
        self,
        approval_wait: ExecutionApprovalWait,
        *,
        decision: Any,
        decided_by: str | None,
        decided_at: datetime,
    ) -> ExecutionApprovalWait:
        approval_wait.decision = decision
        approval_wait.decided_by = decided_by
        approval_wait.decided_at = decided_at
        approval_wait.updated_at = decided_at
        return approval_wait

    async def create_compensation_record(
        self,
        record: ExecutionCompensationRecord,
    ) -> ExecutionCompensationRecord:
        record.id = getattr(record, "id", None) or uuid4()
        record.created_at = datetime.now(UTC)
        record.updated_at = record.created_at
        self.compensations.append(record)
        return record


def make_settings() -> PlatformSettings:
    return PlatformSettings()
