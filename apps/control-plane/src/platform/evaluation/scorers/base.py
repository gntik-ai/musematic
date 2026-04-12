from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class ScoreResult(BaseModel):
    score: float | None = None
    passed: bool | None = None
    rationale: str | None = None
    error: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Scorer(Protocol):
    async def score(self, actual: str, expected: str, config: dict[str, Any]) -> ScoreResult: ...
