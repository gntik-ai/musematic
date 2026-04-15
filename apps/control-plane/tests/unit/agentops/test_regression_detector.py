from __future__ import annotations

from datetime import UTC, datetime
from platform.agentops.exceptions import InsufficientSampleError
from platform.agentops.models import BehavioralRegressionAlert
from platform.agentops.regression.detector import RegressionDetector
from platform.agentops.service import AgentOpsService
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest


class _RegressionRepositoryStub:
    def __init__(self) -> None:
        self.alerts: list[BehavioralRegressionAlert] = []

    async def create_regression_alert(
        self,
        alert: BehavioralRegressionAlert,
    ) -> BehavioralRegressionAlert:
        if getattr(alert, "id", None) is None:
            alert.id = uuid4()
        if getattr(alert, "created_at", None) is None:
            alert.created_at = datetime.now(UTC)
        if getattr(alert, "updated_at", None) is None:
            alert.updated_at = alert.created_at
        self.alerts.append(alert)
        return alert

    async def list_regression_alerts(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        status: str | None = None,
        new_revision_id: UUID | None = None,
    ) -> tuple[list[BehavioralRegressionAlert], str | None]:
        del cursor, limit
        items = [
            alert
            for alert in self.alerts
            if alert.agent_fqn == agent_fqn
            and alert.workspace_id == workspace_id
            and (status is None or alert.status == status)
            and (new_revision_id is None or alert.new_revision_id == new_revision_id)
        ]
        return items, None


class _GovernancePublisherStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def record(
        self,
        event_type: str,
        agent_fqn: str,
        workspace_id: UUID,
        payload: dict[str, Any],
        actor: UUID | str | None = None,
        revision_id: UUID | None = None,
        correlation_ctx=None,
    ) -> None:
        del actor, correlation_ctx
        self.calls.append(
            {
                "event_type": event_type,
                "agent_fqn": agent_fqn,
                "workspace_id": workspace_id,
                "payload": payload,
                "revision_id": revision_id,
            }
        )


@pytest.mark.asyncio
async def test_regression_detector_creates_alert_for_regressed_quality_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    repository = _RegressionRepositoryStub()
    governance = _GovernancePublisherStub()
    detector = RegressionDetector(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=governance,  # type: ignore[arg-type]
        clickhouse_client=None,
    )
    baseline_revision_id = uuid4()
    new_revision_id = uuid4()

    async def _fetch_samples(
        *,
        revision_id: UUID,
        agent_fqn: str,
        workspace_id: UUID,
        dimension: str,
        column: str,
    ) -> list[float]:
        del agent_fqn, workspace_id, column
        if dimension == "quality":
            if revision_id == baseline_revision_id:
                return [0.90 + (index * 0.0005) for index in range(40)]
            return [0.68 + (index * 0.0005) for index in range(40)]
        return [0.80 + (index * 0.0002) for index in range(40)]

    monkeypatch.setattr(detector, "fetch_samples", _fetch_samples)

    alert = await detector.detect(
        new_revision_id=new_revision_id,
        baseline_revision_id=baseline_revision_id,
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
    )

    assert alert is not None
    assert alert.status == "active"
    assert alert.regressed_dimensions == ["quality"]
    assert repository.alerts == [alert]
    assert governance.calls[-1]["event_type"] == "agentops.regression.detected"


@pytest.mark.asyncio
async def test_regression_detector_returns_none_when_variation_is_not_significant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detector = RegressionDetector(
        repository=_RegressionRepositoryStub(),  # type: ignore[arg-type]
        governance_publisher=_GovernancePublisherStub(),  # type: ignore[arg-type]
        clickhouse_client=None,
    )
    baseline_revision_id = uuid4()
    new_revision_id = uuid4()

    async def _fetch_samples(
        *,
        revision_id: UUID,
        agent_fqn: str,
        workspace_id: UUID,
        dimension: str,
        column: str,
    ) -> list[float]:
        del revision_id, agent_fqn, workspace_id, dimension, column
        return [0.80, 0.81, 0.79, 0.82, 0.80] * 8

    monkeypatch.setattr(detector, "fetch_samples", _fetch_samples)

    alert = await detector.detect(
        new_revision_id=new_revision_id,
        baseline_revision_id=baseline_revision_id,
        agent_fqn="finance:agent",
        workspace_id=uuid4(),
    )

    assert alert is None


@pytest.mark.asyncio
async def test_regression_detector_raises_when_samples_are_below_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detector = RegressionDetector(
        repository=_RegressionRepositoryStub(),  # type: ignore[arg-type]
        governance_publisher=_GovernancePublisherStub(),  # type: ignore[arg-type]
        clickhouse_client=None,
        minimum_sample_size=30,
    )

    async def _fetch_samples(
        *,
        revision_id: UUID,
        agent_fqn: str,
        workspace_id: UUID,
        dimension: str,
        column: str,
    ) -> list[float]:
        del revision_id, agent_fqn, workspace_id, column
        if dimension == "quality":
            return [0.8] * 12
        return [0.8] * 10

    monkeypatch.setattr(detector, "fetch_samples", _fetch_samples)

    with pytest.raises(InsufficientSampleError):
        await detector.detect(
            new_revision_id=uuid4(),
            baseline_revision_id=uuid4(),
            agent_fqn="finance:agent",
            workspace_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_active_regression_alerts_service_returns_active_alerts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    repository = _RegressionRepositoryStub()
    detector = RegressionDetector(
        repository=repository,  # type: ignore[arg-type]
        governance_publisher=_GovernancePublisherStub(),  # type: ignore[arg-type]
        clickhouse_client=None,
    )
    baseline_revision_id = uuid4()
    new_revision_id = uuid4()

    async def _fetch_samples(
        *,
        revision_id: UUID,
        agent_fqn: str,
        workspace_id: UUID,
        dimension: str,
        column: str,
    ) -> list[float]:
        del agent_fqn, workspace_id, column
        if dimension == "quality":
            if revision_id == baseline_revision_id:
                return [0.93 + (index * 0.0005) for index in range(40)]
            return [0.70 + (index * 0.0005) for index in range(40)]
        return [0.82 + (index * 0.0002) for index in range(40)]

    monkeypatch.setattr(detector, "fetch_samples", _fetch_samples)
    await detector.detect(
        new_revision_id=new_revision_id,
        baseline_revision_id=baseline_revision_id,
        agent_fqn="finance:agent",
        workspace_id=workspace_id,
    )

    service = AgentOpsService(
        repository=repository,  # type: ignore[arg-type]
        event_publisher=SimpleNamespace(),
        governance_publisher=None,
        trust_service=None,
        eval_suite_service=None,
        policy_service=None,
        workflow_service=None,
        registry_service=None,
    )

    alerts = await service.get_active_regression_alerts(
        "finance:agent",
        new_revision_id,
        workspace_id,
    )

    assert len(alerts) == 1
    assert alerts[0].status == "active"
    assert alerts[0].regressed_dimensions == ["quality"]
