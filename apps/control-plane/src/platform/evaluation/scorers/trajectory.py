from __future__ import annotations

import logging
import time
from difflib import SequenceMatcher
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.evaluation.exceptions import CooperationModeTooFewAgentsError
from platform.evaluation.scorers.base import ScoreResult
from typing import Any, Literal
from uuid import UUID

LOGGER = logging.getLogger(__name__)
ComparisonMethod = Literal["exact", "in_order", "any_order", "precision", "recall"]


class TrajectoryScorer:
    def __init__(
        self,
        *,
        settings: PlatformSettings | None = None,
        execution_query: Any | None = None,
        reasoning_engine: Any | None = None,
        llm_judge: Any | None = None,
    ) -> None:
        self.settings = settings or default_settings
        self.execution_query = execution_query
        self.reasoning_engine = reasoning_engine
        self.llm_judge = llm_judge

    async def score(self, actual: str, expected: str, config: dict[str, Any]) -> ScoreResult:
        started = time.perf_counter()
        raw_execution_id = config.get("execution_id")
        if raw_execution_id is None:
            return ScoreResult(
                score=None,
                passed=None,
                error="missing_execution_id",
                rationale="Trajectory scorer requires execution_id in config.",
            )
        execution_id = UUID(str(raw_execution_id))
        comparison_method = str(config.get("comparison_method", "any_order"))
        LOGGER.info(
            "trajectory scorer start execution_id=%s comparison_method=%s principal=%s",
            execution_id,
            comparison_method,
            config.get("principal_id"),
        )
        events = await self._get_journal_events(execution_id)
        original_step_count = len(events)
        truncated = False
        max_steps = int(self.settings.evaluation.trajectory_max_steps)
        if original_step_count > max_steps:
            events = events[:max_steps]
            truncated = True
        actual_steps = [step for step in (self._extract_step_id(item) for item in events) if step]
        expected_steps = [
            step
            for step in (self._extract_step_id(item) for item in config.get("expected_steps", []))
            if step
        ]
        comparison_score = self._compare(actual_steps, expected_steps, comparison_method)  # type: ignore[arg-type]
        threshold = float(config.get("threshold", 0.7))
        if not actual_steps:
            duration_ms = int((time.perf_counter() - started) * 1000)
            LOGGER.info(
                "trajectory scorer end execution_id=%s outcome=success truncated=%s duration_ms=%s",
                execution_id,
                truncated,
                duration_ms,
            )
            return ScoreResult(
                score=comparison_score,
                passed=comparison_score >= threshold,
                rationale="trajectory has no recorded actions",
                extra={
                    "comparison_method": comparison_method,
                    "comparison_score": comparison_score,
                    "efficiency_score": None,
                    "tool_appropriateness_score": None,
                    "reasoning_coherence_score": None,
                    "cost_effectiveness_score": None,
                    "overall_trajectory_score": comparison_score,
                    "unscored": True,
                    "truncated": truncated,
                    "original_step_count": original_step_count,
                },
            )
        task_plan = await self._get_task_plan(execution_id)
        reasoning = await self._get_reasoning_traces(execution_id)
        optimal_steps = max(
            1, int(config.get("optimal_steps") or len(task_plan) or len(actual_steps))
        )
        efficiency_score = min(1.0, optimal_steps / max(len(actual_steps), 1))
        tool_appropriateness_score = self._score_tool_alignment(task_plan, events)
        cost_effectiveness_score = self._score_cost_effectiveness(actual, expected, config, events)
        reasoning_coherence_score = await self._score_reasoning_coherence(
            reasoning, actual, expected
        )
        available_scores = [
            comparison_score,
            efficiency_score,
            tool_appropriateness_score,
            reasoning_coherence_score,
        ]
        if cost_effectiveness_score is not None:
            available_scores.append(cost_effectiveness_score)
        overall = sum(available_scores) / len(available_scores)
        holistic = None
        if config.get("include_llm_holistic", False) and self.llm_judge is not None:
            holistic_result = await self.llm_judge.score(
                actual,
                expected,
                {
                    "judge_model": str(
                        config.get("judge_model", self.settings.evaluation.llm_judge_model)
                    ),
                    "rubric": {"template": "instruction_following"},
                    "calibration_runs": 1,
                },
            )
            holistic = {
                "score": holistic_result.score,
                "rationale": holistic_result.rationale,
            }
        duration_ms = int((time.perf_counter() - started) * 1000)
        LOGGER.info(
            "trajectory scorer end execution_id=%s outcome=success truncated=%s duration_ms=%s",
            execution_id,
            truncated,
            duration_ms,
        )
        extra = {
            "threshold": threshold,
            "comparison_method": comparison_method,
            "comparison_score": comparison_score,
            "efficiency_score": efficiency_score,
            "tool_appropriateness_score": tool_appropriateness_score,
            "reasoning_coherence_score": reasoning_coherence_score,
            "cost_effectiveness_score": cost_effectiveness_score,
            "overall_trajectory_score": overall,
            "llm_judge_holistic": holistic,
            "truncated": truncated,
            "original_step_count": original_step_count,
            "duration_ms": duration_ms,
        }
        if cost_effectiveness_score is None:
            extra["cost_effectiveness_unscored"] = True
        return ScoreResult(
            score=overall,
            passed=overall >= threshold,
            rationale="trajectory score computed",
            extra=extra,
        )

    async def score_cooperation(
        self,
        agent_execution_ids: list[UUID] | list[str],
        config: dict[str, Any],
    ) -> ScoreResult:
        if len(agent_execution_ids) < 2:
            raise CooperationModeTooFewAgentsError()
        started = time.perf_counter()
        LOGGER.info("trajectory cooperation start executions=%s", agent_execution_ids)
        per_agent_scores: dict[str, dict[str, Any]] = {}
        handoff_edges: list[tuple[str, str]] = []
        total_efficiency = 0.0
        for raw_execution_id in agent_execution_ids:
            execution_id = UUID(str(raw_execution_id))
            result = await self.score(
                "", "", {**config, "execution_id": str(execution_id), "include_llm_holistic": False}
            )
            per_agent_scores[str(execution_id)] = result.model_dump(mode="json")
            total_efficiency += float(
                result.extra.get("overall_trajectory_score") or result.score or 0.0
            )
            events = await self._get_journal_events(execution_id)
            handoff_edges.extend(self._extract_handoff_edges(events))
        cycle_flags = self._detect_cycles(handoff_edges)
        coordination_overhead = max(0.0, 1.0 - (0.25 * len(cycle_flags)))
        unique_edges = len(set(handoff_edges))
        redundancy = max(0.0, min(1.0, unique_edges / max(len(handoff_edges), 1)))
        handoff_timeliness = 1.0 if handoff_edges else 0.5
        joint_path_efficiency = total_efficiency / len(agent_execution_ids)
        overall = (
            coordination_overhead + redundancy + handoff_timeliness + joint_path_efficiency
        ) / 4.0
        duration_ms = int((time.perf_counter() - started) * 1000)
        LOGGER.info(
            "trajectory cooperation end executions=%s outcome=success duration_ms=%s",
            agent_execution_ids,
            duration_ms,
        )
        return ScoreResult(
            score=overall,
            passed=overall >= float(config.get("threshold", 0.7)),
            rationale="cooperation score computed",
            extra={
                "per_agent_scores": per_agent_scores,
                "coordination_overhead": coordination_overhead,
                "handoff_timeliness": handoff_timeliness,
                "redundancy": redundancy,
                "joint_path_efficiency": joint_path_efficiency,
                "cycle_flags": cycle_flags,
                "duration_ms": duration_ms,
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
        if getattr(getter, "__name__", "") == "get_task_plan":
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
    def _compare(
        actual_steps: list[str],
        expected_steps: list[str],
        method: ComparisonMethod,
    ) -> float:
        if not actual_steps and not expected_steps:
            return 0.0
        actual_set = set(actual_steps)
        expected_set = set(expected_steps)
        intersection = len(actual_set & expected_set)
        if method == "exact":
            denominator = max(len(actual_steps), len(expected_steps), 1)
            matches = sum(
                1
                for left, right in zip(actual_steps, expected_steps, strict=False)
                if left == right
            )
            return matches / denominator
        if method == "in_order":
            denominator = max(len(expected_steps), 1)
            return (
                TrajectoryScorer._longest_common_subsequence(actual_steps, expected_steps)
                / denominator
            )
        if method == "any_order":
            denominator = len(actual_set | expected_set)
            return intersection / denominator if denominator else 0.0
        if method == "precision":
            return intersection / len(actual_set) if actual_set else 0.0
        return intersection / len(expected_set) if expected_set else 0.0

    @staticmethod
    def _longest_common_subsequence(actual_steps: list[str], expected_steps: list[str]) -> int:
        if not actual_steps or not expected_steps:
            return 0
        rows = len(actual_steps) + 1
        cols = len(expected_steps) + 1
        matrix = [[0] * cols for _ in range(rows)]
        for row in range(1, rows):
            for col in range(1, cols):
                if actual_steps[row - 1] == expected_steps[col - 1]:
                    matrix[row][col] = matrix[row - 1][col - 1] + 1
                else:
                    matrix[row][col] = max(matrix[row - 1][col], matrix[row][col - 1])
        return matrix[-1][-1]

    @staticmethod
    def _payload_dict(item: Any) -> dict[str, Any]:
        payload = item.get("payload") if isinstance(item, dict) else getattr(item, "payload", None)
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _item_value(item: Any, key: str) -> Any:
        if isinstance(item, dict):
            return item.get(key)
        return getattr(item, key, None)

    @staticmethod
    def _extract_step_id(item: Any) -> str:
        payload = TrajectoryScorer._payload_dict(item)
        for key in ("tool", "selected_tool", "agent_fqn", "step_id"):
            value = TrajectoryScorer._item_value(item, key) or payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _score_tool_alignment(task_plan: list[Any], events: list[Any]) -> float:
        if not task_plan:
            return 1.0
        planned_tools = {
            str(TrajectoryScorer._item_value(item, "selected_tool") or "").strip()
            for item in task_plan
            if item is not None
        }
        planned_tools.discard("")
        if not planned_tools:
            return 1.0
        observed_tools = {
            step for step in (TrajectoryScorer._extract_step_id(item) for item in events) if step
        }
        if not observed_tools:
            return 0.5
        overlap = len(planned_tools & observed_tools)
        return overlap / max(len(planned_tools), 1)

    @staticmethod
    def _score_cost_effectiveness(
        actual: str,
        expected: str,
        config: dict[str, Any],
        events: list[Any],
    ) -> float | None:
        token_ratio = config.get("token_cost_ratio")
        if token_ratio is None:
            token_ratio = TrajectoryScorer._extract_cost_ratio(events)
        if token_ratio is None:
            return None
        quality = SequenceMatcher(None, actual, expected).ratio()
        return max(0.0, min(1.0, quality / max(float(token_ratio), 1.0)))

    @staticmethod
    def _extract_cost_ratio(events: list[Any]) -> float | None:
        totals: list[float] = []
        for item in events:
            payload = TrajectoryScorer._payload_dict(item)
            for key in ("token_cost_ratio", "accumulated_costs", "cost_tokens"):
                value = payload.get(key)
                if isinstance(value, (int, float)):
                    totals.append(float(value))
        if not totals:
            return None
        return max(totals)

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
                str(trace.get(key, "")) for key in ("thought", "summary", "reasoning")
            )
            coherence += SequenceMatcher(None, summary, expected).ratio()
        return max(0.0, min(1.0, coherence / len(traces)))

    def _extract_handoff_edges(self, events: list[Any]) -> list[tuple[str, str]]:
        edges: list[tuple[str, str]] = []
        for item in events:
            payload = self._payload_dict(item)
            event_type = self._item_value(item, "event_type")
            source = self._extract_step_id(item)
            target = payload.get("handoff_to") or payload.get("to_agent_fqn")
            if event_type == "handoff" and isinstance(source, str) and isinstance(target, str):
                edges.append((source, target))
        return edges

    def _detect_cycles(self, edges: list[tuple[str, str]]) -> list[dict[str, Any]]:
        graph: dict[str, set[str]] = {}
        for source, target in edges:
            graph.setdefault(source, set()).add(target)
        visiting: set[str] = set()
        visited: set[str] = set()
        cycles: list[dict[str, Any]] = []
        stack: list[str] = []

        def dfs(node: str) -> None:
            visiting.add(node)
            stack.append(node)
            for neighbour in graph.get(node, set()):
                if neighbour in visiting:
                    try:
                        start = stack.index(neighbour)
                    except ValueError:
                        start = 0
                    cycle = [*stack[start:], neighbour]
                    cycles.append({"agents": cycle})
                    continue
                if neighbour not in visited:
                    dfs(neighbour)
            stack.pop()
            visiting.discard(node)
            visited.add(node)

        for node in list(graph):
            if node not in visited:
                dfs(node)
        return cycles
