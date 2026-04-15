from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.agentops.adaptation.analyzer import BehavioralAnalyzer
from platform.agentops.adaptation.pipeline import AdaptationPipeline
from platform.agentops.canary.manager import CanaryManager
from platform.agentops.canary.monitor import CanaryMonitor
from platform.agentops.cicd.gate import CiCdGate
from platform.agentops.events import AgentOpsEventPublisher, GovernanceEventPublisher
from platform.agentops.governance.grace_period import GracePeriodScanner
from platform.agentops.health.dimensions import HealthDimensionProvider
from platform.agentops.health.scorer import AgentHealthTarget, HealthScorer
from platform.agentops.models import AgentHealthConfig, AgentHealthScore, RegressionAlertStatus
from platform.agentops.regression.detector import RegressionDetector
from platform.agentops.repository import AgentOpsRepository, GovernanceSummaryRepository
from platform.agentops.retirement.workflow import RetirementManager
from platform.agentops.schemas import (
    AdaptationProposalListResponse,
    AdaptationProposalResponse,
    AdaptationReviewRequest,
    AdaptationTriggerRequest,
    AgentHealthConfigPayload,
    AgentHealthConfigResponse,
    AgentHealthScoreHistoryResponse,
    AgentHealthScoreResponse,
    AgentHealthScoreSummary,
    CanaryDecisionRequest,
    CanaryDeploymentCreateRequest,
    CanaryDeploymentListResponse,
    CanaryDeploymentResponse,
    CiCdGateResultListResponse,
    CiCdGateResultResponse,
    CiCdGateSummary,
    GovernanceEventListResponse,
    GovernanceEventResponse,
    GovernanceSummaryResponse,
    RegressionAlertListResponse,
    RegressionAlertResponse,
    RegressionAlertSummary,
    RetirementConfirmRequest,
    RetirementHaltRequest,
    RetirementInitiateRequest,
    RetirementWorkflowResponse,
)
from platform.common.exceptions import NotFoundError, ValidationError
from typing import Any, Protocol
from uuid import UUID


class TrustServiceInterface(Protocol):
    async def is_agent_certified(self, agent_fqn: str, revision_id: UUID) -> Any: ...

    async def get_agent_trust_tier(self, agent_fqn: str, workspace_id: UUID) -> Any: ...

    async def get_guardrail_pass_rate(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        window_days: int,
    ) -> float: ...

    async def trigger_recertification(
        self,
        agent_fqn: str,
        revision_id: UUID,
        trigger_reason: str,
    ) -> None: ...

    async def expire_stale_certifications(self) -> int: ...

    async def get_latest_certification(self, agent_fqn: str) -> Any: ...

    async def list_pending_triggers(self, agent_fqn: str) -> list[Any]: ...

    async def list_upcoming_expirations(
        self,
        agent_fqn: str,
        within_days: int,
    ) -> list[Any]: ...


class EvalSuiteServiceInterface(Protocol):
    async def get_latest_agent_score(self, agent_fqn: str, workspace_id: UUID) -> Any: ...

    async def get_run_results(self, run_id: UUID) -> Any: ...

    async def submit_to_ate(
        self,
        revision_id: UUID,
        eval_set_id: UUID,
        workspace_id: UUID,
    ) -> Any: ...

    async def get_human_grade_aggregate(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        window_days: int,
    ) -> Any: ...

    async def resolve_default_ate_config(self, workspace_id: UUID) -> UUID | None: ...

    async def start_ate_run(
        self,
        *,
        ate_config_id: UUID,
        workspace_id: UUID,
        agent_fqn: str,
        candidate_revision_id: UUID,
    ) -> Any: ...


class PolicyServiceInterface(Protocol):
    async def evaluate_conformance(
        self,
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
    ) -> Any: ...


