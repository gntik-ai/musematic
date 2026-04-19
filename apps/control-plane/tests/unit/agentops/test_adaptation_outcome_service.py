from __future__ import annotations

from datetime import timedelta
from platform.agentops.adaptation.outcome_service import (
    AdaptationOutcomeService,
    _as_float,
    _as_int,
)
from platform.agentops.exceptions import OutcomeImmutableError
from platform.agentops.models import AdaptationProposalStatus, OutcomeClassification
from platform.common.exceptions import NotFoundError, ValidationError
from uuid import UUID

import pytest
from tests.agentops_support import (
    build_adaptation_outcome,
    build_adaptation_proposal,
    utcnow,
)


class _RepositoryStub:
    def __init__(self, proposal, outcome=None):
        self.proposal = proposal
        self.outcome = outcome
        self.created = None

    async def get_adaptation(self, proposal_id):
        return self.proposal if proposal_id == self.proposal.id else None

    async def get_outcome_by_proposal(self, proposal_id):
        assert proposal_id == self.proposal.id
        return self.outcome

    async def create_outcome(self, outcome):
        self.created = outcome
        outcome.created_at = outcome.measured_at
        outcome.updated_at = outcome.measured_at
        self.outcome = outcome
        return outcome


class _ClickHouseStub:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    async def execute_query(self, sql, params):
        self.calls.append((sql, params))
        return list(self.rows)


class _GovernancePublisherStub:
    def __init__(self) -> None:
        self.events = []

    async def record(self, event_type: str, agent_fqn: str, workspace_id: UUID, payload, **kwargs):
        self.events.append(
            {
                "event_type": event_type,
                "agent_fqn": agent_fqn,
                "workspace_id": workspace_id,
                "payload": payload,
                **kwargs,
            }
        )


@pytest.mark.asyncio
async def test_measure_for_proposal_persists_improved_outcome_and_emits_event() -> None:
    proposal = build_adaptation_proposal(
        status=AdaptationProposalStatus.applied,
        applied_at=utcnow() - timedelta(hours=72),
        expected_improvement={
            "metric": "quality_score",
            "baseline_value": 0.60,
            "target_value": 0.75,
            "target_delta": 0.15,
        },
    )
    repository = _RepositoryStub(proposal)
    clickhouse = _ClickHouseStub(
        [
            {"average_value": 0.82, "stddev_value": 0.02, "sample_count": 12},
        ]
    )
    governance = _GovernancePublisherStub()
    service = AdaptationOutcomeService(
        repository=repository,  # type: ignore[arg-type]
        clickhouse_client=clickhouse,
        governance_publisher=governance,  # type: ignore[arg-type]
        observation_window_hours=48,
    )

    response = await service.measure_for_proposal(proposal.id)

    assert response.classification == OutcomeClassification.improved
    assert response.observed_delta["observed_delta"] == pytest.approx(0.22)
    assert repository.created is not None
    assert governance.events[0]["event_type"] == "agentops.adaptation.outcome_recorded"


@pytest.mark.asyncio
async def test_measure_for_proposal_marks_high_variance_as_inconclusive() -> None:
    proposal = build_adaptation_proposal(
        status=AdaptationProposalStatus.applied,
        applied_at=utcnow() - timedelta(hours=72),
        expected_improvement={
            "metric": "quality_score",
            "baseline_value": 0.55,
            "target_value": 0.65,
            "target_delta": 0.10,
        },
    )
    service = AdaptationOutcomeService(
        repository=_RepositoryStub(proposal),  # type: ignore[arg-type]
        clickhouse_client=_ClickHouseStub(
            [
                {"average_value": 0.64, "stddev_value": 0.14, "sample_count": 9},
            ]
        ),
        governance_publisher=None,
        observation_window_hours=48,
    )

    response = await service.measure_for_proposal(proposal.id)

    assert response.classification == OutcomeClassification.inconclusive
    assert response.variance_annotation is not None
    assert (
        response.variance_annotation["reason"] == "variance exceeds expected-improvement magnitude"
    )


