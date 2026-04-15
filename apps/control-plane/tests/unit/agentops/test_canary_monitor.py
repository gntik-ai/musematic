from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.agentops.canary.monitor import CanaryMonitor
from platform.agentops.models import CanaryDeployment, CanaryDeploymentStatus
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


class _RepositoryStub:
    def __init__(self, deployment: CanaryDeployment) -> None:
        self.deployment = deployment
        self.updated: list[CanaryDeployment] = []

    async def list_active_canaries(self) -> list[CanaryDeployment]:
        return [self.deployment]

    async def update_canary(self, canary: CanaryDeployment) -> CanaryDeployment:
        self.updated.append(canary)
        return canary


class _ManagerStub:
    def __init__(self) -> None:
        self.promoted: list[tuple[Any, bool]] = []
        self.rolled_back: list[tuple[Any, str, bool]] = []

    async def promote(self, canary_id, *, manual: bool, reason: str | None = None, actor=None):
        del reason, actor
        self.promoted.append((canary_id, manual))

    async def rollback(self, canary_id, *, reason: str, manual: bool, actor=None):
        del actor
        self.rolled_back.append((canary_id, reason, manual))


class _MonitorWithMetrics(CanaryMonitor):
    def __init__(self, *, metrics_by_revision: dict[str, dict[str, float]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.metrics_by_revision = metrics_by_revision

    async def _fetch_metrics(self, revision_id: Any) -> dict[str, float]:
        return dict(self.metrics_by_revision[str(revision_id)])


def _deployment(*, observation_ends_at: datetime) -> CanaryDeployment:
    return CanaryDeployment(
        id=uuid4(),
        workspace_id=uuid4(),
        agent_fqn="finance:agent",
        production_revision_id=uuid4(),
        canary_revision_id=uuid4(),
        initiated_by=uuid4(),
        traffic_percentage=10,
        observation_window_hours=2.0,
        quality_tolerance_pct=5.0,
        latency_tolerance_pct=5.0,
        error_rate_tolerance_pct=5.0,
        cost_tolerance_pct=5.0,
        status=CanaryDeploymentStatus.active.value,
        started_at=observation_ends_at - timedelta(hours=2),
        observation_ends_at=observation_ends_at,
    )


@pytest.mark.asyncio
async def test_metric_fetch_below_tolerance_results_in_no_action() -> None:
    now = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
    deployment = _deployment(observation_ends_at=now + timedelta(hours=1))
    repository = _RepositoryStub(deployment)
    manager = _ManagerStub()
    monitor = _MonitorWithMetrics(
        repository=repository,  # type: ignore[arg-type]
        manager=manager,  # type: ignore[arg-type]
        clickhouse_client=None,
        now_factory=lambda: now,
        metrics_by_revision={
            str(deployment.production_revision_id): {
                "quality_score": 100.0,
                "latency_p95_ms": 100.0,
                "error_rate": 0.02,
                "cost_per_execution": 1.0,
            },
            str(deployment.canary_revision_id): {
                "quality_score": 96.0,
                "latency_p95_ms": 103.0,
                "error_rate": 0.0205,
                "cost_per_execution": 1.03,
            },
        },
    )

    await monitor.monitor_active_canaries_task()

    assert manager.promoted == []
    assert manager.rolled_back == []
    assert repository.updated[-1].latest_metrics_snapshot is not None


@pytest.mark.asyncio
async def test_metric_above_tolerance_triggers_rollback() -> None:
    now = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
    deployment = _deployment(observation_ends_at=now + timedelta(hours=1))
    manager = _ManagerStub()
    monitor = _MonitorWithMetrics(
        repository=_RepositoryStub(deployment),  # type: ignore[arg-type]
        manager=manager,  # type: ignore[arg-type]
        clickhouse_client=None,
        now_factory=lambda: now,
        metrics_by_revision={
            str(deployment.production_revision_id): {
                "quality_score": 100.0,
                "latency_p95_ms": 100.0,
                "error_rate": 0.02,
                "cost_per_execution": 1.0,
            },
            str(deployment.canary_revision_id): {
                "quality_score": 80.0,
                "latency_p95_ms": 100.0,
                "error_rate": 0.02,
                "cost_per_execution": 1.0,
            },
        },
    )

    await monitor.monitor_active_canaries_task()

    assert manager.rolled_back == [(deployment.id, "auto:quality_score", False)]
    assert manager.promoted == []


@pytest.mark.asyncio
async def test_observation_window_elapsed_with_healthy_metrics_triggers_promote() -> None:
    now = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
    deployment = _deployment(observation_ends_at=now - timedelta(minutes=1))
    manager = _ManagerStub()
    monitor = _MonitorWithMetrics(
        repository=_RepositoryStub(deployment),  # type: ignore[arg-type]
        manager=manager,  # type: ignore[arg-type]
        clickhouse_client=None,
        now_factory=lambda: now,
        metrics_by_revision={
            str(deployment.production_revision_id): {
                "quality_score": 100.0,
                "latency_p95_ms": 100.0,
                "error_rate": 0.02,
                "cost_per_execution": 1.0,
            },
            str(deployment.canary_revision_id): {
                "quality_score": 99.0,
                "latency_p95_ms": 101.0,
                "error_rate": 0.0201,
                "cost_per_execution": 1.01,
            },
        },
    )

    await monitor.monitor_active_canaries_task()

    assert manager.promoted == [(deployment.id, False)]
    assert manager.rolled_back == []


@pytest.mark.asyncio
async def test_canary_monitor_fetch_metrics_and_helper_edges() -> None:
    now = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
    deployment = _deployment(observation_ends_at=now + timedelta(hours=1))
    clickhouse = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                [],
                [
                    {
                        "quality_score": "99.0",
                        "latency_p95_ms": 101,
                        "error_rate": 0.03,
                        "cost_per_execution": None,
                    }
                ],
            ]
        )
    )
    monitor = CanaryMonitor(
        repository=_RepositoryStub(deployment),  # type: ignore[arg-type]
        manager=_ManagerStub(),  # type: ignore[arg-type]
        clickhouse_client=clickhouse,
        now_factory=lambda: now,
    )

    assert await CanaryMonitor(
        repository=_RepositoryStub(deployment),  # type: ignore[arg-type]
        manager=_ManagerStub(),  # type: ignore[arg-type]
        clickhouse_client=None,
    )._fetch_metrics(deployment.canary_revision_id) == {}
    assert await monitor._fetch_metrics(deployment.canary_revision_id) == {}
    assert await monitor._fetch_metrics(deployment.canary_revision_id) == {
        "quality_score": 99.0,
        "latency_p95_ms": 101.0,
        "error_rate": 0.03,
    }
    assert monitor._detect_breaches(deployment, {}, {"quality_score": 100.0}) == []
    assert CanaryMonitor._pct_drop(None, 1.0) == 0.0
    assert CanaryMonitor._pct_drop(0.0, 1.0) == 0.0
    assert CanaryMonitor._pct_increase(None, 1.0) == 0.0
    assert CanaryMonitor._pct_increase(0.0, 1.0) == 0.0
    assert monitor._window_start() == now - timedelta(hours=24)
