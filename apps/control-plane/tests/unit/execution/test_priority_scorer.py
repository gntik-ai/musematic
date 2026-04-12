from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.execution.models import Execution, ExecutionStatus
from platform.execution.scheduler import PriorityScorer
from platform.workflows.ir import StepIR
from platform.workflows.models import TriggerType
from uuid import uuid4


def _execution(
    *,
    status: ExecutionStatus = ExecutionStatus.queued,
    sla_deadline: datetime | None = None,
) -> Execution:
    return Execution(
        workflow_version_id=uuid4(),
        workflow_definition_id=uuid4(),
        trigger_id=None,
        trigger_type=TriggerType.manual,
        status=status,
        input_parameters={},
        workspace_id=uuid4(),
        correlation_workspace_id=uuid4(),
        correlation_conversation_id=None,
        correlation_interaction_id=None,
        correlation_fleet_id=None,
        correlation_goal_id=None,
        parent_execution_id=None,
        rerun_of_execution_id=None,
        started_at=None,
        completed_at=None,
        sla_deadline=sla_deadline,
        created_by=None,
    )


def _context(
    step: StepIR,
    *,
    execution: Execution,
    now: datetime,
    dependency_depth: float = 0.0,
) -> dict[str, object]:
    del step
    return {
        "execution": execution,
        "state": None,
        "now": now,
        "dependency_depth": {"target": dependency_depth},
    }


def test_priority_scorer_favors_urgent_sla_bound_steps() -> None:
    scorer = PriorityScorer()
    now = datetime.now(UTC)
    urgent_step = StepIR(
        step_id="target",
        step_type="approval_gate",
        approval_config=None,
        context_budget_tokens=1024,
    )
    relaxed_step = StepIR(
        step_id="target",
        step_type="tool_call",
        tool_fqn="ns:tool",
    )

    urgent_score = scorer.compute(
        urgent_step,
        _context(
            urgent_step,
            execution=_execution(
                status=ExecutionStatus.running,
                sla_deadline=now + timedelta(minutes=5),
            ),
            now=now,
            dependency_depth=2.0,
        ),
    )
    relaxed_score = scorer.compute(
        relaxed_step,
        _context(
            relaxed_step,
            execution=_execution(status=ExecutionStatus.queued, sla_deadline=None),
            now=now,
            dependency_depth=0.0,
        ),
    )

    assert urgent_score > relaxed_score


def test_priority_scorer_is_deterministic_for_same_inputs() -> None:
    scorer = PriorityScorer()
    now = datetime.now(UTC)
    step = StepIR(
        step_id="target",
        step_type="agent_task",
        agent_fqn="ns:agent",
        context_budget_tokens=2048,
    )
    context = _context(
        step,
        execution=_execution(
            status=ExecutionStatus.running,
            sla_deadline=now + timedelta(minutes=10),
        ),
        now=now,
        dependency_depth=1.0,
    )

    first = scorer.compute(step, context)
    second = scorer.compute(step, context)

    assert first == second
