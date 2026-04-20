from __future__ import annotations

import logging
from platform.common.config import PlatformSettings
from platform.discovery.critique.evaluator import CritiqueEvaluator
from platform.discovery.events import DiscoveryEventPublisher
from platform.discovery.exceptions import (
    DiscoveryNotFoundError,
    InsufficientHypothesesError,
    SessionAlreadyRunningError,
    WorkspaceProximityRecomputeInFlightError,
)
from platform.discovery.experiment.designer import ExperimentDesigner
from platform.discovery.gde.cycle import GDECycleOrchestrator
from platform.discovery.models import DiscoverySession, EloScore, Hypothesis, TournamentRound
from platform.discovery.provenance.graph import ProvenanceGraph
from platform.discovery.proximity.clustering import ProximityClustering
from platform.discovery.proximity.graph import ProximityGraphService
from platform.discovery.repository import DiscoveryRepository
from platform.discovery.schemas import (
    ClusterListResponse,
    CritiqueListResponse,
    DiscoveryExperimentResponse,
    DiscoverySessionCreateRequest,
    DiscoverySessionListResponse,
    DiscoverySessionResponse,
    GDECycleResponse,
    HypothesisListResponse,
    HypothesisResponse,
    LeaderboardEntryResponse,
    LeaderboardResponse,
    ProvenanceGraphResponse,
    ProximityGraphResponse,
    ProximityWorkspaceSettingsResponse,
    ProximityWorkspaceSettingsUpdateRequest,
    RecomputeEnqueuedResponse,
    TournamentRoundListResponse,
    TournamentRoundResponse,
)
from platform.discovery.tournament.comparator import TournamentComparator
from platform.discovery.tournament.elo import EloRatingEngine
from typing import Protocol
from uuid import UUID

LOGGER = logging.getLogger(__name__)
_RECOMPUTE_IN_FLIGHT: set[UUID] = set()


class DiscoveryServiceInterface(Protocol):
    async def get_session_summary(
        self,
        session_id: UUID,
        workspace_id: UUID,
    ) -> dict[str, object] | None: ...

    async def get_top_hypotheses(
        self,
        session_id: UUID,
        workspace_id: UUID,
        limit: int = 5,
    ) -> list[HypothesisResponse]: ...


