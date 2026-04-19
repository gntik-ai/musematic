from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.agentops.models import (
    AdaptationOutcome,
    AdaptationProposal,
    AdaptationProposalStatus,
    AdaptationSnapshot,
    OutcomeClassification,
    ProficiencyAssessment,
    ProficiencyLevel,
    SnapshotType,
)
from uuid import UUID, uuid4


def utcnow() -> datetime:
    return datetime.now(UTC)


def stamp(model, *, created_at: datetime | None = None, updated_at: datetime | None = None):
    model.created_at = created_at or utcnow()
    model.updated_at = updated_at or model.created_at
    return model


def build_adaptation_proposal(
    *,
    proposal_id: UUID | None = None,
    workspace_id: UUID | None = None,
    agent_fqn: str = "finance:agent",
    revision_id: UUID | None = None,
    status: AdaptationProposalStatus | str = AdaptationProposalStatus.proposed,
    proposal_details: dict[str, object] | None = None,
    signals: list[dict[str, object]] | None = None,
    expected_improvement: dict[str, object] | None = None,
    signal_source: str | None = "manual",
    expires_at: datetime | None = None,
    applied_at: datetime | None = None,
) -> AdaptationProposal:
    proposal = AdaptationProposal(
        id=proposal_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        agent_fqn=agent_fqn,
        revision_id=revision_id,
        status=status,
        proposal_details=proposal_details or {"adjustments": []},
        signals=signals or [],
        expected_improvement=expected_improvement,
        signal_source=signal_source,
        expires_at=expires_at,
        applied_at=applied_at,
    )
    return stamp(proposal)


def build_adaptation_snapshot(
    *,
    proposal_id: UUID,
    snapshot_id: UUID | None = None,
    snapshot_type: SnapshotType = SnapshotType.pre_apply,
    configuration: dict[str, object] | None = None,
    configuration_hash: str = "sha256:test",
    retention_expires_at: datetime | None = None,
    revision_id: UUID | None = None,
) -> AdaptationSnapshot:
    snapshot = AdaptationSnapshot(
        id=snapshot_id or uuid4(),
        proposal_id=proposal_id,
        snapshot_type=snapshot_type,
        configuration=configuration or {},
        configuration_hash=configuration_hash,
        revision_id=revision_id,
        retention_expires_at=retention_expires_at or (utcnow() + timedelta(days=30)),
    )
    return stamp(snapshot)


def build_adaptation_outcome(
    *,
    proposal_id: UUID,
    outcome_id: UUID | None = None,
    classification: OutcomeClassification = OutcomeClassification.improved,
    expected_delta: dict[str, object] | None = None,
    observed_delta: dict[str, object] | None = None,
    variance_annotation: dict[str, object] | None = None,
    measured_at: datetime | None = None,
) -> AdaptationOutcome:
    outcome = AdaptationOutcome(
        id=outcome_id or uuid4(),
        proposal_id=proposal_id,
        observation_window_start=utcnow() - timedelta(hours=24),
        observation_window_end=utcnow(),
        expected_delta=expected_delta or {"metric": "quality_score", "target_delta": 0.1},
        observed_delta=observed_delta or {"metric": "quality_score", "observed_delta": 0.2},
        classification=classification,
        variance_annotation=variance_annotation,
        measured_at=measured_at or utcnow(),
    )
    return stamp(outcome)


def build_proficiency_assessment(
    *,
    assessment_id: UUID | None = None,
    workspace_id: UUID | None = None,
    agent_fqn: str = "finance:agent",
    level: ProficiencyLevel = ProficiencyLevel.competent,
    dimension_values: dict[str, float] | None = None,
    observation_count: int = 9,
    trigger: str = "scheduled",
    assessed_at: datetime | None = None,
) -> ProficiencyAssessment:
    assessment = ProficiencyAssessment(
        id=assessment_id or uuid4(),
        workspace_id=workspace_id or uuid4(),
        agent_fqn=agent_fqn,
        level=level,
        dimension_values=dimension_values
        or {
            "retrieval_accuracy": 0.6,
            "instruction_adherence": 0.6,
            "context_coherence": 0.6,
            "aggregate_score": 0.6,
        },
        observation_count=observation_count,
        trigger=trigger,
        assessed_at=assessed_at or utcnow(),
    )
    return stamp(assessment)
