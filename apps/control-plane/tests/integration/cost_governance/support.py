from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4


@dataclass
class AttributionRow:
    execution_id: UUID
    step_id: str | None
    workspace_id: UUID
    agent_id: UUID | None
    user_id: UUID | None
    origin: str
    model_id: str | None
    currency: str
    model_cost_cents: Decimal
    compute_cost_cents: Decimal
    storage_cost_cents: Decimal
    overhead_cost_cents: Decimal
    token_counts: dict[str, Any]
    subscription_id: UUID | None = None
    attribution_metadata: dict[str, Any] = field(default_factory=dict)
    correction_of: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_cost_cents(self) -> Decimal:
        return (
            self.model_cost_cents
            + self.compute_cost_cents
            + self.storage_cost_cents
            + self.overhead_cost_cents
        )


class AttributionRepository:
    def __init__(self) -> None:
        self.rows: list[AttributionRow] = []

    async def get_attribution_by_execution(self, execution_id: UUID) -> AttributionRow | None:
        return next(
            (
                row
                for row in self.rows
                if row.execution_id == execution_id and row.correction_of is None
            ),
            None,
        )

    async def insert_attribution(self, **kwargs: Any) -> AttributionRow:
        kwargs["attribution_metadata"] = kwargs.pop("metadata", {})
        row = AttributionRow(**kwargs)
        self.rows.append(row)
        return row

    async def insert_attribution_correction(
        self,
        original_id: UUID,
        **kwargs: Any,
    ) -> AttributionRow:
        original = next(row for row in self.rows if row.id == original_id)
        row = AttributionRow(
            execution_id=original.execution_id,
            step_id=original.step_id,
            workspace_id=original.workspace_id,
            agent_id=original.agent_id,
            user_id=original.user_id,
            origin=original.origin,
            model_id=original.model_id,
            currency=original.currency,
            model_cost_cents=kwargs.get("model_cost_cents", Decimal("0")),
            compute_cost_cents=kwargs.get("compute_cost_cents", Decimal("0")),
            storage_cost_cents=kwargs.get("storage_cost_cents", Decimal("0")),
            overhead_cost_cents=kwargs.get("overhead_cost_cents", Decimal("0")),
            token_counts={},
            subscription_id=original.subscription_id,
            attribution_metadata=kwargs.get("metadata") or {},
            correction_of=original.id,
        )
        self.rows.append(row)
        return row

    async def list_execution_attributions(self, execution_id: UUID) -> list[AttributionRow]:
        return [row for row in self.rows if row.execution_id == execution_id]

    async def aggregate_attributions(
        self,
        workspace_id: UUID,
        group_by: list[str],
        since: datetime,
        until: datetime,
    ) -> list[dict[str, Any]]:
        del group_by, since, until
        rows = [row for row in self.rows if row.workspace_id == workspace_id]
        return [
            {
                "workspace_id": workspace_id,
                "model_cost_cents": sum((row.model_cost_cents for row in rows), Decimal("0")),
                "compute_cost_cents": sum((row.compute_cost_cents for row in rows), Decimal("0")),
                "storage_cost_cents": sum((row.storage_cost_cents for row in rows), Decimal("0")),
                "overhead_cost_cents": sum((row.overhead_cost_cents for row in rows), Decimal("0")),
                "total_cost_cents": sum((row.total_cost_cents for row in rows), Decimal("0")),
            }
        ]

    async def list_workspace_ids_with_costs(self) -> list[UUID]:
        return sorted({row.workspace_id for row in self.rows}, key=str)


class ClickHouseSink:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def enqueue_cost_event(self, row: dict[str, Any]) -> None:
        self.rows.append(row)

    async def flush(self) -> None:
        return None


class RecordingProducer:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.events.append(kwargs)
