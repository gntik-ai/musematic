from __future__ import annotations

from platform.workspaces.exceptions import InvalidGoalTransitionError
from platform.workspaces.models import GoalStatus

VALID_GOAL_TRANSITIONS: dict[GoalStatus, set[GoalStatus]] = {
    GoalStatus.open: {GoalStatus.in_progress, GoalStatus.cancelled},
    GoalStatus.in_progress: {GoalStatus.completed, GoalStatus.cancelled},
    GoalStatus.completed: set(),
    GoalStatus.cancelled: set(),
}


async def validate_goal_transition(current: GoalStatus, target: GoalStatus) -> None:
    allowed = VALID_GOAL_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidGoalTransitionError(current.value, target.value)
