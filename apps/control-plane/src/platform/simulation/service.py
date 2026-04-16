from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.simulation.comparison.analyzer import ComparisonAnalyzer
from platform.simulation.coordination.runner import SimulationRunner
from platform.simulation.events import SimulationEventsConsumer
from platform.simulation.exceptions import IncompatibleComparisonError, SimulationNotFoundError
from platform.simulation.isolation.enforcer import IsolationEnforcer
from platform.simulation.models import (
    BehavioralPrediction,
    DigitalTwin,
    SimulationComparisonReport,
    SimulationIsolationPolicy,
)
from platform.simulation.prediction.forecaster import BehavioralForecaster, PredictionWorker
from platform.simulation.repository import SimulationRepository
from platform.simulation.schemas import (
    BehavioralPredictionCreateRequest,
    BehavioralPredictionResponse,
    DigitalTwinCreateRequest,
    DigitalTwinListResponse,
    DigitalTwinModifyRequest,
    DigitalTwinResponse,
    DigitalTwinVersionListResponse,
    SimulationComparisonCreateRequest,
    SimulationComparisonReportResponse,
    SimulationIsolationPolicyCreateRequest,
    SimulationIsolationPolicyListResponse,
    SimulationIsolationPolicyResponse,
    SimulationRunCreateRequest,
    SimulationRunListResponse,
    SimulationRunResponse,
    SimulationSummary,
    TwinConfigSnapshot,
)
from typing import Any, Protocol
from uuid import UUID


class SimulationServiceInterface(Protocol):
    async def get_simulation_summary(
        self,
        run_id: UUID,
        workspace_id: UUID,
    ) -> SimulationSummary | None: ...

    async def get_twin_config(
        self,
        twin_id: UUID,
        workspace_id: UUID,
    ) -> TwinConfigSnapshot | None: ...


