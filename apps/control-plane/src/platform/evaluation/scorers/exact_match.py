from __future__ import annotations

from platform.evaluation.scorers.base import ScoreResult
from typing import Any


class ExactMatchScorer:
    async def score(self, actual: str, expected: str, config: dict[str, Any]) -> ScoreResult:
        threshold = float(config.get("threshold", 1.0))
        matched = actual == expected
        score = 1.0 if matched else 0.0
        return ScoreResult(
            score=score,
            passed=score >= threshold,
            rationale="exact match" if matched else "outputs differ",
            extra={"threshold": threshold, "matched": matched},
        )
