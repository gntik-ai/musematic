from __future__ import annotations

from datetime import UTC, datetime
from platform.execution.models import ExecutionEvent, ExecutionEventType
from platform.execution.projector import ExecutionProjector
from uuid import uuid4


def _event(
    sequence: int,
    event_type: ExecutionEventType,
    *,
    step_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> ExecutionEvent:
    execution_id = uuid4()
    return ExecutionEvent(
        id=uuid4(),
        execution_id=execution_id,
        sequence=sequence,
        event_type=event_type,
        step_id=step_id,
        agent_fqn=None,
        payload=payload or {},
        correlation_workspace_id=uuid4(),
        correlation_conversation_id=None,
        correlation_interaction_id=None,
        correlation_goal_id=None,
        correlation_fleet_id=None,
        correlation_execution_id=execution_id,
        created_at=datetime.now(UTC),
    )


def test_projector_tracks_state_transitions() -> None:
    execution_id = uuid4()
    events = [
        ExecutionEvent(
            id=uuid4(),
            execution_id=execution_id,
            sequence=1,
            event_type=ExecutionEventType.created,
            step_id=None,
            agent_fqn=None,
            payload={"all_step_ids": ["step_a", "step_b"], "workflow_version_id": str(uuid4())},
            correlation_workspace_id=uuid4(),
            correlation_conversation_id=None,
            correlation_interaction_id=None,
            correlation_goal_id=None,
            correlation_fleet_id=None,
            correlation_execution_id=execution_id,
            created_at=datetime.now(UTC),
        ),
        _event(2, ExecutionEventType.queued),
        _event(3, ExecutionEventType.dispatched, step_id="step_a"),
        _event(4, ExecutionEventType.completed, step_id="step_a", payload={"output": {"ok": True}}),
        _event(5, ExecutionEventType.waiting_for_approval, step_id="step_b"),
        _event(6, ExecutionEventType.approved, step_id="step_b"),
        _event(7, ExecutionEventType.completed, payload={"execution_completed": True}),
    ]

    state = ExecutionProjector().project_state(events)

    assert state.status.value == "completed"
    assert state.completed_step_ids == ["step_a", "step_b"]
    assert state.pending_step_ids == []
    assert state.step_results["step_a"]["output"] == {"ok": True}
    assert state.last_event_sequence == 7