class SimulationService:
    def __init__(
        self,
        *,
        repository: SimulationRepository,
        settings: PlatformSettings,
        runner: SimulationRunner,
        twin_snapshot: Any,
        isolation_enforcer: IsolationEnforcer,
        forecaster: BehavioralForecaster,
        comparison_analyzer: ComparisonAnalyzer,
        events_consumer: SimulationEventsConsumer,
        prediction_worker: PredictionWorker,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.runner = runner
        self.twin_snapshot = twin_snapshot
        self.isolation_enforcer = isolation_enforcer
        self.forecaster = forecaster
        self.comparison_analyzer = comparison_analyzer
        self.events_consumer = events_consumer
        self.prediction_worker = prediction_worker

    async def create_simulation_run(
        self,
        payload: SimulationRunCreateRequest,
        actor_id: UUID,
    ) -> SimulationRunResponse:
        twins = [
            await self._twin_or_raise(twin_id, payload.workspace_id)
            for twin_id in payload.digital_twin_ids
        ]
        duration = int(
            payload.scenario_config.get(
                "duration_seconds",
                self.settings.simulation.max_duration_seconds,
            )
        )
        duration = min(duration, self.settings.simulation.max_duration_seconds)
        run = await self.runner.create(
            workspace_id=payload.workspace_id,
            name=payload.name,
            description=payload.description,
            digital_twin_ids=payload.digital_twin_ids,
            twin_configs=[_twin_config(item) for item in twins],
            scenario_config=payload.scenario_config,
            max_duration_seconds=duration,
            isolation_policy_id=payload.isolation_policy_id,
            initiated_by=actor_id,
        )
        if payload.isolation_policy_id is not None:
            policy = await self.repository.get_isolation_policy(
                payload.isolation_policy_id,
                payload.workspace_id,
            )
            if policy is None:
                raise SimulationNotFoundError(
                    "Simulation isolation policy",
                    payload.isolation_policy_id,
                )
            await self.isolation_enforcer.apply(run, policy)
        else:
            await self.isolation_enforcer.apply_default_strict(run)
        return SimulationRunResponse.model_validate(run)

    async def cancel_simulation_run(
        self,
        run_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
    ) -> SimulationRunResponse:
        run = await self.runner.cancel(run_id, workspace_id, actor_id=actor_id)
        await self.isolation_enforcer.release(run)
        return SimulationRunResponse.model_validate(run)

    async def get_simulation_run(self, run_id: UUID, workspace_id: UUID) -> SimulationRunResponse:
        run = await self.repository.get_run(run_id, workspace_id)
        if run is None:
            raise SimulationNotFoundError("Simulation run", run_id)
        return SimulationRunResponse.model_validate(run)

    async def list_simulation_runs(
        self,
        workspace_id: UUID,
        *,
        status: str | None,
        limit: int,
        cursor: str | None,
    ) -> SimulationRunListResponse:
        items, next_cursor = await self.repository.list_runs(
            workspace_id,
            status=status,
            limit=limit,
            cursor=cursor,
        )
        return SimulationRunListResponse(
            items=[SimulationRunResponse.model_validate(item) for item in items],
            next_cursor=next_cursor,
        )

    async def create_digital_twin(
        self,
        payload: DigitalTwinCreateRequest,
    ) -> DigitalTwinResponse:
        twin = await self.twin_snapshot.create_twin(
            agent_fqn=payload.agent_fqn,
            workspace_id=payload.workspace_id,
            revision_id=payload.revision_id,
        )
        return DigitalTwinResponse.model_validate(twin)

    async def modify_digital_twin(
        self,
        twin_id: UUID,
        workspace_id: UUID,
        payload: DigitalTwinModifyRequest,
    ) -> DigitalTwinResponse:
        twin = await self.twin_snapshot.modify_twin(
            twin_id=twin_id,
            workspace_id=workspace_id,
            modifications=[item.model_dump() for item in payload.modifications],
        )
        return DigitalTwinResponse.model_validate(twin)

    async def get_digital_twin(self, twin_id: UUID, workspace_id: UUID) -> DigitalTwinResponse:
        twin = await self._twin_or_raise(twin_id, workspace_id)
        return DigitalTwinResponse.model_validate(twin)

    async def list_digital_twins(
        self,
        workspace_id: UUID,
        *,
        agent_fqn: str | None,
        is_active: bool | None,
        limit: int,
        cursor: str | None,
    ) -> DigitalTwinListResponse:
        items, next_cursor = await self.repository.list_twins(
            workspace_id,
            agent_fqn=agent_fqn,
            is_active=is_active,
            limit=limit,
            cursor=cursor,
        )
        return DigitalTwinListResponse(
            items=[DigitalTwinResponse.model_validate(item) for item in items],
            next_cursor=next_cursor,
        )

    async def list_twin_versions(
        self,
        twin_id: UUID,
        workspace_id: UUID,
    ) -> DigitalTwinVersionListResponse:
        twin = await self._twin_or_raise(twin_id, workspace_id)
        versions = await self.repository.list_twin_versions(twin)
        return DigitalTwinVersionListResponse(
            items=[DigitalTwinResponse.model_validate(item) for item in versions],
            total_versions=len(versions),
        )

    async def create_isolation_policy(
        self,
        payload: SimulationIsolationPolicyCreateRequest,
    ) -> SimulationIsolationPolicyResponse:
        policy = await self.repository.create_isolation_policy(
            SimulationIsolationPolicy(
                workspace_id=payload.workspace_id,
                name=payload.name,
                description=payload.description,
                blocked_actions=payload.blocked_actions,
                stubbed_actions=payload.stubbed_actions,
                permitted_read_sources=payload.permitted_read_sources,
                is_default=payload.is_default,
                halt_on_critical_breach=payload.halt_on_critical_breach,
            )
        )
        return SimulationIsolationPolicyResponse.model_validate(policy)

    async def get_isolation_policy(
        self,
        policy_id: UUID,
        workspace_id: UUID,
    ) -> SimulationIsolationPolicyResponse:
        policy = await self.repository.get_isolation_policy(policy_id, workspace_id)
        if policy is None:
            raise SimulationNotFoundError("Simulation isolation policy", policy_id)
        return SimulationIsolationPolicyResponse.model_validate(policy)

    async def list_isolation_policies(
        self,
        workspace_id: UUID,
    ) -> SimulationIsolationPolicyListResponse:
        items = await self.repository.list_isolation_policies(workspace_id)
        return SimulationIsolationPolicyListResponse(
            items=[SimulationIsolationPolicyResponse.model_validate(item) for item in items]
        )

    async def create_behavioral_prediction(
        self,
        twin_id: UUID,
        payload: BehavioralPredictionCreateRequest,
    ) -> BehavioralPredictionResponse:
        await self._twin_or_raise(twin_id, payload.workspace_id)
        prediction = await self.repository.create_prediction(
            BehavioralPrediction(
                digital_twin_id=twin_id,
                condition_modifiers=payload.condition_modifiers,
                status="pending",
            )
        )
        return BehavioralPredictionResponse.model_validate(prediction)

    async def get_behavioral_prediction(
        self,
        prediction_id: UUID,
        workspace_id: UUID,
    ) -> BehavioralPredictionResponse:
        prediction = await self.repository.get_prediction(prediction_id, workspace_id)
        if prediction is None:
            raise SimulationNotFoundError("Behavioral prediction", prediction_id)
        return BehavioralPredictionResponse.model_validate(prediction)

    async def create_comparison_report(
        self,
        run_id: UUID,
        payload: SimulationComparisonCreateRequest,
    ) -> SimulationComparisonReportResponse:
        await self._run_or_raise(run_id, payload.workspace_id)
        report = await self.repository.create_comparison_report(
            SimulationComparisonReport(
                comparison_type=payload.comparison_type,
                primary_run_id=run_id,
                secondary_run_id=payload.secondary_run_id,
                production_baseline_period=payload.production_baseline_period,
                prediction_id=payload.prediction_id,
                status="pending",
                compatible=True,
                incompatibility_reasons=[],
                metric_differences=[],
            )
        )
        try:
            report = await self.comparison_analyzer.analyze(
                report=report,
                workspace_id=payload.workspace_id,
            )
        except IncompatibleComparisonError:
            raise
        return SimulationComparisonReportResponse.model_validate(report)

    async def get_comparison_report(
        self,
        report_id: UUID,
        workspace_id: UUID,
    ) -> SimulationComparisonReportResponse:
        report = await self.repository.get_comparison_report(report_id, workspace_id)
        if report is None:
            raise SimulationNotFoundError("Simulation comparison report", report_id)
        return SimulationComparisonReportResponse.model_validate(report)

    async def get_simulation_summary(
        self,
        run_id: UUID,
        workspace_id: UUID,
    ) -> SimulationSummary | None:
        run = await self.repository.get_run(run_id, workspace_id)
        if run is None:
            return None
        return SimulationSummary(
            run_id=run.id,
            status=run.status,
            name=run.name,
            digital_twin_ids=[UUID(str(item)) for item in run.digital_twin_ids],
            completed_at=run.completed_at,
            results_summary=run.results,
        )

    async def get_twin_config(
        self,
        twin_id: UUID,
        workspace_id: UUID,
    ) -> TwinConfigSnapshot | None:
        twin = await self.repository.get_twin(twin_id, workspace_id)
        if twin is None:
            return None
        return TwinConfigSnapshot(
            twin_id=twin.id,
            source_agent_fqn=twin.source_agent_fqn,
            version=twin.version,
            config_snapshot=twin.config_snapshot,
        )

    async def _twin_or_raise(self, twin_id: UUID, workspace_id: UUID) -> DigitalTwin:
        twin = await self.repository.get_twin(twin_id, workspace_id)
        if twin is None:
            raise SimulationNotFoundError("Digital twin", twin_id)
        return twin

    async def _run_or_raise(self, run_id: UUID, workspace_id: UUID) -> Any:
        run = await self.repository.get_run(run_id, workspace_id)
        if run is None:
            raise SimulationNotFoundError("Simulation run", run_id)
        return run


def _twin_config(twin: DigitalTwin) -> dict[str, Any]:
    return {
        "twin_id": str(twin.id),
        "source_agent_fqn": twin.source_agent_fqn,
        "source_revision_id": str(twin.source_revision_id) if twin.source_revision_id else None,
        "version": twin.version,
        "config_snapshot": twin.config_snapshot,
        "behavioral_history_summary": twin.behavioral_history_summary,
    }
