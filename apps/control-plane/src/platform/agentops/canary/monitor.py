from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from platform.agentops.canary.manager import CanaryManager
from platform.agentops.models import CanaryDeployment
from platform.agentops.repository import AgentOpsRepository
from typing import Any


class CanaryMonitor:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        manager: CanaryManager,
        clickhouse_client: Any | None,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.manager = manager
        self.clickhouse_client = clickhouse_client
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    async def monitor_active_canaries_task(self) -> None:
        active_deployments = await self.repository.list_active_canaries()
        for deployment in active_deployments:
            await self._evaluate(deployment)

    async def _evaluate(self, deployment: CanaryDeployment) -> None:
        canary_metrics = await self._fetch_metrics(deployment.canary_revision_id)
        production_metrics = await self._fetch_metrics(deployment.production_revision_id)
        breaches = self._detect_breaches(deployment, canary_metrics, production_metrics)
        deployment.latest_metrics_snapshot = {
            "observed_at": self._now().isoformat(),
            "canary": canary_metrics,
            "production": production_metrics,
            "breaches": breaches,
        }
        await self.repository.update_canary(deployment)
        if breaches:
            await self.manager.rollback(
                deployment.id,
                reason=f"auto:{breaches[0]}",
                manual=False,
            )
            return
        if deployment.observation_ends_at <= self._now():
            await self.manager.promote(deployment.id, manual=False)

    async def _fetch_metrics(self, revision_id: Any) -> dict[str, float]:
        if self.clickhouse_client is None:
            return {}
        rows = await self.clickhouse_client.execute_query(
            """
            SELECT
              avg(quality_score) AS quality_score,
              avg(latency_p95_ms) AS latency_p95_ms,
              avg(error_rate) AS error_rate,
              avg(cost_per_execution) AS cost_per_execution
            FROM agentops_behavioral_versions
            WHERE revision_id = {revision_id:String}
              AND observed_at >= {window_start:DateTime}
            """,
            params={
                "revision_id": str(revision_id),
                "window_start": self._window_start(),
            },
        )
        if not rows:
            return {}
        row = rows[0]
        return {
            key: float(row[key])
            for key in (
                "quality_score",
                "latency_p95_ms",
                "error_rate",
                "cost_per_execution",
            )
            if row.get(key) is not None
        }

    def _detect_breaches(
        self,
        deployment: CanaryDeployment,
        canary_metrics: dict[str, float],
        production_metrics: dict[str, float],
    ) -> list[str]:
        if not canary_metrics or not production_metrics:
            return []
        breaches: list[str] = []
        if self._pct_drop(
            production_metrics.get("quality_score"),
            canary_metrics.get("quality_score"),
        ) > deployment.quality_tolerance_pct:
            breaches.append("quality_score")
        if self._pct_increase(
            production_metrics.get("latency_p95_ms"),
            canary_metrics.get("latency_p95_ms"),
        ) > deployment.latency_tolerance_pct:
            breaches.append("latency_p95_ms")
        if self._pct_increase(
            production_metrics.get("error_rate"),
            canary_metrics.get("error_rate"),
        ) > deployment.error_rate_tolerance_pct:
            breaches.append("error_rate")
        if self._pct_increase(
            production_metrics.get("cost_per_execution"),
            canary_metrics.get("cost_per_execution"),
        ) > deployment.cost_tolerance_pct:
            breaches.append("cost_per_execution")
        return breaches

    @staticmethod
    def _pct_drop(baseline: float | None, observed: float | None) -> float:
        if baseline is None or baseline == 0 or observed is None:
            return 0.0
        return max(0.0, ((baseline - observed) / baseline) * 100)

    @staticmethod
    def _pct_increase(baseline: float | None, observed: float | None) -> float:
        if baseline is None or baseline == 0 or observed is None:
            return 0.0
        return max(0.0, ((observed - baseline) / baseline) * 100)

    def _now(self) -> datetime:
        return self._now_factory()

    def _window_start(self) -> datetime:
        return self._now() - timedelta(hours=24)
