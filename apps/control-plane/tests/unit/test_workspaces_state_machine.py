from __future__ import annotations

from platform.workspaces.exceptions import InvalidGoalTransitionError
from platform.workspaces.models import GoalStatus
from platform.workspaces.state_machine import validate_goal_transition

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("current", "target"),
    [
        (GoalStatus.open, GoalStatus.in_progress),
        (GoalStatus.open, GoalStatus.cancelled),
        (GoalStatus.in_progress, GoalStatus.completed),
        (GoalStatus.in_progress, GoalStatus.cancelled),
    ],
)
async def test_validate_goal_transition_accepts_valid_edges(
    current: GoalStatus,
    target: GoalStatus,
) -> None:
    assert await validate_goal_transition(current, target) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("current", "target"),
    [
        (GoalStatus.open, GoalStatus.completed),
        (GoalStatus.completed, GoalStatus.open),
        (GoalStatus.completed, GoalStatus.cancelled),
        (GoalStatus.cancelled, GoalStatus.open),
        (GoalStatus.cancelled, GoalStatus.in_progress),
    ],
)
async def test_validate_goal_transition_rejects_invalid_edges(
    current: GoalStatus,
    target: GoalStatus,
) -> None:
    with pytest.raises(InvalidGoalTransitionError):
        await validate_goal_transition(current, target)