class WorkflowServiceInterface(Protocol):
    async def find_workflows_using_agent(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> list[dict[str, Any]]: ...


class RegistryServiceInterface(Protocol):
    async def get_agent_revision(self, agent_fqn: str, revision_id: UUID) -> Any: ...

    async def set_marketplace_visibility(
        self,
        agent_fqn: str,
        visible: bool,
        workspace_id: UUID,
    ) -> None: ...

    async def list_active_agents(
        self,
        workspace_id: UUID | None = None,
    ) -> list[dict[str, Any]]: ...

    async def create_candidate_revision(
        self,
        *,
        agent_fqn: str,
        base_revision_id: UUID,
        workspace_id: UUID,
        adjustments: list[dict[str, object]],
        actor_id: UUID,
    ) -> Any: ...


class AgentOpsService:
    def __init__(
        self,
        *,
        repository: AgentOpsRepository,
        event_publisher: AgentOpsEventPublisher,
        governance_publisher: GovernanceEventPublisher | None,
        trust_service: TrustServiceInterface | Any | None,
        eval_suite_service: EvalSuiteServiceInterface | Any | None,
        policy_service: PolicyServiceInterface | Any | None,
        workflow_service: WorkflowServiceInterface | Any | None,
        registry_service: RegistryServiceInterface | Any | None,
        redis_client: Any | None = None,
        clickhouse_client: Any | None = None,
    ) -> None:
        self.repository = repository
        self.event_publisher = event_publisher
        self.governance_publisher = governance_publisher
        self.trust_service = trust_service
        self.eval_suite_service = eval_suite_service
        self.policy_service = policy_service
        self.workflow_service = workflow_service
        self.registry_service = registry_service
        self.redis_client = redis_client
        self.clickhouse_client = clickhouse_client

    async def get_active_regression_alerts(
        self,
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
    ) -> list[RegressionAlertSummary]:
        alerts, _ = await self.repository.list_regression_alerts(
            agent_fqn,
            workspace_id,
            status=RegressionAlertStatus.active.value,
            new_revision_id=revision_id,
            limit=100,
        )
        return [
            RegressionAlertSummary(
                id=alert.id,
                status=alert.status,
                regressed_dimensions=list(alert.regressed_dimensions),
                p_value=alert.p_value,
                effect_size=alert.effect_size,
                detected_at=alert.detected_at,
            )
            for alert in alerts
        ]

    async def list_regression_alerts(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> RegressionAlertListResponse:
        alerts, next_cursor = await self.repository.list_regression_alerts(
            agent_fqn,
            workspace_id,
            status=status,
            cursor=cursor,
            limit=limit,
        )
        return RegressionAlertListResponse(
            items=[RegressionAlertResponse.model_validate(alert) for alert in alerts],
            next_cursor=next_cursor,
        )

    async def get_regression_alert(self, alert_id: UUID) -> RegressionAlertResponse:
        alert = await self.repository.get_regression_alert(alert_id)
        if alert is None:
            raise NotFoundError("AGENTOPS_REGRESSION_ALERT_NOT_FOUND", "Regression alert not found")
        return RegressionAlertResponse.model_validate(alert)

    async def resolve_regression_alert(
        self,
        alert_id: UUID,
        *,
        resolution: str,
        reason: str,
        resolved_by: UUID | None,
    ) -> RegressionAlertResponse:
        alert = await self.repository.get_regression_alert(alert_id)
        if alert is None:
            raise NotFoundError("AGENTOPS_REGRESSION_ALERT_NOT_FOUND", "Regression alert not found")
        alert.status = resolution
        alert.resolution_reason = reason
        alert.resolved_at = datetime.now(UTC)
        alert.resolved_by = resolved_by
        updated = await self.repository.update_regression_alert(alert)
        return RegressionAlertResponse.model_validate(updated)

    async def get_current_health_score(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> AgentHealthScoreSummary | None:
        score = await self.repository.get_current_health_score(agent_fqn, workspace_id)
        if score is None:
            return None
        return AgentHealthScoreSummary(
            id=score.id,
            agent_fqn=score.agent_fqn,
            workspace_id=score.workspace_id,
            composite_score=score.composite_score,
            below_warning=score.below_warning,
            below_critical=score.below_critical,
            insufficient_data=score.insufficient_data,
            computed_at=score.computed_at,
        )

    async def get_health_score(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> AgentHealthScoreResponse:
        score = await self.repository.get_current_health_score(agent_fqn, workspace_id)
        if score is None:
            return await self._build_placeholder_health_score(agent_fqn, workspace_id)
        return AgentHealthScoreResponse.model_validate(score)

    async def list_health_history(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> AgentHealthScoreHistoryResponse:
        items, next_cursor = await self.repository.list_health_history(
            agent_fqn,
            workspace_id,
            cursor=cursor,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
        )
        return AgentHealthScoreHistoryResponse(
            items=[AgentHealthScoreResponse.model_validate(item) for item in items],
            next_cursor=next_cursor,
        )

    async def get_health_config(self, workspace_id: UUID) -> AgentHealthConfigResponse:
        config = await self._get_or_create_health_config(workspace_id)
        return AgentHealthConfigResponse.model_validate(config)

    async def update_health_config(
        self,
        workspace_id: UUID,
        payload: AgentHealthConfigPayload,
    ) -> AgentHealthConfigResponse:
        config = await self.repository.upsert_health_config(
            AgentHealthConfig(
                workspace_id=workspace_id,
                weight_uptime=payload.weight_uptime,
                weight_quality=payload.weight_quality,
                weight_safety=payload.weight_safety,
                weight_cost_efficiency=payload.weight_cost_efficiency,
                weight_satisfaction=payload.weight_satisfaction,
                warning_threshold=payload.warning_threshold,
                critical_threshold=payload.critical_threshold,
                scoring_interval_minutes=payload.scoring_interval_minutes,
                min_sample_size=payload.min_sample_size,
                rolling_window_days=payload.rolling_window_days,
            )
        )
        return AgentHealthConfigResponse.model_validate(config)

    async def run_gate_check(
        self,
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
        requested_by: UUID,
    ) -> CiCdGateSummary:
        result = await self.evaluate_gate_check(
            agent_fqn,
            revision_id,
            workspace_id,
            requested_by,
        )
        return _gate_summary(result)

    async def evaluate_gate_check(
        self,
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
        requested_by: UUID,
    ) -> CiCdGateResultResponse:
        if requested_by.int == 0:
            raise ValidationError("AGENTOPS_REQUESTED_BY_REQUIRED", "requested_by is required")
        return await self._cicd_gate().evaluate(
            agent_fqn=agent_fqn,
            revision_id=revision_id,
            workspace_id=workspace_id,
            requested_by=requested_by,
        )

    async def list_gate_checks(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        revision_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> CiCdGateResultListResponse:
        items, next_cursor = await self.repository.list_gate_results(
            agent_fqn,
            workspace_id,
            revision_id=revision_id,
            cursor=cursor,
            limit=limit,
        )
        return CiCdGateResultListResponse(
            items=[CiCdGateResultResponse.model_validate(item) for item in items],
            next_cursor=next_cursor,
        )

    async def start_canary(
        self,
        agent_fqn: str,
        payload: CanaryDeploymentCreateRequest,
        *,
        initiated_by: UUID,
    ) -> CanaryDeploymentResponse:
        deployment = await self._canary_manager().start(
            agent_fqn,
            payload,
            initiated_by=initiated_by,
        )
        return CanaryDeploymentResponse.model_validate(deployment)

    async def get_active_canary(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> CanaryDeploymentResponse | None:
        deployment = await self.repository.get_active_canary(agent_fqn, workspace_id)
        if deployment is None:
            return None
        return CanaryDeploymentResponse.model_validate(deployment)

    async def get_canary(self, canary_id: UUID) -> CanaryDeploymentResponse:
        deployment = await self.repository.get_canary(canary_id)
        if deployment is None:
            raise NotFoundError("AGENTOPS_CANARY_NOT_FOUND", "Canary deployment not found")
        return CanaryDeploymentResponse.model_validate(deployment)

    async def list_canaries(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> CanaryDeploymentListResponse:
        items, next_cursor = await self.repository.list_canaries(
            agent_fqn,
            workspace_id,
            cursor=cursor,
            limit=limit,
        )
        return CanaryDeploymentListResponse(
            items=[CanaryDeploymentResponse.model_validate(item) for item in items],
            next_cursor=next_cursor,
        )

    async def promote_canary(
        self,
        canary_id: UUID,
        payload: CanaryDecisionRequest,
        *,
        actor: UUID,
    ) -> CanaryDeploymentResponse:
        deployment = await self._canary_manager().promote(
            canary_id,
            manual=True,
            reason=payload.reason,
            actor=actor,
        )
        return CanaryDeploymentResponse.model_validate(deployment)

    async def rollback_canary(
        self,
        canary_id: UUID,
        payload: CanaryDecisionRequest,
        *,
        actor: UUID,
    ) -> CanaryDeploymentResponse:
        deployment = await self._canary_manager().rollback(
            canary_id,
            reason=payload.reason,
            manual=True,
            actor=actor,
        )
        return CanaryDeploymentResponse.model_validate(deployment)

    async def initiate_retirement(
        self,
        agent_fqn: str,
        payload: RetirementInitiateRequest,
        *,
        actor: UUID,
    ) -> RetirementWorkflowResponse:
        workflow = await self._retirement_manager().initiate(
            agent_fqn,
            payload.revision_id,
            payload.workspace_id,
            trigger_reason=payload.reason,
            triggered_by=actor,
            operator_confirmed=payload.operator_confirmed,
        )
        return RetirementWorkflowResponse.model_validate(workflow)

    async def initiate_retirement_from_trigger(
        self,
        agent_fqn: str,
        revision_id: UUID,
        workspace_id: UUID,
        *,
        trigger_reason: str,
    ) -> RetirementWorkflowResponse:
        workflow = await self._retirement_manager().initiate(
            agent_fqn,
            revision_id,
            workspace_id,
            trigger_reason=trigger_reason,
            triggered_by=None,
            operator_confirmed=False,
        )
        return RetirementWorkflowResponse.model_validate(workflow)

    async def get_retirement(self, workflow_id: UUID) -> RetirementWorkflowResponse:
        workflow = await self._retirement_manager().get(workflow_id)
        return RetirementWorkflowResponse.model_validate(workflow)

    async def halt_retirement(
        self,
        workflow_id: UUID,
        payload: RetirementHaltRequest,
        *,
        actor: UUID,
    ) -> RetirementWorkflowResponse:
        workflow = await self._retirement_manager().halt(
            workflow_id,
            reason=payload.reason,
            halted_by=actor,
        )
        return RetirementWorkflowResponse.model_validate(workflow)

    async def confirm_retirement(
        self,
        workflow_id: UUID,
        payload: RetirementConfirmRequest,
        *,
        actor: UUID,
    ) -> RetirementWorkflowResponse:
        workflow = await self._retirement_manager().confirm(
            workflow_id,
            confirmed_by=actor,
            reason=payload.reason,
        )
        return RetirementWorkflowResponse.model_validate(workflow)

    async def list_governance_events(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        event_type: str | None = None,
        since: datetime | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> GovernanceEventListResponse:
        items, next_cursor = await self.repository.list_governance_events(
            agent_fqn,
            workspace_id,
            event_type=event_type,
            since=since,
            cursor=cursor,
            limit=limit,
        )
        return GovernanceEventListResponse(
            items=[GovernanceEventResponse.model_validate(item) for item in items],
            next_cursor=next_cursor,
        )

    async def get_governance_summary(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> GovernanceSummaryResponse:
        summary = await GovernanceSummaryRepository(self.repository).get_summary(
            agent_fqn,
            workspace_id,
            trust_service=self.trust_service,
        )
        return GovernanceSummaryResponse(
            agent_fqn=agent_fqn,
            workspace_id=workspace_id,
            certification_status=(
                str(summary["certification_status"])
                if summary["certification_status"] is not None
                else None
            ),
            trust_tier=summary["trust_tier"],
            pending_triggers=summary["pending_triggers"],
            upcoming_expirations=summary["upcoming_expirations"],
            active_alerts=[
                RegressionAlertResponse.model_validate(item) for item in summary["active_alerts"]
            ],
            active_retirement=(
                RetirementWorkflowResponse.model_validate(summary["active_retirement"])
                if summary["active_retirement"] is not None
                else None
            ),
        )

    async def is_agent_retiring(self, agent_fqn: str, workspace_id: UUID) -> bool:
        return await self.repository.has_active_retirement(agent_fqn, workspace_id)

    async def propose_adaptation(
        self,
        agent_fqn: str,
        payload: AdaptationTriggerRequest,
        *,
        actor: UUID,
    ) -> AdaptationProposalResponse:
        proposal = await self._adaptation_pipeline().propose(
            agent_fqn=agent_fqn,
            workspace_id=payload.workspace_id,
            revision_id=payload.revision_id,
            triggered_by=actor,
        )
        return AdaptationProposalResponse.model_validate(proposal)

    async def review_adaptation(
        self,
        proposal_id: UUID,
        payload: AdaptationReviewRequest,
        *,
        actor: UUID,
    ) -> AdaptationProposalResponse:
        proposal = await self._adaptation_pipeline().review(
            proposal_id,
            decision=payload.decision,
            reason=payload.reason,
            reviewed_by=actor,
        )
        return AdaptationProposalResponse.model_validate(proposal)

    async def list_adaptations(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        *,
        cursor: str | None = None,
        limit: int = 20,
        status: str | None = None,
    ) -> AdaptationProposalListResponse:
        items, next_cursor = await self.repository.list_adaptations(
            agent_fqn,
            workspace_id,
            cursor=cursor,
            limit=limit,
            status=status,
        )
        return AdaptationProposalListResponse(
            items=[AdaptationProposalResponse.model_validate(item) for item in items],
            next_cursor=next_cursor,
        )

    async def score_all_agents_task(
        self,
        *,
        workspace_id: UUID | None = None,
        agent_targets: list[AgentHealthTarget | dict[str, Any] | Any] | None = None,
    ) -> list[AgentHealthScore]:
        resolved_targets: list[AgentHealthTarget | dict[str, Any] | Any]
        if agent_targets is None:
            if self.registry_service is None or not hasattr(
                self.registry_service,
                "list_active_agents",
            ):
                return []
            resolved_targets = list(await self.registry_service.list_active_agents(workspace_id))
        else:
            resolved_targets = list(agent_targets)

        scorer = self._health_scorer()
        computed: list[AgentHealthScore] = []
        for target in resolved_targets:
            resolved = _coerce_target(target, default_workspace_id=workspace_id)
            if resolved is None:
                continue
            computed.append(
                await scorer.compute(
                    agent_fqn=resolved.agent_fqn,
                    workspace_id=resolved.workspace_id,
                    revision_id=resolved.revision_id,
                )
            )
        return computed

    async def monitor_active_canaries_task(self) -> None:
        await self._canary_monitor().monitor_active_canaries_task()

    async def retirement_grace_period_scanner_task(self) -> None:
        await self._grace_period_scanner().retirement_grace_period_scanner_task()

    async def recertification_grace_period_scanner_task(self) -> None:
        await self._grace_period_scanner().recertification_grace_period_scanner_task()

    async def _get_or_create_health_config(self, workspace_id: UUID) -> AgentHealthConfig:
        config = await self.repository.get_health_config(workspace_id)
        if config is not None:
            return config
        return await self.repository.upsert_health_config(
            AgentHealthConfig(workspace_id=workspace_id)
        )

    async def _build_placeholder_health_score(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> AgentHealthScoreResponse:
        config = await self._get_or_create_health_config(workspace_id)
        now = datetime.now(UTC)
        start = now - timedelta(days=config.rolling_window_days)
        nil_uuid = UUID(int=0)
        return AgentHealthScoreResponse(
            id=nil_uuid,
            workspace_id=workspace_id,
            agent_fqn=agent_fqn,
            revision_id=nil_uuid,
            composite_score=Decimal("0.00"),
            uptime_score=None,
            quality_score=None,
            safety_score=None,
            cost_efficiency_score=None,
            satisfaction_score=None,
            weights_snapshot={
                "uptime": float(config.weight_uptime),
                "quality": float(config.weight_quality),
                "safety": float(config.weight_safety),
                "cost_efficiency": float(config.weight_cost_efficiency),
                "satisfaction": float(config.weight_satisfaction),
            },
            missing_dimensions=["uptime", "quality", "safety", "cost_efficiency", "satisfaction"],
            sample_counts={},
            computed_at=now,
            observation_window_start=start,
            observation_window_end=now,
            below_warning=False,
            below_critical=False,
            insufficient_data=True,
            created_at=now,
            updated_at=now,
        )

    def _health_scorer(self) -> HealthScorer:
        return HealthScorer(
            repository=self.repository,
            dimensions=HealthDimensionProvider(
                redis_client=self.redis_client,
                clickhouse_client=self.clickhouse_client,
                trust_service=self.trust_service,
                eval_suite_service=self.eval_suite_service,
            ),
            event_publisher=self.event_publisher,
            redis_client=self.redis_client,
        )

    def regression_detector(
        self,
        *,
        alpha: float = 0.05,
        minimum_sample_size: int = 30,
    ) -> RegressionDetector:
        return RegressionDetector(
            repository=self.repository,
            governance_publisher=self.governance_publisher,
            clickhouse_client=self.clickhouse_client,
            alpha=alpha,
            minimum_sample_size=minimum_sample_size,
        )

    def _cicd_gate(self) -> CiCdGate:
        return CiCdGate(
            repository=self.repository,
            governance_publisher=self.governance_publisher,
            trust_service=self.trust_service,
            eval_suite_service=self.eval_suite_service,
            policy_service=self.policy_service,
            regression_provider=self.get_active_regression_alerts,
        )

    def _canary_manager(self) -> CanaryManager:
        return CanaryManager(
            repository=self.repository,
            governance_publisher=self.governance_publisher,
            redis_client=self.redis_client,
        )

    def _canary_monitor(self) -> CanaryMonitor:
        return CanaryMonitor(
            repository=self.repository,
            manager=self._canary_manager(),
            clickhouse_client=self.clickhouse_client,
        )

    def _retirement_manager(self) -> RetirementManager:
        return RetirementManager(
            repository=self.repository,
            governance_publisher=self.governance_publisher,
            workflow_service=self.workflow_service,
            registry_service=self.registry_service,
        )

    def _grace_period_scanner(self) -> GracePeriodScanner:
        return GracePeriodScanner(
            repository=self.repository,
            retirement_manager=self._retirement_manager(),
            trust_service=self.trust_service,
        )

    def _adaptation_pipeline(self) -> AdaptationPipeline:
        return AdaptationPipeline(
            repository=self.repository,
            analyzer=BehavioralAnalyzer(clickhouse_client=self.clickhouse_client),
            governance_publisher=self.governance_publisher,
            registry_service=self.registry_service,
            eval_suite_service=self.eval_suite_service,
        )


def _coerce_target(
    value: AgentHealthTarget | dict[str, Any] | Any,
    *,
    default_workspace_id: UUID | None,
) -> AgentHealthTarget | None:
    if isinstance(value, AgentHealthTarget):
        return value
    if isinstance(value, dict):
        agent_fqn = value.get("agent_fqn")
        revision_id = value.get("revision_id")
        workspace_id = value.get("workspace_id", default_workspace_id)
    else:
        agent_fqn = getattr(value, "agent_fqn", None)
        revision_id = getattr(value, "revision_id", None)
        workspace_id = getattr(value, "workspace_id", default_workspace_id)

    if not isinstance(agent_fqn, str) or workspace_id is None or revision_id is None:
        return None

    try:
        return AgentHealthTarget(
            agent_fqn=agent_fqn,
            workspace_id=UUID(str(workspace_id)),
            revision_id=UUID(str(revision_id)),
        )
    except ValueError:
        return None


def _gate_summary(result: CiCdGateResultResponse) -> CiCdGateSummary:
    return CiCdGateSummary(
        id=result.id,
        agent_fqn=result.agent_fqn,
        revision_id=result.revision_id,
        workspace_id=result.workspace_id,
        requested_by=result.requested_by,
        overall_passed=result.overall_passed,
        summary={
            "policy_gate_passed": result.policy_gate_passed,
            "evaluation_gate_passed": result.evaluation_gate_passed,
            "certification_gate_passed": result.certification_gate_passed,
            "regression_gate_passed": result.regression_gate_passed,
            "trust_tier_gate_passed": result.trust_tier_gate_passed,
            "evaluation_duration_ms": result.evaluation_duration_ms,
        },
    )
