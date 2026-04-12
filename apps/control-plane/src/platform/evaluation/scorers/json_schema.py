from __future__ import annotations

import json
from platform.evaluation.scorers.base import ScoreResult
from typing import Any

from jsonschema import ValidationError as JsonSchemaValidationError  # type: ignore[import-untyped]
from jsonschema import validate


class JsonSchemaScorer:
    async def score(self, actual: str, expected: str, config: dict[str, Any]) -> ScoreResult:
        schema = config.get("schema")
        threshold = float(config.get("threshold", 1.0))
        if not isinstance(schema, dict):
            return ScoreResult(
                score=None,
                passed=None,
                error="missing_json_schema",
                rationale="JsonSchema scorer requires config['schema'].",
            )
        try:
            payload = json.loads(actual)
        except json.JSONDecodeError as exc:
            return ScoreResult(
                score=0.0,
                passed=False,
                error="invalid_json",
                rationale=str(exc),
            )
        try:
            validate(instance=payload, schema=schema)
        except JsonSchemaValidationError as exc:
            return ScoreResult(
                score=0.0,
                passed=False,
                rationale=exc.message,
                extra={"validator": exc.validator, "path": list(exc.path)},
            )
        return ScoreResult(
            score=1.0,
            passed=1.0 >= threshold,
            rationale="json schema validation passed",
            extra={"threshold": threshold},
        )
