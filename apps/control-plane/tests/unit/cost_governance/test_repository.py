from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.cost_governance.models import (
    BudgetAlert,
    CostAnomaly,
    CostAttribution,
    CostForecast,
    OverrideRecord,
    WorkspaceBudget,
)
from platform.cost_governance.repository import CostGovernanceRepository, _group_columns
from typing import Any
from uuid import UUID, uuid4

import pytest


class ScalarRows:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


class Result:
    def __init__(
        self,
        *,
        scalar: Any = None,
        scalar_rows: list[Any] | None = None,
        rows: list[Any] | None = None,
    ) -> None:
        self.scalar = scalar
        self.scalar_rows = scalar_rows or []
        self.rows = rows or []

    def scalar_one(self) -> Any:
        return self.scalar

    def scalar_one_or_none(self) -> Any | None:
        return self.scalar

    def scalars(self) -> ScalarRows:
        return ScalarRows(self.scalar_rows)

    def all(self) -> list[Any]:
        return self.rows


class Row:
    def __init__(self, **mapping: Any) -> None:
        self._mapping = mapping


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.flushed = 0
        self.execute_results: list[Result] = []
        self.scalar_value: Any = None
        self.objects: dict[tuple[type[Any], UUID], Any] = {}

    def add(self, row: Any) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flushed += 1

    async def delete(self, row: Any) -> None:
        self.deleted.append(row)

    async def get(self, model: type[Any], key: UUID) -> Any | None:
        return self.objects.get((model, key))

    async def execute(self, statement: Any) -> Result:
        del statement
        if self.execute_results:
            return self.execute_results.pop(0)
        return Result()

    async def scalar(self, statement: Any) -> Any:
        del statement
        return self.scalar_value


def _attribution(
    *,
    row_id: UUID | None = None,
    execution_id: UUID | None = None,
    correction_of: UUID | None = None,
) -> CostAttribution:
    row = CostAttribution(
        execution_id=execution_id or uuid4(),
        step_id="step-1",
        workspace_id=uuid4(),
        agent_id=uuid4(),
        user_id=uuid4(),
        origin="user_trigger",
        model_id="gpt-test",
        currency="USD",
        model_cost_cents=Decimal("10"),
        compute_cost_cents=Decimal("1"),
        storage_cost_cents=Decimal("2"),
        overhead_cost_cents=Decimal("3"),
        token_counts={"tokens_in": 10, "tokens_out": 20},
        attribution_metadata={"source": "test"},
        correction_of=correction_of,
    )
    row.id = row_id or uuid4()
    row.created_at = datetime.now(UTC)
    row.total_cost_cents = Decimal("16")
    return row


def _budget(workspace_id: UUID | None = None) -> WorkspaceBudget:
    row = WorkspaceBudget(
        workspace_id=workspace_id or uuid4(),
        period_type="monthly",
        budget_cents=100,
        soft_alert_thresholds=[50, 80, 100],
        hard_cap_enabled=True,
        admin_override_enabled=True,
        currency="USD",
    )
    row.id = uuid4()
    return row


def _anomaly(workspace_id: UUID | None = None) -> CostAnomaly:
    now = datetime.now(UTC)
    row = CostAnomaly(
        workspace_id=workspace_id or uuid4(),
        anomaly_type="sudden_spike",
        severity="high",
        state="open",
        baseline_cents=Decimal("10"),
        observed_cents=Decimal("80"),
        period_start=now - timedelta(hours=1),
        period_end=now,
        summary="Spike",
        correlation_fingerprint="fingerprint",
    )
    row.id = uuid4()
    row.detected_at = now
    return row


@pytest.mark.asyncio
async def test_repository_inserts_attributions_and_corrections() -> None:
    session = FakeSession()
    repository = CostGovernanceRepository(session)  # type: ignore[arg-type]
    execution_id = uuid4()

    created = await repository.insert_attribution(
        execution_id=execution_id,
        step_id="step-1",
        workspace_id=uuid4(),
        agent_id=None,
        user_id=None,
        origin="system_trigger",
        model_id=None,
        currency="USD",
        model_cost_cents=Decimal("1"),
        compute_cost_cents=Decimal("2"),
        storage_cost_cents=Decimal("3"),
        overhead_cost_cents=Decimal("4"),
        token_counts={},
    )
    session.objects[(CostAttribution, created.id)] = created

    correction = await repository.insert_attribution_correction(
        created.id,
        compute_cost_cents=Decimal("-1"),
        metadata={"reason": "refund"},
    )

    assert session.added == [created, correction]
    assert correction.correction_of == created.id
    with pytest.raises(LookupError):
        await repository.insert_attribution_correction(uuid4())