@pytest.mark.asyncio
async def test_measure_for_proposal_rejects_duplicate_outcomes() -> None:
    proposal = build_adaptation_proposal(
        status=AdaptationProposalStatus.applied,
        applied_at=utcnow() - timedelta(hours=72),
    )
    existing = build_adaptation_outcome(proposal_id=proposal.id)
    service = AdaptationOutcomeService(
        repository=_RepositoryStub(proposal, outcome=existing),  # type: ignore[arg-type]
        clickhouse_client=None,
        governance_publisher=None,
        observation_window_hours=48,
    )

    with pytest.raises(OutcomeImmutableError):
        await service.measure_for_proposal(proposal.id)


@pytest.mark.asyncio
async def test_get_outcome_blocks_until_observation_window_elapses() -> None:
    proposal = build_adaptation_proposal(
        status=AdaptationProposalStatus.applied,
        applied_at=utcnow() - timedelta(hours=2),
    )
    service = AdaptationOutcomeService(
        repository=_RepositoryStub(proposal),  # type: ignore[arg-type]
        clickhouse_client=None,
        governance_publisher=None,
        observation_window_hours=24,
    )

    with pytest.raises(ValidationError) as excinfo:
        await service.get_outcome(proposal.id)

    assert excinfo.value.code == "AGENTOPS_ADAPTATION_OUTCOME_PENDING"


@pytest.mark.asyncio
async def test_get_outcome_rejects_unknown_proposal() -> None:
    proposal = build_adaptation_proposal()
    service = AdaptationOutcomeService(
        repository=_RepositoryStub(proposal),  # type: ignore[arg-type]
        clickhouse_client=None,
        governance_publisher=None,
        observation_window_hours=24,
    )

    with pytest.raises(NotFoundError) as excinfo:
        await service.get_outcome(UUID(int=0))

    assert excinfo.value.code == "AGENTOPS_ADAPTATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_outcome_returns_not_found_after_window_without_measurement() -> None:
    proposal = build_adaptation_proposal(
        status=AdaptationProposalStatus.applied,
        applied_at=utcnow() - timedelta(hours=48),
    )
    service = AdaptationOutcomeService(
        repository=_RepositoryStub(proposal),  # type: ignore[arg-type]
        clickhouse_client=None,
        governance_publisher=None,
        observation_window_hours=24,
    )

    with pytest.raises(NotFoundError) as excinfo:
        await service.get_outcome(proposal.id)

    assert excinfo.value.code == "AGENTOPS_ADAPTATION_OUTCOME_NOT_FOUND"


@pytest.mark.asyncio
async def test_measure_for_proposal_rejects_unknown_or_unapplied_proposals() -> None:
    proposal = build_adaptation_proposal(status=AdaptationProposalStatus.proposed)
    service = AdaptationOutcomeService(
        repository=_RepositoryStub(proposal),  # type: ignore[arg-type]
        clickhouse_client=None,
        governance_publisher=None,
        observation_window_hours=24,
    )

    with pytest.raises(NotFoundError):
        await service.measure_for_proposal(UUID(int=0))

    with pytest.raises(ValidationError) as excinfo:
        await service.measure_for_proposal(proposal.id)

    assert excinfo.value.code == "AGENTOPS_ADAPTATION_NOT_APPLIED"


@pytest.mark.asyncio
async def test_measure_for_proposal_handles_negative_metrics_and_no_change() -> None:
    regressed = build_adaptation_proposal(
        status=AdaptationProposalStatus.applied,
        applied_at=utcnow() - timedelta(hours=72),
        expected_improvement={
            "metric": "failure_rate",
            "baseline_value": 0.20,
            "target_value": 0.15,
            "target_delta": 0.05,
        },
    )
    regressed_service = AdaptationOutcomeService(
        repository=_RepositoryStub(regressed),  # type: ignore[arg-type]
        clickhouse_client=_ClickHouseStub(
            [{"average_value": 0.40, "stddev_value": 0.01, "sample_count": 8}]
        ),
        governance_publisher=None,
        observation_window_hours=24,
    )

    regressed_response = await regressed_service.measure_for_proposal(regressed.id)

    assert regressed_response.classification == OutcomeClassification.regressed

    unchanged = build_adaptation_proposal(
        status=AdaptationProposalStatus.applied,
        applied_at=utcnow() - timedelta(hours=72),
        expected_improvement={
            "metric": "quality_score",
            "baseline_value": 0.70,
            "target_value": 0.82,
            "target_delta": 0.12,
        },
    )
    unchanged_service = AdaptationOutcomeService(
        repository=_RepositoryStub(unchanged),  # type: ignore[arg-type]
        clickhouse_client=_ClickHouseStub(
            [{"average_value": 0.71, "stddev_value": 0.01, "sample_count": 8}]
        ),
        governance_publisher=None,
        observation_window_hours=24,
    )

    unchanged_response = await unchanged_service.measure_for_proposal(unchanged.id)

    assert unchanged_response.classification == OutcomeClassification.no_change


