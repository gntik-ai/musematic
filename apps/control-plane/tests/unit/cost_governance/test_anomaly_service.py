from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from platform.cost_governance.services.anomaly_service import AnomalyService
from typing import Any
from uuid import UUID, uuid4

import pytest


@dataclass
class AnomalyRow:
    workspace_id: UUID
    anomaly_type: str
    severity: str
    baseline_cents: Decimal
    observed_cents: Decimal
    period_start: datetime
    period_end: datetime
    summary: str
    correlation_fingerprint: str
    id: UUID = field(default_factory=uuid4)
    state: str = "open"
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    acknowledged_at: datetime | None = None
    acknowledged_by: UUID | None = None
    resolved_at: datetime | None = None


class Repo:
    def __init__(self) -> None:
        self.rows: list[AnomalyRow] = []

    async def find_open_anomaly_by_fingerprint(
        self,
        workspace_id: UUID,
        fingerprint: str,
    ) -> AnomalyRow | None:
        return next(
            (
                row
                for row in self.rows
                if row.workspace_id == workspace_id
                and row.correlation_fingerprint == fingerprint
                and row.state == "open"
            ),
            None,
        )

    async def insert_anomaly(self, **kwargs: Any) -> AnomalyRow:
        row = AnomalyRow(**kwargs)
        self.rows.append(row)
        return row

    async def acknowledge_anomaly(self, anomaly_id: UUID, by_user_id: UUID) -> AnomalyRow | None:
        for row in self.rows:
            if row.id == anomaly_id:
                row.state = "acknowledged"
                row.acknowledged_at = datetime.now(UTC)
                row.acknowledged_by = by_user_id
                return row
        return None

    async def resolve_anomaly(self, anomaly_id: UUID) -> AnomalyRow | None:
        for row in self.rows:
            if row.id == anomaly_id:
                row.state = "resolved"
                row.resolved_at = datetime.now(UTC)
                return row
        return None

    async def list_anomalies(
        self,
        workspace_id: UUID,
        state: str | None,
        limit: int,
        cursor: datetime | None,
    ) -> list[AnomalyRow]:
        del limit, cursor
        return [
            row
            for row in self.rows
            if row.workspace_id == workspace_id and (state is None or row.state == state)
        ]

    async def aggregate_attributions(
        self,
        workspace_id: UUID,
        group_by: list[str],
        since: datetime,
        until: datetime,
    ) -> list[dict[str, Decimal]]:
        del workspace_id, group_by, since, until
        return [{"total_cost_cents": Decimal("0")} for _ in range(4)]


class History:
    def __init__(self, values: list[Decimal]) -> None:
        self.values = values

    async def query_cost_baseline(
        self,
        workspace_id: UUID,
        lookback_periods: int,
    ) -> list[dict[str, Decimal]]:
        del workspace_id, lookback_periods
        return [{"total_cost_cents": value} for value in self.values]


class AlertRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, UUID]] = []

    async def process_state_change(self, payload: Any, workspace_id: UUID) -> list[Any]:
        self.calls.append((payload, workspace_id))
        return []


class AuditRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    async def append(self, *payload: Any) -> None:
        self.events.append(payload)


@pytest.mark.asyncio
async def test_sudden_spike_detects_and_suppresses_duplicate() -> None:
    workspace_id = uuid4()
    repo = Repo()
    alerts = AlertRecorder()
    service = AnomalyService(
        repository=repo,  # type: ignore[arg-type]
        clickhouse_repository=History([Decimal("10"), Decimal("11"), Decimal("10"), Decimal("55")]),  # type: ignore[arg-type]
        alert_service=alerts,
    )

    first = await service.detect(workspace_id)
    second = await service.detect(workspace_id)

    assert first is not None
    assert first.anomaly_type == "sudden_spike"
    assert first.severity == "high"
    assert second is not None
    assert second.id == first.id
    assert len(repo.rows) == 1
    assert len(alerts.calls) == 1


@pytest.mark.asyncio
async def test_sustained_deviation_and_lifecycle_allows_refire_after_resolution() -> None:
    workspace_id = uuid4()
    repo = Repo()
    service = AnomalyService(
        repository=repo,  # type: ignore[arg-type]
        clickhouse_repository=History(
            [Decimal("10"), Decimal("10"), Decimal("40"), Decimal("42"), Decimal("44")]
        ),  # type: ignore[arg-type]
    )

    detected = await service.detect(workspace_id)
    assert detected is not None
    assert detected.anomaly_type == "sustained_deviation"

    acknowledged = await service.acknowledge(detected.id, uuid4())
    assert acknowledged is not None
    assert acknowledged.state == "acknowledged"
    resolved = await service.resolve(detected.id)
    assert resolved is not None
    assert resolved.state == "resolved"

    refired = await service.detect(workspace_id)
    assert refired is not None
    assert refired.id != detected.id


@pytest.mark.asyncio
async def test_brand_new_workspace_with_zero_history_is_skipped() -> None:
    response = await AnomalyService(
        repository=Repo(),  # type: ignore[arg-type]
        clickhouse_repository=History([]),  # type: ignore[arg-type]
    ).detect(uuid4())

    assert response is None


@pytest.mark.asyncio
async def test_anomaly_fallback_baseline_lifecycle_none_and_audit_paths() -> None:
    workspace_id = uuid4()
    repo = Repo()
    audit = AuditRecorder()
    service = AnomalyService(
        repository=repo,  # type: ignore[arg-type]
        clickhouse_repository=None,
        audit_chain_service=audit,
        alert_service=object(),
    )

    assert await service.detect(workspace_id) is None
    assert await service.acknowledge(uuid4(), uuid4()) is None
    assert await service.resolve(uuid4()) is None
    assert await service.list_anomalies(workspace_id, None, 10, None) == []

    detected = await AnomalyService(
        repository=repo,  # type: ignore[arg-type]
        clickhouse_repository=History([Decimal("10"), Decimal("10"), Decimal("10"), Decimal("35")]),  # type: ignore[arg-type]
        audit_chain_service=audit,
    ).detect(workspace_id)
    assert detected is not None
    await service.acknowledge(detected.id, uuid4(), notes="checked")
    await service.resolve(detected.id)

    assert len(audit.events) == 2