@pytest.mark.asyncio
async def test_repository_query_methods_return_scalar_and_row_results() -> None:
    session = FakeSession()
    repository = CostGovernanceRepository(session)  # type: ignore[arg-type]
    execution_id = uuid4()
    workspace_id = uuid4()
    attribution = _attribution(execution_id=execution_id)
    budget = _budget(workspace_id)
    alert = BudgetAlert(
        budget_id=budget.id,
        workspace_id=workspace_id,
        threshold_percentage=80,
        period_start=datetime.now(UTC),
        period_end=datetime.now(UTC) + timedelta(days=1),
        spend_cents=Decimal("80"),
    )
    alert.id = uuid4()
    forecast = CostForecast(
        workspace_id=workspace_id,
        period_start=datetime.now(UTC),
        period_end=datetime.now(UTC) + timedelta(days=30),
        forecast_cents=Decimal("100"),
        confidence_interval={"status": "ok"},
        currency="USD",
    )
    forecast.id = uuid4()
    forecast.computed_at = datetime.now(UTC)

    session.execute_results.extend(
        [
            Result(scalar=attribution),
            Result(scalar_rows=[attribution]),
            Result(scalar_rows=[attribution]),
            Result(scalar_rows=[attribution]),
            Result(rows=[Row(workspace_id=workspace_id, total_cost_cents=Decimal("16"))]),
            Result(scalar=budget),
            Result(scalar_rows=[budget]),
            Result(scalar=budget),
            Result(scalar=alert),
            Result(scalar_rows=[alert]),
            Result(scalar_rows=[]),
            Result(scalar=forecast),
        ]
    )

    since = datetime.now(UTC) - timedelta(days=1)
    until = datetime.now(UTC)
    assert await repository.get_attribution_by_execution(execution_id) is attribution
    assert await repository.list_execution_attributions(execution_id) == [attribution]
    assert await repository.get_workspace_attributions(
        workspace_id,
        since,
        until,
        cursor=until,
        limit=10,
        agent_id=uuid4(),
        user_id=uuid4(),
    ) == [attribution]
    assert await repository.get_workspace_attributions(
        workspace_id,
        None,
        None,
        cursor=None,
        limit=10,
    ) == [attribution]
    assert await repository.aggregate_attributions(workspace_id, ["workspace"], since, until) == [
        {"workspace_id": workspace_id, "total_cost_cents": Decimal("16")}
    ]
    assert await repository.get_active_budget(workspace_id, "monthly") is budget
    assert await repository.list_budgets(workspace_id) == [budget]
    assert await repository.upsert_budget(
        workspace_id=workspace_id,
        period_type="monthly",
        budget_cents=100,
        soft_alert_thresholds=[50],
        hard_cap_enabled=True,
        admin_override_enabled=True,
        currency="USD",
        actor_id=uuid4(),
    ) is budget
    assert await repository.record_alert(
        budget.id,
        workspace_id,
        80,
        since,
        until,
        Decimal("80"),
    ) is alert
    assert await repository.list_alerts(workspace_id, cursor=until) == [alert]
    assert await repository.list_alerts(workspace_id) == []
    assert await repository.get_latest_forecast(workspace_id) is forecast


@pytest.mark.asyncio
async def test_repository_mutates_budget_forecast_anomaly_override_state() -> None:
    session = FakeSession()
    repository = CostGovernanceRepository(session)  # type: ignore[arg-type]
    workspace_id = uuid4()
    budget = _budget(workspace_id)
    anomaly = _anomaly(workspace_id)
    override = OverrideRecord(
        workspace_id=workspace_id,
        issued_by=uuid4(),
        reason="incident",
        token_hash="hash",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    override.id = uuid4()
    session.objects[(WorkspaceBudget, budget.id)] = budget
    session.objects[(CostAnomaly, anomaly.id)] = anomaly
    session.execute_results.extend(
        [
            Result(scalar=anomaly),
            Result(scalar_rows=[anomaly]),
            Result(scalar_rows=[]),
            Result(scalar=override),
            Result(scalar=None),
            Result(scalar_rows=[workspace_id]),
        ]
    )
    session.scalar_value = Decimal("123.45")

    assert await repository.delete_budget(budget.id) is True
    assert await repository.delete_budget(uuid4()) is False
    forecast = await repository.insert_forecast(
        workspace_id=workspace_id,
        period_start=datetime.now(UTC),
        period_end=datetime.now(UTC) + timedelta(days=30),
        forecast_cents=None,
        confidence_interval={"status": "insufficient_history"},
        currency="USD",
    )
    inserted_anomaly = await repository.insert_anomaly(
        workspace_id=workspace_id,
        anomaly_type="sudden_spike",
        severity="high",
        baseline_cents=Decimal("10"),
        observed_cents=Decimal("50"),
        period_start=datetime.now(UTC) - timedelta(hours=1),
        period_end=datetime.now(UTC),
        summary="Spike",
        correlation_fingerprint="fingerprint-2",
    )
    assert forecast in session.added
    assert inserted_anomaly in session.added
    assert await repository.find_open_anomaly_by_fingerprint(workspace_id, "fingerprint") is anomaly
    assert await repository.get_anomaly(anomaly.id) is anomaly
    assert await repository.acknowledge_anomaly(anomaly.id, uuid4()) is anomaly
    assert anomaly.state == "acknowledged"
    assert await repository.acknowledge_anomaly(uuid4(), uuid4()) is None
    assert await repository.resolve_anomaly(anomaly.id) is anomaly
    assert anomaly.state == "resolved"
    assert await repository.resolve_anomaly(uuid4()) is None
    assert await repository.list_anomalies(workspace_id, "open", 10, datetime.now(UTC)) == [
        anomaly
    ]
    assert await repository.list_anomalies(workspace_id, None, 10, None) == []
    record = await repository.create_override_record(
        workspace_id=workspace_id,
        issued_by=uuid4(),
        reason="incident",
        token_hash="new-hash",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    assert record in session.added
    assert await repository.mark_override_redeemed("hash", uuid4()) is override
    assert override.redeemed_at is not None
    assert await repository.mark_override_redeemed("missing", uuid4()) is None
    period_spend = await repository.period_spend(
        workspace_id,
        datetime.now(UTC),
        datetime.now(UTC),
    )
    assert period_spend == Decimal("123.45")
    assert await repository.list_workspace_ids_with_costs() == [workspace_id]
    assert _group_columns(["unknown"])
