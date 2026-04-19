from __future__ import annotations

from dataclasses import dataclass, field
from platform.evaluation.exceptions import CooperationModeTooFewAgentsError
from platform.evaluation.scorers.base import ScoreResult
from platform.evaluation.scorers.trajectory import TrajectoryScorer
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from tests.evaluation_testing_support import ReasoningEngineStub, make_settings


@dataclass
class MultiExecutionQuery:
    journal_by_id: dict[UUID, list[object]] = field(default_factory=dict)
    task_plan_by_id: dict[UUID, list[object]] = field(default_factory=dict)

    async def get_journal(self, execution_id: UUID) -> SimpleNamespace:
        return SimpleNamespace(items=list(self.journal_by_id.get(execution_id, [])))

    async def get_task_plan(self, execution_id: UUID, _workspace_id: object) -> list[object]:
        return list(self.task_plan_by_id.get(execution_id, []))


class HolisticJudgeStub:
    async def score(self, *_args: object, **_kwargs: object) -> ScoreResult:
        return ScoreResult(score=4.0, rationale="holistic", extra={"max_scale": 5.0})


def test_compare_methods_cover_all_supported_modes() -> None:
    assert TrajectoryScorer._compare(["a", "b"], ["a", "b"], "exact") == 1.0
    assert TrajectoryScorer._compare(["a", "c"], ["a", "b", "c"], "in_order") == pytest.approx(
        2 / 3
    )
    assert TrajectoryScorer._compare(["b", "a"], ["a", "b"], "any_order") == 1.0
    assert TrajectoryScorer._compare(["a", "c"], ["a", "b"], "precision") == 0.5
    assert TrajectoryScorer._compare(["a"], ["a", "b"], "recall") == 0.5


@pytest.mark.asyncio
async def test_trajectory_score_marks_empty_trajectories_as_unscored() -> None:
    scorer = TrajectoryScorer(settings=make_settings(), execution_query=MultiExecutionQuery())
    result = await scorer.score(
        "actual",
        "expected",
        {"execution_id": str(uuid4()), "comparison_method": "any_order", "threshold": 0.5},
    )

    assert result.score == 0.0
    assert result.passed is False
    assert result.extra["unscored"] is True
    assert result.extra["overall_trajectory_score"] == 0.0


@pytest.mark.asyncio
async def test_trajectory_score_truncates_and_leaves_cost_dimension_unscored() -> None:
    execution_id = uuid4()
    settings = make_settings()
    settings.evaluation.trajectory_max_steps = 1
    query = MultiExecutionQuery(
        journal_by_id={
            execution_id: [
                {"step_id": "tool.alpha", "payload": {"output": "a"}},
                {"step_id": "tool.beta", "payload": {"output": "b"}},
                {"step_id": "tool.gamma", "payload": {"output": "c"}},
            ]
        },
        task_plan_by_id={execution_id: [{"selected_tool": "tool.alpha"}]},
    )
    scorer = TrajectoryScorer(
        settings=settings,
        execution_query=query,
        reasoning_engine=ReasoningEngineStub(traces=[{"summary": "expected"}]),
        llm_judge=HolisticJudgeStub(),
    )

    result = await scorer.score(
        "expected",
        "expected",
        {
            "execution_id": str(execution_id),
            "comparison_method": "any_order",
            "expected_steps": [{"step_id": "tool.alpha"}, {"step_id": "tool.beta"}],
            "include_llm_holistic": True,
        },
    )

    assert result.extra["truncated"] is True
    assert result.extra["original_step_count"] == 3
    assert result.extra["cost_effectiveness_score"] is None
    assert result.extra["cost_effectiveness_unscored"] is True
    assert result.extra["llm_judge_holistic"] == {"score": 4.0, "rationale": "holistic"}


@pytest.mark.asyncio
async def test_trajectory_cooperation_detects_cycles() -> None:
    execution_a = uuid4()
    execution_b = uuid4()
    query = MultiExecutionQuery(
        journal_by_id={
            execution_a: [
                {
                    "event_type": "handoff",
                    "agent_fqn": "agent.alpha",
                    "payload": {"handoff_to": "agent.beta"},
                }
            ],
            execution_b: [
                {
                    "event_type": "handoff",
                    "agent_fqn": "agent.beta",
                    "payload": {"handoff_to": "agent.alpha"},
                }
            ],
        },
        task_plan_by_id={
            execution_a: [{"selected_tool": "agent.alpha"}],
            execution_b: [{"selected_tool": "agent.beta"}],
        },
    )
    scorer = TrajectoryScorer(settings=make_settings(), execution_query=query)

    result = await scorer.score_cooperation(
        [execution_a, execution_b],
        {"threshold": 0.0, "comparison_method": "any_order"},
    )

    assert result.passed is True
    assert set(result.extra["per_agent_scores"]) == {str(execution_a), str(execution_b)}
    assert result.extra["cycle_flags"]
    assert result.extra["coordination_overhead"] < 1.0


@pytest.mark.asyncio
async def test_trajectory_cooperation_requires_at_least_two_agents() -> None:
    scorer = TrajectoryScorer(settings=make_settings(), execution_query=MultiExecutionQuery())

    with pytest.raises(CooperationModeTooFewAgentsError):
        await scorer.score_cooperation([uuid4()], {"threshold": 0.0})
