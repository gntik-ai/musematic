from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from platform.common.config import PlatformSettings
from platform.cost_governance.services.attribution_service import AttributionService
from typing import Any
from uuid import UUID, uuid4

import pytest


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


class FakeRepository:
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
            attribution_metadata=kwargs.get("metadata") or {},
            correction_of=original.id,
        )
        self.rows.append(row)
        return row

    async def list_execution_attributions(self, execution_id: UUID) -> list[AttributionRow]:
        return [row for row in self.rows if row.execution_id == execution_id]


def _service(repository: FakeRepository) -> AttributionService:
    settings = PlatformSettings(
        cost_governance={
            "compute_cost_per_ms_cents": 0.01,
            "storage_cost_per_byte_cents": 0.001,
            "overhead_cost_per_execution_cents": 0.5,
        }
    )
    return AttributionService(
        repository=repository,  # type: ignore[arg-type]
        settings=settings,
        fail_open=False,
    )


@pytest.mark.asyncio
async def test_record_step_cost_calculates_model_compute_storage_and_overhead() -> None:
    repository = FakeRepository()
    service = _service(repository)
    execution_id = uuid4()
    workspace_id = uuid4()
    user_id = uuid4()

    row = await service.record_step_cost(
        execution_id=execution_id,
        step_id="step-1",
        workspace_id=workspace_id,
        agent_id=uuid4(),
        user_id=user_id,
        payload={
            "model_id": "gpt-test",
            "tokens_in": 1000,
            "tokens_out": 500,
            "input_cost_per_1k_tokens": "2",
            "output_cost_per_1k_tokens": "4",
            "duration_ms": 100,
            "bytes_written": 10,
        },
    )

    assert row is not None
    assert row.model_cost_cents == Decimal("4.0000")
    assert row.compute_cost_cents == Decimal("1.0000")
    assert row.storage_cost_cents == Decimal("0.0100")
    assert row.overhead_cost_cents == Decimal("0.5000")
    assert row.total_cost_cents == Decimal("5.5100")
    assert row.user_id == user_id
    assert row.origin == "user_trigger"


@pytest.mark.asyncio
async def test_system_initiated_cost_has_no_user_and_system_origin() -> None:
    repository = FakeRepository()
    service = _service(repository)

    row = await service.record_step_cost(
        execution_id=uuid4(),
        step_id=None,
        workspace_id=uuid4(),
        agent_id=None,
        user_id=None,
        payload={"model_id": "gpt-test", "tokens_in": 1, "input_cost_per_1k_tokens": "1"},
    )

    assert row is not None
    assert row.user_id is None
    assert row.origin == "system_trigger"


@pytest.mark.asyncio
async def test_late_arriving_cost_appends_correction_row() -> None:
    repository = FakeRepository()
    service = _service(repository)
    execution_id = uuid4()
    workspace_id = uuid4()

    original = await service.record_step_cost(
        execution_id=execution_id,
        step_id="step-1",
        workspace_id=workspace_id,
        agent_id=None,
        user_id=uuid4(),
        payload={"model_cost_cents": "3.25"},
    )
    correction = await service.record_step_cost(
        execution_id=execution_id,
        step_id="step-1",
        workspace_id=workspace_id,
        agent_id=None,
        user_id=uuid4(),
        payload={"compute_cost_cents": "1.75"},
    )

    result = await service.get_execution_cost(execution_id)

    assert original is not None
    assert correction is not None
    assert correction.correction_of == original.id
    assert result is not None
    assert result["totals"]["total_cost_cents"] == Decimal("5.5000")
    assert len(repository.rows) == 2
