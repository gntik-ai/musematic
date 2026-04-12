from __future__ import annotations

from platform.evaluation.scorers.base import Scorer
from platform.evaluation.scorers.exact_match import ExactMatchScorer
from platform.evaluation.scorers.json_schema import JsonSchemaScorer
from platform.evaluation.scorers.llm_judge import LLMJudgeScorer
from platform.evaluation.scorers.regex import RegexScorer
from platform.evaluation.scorers.semantic import SemanticSimilarityScorer
from platform.evaluation.scorers.trajectory import TrajectoryScorer


class ScorerRegistry:
    def __init__(self) -> None:
        self._scorers: dict[str, Scorer] = {}

    def register(self, scorer_type: str, scorer: Scorer) -> None:
        self._scorers[scorer_type] = scorer

    def get(self, scorer_type: str) -> Scorer:
        try:
            return self._scorers[scorer_type]
        except KeyError as exc:
            raise KeyError(f"Unknown scorer type: {scorer_type}") from exc

    def has(self, scorer_type: str) -> bool:
        return scorer_type in self._scorers

    def registered_types(self) -> list[str]:
        return sorted(self._scorers)


default_scorer_registry = ScorerRegistry()
default_scorer_registry.register("exact_match", ExactMatchScorer())
default_scorer_registry.register("regex", RegexScorer())
default_scorer_registry.register("json_schema", JsonSchemaScorer())
default_scorer_registry.register("semantic", SemanticSimilarityScorer())
default_scorer_registry.register("llm_judge", LLMJudgeScorer())
default_scorer_registry.register("trajectory", TrajectoryScorer())
