from __future__ import annotations

from difflib import SequenceMatcher
from platform.evaluation.scorers.base import ScoreResult
from platform.evaluation.scorers.llm_judge import LLMJudgeScorer
from typing import Any
from uuid import UUID


class TrajectoryScorer:
    def __init__(
        self,
        *,
        execution_query: Any | None = None,
        reasoning_engine: Any | None = None,
        llm_judge: LLMJudgeScorer | None = None,
    ) -> None:
        self.execution_query = execution_query
        self.reasoning_engine = reasoning_engine
        self.llm_judge = llm_judge or LLMJudgeScorer()

    async def score(self, actual: str, expected: str, config: dict[str, Any]) -> ScoreResult:
        raw_execution_id = config.get("execution_id")
        if raw_execution_id is None:
            return ScoreResult(
                score=None,
                passed=None,
                error="missing_execution_id",
                rationale="Trajectory scorer requires execution_id in config.",
            )
        execution_id = UUID(str(raw_execution_id))
        events = await self._get_journal_events(execution_id)
        task_plan = await self._get_task_plan(execution_id)
        reasoning = await self._get_reasoning_traces(execution_id)
        actual_steps = max(1, len(events))
        optimal_steps = max(1, int(config.get("optimal_steps") or len(task_plan) or actual_steps))
        efficiency_score = min(1.0, optimal_steps / actual_steps)
        tool_appropriateness_score = self._score_tool_alignment(task_plan, events)
        cost_effectiveness_score = self._score_cost_effectiveness(actual, expected, config)
        reasoning_coherence_score = await self._score_reasoning_coherence(
            reasoning,
            actual,
            expected,
        )
        overall = (
            efficiency_score
            + tool_appropriateness_score
            + reasoning_coherence_score
            + cost_effectiveness_score
        ) / 4.0
        threshold = float(config.get("threshold", 0.7))
        holistic = None
        if config.get("include_llm_holistic", False):
            holistic_result = await self.llm_judge.score(
                actual,
                expected,
                {
                    "judge_model": str(config.get("judge_model", "heuristic-judge")),
                    "rubric": {"template": "instruction_following"},
                    "calibration_runs": 1,
                },
            )
            holistic = {
                "score": holistic_result.score,
                "rationale": holistic_result.rationale,
            }
        return ScoreResult(
            score=overall,
            passed=overall >= threshold,
            rationale="trajectory score computed",
            extra={
                "threshold": threshold,
                "efficiency_score": efficiency_score,
                "tool_appropriateness_score": tool_appropriateness_score,
                "reasoning_coherence_score": reasoning_coherence_score,
                "cost_effectiveness_score": cost_effectiveness_score,
                "overall_trajectory_score": overall,
                "llm_judge_holistic": holistic,
            },
        )

    async def _get_journal_events(self, execution_id: UUID) -> list[Any]:
        if self.execution_query is None:
            return []
        getter = getattr(self.execution_query, "get_journal", None) or getattr(
            self.execution_query,
            "get_journal_events",
            None,
        )
        if getter is None:
            return []
        result = await getter(execution_id)
        if isinstance(result, list):
            return result
        return list(getattr(result, "items", []) or [])

    async def _get_task_plan(self, execution_id: UUID) -> list[Any]:
        if self.execution_query is None:
            return []
        getter = getattr(self.execution_query, "get_task_plan", None) or getattr(
            self.execution_query,
            "get_task_plan_record",
            None,
        )
        if getter is None:
            return []
        if getter.__name__ == "get_task_plan":
            result = await getter(execution_id, None)
        else:
            result = await getter(execution_id)
        if isinstance(result, list):
            return result
        return [result] if result is not None else []

    async def _get_reasoning_traces(self, execution_id: UUID) -> list[dict[str, Any]]:
        if self.reasoning_engine is None:
            return []
        getter = getattr(self.reasoning_engine, "get_reasoning_traces", None) or getattr(
            self.reasoning_engine,
            "fetch_reasoning_traces",
            None,
        )
        if getter is None:
            return []
        result = await getter(execution_id=execution_id)
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        return list(getattr(result, "items", []) or [])

    @staticmethod
    def _score_tool_alignment(task_plan: list[Any], events: list[Any]) -> float:
        if not task_plan:
            return 1.0
        planned_tools = {
            str(getattr(item, "selected_tool", "") or item.get("selected_tool", "")).strip()
            for item in task_plan
            if item is not None
        }
        planned_tools.discard("")
        if not planned_tools:
            return 1.0
        observed_tools = {
            str(getattr(item, "agent_fqn", "") or item.get("agent_fqn", "")).strip()
            for item in events
            if item is not None
        }
        observed_tools.discard("")
        if not observed_tools:
            return 0.5
        overlap = len(planned_tools & observed_tools)
        return overlap / max(len(planned_tools), 1)

    @staticmethod
    def _score_cost_effectiveness(actual: str, expected: str, config: dict[str, Any]) -> float:
        token_ratio = float(config.get("token_cost_ratio", 1.0))
        quality = SequenceMatcher(None, actual, expected).ratio()
        return max(0.0, min(1.0, quality / max(token_ratio, 1.0)))

    async def _score_reasoning_coherence(
        self,
        traces: list[dict[str, Any]],
        actual: str,
        expected: str,
    ) -> float:
        if not traces:
            return SequenceMatcher(None, actual, expected).ratio()
        coherence = 0.0
        for trace in traces:
            summary = " ".join(
                str(trace.get(key, ""))
                for key in ("thought", "summary", "reasoning")
            )
            coherence += SequenceMatcher(None, summary, expected).ratio()
        return max(0.0, min(1.0, coherence / len(traces)))
