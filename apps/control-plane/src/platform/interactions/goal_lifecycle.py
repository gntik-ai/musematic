from __future__ import annotations

import logging
from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import PlatformError
from platform.interactions.events import GoalStateChangedPayload, publish_goal_state_changed
from platform.workspaces.models import WorkspaceGoal, WorkspaceGoalState
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = logging.getLogger(__name__)


class GoalStateConflictError(PlatformError):
    status_code = 409

    def __init__(self, goal: WorkspaceGoal, message: str) -> None:
        state_value = getattr(goal.state, "value", str(goal.state))
        super().__init__(
            "GOAL_STATE_CONFLICT",
            message,
            {
                "goal_id": str(goal.id),
                "workspace_id": str(goal.workspace_id),
                "current_state": state_value,
            },
        )


class GoalLifecycleService:
    def __init__(self, producer: EventProducer | None = None) -> None:
        self.producer = producer

    async def transition_ready_to_working(
        self,
        goal: WorkspaceGoal,
        session: AsyncSession | None,
    ) -> WorkspaceGoal:
        del session
        if goal.state == WorkspaceGoalState.working:
            return goal
        if goal.state != WorkspaceGoalState.ready:
            raise GoalStateConflictError(
                goal,
                f"Goal is in state '{goal.state.value}' and cannot transition to working",
            )
        previous_state = goal.state
        goal.state = WorkspaceGoalState.working
        await self._publish_state_change(
            goal,
            previous_state=previous_state,
            new_state=goal.state,
            automatic=False,
            reason=None,
        )
        return goal

    async def transition_working_to_complete(
        self,
        goal: WorkspaceGoal,
        session: AsyncSession | None,
        *,
        automatic: bool = False,
        reason: str | None = None,
    ) -> WorkspaceGoal:
        del session
        if goal.state == WorkspaceGoalState.complete:
            raise GoalStateConflictError(goal, "Goal is already complete")
        if goal.state != WorkspaceGoalState.working:
            raise GoalStateConflictError(
                goal,
                (
                    "Goal must be in state 'working' before it can complete; "
                    f"current state is '{goal.state.value}'"
                ),
            )
        previous_state = goal.state
        goal.state = WorkspaceGoalState.complete
        await self._publish_state_change(
            goal,
            previous_state=previous_state,
            new_state=goal.state,
            automatic=automatic,
            reason=reason,
        )
        return goal

    def assert_accepts_messages(self, goal: WorkspaceGoal) -> None:
        if goal.state == WorkspaceGoalState.complete:
            raise GoalStateConflictError(goal, "Goal is complete and cannot accept new messages")

    def update_last_message_at(self, goal: WorkspaceGoal, ts: datetime) -> WorkspaceGoal:
        goal.last_message_at = ts
        return goal

    async def _publish_state_change(
        self,
        goal: WorkspaceGoal,
        *,
        previous_state: WorkspaceGoalState,
        new_state: WorkspaceGoalState,
        automatic: bool,
        reason: str | None,
    ) -> None:
        await publish_goal_state_changed(
            self.producer,
            GoalStateChangedPayload(
                goal_id=goal.id,
                workspace_id=goal.workspace_id,
                previous_state=previous_state.value,
                new_state=new_state.value,
                automatic=automatic,
                reason=reason,
                transitioned_at=datetime.now(UTC),
            ),
            CorrelationContext(
                correlation_id=uuid4(),
                workspace_id=goal.workspace_id,
                goal_id=goal.id,
            ),
        )


class GoalAutoCompletionScanner:
    def __init__(self, producer: EventProducer | None = None) -> None:
        self.lifecycle = GoalLifecycleService(producer)

    async def scan_and_complete_idle_goals(self, session: AsyncSession) -> int:
        elapsed_seconds = func.extract("epoch", func.now() - WorkspaceGoal.last_message_at)
        result = await session.execute(
            select(WorkspaceGoal)
            .where(
                WorkspaceGoal.state == WorkspaceGoalState.working,
                WorkspaceGoal.auto_complete_timeout_seconds.is_not(None),
                WorkspaceGoal.last_message_at.is_not(None),
                elapsed_seconds > WorkspaceGoal.auto_complete_timeout_seconds,
            )
            .order_by(WorkspaceGoal.last_message_at.asc(), WorkspaceGoal.id.asc())
            .with_for_update(skip_locked=True)
        )
        goals = list(result.scalars().all())
        for goal in goals:
            await self.lifecycle.transition_working_to_complete(
                goal,
                session,
                automatic=True,
                reason="idle_timeout",
            )
        if goals:
            await session.flush()
        LOGGER.info("Goal auto-completion scanner transitioned %s goals", len(goals))
        return len(goals)
