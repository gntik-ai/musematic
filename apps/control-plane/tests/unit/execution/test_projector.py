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


def test_projector_handles_checkpoints_and_additional_event_types() -> None:
    execution_id = uuid4()
    checkpoint = __import__(
        "platform.execution.models",
        fromlist=["ExecutionCheckpoint"],
    ).ExecutionCheckpoint(
        id=uuid4(),
        execution_id=execution_id,
        last_event_sequence=2,
        step_results={"_execution_data": {"budget": 12}, "step_a": {"status": "completed"}},
        completed_step_ids=["step_a"],
        active_step_ids=["step_b"],
        pending_step_ids=["step_c"],
        execution_data={"budget": 12},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    events = [
        ExecutionEvent(
            id=uuid4(),
            execution_id=execution_id,
            sequence=3,
            event_type=ExecutionEventType.rejected,
            step_id="step_b",
            agent_fqn=None,
            payload={"reason": "manual"},
            correlation_workspace_id=uuid4(),
            correlation_conversation_id=None,
            correlation_interaction_id=None,
            correlation_goal_id=None,
            correlation_fleet_id=None,
            correlation_execution_id=execution_id,
            created_at=datetime.now(UTC),
        ),
        _event(
            4,
            ExecutionEventType.approval_timed_out,
            step_id="step_c",
            payload={"timeout_action": "skip"},
        ),
        _event(5, ExecutionEventType.resumed),
        _event(6, ExecutionEventType.retried, step_id="step_c"),
        _event(7, ExecutionEventType.failed, step_id="step_c", payload={"error": "boom"}),
        _event(8, ExecutionEventType.canceled, step_id="step_c"),
        _event(
            9,
            ExecutionEventType.compensated,
            step_id="step_a",
            payload={"compensation_handler": "undo"},
        ),
        _event(
            10,
            ExecutionEventType.compensation_failed,
            step_id="step_c",
            payload={"compensation_handler": "undo", "outcome": "failed"},
        ),
        _event(
            11,
            ExecutionEventType.hot_changed,
            payload={"new_version_id": str(uuid4())},
        ),
        _event(
            12,
            ExecutionEventType.context_assembled,
            step_id="step_c",
            payload={"sources": ["workspace"]},
        ),
        _event(
            13,
            ExecutionEventType.reprioritized,
            payload={"trigger_reason": "budget_threshold_breached"},
        ),
        _event(14, ExecutionEventType.reasoning_trace_emitted),
        _event(15, ExecutionEventType.self_correction_started),
        _event(16, ExecutionEventType.self_correction_converged),
    ]

    state = ExecutionProjector().project_state(events, checkpoint)

    assert state.status.value == "failed"
    assert state.step_results["_execution_data"] == {"budget": 12}
    assert state.step_results["step_b"]["status"] == "rejected"
    assert state.step_results["step_c"]["context"] == {"sources": ["workspace"]}
    assert state.step_results["step_a"]["status"] == "compensated"
    assert state.step_results["_reprioritization"] == [
        {"trigger_reason": "budget_threshold_breached"}
    ]
    assert state.last_event_sequence == 16
