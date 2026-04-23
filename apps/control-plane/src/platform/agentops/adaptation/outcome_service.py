from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.agentops.events import AgentOpsEventType, GovernanceEventPublisher
from platform.agentops.exceptions import OutcomeImmutableError
from platform.agentops.models import (
    AdaptationOutcome,
    AdaptationProposalStatus,
    OutcomeClassification,
)
from platform.agentops.repository import AgentOpsRepository
from platform.agentops.schemas import AdaptationOutcomeResponse
from platform.common.exceptions import NotFoundError, ValidationError
from typing import Any
from uuid import UUID, uuid4

_POSITIVE_METRICS = {"quality_score", "tool_utilization_rate"}
_NEGATIVE_METRICS = {"cost_quality_ratio", "failure_rate", "self_correction_loops"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AdaptationOutcomeService:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        clickhouse_client: Any | None,
        governance_publisher: GovernanceEventPublisher | None,
        observation_window_hours: int,
    ) -> None:
        self.repository = repository
        self.clickhouse_client = clickhouse_client
        self.governance_publisher = governance_publisher
        self.observation_window_hours = observation_window_hours

    async def get_outcome(self, proposal_id: UUID) -> AdaptationOutcomeResponse:
        proposal = await self.repository.get_adaptation(proposal_id)
        if proposal is None:
            raise NotFoundError("AGENTOPS_ADAPTATION_NOT_FOUND", "Adaptation proposal not found")
        outcome = await self.repository.get_outcome_by_proposal(proposal_id)
        if outcome is None:
            applied_at = proposal.applied_at
            if proposal.status == AdaptationProposalStatus.applied.value and applied_at is not None:
                if _utcnow() < applied_at + timedelta(hours=self.observation_window_hours):
                    raise ValidationError(
                        "AGENTOPS_ADAPTATION_OUTCOME_PENDING",
                        "Outcome has not been measured yet.",
                    )
            raise NotFoundError("AGENTOPS_ADAPTATION_OUTCOME_NOT_FOUND", "Outcome not found")
        return AdaptationOutcomeResponse.model_validate(outcome)

    async def measure_for_proposal(self, proposal_id: UUID) -> AdaptationOutcomeResponse:
        proposal = await self.repository.get_adaptation(proposal_id)
        if proposal is None:
            raise NotFoundError("AGENTOPS_ADAPTATION_NOT_FOUND", "Adaptation proposal not found")
        existing = await self.repository.get_outcome_by_proposal(proposal.id)
        if existing is not None:
            raise OutcomeImmutableError(proposal.id)
        if proposal.applied_at is None:
            raise ValidationError(
                "AGENTOPS_ADAPTATION_NOT_APPLIED", "Proposal has not been applied."
            )
        expected = dict(proposal.expected_improvement or {})
        metric = str(expected.get("metric") or "quality_score")
        baseline_value = _as_float(expected.get("baseline_value"), 0.0)
        target_delta = _as_float(expected.get("target_delta"), 0.0)
        observation_window_start = proposal.applied_at
        observation_window_end = proposal.applied_at + timedelta(
            hours=self.observation_window_hours
        )
        measurement = await self._fetch_metric_summary(
            proposal.agent_fqn,
            proposal.workspace_id,
            metric=metric,
            window_start=observation_window_start,
            window_end=observation_window_end,
        )
        observation_period_value = _as_float(measurement.get("average_value"), baseline_value)
        observed_stddev = _as_float(measurement.get("stddev_value"), 0.0)
        sample_count = _as_int(measurement.get("sample_count"), 0)
        observed_delta = observation_period_value - baseline_value
        if metric in _NEGATIVE_METRICS:
            effective_delta = baseline_value - observation_period_value
        else:
            effective_delta = observed_delta
        variance_annotation: dict[str, object] | None = None
        if sample_count < 5:
            classification = OutcomeClassification.inconclusive
        elif abs(target_delta) > 0 and observed_stddev > abs(target_delta):
            classification = OutcomeClassification.inconclusive
            variance_annotation = {
                "observed_stddev": round(observed_stddev, 4),
                "expected_delta_magnitude": round(abs(target_delta), 4),
                "reason": "variance exceeds expected-improvement magnitude",
            }
        elif effective_delta >= max(abs(target_delta) * 0.5, 0.01):
            classification = OutcomeClassification.improved
        elif effective_delta <= -max(abs(target_delta) * 0.5, 0.01):
            classification = OutcomeClassification.regressed
        else:
            classification = OutcomeClassification.no_change
        outcome = await self.repository.create_outcome(
            AdaptationOutcome(
                id=uuid4(),
                proposal_id=proposal.id,
                observation_window_start=observation_window_start,
                observation_window_end=observation_window_end,
                expected_delta=expected,
                observed_delta={
                    "metric": metric,
                    "pre_apply_value": round(baseline_value, 4),
                    "observation_period_value": round(observation_period_value, 4),
                    "observed_delta": round(observed_delta, 4),
                    "observed_stddev": round(observed_stddev, 4),
                    "sample_count": sample_count,
                },
                classification=classification,
                variance_annotation=variance_annotation,
                measured_at=_utcnow(),
            )
        )
        await self._record_event(
            AgentOpsEventType.adaptation_outcome_recorded.value,
            proposal,
            payload={
                "proposal_id": str(proposal.id),
                "classification": classification.value,
                "sample_count": sample_count,
            },
        )
        return AdaptationOutcomeResponse.model_validate(outcome)

    async def _fetch_metric_summary(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        metric: str,
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, object]:
        if self.clickhouse_client is None:
            return {"average_value": 0.0, "stddev_value": 0.0, "sample_count": 0}
        rows = await self.clickhouse_client.execute_query(
            "SELECT %(metric)s AS metric",
            {
                "agent_fqn": agent_fqn,
                "workspace_id": workspace_id,
                "window_start": window_start,
                "window_end": window_end,
                "metric": metric,
            },
        )
        if rows:
            return dict(rows[0])
        return {"average_value": 0.0, "stddev_value": 0.0, "sample_count": 0}

    async def _record_event(
        self,
        event_type: str,
        proposal: Any,
        *,
        payload: dict[str, object],
    ) -> None:
        if self.governance_publisher is None:
            return
        await self.governance_publisher.record(
            event_type,
            proposal.agent_fqn,
            proposal.workspace_id,
            payload=payload,
            actor=proposal.applied_by,
            revision_id=proposal.revision_id,
        )


def _as_float(value: object, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return default
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _as_int(value: object, default: int) -> int:
    if isinstance(value, int):
        return value
    if value is None:
        return default
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default