class DiscoveryService:
    """Application service for scientific discovery orchestration."""

    def __init__(
        self,
        *,
        repository: DiscoveryRepository,
        settings: PlatformSettings,
        publisher: DiscoveryEventPublisher,
        elo_engine: EloRatingEngine,
        tournament: TournamentComparator,
        critique_evaluator: CritiqueEvaluator,
        gde_orchestrator: GDECycleOrchestrator | None,
        experiment_designer: ExperimentDesigner | None,
        provenance_graph: ProvenanceGraph,
        proximity_clustering: ProximityClustering | None,
        proximity_graph_service: ProximityGraphService | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.publisher = publisher
        self.elo_engine = elo_engine
        self.tournament = tournament
        self.critique_evaluator = critique_evaluator
        self.gde_orchestrator = gde_orchestrator
        self.experiment_designer = experiment_designer
        self.provenance_graph = provenance_graph
        self.proximity_clustering = proximity_clustering
        self.proximity_graph_service = proximity_graph_service

    async def start_session(
        self,
        payload: DiscoverySessionCreateRequest,
        actor_id: UUID,
    ) -> DiscoverySessionResponse:
        session = await self.repository.create_session(
            DiscoverySession(
                workspace_id=payload.workspace_id,
                research_question=payload.research_question,
                corpus_refs=[item.model_dump() for item in payload.corpus_refs],
                config=payload.config.model_dump(),
                status="active",
                current_cycle=0,
                convergence_metrics=None,
                initiated_by=actor_id,
            )
        )
        await self.publisher.session_started(session.id, session.workspace_id, actor_id)
        return DiscoverySessionResponse.model_validate(session)

    async def get_session(self, session_id: UUID, workspace_id: UUID) -> DiscoverySessionResponse:
        session = await self._session(session_id, workspace_id)
        return DiscoverySessionResponse.model_validate(session)

    async def list_sessions(
        self,
        workspace_id: UUID,
        *,
        status: str | None,
        limit: int,
        cursor: str | None,
    ) -> DiscoverySessionListResponse:
        items, next_cursor = await self.repository.list_sessions(
            workspace_id,
            status=status,
            limit=limit,
            cursor=cursor,
        )
        return DiscoverySessionListResponse(
            items=[DiscoverySessionResponse.model_validate(item) for item in items],
            next_cursor=next_cursor,
        )

    async def halt_session(
        self,
        session_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
        reason: str,
    ) -> DiscoverySessionResponse:
        session = await self.repository.update_session_status(session_id, workspace_id, "halted")
        if session is None:
            raise DiscoveryNotFoundError("Discovery session", session_id)
        await self.publisher.session_halted(session_id, workspace_id, actor_id, reason)
        return DiscoverySessionResponse.model_validate(session)

    async def run_tournament_round(
        self,
        session_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
    ) -> None:
        hypotheses = await self.repository.list_active_hypotheses(session_id, workspace_id)
        if len(hypotheses) < 2:
            raise InsufficientHypothesesError()
        await self.tournament.run_round(
            session_id=session_id,
            workspace_id=workspace_id,
            hypotheses=hypotheses,
            actor_id=actor_id,
        )

    async def run_gde_cycle(
        self,
        session_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
    ) -> GDECycleResponse:
        session = await self._session(session_id, workspace_id)
        if session.status != "active":
            raise SessionAlreadyRunningError("Discovery session is not active")
        running = await self.repository.get_running_cycle(session_id, workspace_id)
        if running is not None:
            raise SessionAlreadyRunningError()
        if self.gde_orchestrator is None:
            raise RuntimeError("GDE orchestrator is not configured")
        cycle = await self.gde_orchestrator.run_cycle(
            session_id=session_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
        )
        return GDECycleResponse.model_validate(cycle)

    async def get_cycle(self, cycle_id: UUID, workspace_id: UUID) -> GDECycleResponse:
        cycle = await self.repository.get_cycle(cycle_id, workspace_id)
        if cycle is None:
            raise DiscoveryNotFoundError("Discovery cycle", cycle_id)
        return GDECycleResponse.model_validate(cycle)

    async def list_hypotheses(
        self,
        session_id: UUID,
        workspace_id: UUID,
        *,
        status: str | None,
        order_by: str,
        limit: int,
        cursor: str | None,
    ) -> HypothesisListResponse:
        if order_by == "elo_desc":
            entries = await self.get_top_hypotheses(session_id, workspace_id, limit=limit)
            return HypothesisListResponse(items=entries, next_cursor=None)
        rows, next_cursor = await self.repository.list_hypotheses(
            session_id,
            workspace_id,
            status=status,
            limit=limit,
            cursor=cursor,
        )
        scores = await self.repository.list_elo_scores(session_id)
        response_items: list[HypothesisResponse] = []
        for item in rows:
            elo_row = scores.get(item.id)
            response_items.append(
                _hypothesis_response(
                    item,
                    elo_score=None if elo_row is None else elo_row.current_score,
                    elo_row=elo_row,
                )
            )
        return HypothesisListResponse(items=response_items, next_cursor=next_cursor)

    async def get_hypothesis(self, hypothesis_id: UUID, workspace_id: UUID) -> HypothesisResponse:
        hypothesis = await self._hypothesis(hypothesis_id, workspace_id)
        elo_row = await self.repository.get_elo_score(hypothesis.id, hypothesis.session_id)
        return _hypothesis_response(
            hypothesis,
            elo_score=None if elo_row is None else elo_row.current_score,
            elo_row=elo_row,
        )

    async def get_top_hypotheses(
        self,
        session_id: UUID,
        workspace_id: UUID,
        limit: int = 5,
    ) -> list[HypothesisResponse]:
        entries = await self.elo_engine.get_leaderboard(session_id, limit)
        score_rows = await self.repository.list_elo_scores(session_id)
        responses: list[HypothesisResponse] = []
        for entry in entries:
            hypothesis = await self.repository.get_hypothesis(entry.hypothesis_id, workspace_id)
            if hypothesis is None:
                continue
            responses.append(
                _hypothesis_response(
                    hypothesis,
                    elo_score=entry.elo_score,
                    rank=entry.rank,
                    elo_row=score_rows.get(hypothesis.id),
                )
            )
        return responses

    async def get_leaderboard(
        self,
        session_id: UUID,
        workspace_id: UUID,
        limit: int,
    ) -> LeaderboardResponse:
        items = [
            LeaderboardEntryResponse(
                hypothesis_id=item.hypothesis_id,
                title=item.title,
                elo_score=float(item.elo_score or 0.0),
                rank=item.rank or index,
                wins=item.wins,
                losses=item.losses,
                draws=item.draws,
                cluster_id=item.cluster_id,
            )
            for index, item in enumerate(
                await self.get_top_hypotheses(session_id, workspace_id, limit),
                start=1,
            )
        ]
        return LeaderboardResponse(
            items=items,
            session_id=session_id,
            total_hypotheses=len(items),
        )

    async def list_tournament_rounds(
        self,
        session_id: UUID,
        workspace_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> TournamentRoundListResponse:
        items, next_cursor = await self.repository.list_tournament_rounds(
            session_id,
            workspace_id,
            limit=limit,
            cursor=cursor,
        )
        return TournamentRoundListResponse(
            items=[_model_validate_tournament_round(item) for item in items],
            next_cursor=next_cursor,
        )

    async def submit_for_critique(
        self,
        hypothesis_id: UUID,
        workspace_id: UUID,
        reviewer_agents: list[str],
        actor_id: UUID,
    ) -> CritiqueListResponse:
        hypothesis = await self._hypothesis(hypothesis_id, workspace_id)
        await self.critique_evaluator.critique_hypothesis(
            hypothesis,
            reviewer_agents,
            actor_id=actor_id,
        )
        return await self.get_critiques(hypothesis_id, workspace_id)

    async def get_critiques(self, hypothesis_id: UUID, workspace_id: UUID) -> CritiqueListResponse:
        rows = await self.repository.list_critiques(hypothesis_id, workspace_id)
        items = [row for row in rows if not row.is_aggregated]
        aggregated = next((row for row in rows if row.is_aggregated), None)
        from platform.discovery.schemas import HypothesisCritiqueResponse

        return CritiqueListResponse(
            items=[HypothesisCritiqueResponse.model_validate(row) for row in items],
            aggregated=None
            if aggregated is None
            else HypothesisCritiqueResponse.model_validate(aggregated),
        )

    async def design_experiment(
        self,
        hypothesis_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
    ) -> DiscoveryExperimentResponse:
        hypothesis = await self._hypothesis(hypothesis_id, workspace_id)
        if self.experiment_designer is None:
            raise RuntimeError("Experiment designer is not configured")
        experiment = await self.experiment_designer.design(hypothesis, actor_id=actor_id)
        return DiscoveryExperimentResponse.model_validate(experiment)

    async def get_experiment(
        self,
        experiment_id: UUID,
        workspace_id: UUID,
    ) -> DiscoveryExperimentResponse:
        experiment = await self.repository.get_experiment(experiment_id, workspace_id)
        if experiment is None:
            raise DiscoveryNotFoundError("Discovery experiment", experiment_id)
        return DiscoveryExperimentResponse.model_validate(experiment)

    async def execute_experiment(
        self,
        experiment_id: UUID,
        workspace_id: UUID,
    ) -> DiscoveryExperimentResponse:
        experiment = await self.repository.get_experiment(experiment_id, workspace_id)
        if experiment is None:
            raise DiscoveryNotFoundError("Discovery experiment", experiment_id)
        hypothesis = await self._hypothesis(experiment.hypothesis_id, workspace_id)
        if self.experiment_designer is None:
            raise RuntimeError("Experiment designer is not configured")
        executed = await self.experiment_designer.execute(experiment, hypothesis)
        return DiscoveryExperimentResponse.model_validate(executed)

    async def get_hypothesis_provenance(
        self,
        hypothesis_id: UUID,
        workspace_id: UUID,
        depth: int,
    ) -> ProvenanceGraphResponse:
        return await self.provenance_graph.query_provenance(
            hypothesis_id,
            workspace_id,
            depth=depth,
        )

    async def get_proximity_clusters(
        self,
        session_id: UUID,
        workspace_id: UUID,
    ) -> ClusterListResponse:
        from platform.discovery.schemas import HypothesisClusterResponse

        items = await self.repository.list_clusters(session_id, workspace_id)
        landscape_status = (
            "saturated"
            if any(item.classification == "over_explored" for item in items)
            else "normal"
        )
        if not items:
            landscape_status = "low_data"
        return ClusterListResponse(
            items=[HypothesisClusterResponse.model_validate(item) for item in items],
            landscape_status=landscape_status,
        )

    async def trigger_proximity_computation(
        self,
        session_id: UUID,
        workspace_id: UUID,
    ) -> ClusterListResponse:
        if self.proximity_clustering is None:
            return await self.get_proximity_clusters(session_id, workspace_id)
        result = await self.proximity_clustering.compute(session_id, workspace_id)
        from platform.discovery.schemas import HypothesisClusterResponse

        return ClusterListResponse(
            items=[HypothesisClusterResponse.model_validate(item) for item in result.clusters],
            landscape_status=result.status,
        )

    async def get_proximity_graph(
        self,
        workspace_id: UUID,
        *,
        session_id: UUID | None,
        include_edges: bool,
        max_nodes: int,
    ) -> ProximityGraphResponse:
        if self.proximity_graph_service is None:
            return ProximityGraphResponse(
                workspace_id=workspace_id,
                session_id=session_id,
                status="pre_proximity",
                saturation_indicator="low_data",
                min_hypotheses_required=self.settings.discovery.min_hypotheses,
                current_embedded_count=0,
            )
        return await self.proximity_graph_service.compute_workspace_graph(
            workspace_id,
            session_id=session_id,
            include_edges=include_edges,
            max_nodes=max_nodes,
        )

    async def get_workspace_proximity_settings(
        self,
        workspace_id: UUID,
    ) -> ProximityWorkspaceSettingsResponse:
        if self.proximity_graph_service is None:
            raise RuntimeError("Proximity graph service is not configured")
        row = await self.proximity_graph_service._get_or_create_workspace_settings(workspace_id)
        return ProximityWorkspaceSettingsResponse(
            workspace_id=row.workspace_id,
            bias_enabled=row.bias_enabled,
            recompute_interval_minutes=row.recompute_interval_minutes,
            last_recomputed_at=row.last_recomputed_at,
            last_transition_summary=row.last_transition_summary,
        )

    async def update_workspace_proximity_settings(
        self,
        workspace_id: UUID,
        payload: ProximityWorkspaceSettingsUpdateRequest,
        actor: UUID,
    ) -> ProximityWorkspaceSettingsResponse:
        del actor
        existing = await self.get_workspace_proximity_settings(workspace_id)
        fields: dict[str, object] = {}
        if payload.bias_enabled is not None:
            fields["bias_enabled"] = payload.bias_enabled
        if payload.recompute_interval_minutes is not None:
            fields["recompute_interval_minutes"] = payload.recompute_interval_minutes
        row = await self.repository.upsert_workspace_settings(
            workspace_id,
            bias_enabled=fields.get("bias_enabled", existing.bias_enabled),
            recompute_interval_minutes=fields.get(
                "recompute_interval_minutes",
                existing.recompute_interval_minutes,
            ),
            last_recomputed_at=existing.last_recomputed_at,
            last_transition_summary=existing.last_transition_summary,
        )
        return ProximityWorkspaceSettingsResponse(
            workspace_id=row.workspace_id,
            bias_enabled=row.bias_enabled,
            recompute_interval_minutes=row.recompute_interval_minutes,
            last_recomputed_at=row.last_recomputed_at,
            last_transition_summary=row.last_transition_summary,
        )

    async def enqueue_workspace_recompute(
        self,
        workspace_id: UUID,
        actor: UUID,
    ) -> RecomputeEnqueuedResponse:
        del actor
        if self.proximity_graph_service is None:
            raise RuntimeError("Proximity graph service is not configured")
        if workspace_id in _RECOMPUTE_IN_FLIGHT:
            raise WorkspaceProximityRecomputeInFlightError(workspace_id)
        _RECOMPUTE_IN_FLIGHT.add(workspace_id)
        try:
            pending = await self.repository.list_hypotheses_pending_embedding(
                workspace_id, limit=100
            )
            for item in pending:
                await self.proximity_graph_service.index_hypothesis(item.id)
            await self.proximity_graph_service.recompute_workspace_graph(workspace_id)
        finally:
            _RECOMPUTE_IN_FLIGHT.discard(workspace_id)
        return RecomputeEnqueuedResponse()

    async def workspace_proximity_recompute_task(self) -> None:
        if self.proximity_graph_service is None:
            return
        for workspace_id in await self.repository.list_active_workspace_ids():
            try:
                pending = await self.repository.list_hypotheses_pending_embedding(
                    workspace_id, limit=100
                )
                for item in pending:
                    await self.proximity_graph_service.index_hypothesis(item.id)
                await self.proximity_graph_service.recompute_workspace_graph(workspace_id)
            except Exception:
                LOGGER.exception(
                    "Discovery workspace proximity recompute failed for workspace %s",
                    workspace_id,
                )

    async def get_session_summary(
        self,
        session_id: UUID,
        workspace_id: UUID,
    ) -> dict[str, object] | None:
        session = await self.repository.get_session(session_id, workspace_id)
        if session is None:
            return None
        top = await self.get_top_hypotheses(session_id, workspace_id, limit=5)
        return {
            "session_id": session.id,
            "status": session.status,
            "current_cycle": session.current_cycle,
            "top_hypothesis": top[0] if top else None,
            "leaderboard_top5": top,
        }

    async def _session(self, session_id: UUID, workspace_id: UUID) -> DiscoverySession:
        session = await self.repository.get_session(session_id, workspace_id)
        if session is None:
            raise DiscoveryNotFoundError("Discovery session", session_id)
        return session

    async def _hypothesis(self, hypothesis_id: UUID, workspace_id: UUID) -> Hypothesis:
        hypothesis = await self.repository.get_hypothesis(hypothesis_id, workspace_id)
        if hypothesis is None:
            raise DiscoveryNotFoundError("Discovery hypothesis", hypothesis_id)
        return hypothesis


def _hypothesis_response(
    hypothesis: Hypothesis,
    *,
    elo_score: float | None,
    rank: int | None = None,
    elo_row: EloScore | None = None,
) -> HypothesisResponse:
    return HypothesisResponse(
        hypothesis_id=hypothesis.id,
        session_id=hypothesis.session_id,
        title=hypothesis.title,
        description=hypothesis.description,
        reasoning=hypothesis.reasoning,
        confidence=hypothesis.confidence,
        generating_agent_fqn=hypothesis.generating_agent_fqn,
        status=hypothesis.status,
        elo_score=elo_score,
        rank=rank,
        wins=0 if elo_row is None else elo_row.wins,
        losses=0 if elo_row is None else elo_row.losses,
        draws=0 if elo_row is None else elo_row.draws,
        cluster_id=hypothesis.cluster_id,
        embedding_status=hypothesis.embedding_status or "pending",
        rationale_metadata=hypothesis.rationale_metadata,
        created_at=hypothesis.created_at,
    )


def _model_validate_tournament_round(item: TournamentRound) -> TournamentRoundResponse:
    return TournamentRoundResponse.model_validate(item)
