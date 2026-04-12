from __future__ import annotations

import re
from platform.evaluation.scorers.base import ScoreResult
from typing import Any


class RegexScorer:
    async def score(self, actual: str, expected: str, config: dict[str, Any]) -> ScoreResult:
        pattern = str(config.get("pattern") or expected or "").strip()
        threshold = float(config.get("threshold", 1.0))
        if not pattern:
            return ScoreResult(
                score=None,
                passed=None,
                error="missing_regex_pattern",
                rationale="Regex scorer requires config['pattern'] or expected output.",
            )
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            return ScoreResult(
                score=None,
                passed=None,
                error="invalid_regex",
                rationale=str(exc),
                extra={"pattern": pattern},
            )
        matched = compiled.search(actual) is not None
        score = 1.0 if matched else 0.0
        return ScoreResult(
            score=score,
            passed=score >= threshold,
            rationale="regex matched" if matched else "regex did not match",
            extra={"threshold": threshold, "pattern": pattern},
        )
