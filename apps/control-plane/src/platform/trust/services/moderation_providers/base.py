from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class ProviderVerdict:
    provider: str
    scores: dict[str, float]
    triggered_categories: list[str] = field(default_factory=list)
    language: str | None = None
    latency_ms: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class ModerationProvider(Protocol):
    """Provider adapters must return scores mapped to the canonical safety taxonomy."""

    async def score(
        self,
        text: str,
        *,
        language: str | None,
        categories: set[str] | None,
    ) -> ProviderVerdict: ...