@pytest.mark.asyncio
async def test_metric_summary_and_numeric_coercion_fallbacks() -> None:
    proposal = build_adaptation_proposal(
        status=AdaptationProposalStatus.applied,
        applied_at=utcnow() - timedelta(hours=72),
    )
    no_client = AdaptationOutcomeService(
        repository=_RepositoryStub(proposal),  # type: ignore[arg-type]
        clickhouse_client=None,
        governance_publisher=None,
        observation_window_hours=24,
    )
    empty_client = AdaptationOutcomeService(
        repository=_RepositoryStub(proposal),  # type: ignore[arg-type]
        clickhouse_client=_ClickHouseStub([]),
        governance_publisher=None,
        observation_window_hours=24,
    )

    summary_without_client = await no_client._fetch_metric_summary(
        proposal.agent_fqn,
        proposal.workspace_id,
        metric="quality_score",
        window_start=proposal.applied_at - timedelta(hours=1),
        window_end=proposal.applied_at,
    )
    summary_without_rows = await empty_client._fetch_metric_summary(
        proposal.agent_fqn,
        proposal.workspace_id,
        metric="quality_score",
        window_start=proposal.applied_at - timedelta(hours=1),
        window_end=proposal.applied_at,
    )

    assert summary_without_client["sample_count"] == 0
    assert summary_without_rows["average_value"] == 0.0
    assert _as_float("1.25", 0.0) == pytest.approx(1.25)
    assert _as_float("bad", 3.5) == pytest.approx(3.5)
    assert _as_int("8", 0) == 8
    assert _as_int("bad", 7) == 7



@pytest.mark.asyncio
async def test_get_outcome_returns_existing_row() -> None:
    proposal = build_adaptation_proposal(
        status=AdaptationProposalStatus.applied,
        applied_at=utcnow() - timedelta(hours=72),
    )
    existing = build_adaptation_outcome(
        proposal_id=proposal.id,
        classification=OutcomeClassification.improved,
    )
    service = AdaptationOutcomeService(
        repository=_RepositoryStub(proposal, outcome=existing),  # type: ignore[arg-type]
        clickhouse_client=None,
        governance_publisher=None,
        observation_window_hours=24,
    )

    response = await service.get_outcome(proposal.id)

    assert response.proposal_id == proposal.id
    assert response.classification == OutcomeClassification.improved


@pytest.mark.asyncio
async def test_measure_for_proposal_marks_low_sample_counts_as_inconclusive() -> None:
    proposal = build_adaptation_proposal(
        status=AdaptationProposalStatus.applied,
        applied_at=utcnow() - timedelta(hours=72),
        expected_improvement={
            "metric": "quality_score",
            "baseline_value": 0.50,
            "target_value": 0.60,
            "target_delta": 0.10,
        },
    )
    service = AdaptationOutcomeService(
        repository=_RepositoryStub(proposal),  # type: ignore[arg-type]
        clickhouse_client=_ClickHouseStub(
            [{"average_value": 0.58, "stddev_value": 0.01, "sample_count": 3}]
        ),
        governance_publisher=None,
        observation_window_hours=24,
    )

    response = await service.measure_for_proposal(proposal.id)

    assert response.classification == OutcomeClassification.inconclusive
    assert response.observed_delta["sample_count"] == 3


def test_numeric_coercion_none_defaults() -> None:
    assert _as_float(None, 1.5) == pytest.approx(1.5)
    assert _as_int(None, 4) == 4
