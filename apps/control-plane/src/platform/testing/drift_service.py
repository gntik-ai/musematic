from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import NotFoundError
from platform.common.tracing import traced_async
from platform.evaluation.repository import EvaluationRepository
from platform.testing.events import (
    TestingDriftDetectedPayload,
    TestingEventType,
    publish_testing_event,
)
from platform.testing.models import DriftAlert
from platform.testing.repository import TestingRepository
from platform.testing.schemas import DriftAlertListResponse, DriftAlertResponse
from typing import Any
from uuid import UUID, uuid4

_SCHEMA_PATH = Path(__file__).with_name("clickhouse_schema.sql")
_METRICS_TABLE = "testing_drift_metrics"


class DriftDetectionService:
    def __init__(
        self,
        *,
        repository: TestingRepository,
        evaluation_repository: EvaluationRepository,
        clickhouse_client: Any,
        settings: Any,
        producer: EventProducer | None = None,
    ) -> None:
        self.repository = repository
        self.evaluation_repository = evaluation_repository
        self.clickhouse_client = clickhouse_client
        self.settings = settings
        self.producer = producer

    @traced_async("testing.drift.ensure_schema")
    async def ensure_schema(self) -> None:
        sql = _SCHEMA_PATH.read_text(encoding="utf-8").strip()
        if not sql:
            return
        await self.clickhouse_client.execute_command(sql)

    @traced_async("testing.drift.record_eval_metric")
    async def record_eval_metric(
        self,
        *,
        run_id: UUID,
        agent_fqn: str,
        eval_set_id: UUID,
        score: float,
        workspace_id: UUID,
    ) -> None:
        await self.clickhouse_client.insert(
            _METRICS_TABLE,
            [
                {
                    "run_id": str(run_id),
                    "workspace_id": str(workspace_id),
                    "agent_fqn": agent_fqn,
                    "eval_set_id": str(eval_set_id),
                    "score": float(score),
                    "measured_at": datetime.now(UTC),
                }
            ],
            [
                "run_id",
                "workspace_id",
                "agent_fqn",
                "eval_set_id",
                "score",
                "measured_at",
            ],
        )

    @traced_async("testing.drift.should_suppress")
    async def should_suppress(self, agent_fqn: str) -> bool:
        active_runs = await self.evaluation_repository.list_active_robustness_runs_by_agent(
            agent_fqn
        )
        return bool(active_runs)

    @traced_async("testing.drift.detect_drift")
    async def detect_drift(
        self,
        agent_fqn: str,
        eval_set_id: UUID,
        workspace_id: UUID,
    ) -> DriftAlertResponse | None:
        if await self.should_suppress(agent_fqn):
            return None
        baseline_rows = await self.clickhouse_client.execute_query(
            f"""
            SELECT
                avg(score) AS baseline_value,
                stddevPop(score) AS stddev_value,
                max(measured_at) AS latest_measured_at
            FROM {_METRICS_TABLE}
            WHERE workspace_id = {{workspace_id:String}}
              AND agent_fqn = {{agent_fqn:String}}
              AND eval_set_id = {{eval_set_id:String}}
              AND measured_at >= now() - INTERVAL 30 DAY
            """,
            {
                "workspace_id": str(workspace_id),
                "agent_fqn": agent_fqn,
                "eval_set_id": str(eval_set_id),
            },
        )
        if not baseline_rows:
            return None
        baseline_row = baseline_rows[0]
        baseline_value = float(baseline_row.get("baseline_value") or 0.0)
        stddev_value = float(baseline_row.get("stddev_value") or 0.0)
        if stddev_value <= 0.0:
            return None
        latest_rows = await self.clickhouse_client.execute_query(
            f"""
            SELECT score, run_id
            FROM {_METRICS_TABLE}
            WHERE workspace_id = {{workspace_id:String}}
              AND agent_fqn = {{agent_fqn:String}}
              AND eval_set_id = {{eval_set_id:String}}
            ORDER BY measured_at DESC
            LIMIT 1
            """,
            {
                "workspace_id": str(workspace_id),
                "agent_fqn": agent_fqn,
                "eval_set_id": str(eval_set_id),
            },
        )
        if not latest_rows:
            return None
        latest_row = latest_rows[0]
        current_value = float(latest_row.get("score") or 0.0)
        threshold = float(
            getattr(self.settings.context_engineering, "drift_stddev_multiplier", 2.0)
        )
        deviation = baseline_value - current_value
        stddevs = deviation / stddev_value if stddev_value else 0.0
        if stddevs < threshold:
            return None
        alert = await self.repository.create_drift_alert(
            DriftAlert(
                workspace_id=workspace_id,
                agent_fqn=agent_fqn,
                eval_set_id=eval_set_id,
                metric_name="overall_score",
                baseline_value=baseline_value,
                current_value=current_value,
                deviation_magnitude=deviation,
                stddevs_from_baseline=stddevs,
                acknowledged=False,
            )
        )
        await self.repository.session.commit()
        await publish_testing_event(
            self.producer,
            TestingEventType.drift_detected,
            TestingDriftDetectedPayload(
                alert_id=alert.id,
                workspace_id=workspace_id,
                agent_fqn=agent_fqn,
                eval_set_id=eval_set_id,
                metric_name=alert.metric_name,
                stddevs_from_baseline=stddevs,
            ),
            CorrelationContext(correlation_id=uuid4(), workspace_id=workspace_id),
        )
        return DriftAlertResponse.model_validate(alert)

    @traced_async("testing.drift.list_alerts")
    async def list_alerts(
        self,
        *,
        workspace_id: UUID,
        agent_fqn: str | None,
        eval_set_id: UUID | None,
        acknowledged: bool | None,
        page: int,
        page_size: int,
    ) -> DriftAlertListResponse:
        items, total = await self.repository.list_drift_alerts(
            workspace_id,
            agent_fqn=agent_fqn,
            eval_set_id=eval_set_id,
            acknowledged=acknowledged,
            page=page,
            page_size=page_size,
        )
        return DriftAlertListResponse(
            items=[DriftAlertResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @traced_async("testing.drift.acknowledge_alert")
    async def acknowledge_alert(self, alert_id: UUID, actor_id: UUID) -> DriftAlertResponse:
        alert = await self.repository.get_drift_alert(alert_id)
        if alert is None:
            raise NotFoundError("DRIFT_ALERT_NOT_FOUND", "Drift alert not found")
        updated = await self.repository.acknowledge_drift_alert(
            alert,
            acknowledged_by=actor_id,
            acknowledged_at=datetime.now(UTC),
        )
        await self.repository.session.commit()
        return DriftAlertResponse.model_validate(updated)

    @traced_async("testing.drift.run_drift_scan_all")
    async def run_drift_scan_all(self) -> list[DriftAlertResponse]:
        rows = await self.clickhouse_client.execute_query(
            f"""
            SELECT DISTINCT workspace_id, agent_fqn, eval_set_id
            FROM {_METRICS_TABLE}
            WHERE measured_at >= now() - INTERVAL 30 DAY
            """
        )
        alerts: list[DriftAlertResponse] = []
        for row in rows:
            alert = await self.detect_drift(
                agent_fqn=str(row["agent_fqn"]),
                eval_set_id=UUID(str(row["eval_set_id"])),
                workspace_id=UUID(str(row["workspace_id"])),
            )
            if alert is not None:
                alerts.append(alert)
        return alerts
