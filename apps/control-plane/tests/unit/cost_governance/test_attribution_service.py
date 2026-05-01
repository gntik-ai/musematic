from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from platform.common.config import PlatformSettings
from platform.cost_governance.services.attribution_service import AttributionService
from types import SimpleNamespace
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
            subscription_id=original.subscription_id,
            attribution_metadata=kwargs.get("metadata") or {},
            correction_of=original.id,
        )
        self.rows.append(row)
        return row

    async def list_execution_attributions(self, execution_id: UUID) -> list[AttributionRow]:
        return [row for row in self.rows if row.execution_id == execution_id]


class FailingRepository(FakeRepository):
    async def get_attribution_by_execution(self, execution_id: UUID) -> AttributionRow | None:
        del execution_id
        raise RuntimeError("storage unavailable")


class RecordingBudgetService:
    def __init__(self) -> None:
        self.invalidated: list[tuple[UUID, str]] = []

    async def invalidate_hot_counter(self, workspace_id: UUID, period_type: str) -> None:
        self.invalidated.append((workspace_id, period_type))


class RecordingClickHouse:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def enqueue_cost_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class CatalogRepository:
    async def get_entry_by_provider_model(self, provider: str, model_id: str) -> object:
        return SimpleNamespace(
            provider=provider,
            model_id=model_id,
            input_cost_per_1k_tokens=Decimal("1"),
            output_cost_per_1k_tokens=Decimal("2"),
        )


class CatalogService:
    repository = CatalogRepository()


class GetterCatalogService:
    async def get_pricing(self, model_id: str) -> dict[str, Decimal]:
        assert model_id == "gpt-priced"
        return {
            "input_cost_per_1k_tokens": Decimal("3"),
            "output_cost_per_1k_tokens": Decimal("4"),
        }


class EmptyCatalogRepository:
    async def get_entry_by_provider_model(self, provider: str, model_id: str) -> None:
        del provider, model_id
        return None


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


@pytest.mark.asyncio
async def test_partial_failed_step_keeps_incurred_cost() -> None:
    repository = FakeRepository()
    service = _service(repository)

    row = await service.record_step_cost(
        execution_id=uuid4(),
        step_id="failed-step",
        workspace_id=uuid4(),
        agent_id=uuid4(),
        user_id=uuid4(),
        payload={
            "status": "failed",
            "tokens_in": 250,
            "tokens_out": 0,
            "input_cost_per_1k_tokens": "8",
            "duration_ms": 25,
        },
    )

    assert row is not None
    assert row.model_cost_cents == Decimal("2.0000")
    assert row.compute_cost_cents == Decimal("0.2500")
    assert row.total_cost_cents > Decimal("0")


@pytest.mark.asyncio
async def test_shared_infrastructure_allocation_creates_workspace_row() -> None:
    repository = FakeRepository()
    service = _service(repository)
    workspace_id = uuid4()

    row = await service.record_step_cost(
        execution_id=uuid4(),
        step_id="warm-pool",
        workspace_id=workspace_id,
        agent_id=None,
        user_id=None,
        payload={
            "origin": "shared_infra_allocation",
            "overhead_cost_cents": "7.25",
            "metadata": {"allocation_rule": "beneficiary_workspace"},
        },
    )

    assert row is not None
    assert row.workspace_id == workspace_id
    assert row.overhead_cost_cents == Decimal("7.2500")
    assert len(repository.rows) == 1


@pytest.mark.asyncio
async def test_fail_open_returns_none_and_fail_closed_raises() -> None:
    kwargs = {
        "execution_id": uuid4(),
        "step_id": "step",
        "workspace_id": uuid4(),
        "agent_id": None,
        "user_id": uuid4(),
        "payload": {},
    }
    open_service = AttributionService(
        repository=FailingRepository(),  # type: ignore[arg-type]
        settings=PlatformSettings(),
        fail_open=True,
    )
    closed_service = AttributionService(
        repository=FailingRepository(),  # type: ignore[arg-type]
        settings=PlatformSettings(),
        fail_open=False,
    )

    assert await open_service.record_step_cost(**kwargs) is None
    with pytest.raises(RuntimeError):
        await closed_service.record_step_cost(**kwargs)


@pytest.mark.asyncio
async def test_catalog_repository_pricing_clickhouse_and_budget_invalidation() -> None:
    repository = FakeRepository()
    budget = RecordingBudgetService()
    clickhouse = RecordingClickHouse()
    service = AttributionService(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(cost_governance={"overhead_cost_per_execution_cents": 0}),
        clickhouse_repository=clickhouse,  # type: ignore[arg-type]
        model_catalog_service=CatalogService(),
        budget_service=budget,
        fail_open=False,
    )
    workspace_id = uuid4()

    row = await service.record_step_cost(
        execution_id=uuid4(),
        step_id="step",
        workspace_id=workspace_id,
        agent_id=None,
        user_id=uuid4(),
        payload={
            "provider": "openai",
            "model": "gpt-test",
            "input_tokens": 1000,
            "output_tokens": 1000,
        },
    )

    assert row is not None
    assert row.model_cost_cents == Decimal("3.0000")
    assert budget.invalidated == [(workspace_id, "monthly")]
    assert clickhouse.events[0]["workspace_id"] == workspace_id
    assert await service.get_execution_cost(uuid4()) is None


@pytest.mark.asyncio
async def test_record_correction_and_pricing_resolution_edges() -> None:
    repository = FakeRepository()
    clickhouse = RecordingClickHouse()
    service = AttributionService(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(cost_governance={"overhead_cost_per_execution_cents": 0}),
        clickhouse_repository=clickhouse,  # type: ignore[arg-type]
        model_catalog_service=GetterCatalogService(),
        budget_service=object(),
        fail_open=False,
    )
    original = await service.record_step_cost(
        execution_id=uuid4(),
        step_id="step",
        workspace_id=uuid4(),
        agent_id=None,
        user_id=uuid4(),
        payload={
            "model": "gpt-priced",
            "input_tokens": 1000,
            "output_tokens": 1000,
        },
    )

    assert original is not None
    assert original.model_cost_cents == Decimal("7.0000")
    correction = await service.record_correction(
        original.id,
        deltas={"model_cost_cents": "-1.25"},
    )
    assert correction.correction_of == original.id
    assert correction.model_cost_cents == Decimal("-1.25")
    assert len(clickhouse.events) == 2

    empty_catalog_service = AttributionService(
        repository=FakeRepository(),  # type: ignore[arg-type]
        settings=PlatformSettings(),
        model_catalog_service=SimpleNamespace(repository=EmptyCatalogRepository()),
        fail_open=False,
    )
    assert await empty_catalog_service._resolve_pricing("missing", "openai") == {}
    assert await empty_catalog_service._resolve_pricing("missing", None) == {}
