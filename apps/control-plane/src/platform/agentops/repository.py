from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from platform.agentops.models import (
    AdaptationOutcome,
    AdaptationProposal,
    AdaptationProposalStatus,
    AdaptationSnapshot,
    AgentHealthConfig,
    AgentHealthScore,
    BehavioralBaseline,
    BehavioralRegressionAlert,
    CanaryDeployment,
    CiCdGateResult,
    GovernanceEvent,
    ProficiencyAssessment,
    RegressionAlertStatus,
    RetirementWorkflow,
    RetirementWorkflowStatus,
)
from platform.common.pagination import apply_cursor_pagination, encode_cursor
from typing import Any, TypeVar
from uuid import UUID, uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class AgentOpsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_health_config(self, config: AgentHealthConfig) -> AgentHealthConfig:
        values = {
            "id": config.id or uuid4(),
            "workspace_id": config.workspace_id,
            "weight_uptime": _decimal_or_default(config.weight_uptime, Decimal("20.00")),
            "weight_quality": _decimal_or_default(config.weight_quality, Decimal("35.00")),
            "weight_safety": _decimal_or_default(config.weight_safety, Decimal("25.00")),
            "weight_cost_efficiency": _decimal_or_default(
                config.weight_cost_efficiency, Decimal("10.00")
            ),
            "weight_satisfaction": _decimal_or_default(
                config.weight_satisfaction, Decimal("10.00")
            ),
            "warning_threshold": _decimal_or_default(config.warning_threshold, Decimal("60.00")),
            "critical_threshold": _decimal_or_default(config.critical_threshold, Decimal("40.00")),
            "scoring_interval_minutes": _int_or_default(config.scoring_interval_minutes, 15),
            "min_sample_size": _int_or_default(config.min_sample_size, 50),
            "rolling_window_days": _int_or_default(config.rolling_window_days, 30),
        }
        await self.session.execute(
            self._upsert_stmt(
                AgentHealthConfig,
                values,
                conflict_columns=["workspace_id"],
            )
        )
        result = await self.session.execute(
            select(AgentHealthConfig).where(AgentHealthConfig.workspace_id == config.workspace_id)
        )
        return result.scalar_one()

    async def get_health_config(self, workspace_id: UUID) -> AgentHealthConfig | None:
        result = await self.session.execute(
            select(AgentHealthConfig).where(AgentHealthConfig.workspace_id == workspace_id)
        )
        return result.scalar_one_or_none()

    async def upsert_health_score(self, score: AgentHealthScore) -> AgentHealthScore:
        values = {
            "id": score.id or uuid4(),
            "workspace_id": score.workspace_id,
            "agent_fqn": score.agent_fqn,
            "revision_id": score.revision_id,
            "composite_score": score.composite_score,
            "uptime_score": score.uptime_score,
            "quality_score": score.quality_score,
            "safety_score": score.safety_score,
            "cost_efficiency_score": score.cost_efficiency_score,
            "satisfaction_score": score.satisfaction_score,
            "weights_snapshot": score.weights_snapshot,
            "missing_dimensions": score.missing_dimensions,
            "sample_counts": score.sample_counts,
            "computed_at": score.computed_at,
            "observation_window_start": score.observation_window_start,
            "observation_window_end": score.observation_window_end,
            "below_warning": score.below_warning,
            "below_critical": score.below_critical,
            "insufficient_data": score.insufficient_data,
        }
        await self.session.execute(
            self._upsert_stmt(
                AgentHealthScore,
                values,
                conflict_columns=["agent_fqn", "workspace_id"],
            )
        )
        result = await self.session.execute(
            select(AgentHealthScore).where(
                AgentHealthScore.workspace_id == score.workspace_id,
                AgentHealthScore.agent_fqn == score.agent_fqn,
            )
        )
        return result.scalar_one()

    async def get_current_health_score(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> AgentHealthScore | None:
        result = await self.session.execute(
            select(AgentHealthScore)
            .where(
                AgentHealthScore.agent_fqn == agent_fqn,
                AgentHealthScore.workspace_id == workspace_id,
            )
            .order_by(AgentHealthScore.computed_at.desc(), AgentHealthScore.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_health_history(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> tuple[list[AgentHealthScore], str | None]:
        query = select(AgentHealthScore).where(
            AgentHealthScore.agent_fqn == agent_fqn,
            AgentHealthScore.workspace_id == workspace_id,
        )
        if start_time is not None:
            query = query.where(AgentHealthScore.computed_at >= start_time)
        if end_time is not None:
            query = query.where(AgentHealthScore.computed_at <= end_time)
        return await self._paginate(query, limit=limit, cursor=cursor)

    async def create_baseline(self, baseline: BehavioralBaseline) -> BehavioralBaseline:
        self.session.add(baseline)
        await self.session.flush()
        return baseline

    async def get_baseline_by_revision(self, revision_id: UUID) -> BehavioralBaseline | None:
        result = await self.session.execute(
            select(BehavioralBaseline).where(BehavioralBaseline.revision_id == revision_id)
        )
        return result.scalar_one_or_none()

    async def list_baselines(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[BehavioralBaseline], str | None]:
        query = select(BehavioralBaseline).where(
            BehavioralBaseline.agent_fqn == agent_fqn,
            BehavioralBaseline.workspace_id == workspace_id,
        )
        return await self._paginate(query, limit=limit, cursor=cursor)

    async def create_regression_alert(
        self,
        alert: BehavioralRegressionAlert,
    ) -> BehavioralRegressionAlert:
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def get_regression_alert(self, alert_id: UUID) -> BehavioralRegressionAlert | None:
        result = await self.session.execute(
            select(BehavioralRegressionAlert).where(BehavioralRegressionAlert.id == alert_id)
        )
        return result.scalar_one_or_none()

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
        query = select(BehavioralRegressionAlert).where(
            BehavioralRegressionAlert.agent_fqn == agent_fqn,
            BehavioralRegressionAlert.workspace_id == workspace_id,
        )
        if status is not None:
            query = query.where(BehavioralRegressionAlert.status == status)
        if new_revision_id is not None:
            query = query.where(BehavioralRegressionAlert.new_revision_id == new_revision_id)
        return await self._paginate(query, limit=limit, cursor=cursor)

    async def update_regression_alert(
        self,
        alert: BehavioralRegressionAlert,
    ) -> BehavioralRegressionAlert:
        await self.session.flush()
        return alert

    async def create_gate_result(self, result_model: CiCdGateResult) -> CiCdGateResult:
        self.session.add(result_model)
        await self.session.flush()
        return result_model

    async def list_gate_results(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        revision_id: UUID | None = None,
    ) -> tuple[list[CiCdGateResult], str | None]:
        query = select(CiCdGateResult).where(
            CiCdGateResult.agent_fqn == agent_fqn,
            CiCdGateResult.workspace_id == workspace_id,
        )
        if revision_id is not None:
            query = query.where(CiCdGateResult.revision_id == revision_id)
        return await self._paginate(query, limit=limit, cursor=cursor)

    async def create_canary(self, canary: CanaryDeployment) -> CanaryDeployment:
        self.session.add(canary)
        await self.session.flush()
        return canary

    async def get_canary(self, canary_id: UUID) -> CanaryDeployment | None:
        result = await self.session.execute(
            select(CanaryDeployment).where(CanaryDeployment.id == canary_id)
        )
        return result.scalar_one_or_none()

    async def get_active_canary(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> CanaryDeployment | None:
        result = await self.session.execute(
            select(CanaryDeployment).where(
                CanaryDeployment.agent_fqn == agent_fqn,
                CanaryDeployment.workspace_id == workspace_id,
                CanaryDeployment.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def list_canaries(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[CanaryDeployment], str | None]:
        query = select(CanaryDeployment).where(
            CanaryDeployment.agent_fqn == agent_fqn,
            CanaryDeployment.workspace_id == workspace_id,
        )
        return await self._paginate(query, limit=limit, cursor=cursor)

    async def list_active_canaries(
        self,
        *,
        workspace_id: UUID | None = None,
    ) -> list[CanaryDeployment]:
        query = select(CanaryDeployment).where(
            CanaryDeployment.status == "active",
        )
        if workspace_id is not None:
            query = query.where(CanaryDeployment.workspace_id == workspace_id)
        query = query.order_by(CanaryDeployment.started_at.asc(), CanaryDeployment.id.asc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_canary(self, canary: CanaryDeployment) -> CanaryDeployment:
        await self.session.flush()
        return canary

    async def create_retirement(
        self,
        workflow: RetirementWorkflow,
    ) -> RetirementWorkflow:
        self.session.add(workflow)
        await self.session.flush()
        return workflow

    async def get_retirement(self, workflow_id: UUID) -> RetirementWorkflow | None:
        result = await self.session.execute(
            select(RetirementWorkflow).where(RetirementWorkflow.id == workflow_id)
        )
        return result.scalar_one_or_none()

    async def get_active_retirement(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> RetirementWorkflow | None:
        result = await self.session.execute(
            select(RetirementWorkflow).where(
                RetirementWorkflow.agent_fqn == agent_fqn,
                RetirementWorkflow.workspace_id == workspace_id,
                RetirementWorkflow.status.in_(
                    [
                        RetirementWorkflowStatus.initiated.value,
                        RetirementWorkflowStatus.grace_period.value,
                    ]
                ),
            )
        )
        return result.scalar_one_or_none()

    async def has_active_retirement(self, agent_fqn: str, workspace_id: UUID) -> bool:
        return await self.get_active_retirement(agent_fqn, workspace_id) is not None

    async def list_retirements(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        status: str | None = None,
    ) -> tuple[list[RetirementWorkflow], str | None]:
        query = select(RetirementWorkflow).where(
            RetirementWorkflow.agent_fqn == agent_fqn,
            RetirementWorkflow.workspace_id == workspace_id,
        )
        if status is not None:
            query = query.where(RetirementWorkflow.status == status)
        return await self._paginate(query, limit=limit, cursor=cursor)

    async def list_due_retirements(
        self,
        now: datetime,
        *,
        workspace_id: UUID | None = None,
    ) -> list[RetirementWorkflow]:
        query = select(RetirementWorkflow).where(
            RetirementWorkflow.status == RetirementWorkflowStatus.grace_period.value,
            RetirementWorkflow.grace_period_ends_at <= now,
        )
        if workspace_id is not None:
            query = query.where(RetirementWorkflow.workspace_id == workspace_id)
        query = query.order_by(
            RetirementWorkflow.grace_period_ends_at.asc(),
            RetirementWorkflow.id.asc(),
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_retirement(self, workflow: RetirementWorkflow) -> RetirementWorkflow:
        await self.session.flush()
        return workflow

    # Append-only invariant: GovernanceEvent rows are inserted via this method only.
    # Do not add update/delete helpers for governance events.
    async def insert_governance_event(self, event: GovernanceEvent) -> GovernanceEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_governance_event(self, event_id: UUID) -> GovernanceEvent | None:
        result = await self.session.execute(
            select(GovernanceEvent).where(GovernanceEvent.id == event_id)
        )
        return result.scalar_one_or_none()

    async def list_governance_events(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        event_type: str | None = None,
        since: datetime | None = None,
    ) -> tuple[list[GovernanceEvent], str | None]:
        query = select(GovernanceEvent).where(
            GovernanceEvent.agent_fqn == agent_fqn,
            GovernanceEvent.workspace_id == workspace_id,
        )
        if event_type is not None:
            query = query.where(GovernanceEvent.event_type == event_type)
        if since is not None:
            query = query.where(GovernanceEvent.created_at >= since)
        return await self._paginate(query, limit=limit, cursor=cursor)

    async def create_adaptation(self, proposal: AdaptationProposal) -> AdaptationProposal:
        self.session.add(proposal)
        await self.session.flush()
        return proposal

    async def get_adaptation(self, proposal_id: UUID) -> AdaptationProposal | None:
        result = await self.session.execute(
            select(AdaptationProposal).where(AdaptationProposal.id == proposal_id)
        )
        return result.scalar_one_or_none()

    async def get_adaptation_by_evaluation_run_id(
        self,
        evaluation_run_id: UUID,
    ) -> AdaptationProposal | None:
        result = await self.session.execute(
            select(AdaptationProposal).where(
                AdaptationProposal.evaluation_run_id == evaluation_run_id
            )
        )
        return result.scalar_one_or_none()

    async def get_open_adaptation(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> AdaptationProposal | None:
        result = await self.session.execute(
            select(AdaptationProposal)
            .where(
                AdaptationProposal.agent_fqn == agent_fqn,
                AdaptationProposal.workspace_id == workspace_id,
                AdaptationProposal.status.in_(
                    [
                        AdaptationProposalStatus.proposed.value,
                        AdaptationProposalStatus.approved.value,
                        AdaptationProposalStatus.applied.value,
                    ]
                ),
            )
            .order_by(AdaptationProposal.created_at.desc(), AdaptationProposal.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_adaptations(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        status: str | None = None,
    ) -> tuple[list[AdaptationProposal], str | None]:
        query = select(AdaptationProposal).where(
            AdaptationProposal.agent_fqn == agent_fqn,
            AdaptationProposal.workspace_id == workspace_id,
        )
        if status is not None:
            query = query.where(AdaptationProposal.status == status)
        return await self._paginate(query, limit=limit, cursor=cursor)

    async def update_adaptation(self, proposal: AdaptationProposal) -> AdaptationProposal:
        await self.session.flush()
        return proposal

    async def create_snapshot(self, snapshot: AdaptationSnapshot) -> AdaptationSnapshot:
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def get_snapshot_by_proposal(self, proposal_id: UUID) -> AdaptationSnapshot | None:
        result = await self.session.execute(
            select(AdaptationSnapshot)
            .where(AdaptationSnapshot.proposal_id == proposal_id)
            .order_by(AdaptationSnapshot.created_at.asc(), AdaptationSnapshot.id.asc())
        )
        return result.scalars().first()

    async def list_snapshots_by_proposal(self, proposal_id: UUID) -> list[AdaptationSnapshot]:
        result = await self.session.execute(
            select(AdaptationSnapshot)
            .where(AdaptationSnapshot.proposal_id == proposal_id)
            .order_by(AdaptationSnapshot.created_at.asc(), AdaptationSnapshot.id.asc())
        )
        return list(result.scalars().all())

    async def create_outcome(self, outcome: AdaptationOutcome) -> AdaptationOutcome:
        self.session.add(outcome)
        await self.session.flush()
        return outcome

    async def get_outcome_by_proposal(self, proposal_id: UUID) -> AdaptationOutcome | None:
        result = await self.session.execute(
            select(AdaptationOutcome).where(AdaptationOutcome.proposal_id == proposal_id)
        )
        return result.scalar_one_or_none()

    async def list_proposals_past_ttl(self, now: datetime) -> list[AdaptationProposal]:
        result = await self.session.execute(
            select(AdaptationProposal).where(
                AdaptationProposal.status == AdaptationProposalStatus.proposed.value,
                AdaptationProposal.expires_at.is_not(None),
                AdaptationProposal.expires_at < now,
            )
        )
        return list(result.scalars().all())

    async def list_orphaned_proposals(self) -> list[AdaptationProposal]:
        result = await self.session.execute(
            select(AdaptationProposal).where(
                AdaptationProposal.status.in_(
                    [
                        AdaptationProposalStatus.proposed.value,
                        AdaptationProposalStatus.approved.value,
                        AdaptationProposalStatus.applied.value,
                    ]
                )
            )
        )
        return list(result.scalars().all())

    async def list_proposals_pending_outcome(self, before: datetime) -> list[AdaptationProposal]:
        result = await self.session.execute(
            select(AdaptationProposal)
            .outerjoin(AdaptationOutcome, AdaptationOutcome.proposal_id == AdaptationProposal.id)
            .where(
                AdaptationProposal.status == AdaptationProposalStatus.applied.value,
                AdaptationProposal.applied_at.is_not(None),
                AdaptationProposal.applied_at < before,
                AdaptationOutcome.id.is_(None),
            )
        )
        return list(result.scalars().all())

    async def list_snapshots_past_retention(self, now: datetime) -> list[AdaptationSnapshot]:
        result = await self.session.execute(
            select(AdaptationSnapshot).where(AdaptationSnapshot.retention_expires_at < now)
        )
        return list(result.scalars().all())

    async def delete_snapshot(self, snapshot: AdaptationSnapshot) -> None:
        await self.session.delete(snapshot)
        await self.session.flush()

    async def create_proficiency_assessment(
        self,
        assessment: ProficiencyAssessment,
    ) -> ProficiencyAssessment:
        self.session.add(assessment)
        await self.session.flush()
        return assessment

    async def get_latest_proficiency_assessment(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> ProficiencyAssessment | None:
        result = await self.session.execute(
            select(ProficiencyAssessment)
            .where(
                ProficiencyAssessment.agent_fqn == agent_fqn,
                ProficiencyAssessment.workspace_id == workspace_id,
            )
            .order_by(ProficiencyAssessment.assessed_at.desc(), ProficiencyAssessment.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_proficiency_assessments(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[ProficiencyAssessment], str | None]:
        query = select(ProficiencyAssessment).where(
            ProficiencyAssessment.agent_fqn == agent_fqn,
            ProficiencyAssessment.workspace_id == workspace_id,
        )
        return await self._paginate(query, limit=limit, cursor=cursor)

    async def list_proficiency_fleet(
        self,
        workspace_id: UUID,
        *,
        levels: list[str] | None = None,
    ) -> list[ProficiencyAssessment]:
        latest_subquery = (
            select(
                ProficiencyAssessment.agent_fqn.label("agent_fqn"),
                func.max(ProficiencyAssessment.assessed_at).label("max_assessed_at"),
            )
            .where(ProficiencyAssessment.workspace_id == workspace_id)
            .group_by(ProficiencyAssessment.agent_fqn)
            .subquery()
        )
        query = (
            select(ProficiencyAssessment)
            .join(
                latest_subquery,
                (ProficiencyAssessment.agent_fqn == latest_subquery.c.agent_fqn)
                & (ProficiencyAssessment.assessed_at == latest_subquery.c.max_assessed_at),
            )
            .where(ProficiencyAssessment.workspace_id == workspace_id)
        )
        if levels is not None:
            query = query.where(ProficiencyAssessment.level.in_(levels))
        query = query.order_by(
            ProficiencyAssessment.assessed_at.desc(), ProficiencyAssessment.id.desc()
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_active_regression_alerts(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        revision_id: UUID,
    ) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(BehavioralRegressionAlert)
            .where(
                BehavioralRegressionAlert.agent_fqn == agent_fqn,
                BehavioralRegressionAlert.workspace_id == workspace_id,
                BehavioralRegressionAlert.new_revision_id == revision_id,
                BehavioralRegressionAlert.status == RegressionAlertStatus.active.value,
            )
        )
        return int(total or 0)

    def _upsert_stmt(
        self,
        model: type[Any],
        values: dict[str, Any],
        *,
        conflict_columns: list[str],
    ) -> Any:
        dialect = self.session.bind.dialect.name if self.session.bind is not None else "postgresql"
        insert_factory = sqlite_insert if dialect == "sqlite" else postgresql_insert
        stmt = insert_factory(model).values(**values)
        update_values = {key: value for key, value in values.items() if key != "id"}
        return stmt.on_conflict_do_update(
            index_elements=[getattr(model, column) for column in conflict_columns],
            set_=update_values,
        )

    async def _paginate(
        self,
        query: Select[tuple[T]],
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[T], str | None]:
        result = await self.session.execute(apply_cursor_pagination(query, cursor, limit))
        items = list(result.scalars().all())
        next_cursor: str | None = None
        if len(items) > limit:
            page_items = items[:limit]
            last = page_items[-1]
            next_cursor = encode_cursor(last.id, last.created_at)
            return page_items, next_cursor
        return items, None


class GovernanceSummaryRepository:
    def __init__(self, agentops_repository: AgentOpsRepository) -> None:
        self.agentops_repository = agentops_repository

    async def get_summary(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        trust_service: Any | None,
        within_days: int = 30,
    ) -> dict[str, Any]:
        certification_status = None
        pending_triggers: list[dict[str, Any]] = []
        upcoming_expirations: list[dict[str, Any]] = []
        trust_tier: int | None = None
        if trust_service is not None:
            certification = await trust_service.get_latest_certification(agent_fqn)
            certification_status = getattr(certification, "status", None)
            trust_result = await trust_service.get_agent_trust_tier(agent_fqn, workspace_id)
            trust_tier = _coerce_tier(getattr(trust_result, "tier", None), trust_result)
            pending_triggers = [
                {
                    "id": str(item.id),
                    "trigger_type": str(item.trigger_type),
                    "status": str(item.status),
                    "created_at": item.created_at.isoformat(),
                }
                for item in await trust_service.list_pending_triggers(agent_fqn)
            ]
            upcoming_expirations = [
                {
                    "certification_id": str(item.id),
                    "expires_at": (
                        item.expires_at.isoformat() if item.expires_at is not None else None
                    ),
                    "status": str(item.status),
                }
                for item in await trust_service.list_upcoming_expirations(agent_fqn, within_days)
            ]
        active_alerts, _ = await self.agentops_repository.list_regression_alerts(
            agent_fqn,
            workspace_id,
            status=RegressionAlertStatus.active.value,
            limit=100,
        )
        active_retirement = await self.agentops_repository.get_active_retirement(
            agent_fqn,
            workspace_id,
        )
        return {
            "certification_status": certification_status,
            "trust_tier": trust_tier,
            "pending_triggers": pending_triggers,
            "upcoming_expirations": upcoming_expirations,
            "active_alerts": active_alerts,
            "active_retirement": active_retirement,
        }


def _coerce_tier(explicit: Any, fallback: Any) -> int | None:
    source = explicit if explicit is not None else fallback
    if source is None:
        return None
    if isinstance(source, bool):
        return int(source)
    if isinstance(source, (int, float)):
        return int(source)
    mapping = {"untrusted": 0, "provisional": 1, "certified": 3}
    return mapping.get(str(source).lower())


def _decimal_or_default(value: Decimal | None, default: Decimal) -> Decimal:
    return value if value is not None else default


def _int_or_default(value: int | None, default: int) -> int:
    return value if value is not None else default
