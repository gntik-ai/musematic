from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.common.audit_hook import audit_chain_hook
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.cost_governance.clickhouse_repository import ClickHouseCostRepository
from platform.cost_governance.events import (
    CostAnomalyDetectedPayload,
    CostGovernanceEventType,
    publish_cost_governance_event,
)
from platform.cost_governance.exceptions import InsufficientHistoryError
from platform.cost_governance.repository import CostGovernanceRepository
from platform.cost_governance.schemas import CostAnomalyResponse
from statistics import median
from typing import Any
from uuid import UUID, uuid4


class AnomalyService:
    def __init__(
        self,
        *,
        repository: CostGovernanceRepository,
        clickhouse_repository: ClickHouseCostRepository | None,
        kafka_producer: EventProducer | None = None,
        audit_chain_service: Any | None = None,
        alert_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.clickhouse_repository = clickhouse_repository
        self.kafka_producer = kafka_producer
        self.audit_chain_service = audit_chain_service
        self.alert_service = alert_service

    async def detect(self, workspace_id: UUID) -> CostAnomalyResponse | None:
        baseline = await self._baseline(workspace_id)
        if len(baseline) < 4:
            raise InsufficientHistoryError()
        values = [Decimal(str(row["total_cost_cents"])) for row in baseline]
        observed = values[-1]
        baseline_value = Decimal(str(median(values[:-1])))
        if baseline_value <= 0 or observed <= baseline_value * Decimal("2.0"):
            return None
        severity = _severity(observed / baseline_value)
        period_end = datetime.now(UTC)
        period_start = period_end - timedelta(hours=1)
        fingerprint = _fingerprint(workspace_id, period_start, "sudden_spike", severity)
        existing = await self.repository.find_open_anomaly_by_fingerprint(workspace_id, fingerprint)
        if existing is not None:
            return CostAnomalyResponse.model_validate(existing)
        anomaly = await self.repository.insert_anomaly(
            workspace_id=workspace_id,
            anomaly_type="sudden_spike",
            severity=severity,
            baseline_cents=baseline_value,
            observed_cents=observed,
            period_start=period_start,
            period_end=period_end,
            summary=f"Observed spend {observed} cents exceeded baseline {baseline_value} cents.",
            correlation_fingerprint=fingerprint,
        )
        await publish_cost_governance_event(
            self.kafka_producer,
            CostGovernanceEventType.anomaly_detected,
            CostAnomalyDetectedPayload(
                anomaly_id=anomaly.id,
                workspace_id=workspace_id,
                anomaly_type=anomaly.anomaly_type,
                severity=anomaly.severity,
                baseline_cents=anomaly.baseline_cents,
                observed_cents=anomaly.observed_cents,
                detected_at=anomaly.detected_at,
            ),
            CorrelationContext(workspace_id=workspace_id, correlation_id=uuid4()),
        )
        return CostAnomalyResponse.model_validate(anomaly)

    async def acknowledge(
        self,
        anomaly_id: UUID,
        by_user_id: UUID,
        *,
        notes: str | None = None,
    ) -> CostAnomalyResponse | None:
        anomaly = await self.repository.acknowledge_anomaly(anomaly_id, by_user_id)
        if anomaly is not None:
            await self._audit(
                "cost.anomaly.acknowledged",
                anomaly_id,
                {"anomaly_id": anomaly_id, "by_user_id": by_user_id, "notes": notes},
            )
        return None if anomaly is None else CostAnomalyResponse.model_validate(anomaly)

    async def resolve(self, anomaly_id: UUID) -> CostAnomalyResponse | None:
        anomaly = await self.repository.resolve_anomaly(anomaly_id)
        if anomaly is not None:
            await self._audit("cost.anomaly.resolved", anomaly_id, {"anomaly_id": anomaly_id})
        return None if anomaly is None else CostAnomalyResponse.model_validate(anomaly)

    async def list_anomalies(
        self,
        workspace_id: UUID,
        state: str | None,
        limit: int,
        cursor: datetime | None,
    ) -> list[CostAnomalyResponse]:
        rows = await self.repository.list_anomalies(workspace_id, state, limit, cursor)
        return [CostAnomalyResponse.model_validate(row) for row in rows]

    async def _baseline(self, workspace_id: UUID) -> list[dict[str, Any]]:
        if self.clickhouse_repository is not None:
            return await self.clickhouse_repository.query_cost_baseline(workspace_id, 24)
        end = datetime.now(UTC)
        start = end - timedelta(hours=24)
        return await self.repository.aggregate_attributions(workspace_id, ["day"], start, end)

    async def _audit(self, event: str, event_id: UUID, payload: dict[str, Any]) -> None:
        if self.audit_chain_service is None:
            return
        await audit_chain_hook(
            self.audit_chain_service,
            event_id,
            "cost_governance",
            {"event": event, **payload},
        )


def _severity(ratio: Decimal) -> str:
    if ratio >= Decimal("10"):
        return "critical"
    if ratio >= Decimal("5"):
        return "high"
    if ratio >= Decimal("3"):
        return "medium"
    return "low"


def _fingerprint(
    workspace_id: UUID,
    period_start: datetime,
    anomaly_type: str,
    severity: str,
) -> str:
    payload = f"{workspace_id}:{period_start.isoformat()}:{anomaly_type}:{severity}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

