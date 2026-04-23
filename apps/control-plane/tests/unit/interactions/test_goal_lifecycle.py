from __future__ import annotations

from platform.interactions.events import InteractionsEventType
from platform.interactions.goal_lifecycle import (
    GoalAutoCompletionScanner,
    GoalLifecycleService,
    GoalStateConflictError,
)
from platform.workspaces.models import WorkspaceGoalState
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.auth_support import RecordingProducer
from tests.workspaces_support import build_goal


class _GoalResult:
    def __init__(self, goals: list[object]) -> None:
        self.goals = goals

    def scalars(self) -> _GoalResult:
        return self

    def all(self) -> list[object]:
        return list(self.goals)


class _ScannerSession:
    def __init__(self, goals: list[object]) -> None:
        self.goals = goals
        self.flush_count = 0

    async def execute(self, statement: object) -> _GoalResult:
        del statement
        return _GoalResult(self.goals)

    async def flush(self) -> None:
        self.flush_count += 1


@pytest.mark.asyncio
async def test_transition_ready_to_working_emits_event() -> None:
    producer = RecordingProducer()
    service = GoalLifecycleService(producer)
    goal = build_goal(state=WorkspaceGoalState.ready)

    updated = await service.transition_ready_to_working(goal, SimpleNamespace())

    assert updated.state == WorkspaceGoalState.working
    assert producer.events[-1]["event_type"] == InteractionsEventType.goal_state_changed.value
    assert producer.events[-1]["payload"]["previous_state"] == "ready"
    assert producer.events[-1]["payload"]["new_state"] == "working"
    assert producer.events[-1]["payload"]["automatic"] is False


def test_assert_accepts_messages_rejects_complete_goals() -> None:
    service = GoalLifecycleService()

    service.assert_accepts_messages(build_goal(state=WorkspaceGoalState.ready))
    service.assert_accepts_messages(build_goal(state=WorkspaceGoalState.working))

    with pytest.raises(GoalStateConflictError):
        service.assert_accepts_messages(build_goal(state=WorkspaceGoalState.complete))


@pytest.mark.asyncio
async def test_transition_working_to_complete_emits_manual_event() -> None:
    producer = RecordingProducer()
    service = GoalLifecycleService(producer)
    goal = build_goal(state=WorkspaceGoalState.working)

    updated = await service.transition_working_to_complete(
        goal,
        SimpleNamespace(),
        automatic=False,
        reason="completed manually",
    )

    assert updated.state == WorkspaceGoalState.complete
    assert producer.events[-1]["payload"]["automatic"] is False
    assert producer.events[-1]["payload"]["reason"] == "completed manually"


@pytest.mark.asyncio
async def test_goal_state_transitions_are_one_directional() -> None:
    service = GoalLifecycleService()

    with pytest.raises(GoalStateConflictError):
        await service.transition_ready_to_working(
            build_goal(state=WorkspaceGoalState.complete),
            SimpleNamespace(),
        )

    with pytest.raises(GoalStateConflictError):
        await service.transition_working_to_complete(
            build_goal(state=WorkspaceGoalState.ready),
            SimpleNamespace(),
        )

    with pytest.raises(GoalStateConflictError):
        await service.transition_working_to_complete(
            build_goal(state=WorkspaceGoalState.complete),
            SimpleNamespace(),
        )


@pytest.mark.asyncio
async def test_goal_auto_completion_scanner_transitions_goals_and_flushes() -> None:
    producer = RecordingProducer()
    scanner = GoalAutoCompletionScanner(producer)
    goal = build_goal(
        goal_id=uuid4(),
        state=WorkspaceGoalState.working,
        auto_complete_timeout_seconds=60,
    )
    session = _ScannerSession([goal])

    transitioned = await scanner.scan_and_complete_idle_goals(session)

    assert transitioned == 1
    assert goal.state == WorkspaceGoalState.complete
    assert session.flush_count == 1
    assert producer.events[-1]["payload"]["automatic"] is True
