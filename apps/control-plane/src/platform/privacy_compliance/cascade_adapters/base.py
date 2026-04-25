from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

STORE_ORDER: tuple[str, ...] = (
    "postgresql",
    "qdrant",
    "opensearch",
    "s3",
    "clickhouse",
    "neo4j",
)


@dataclass(frozen=True, slots=True)
class CascadePlan:
    store_name: str
    estimated_count: int
    per_target_estimates: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CascadeResult:
    store_name: str
    started_at: datetime
    completed_at: datetime
    affected_count: int
    per_target_counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def empty_result(store_name: str) -> CascadeResult:
    now = datetime.now(UTC)
    return CascadeResult(
        store_name=store_name,
        started_at=now,
        completed_at=now,
        affected_count=0,
        per_target_counts={},
        errors=[],
    )


class CascadeAdapter(ABC):
    store_name: ClassVar[str]

    @abstractmethod
    async def dry_run(self, subject_user_id: UUID) -> CascadePlan:
        """Return what would be deleted without mutating the backing store."""

    @abstractmethod
    async def execute(self, subject_user_id: UUID) -> CascadeResult:
        """Perform idempotent deletion for one backing store."""

