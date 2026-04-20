from __future__ import annotations

import logging
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.discovery.critique.evaluator import CritiqueEvaluator
from platform.discovery.events import DiscoveryEventPublisher
from platform.discovery.models import GDECycle, Hypothesis
from platform.discovery.proximity.graph import BiasSignal, ProximityGraphService
from platform.discovery.repository import DiscoveryRepository
from platform.discovery.tournament.comparator import TournamentComparator, WorkflowServiceInterface
from typing import Any
from uuid import UUID

LOGGER = logging.getLogger(__name__)


class GDECycleOrchestrator:
    """Run a generate-debate-evolve cycle for a discovery session."""

    def __init__(
        self,
        *,
        repository: DiscoveryRepository,
        settings: PlatformSettings,
        publisher: DiscoveryEventPublisher,
        tournament: TournamentComparator,
        critique_evaluator: CritiqueEvaluator,
        workflow_service: WorkflowServiceInterface | None = None,
        proximity_graph_service: ProximityGraphService | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.publisher = publisher
        self.tournament = tournament
        self.critique_evaluator = critique_evaluator
        self.workflow_service = workflow_service
        self.proximity_graph_service = proximity_graph_service

    async def run_cycle(
        self,
        *,
        session_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
    ) -> GDECycle:
        session = await self.repository.get_session(session_id, workspace_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        cycle_number = session.current_cycle + 1
        cycle = await self.repository.create_cycle(
            GDECycle(
                session_id=session_id,
                workspace_id=workspace_id,
                cycle_number=cycle_number,
                status="running",
                generation_count=0,
                debate_record={},
                refinement_count=0,
                convergence_metric=None,
                converged=False,
            )
        )
        generated = await self._generate_hypotheses(session, cycle, actor_id)
        for hypothesis in generated:
            await self.publisher.hypothesis_generated(session_id, workspace_id, hypothesis.id)
            await self.critique_evaluator.critique_hypothesis(
                hypothesis,
                ["discovery.reviewer.consistency", "discovery.reviewer.novelty"],
                actor_id=actor_id,
            )
        active = await self.repository.list_active_hypotheses(session_id, workspace_id)
        if len(active) >= 2:
            await self.tournament.run_round(
                session_id=session_id,
                workspace_id=workspace_id,
                hypotheses=active,
                actor_id=actor_id,
                cycle_id=cycle.id,
            )
        debate_record = await self._debate(active, workspace_id, actor_id)
        convergence_metric, converged = await self._check_convergence(session_id)
        status = "completed"
        if cycle_number >= int(
            session.config.get("max_cycles", self.settings.discovery.max_cycles_default)
        ):
            await self.repository.update_session_status(
                session_id,
                workspace_id,
                "iteration_limit_reached",
                current_cycle=cycle_number,
                convergence_metrics={"last_delta": convergence_metric},
            )
        elif converged:
            await self.repository.update_session_status(
                session_id,
                workspace_id,
                "converged",
                current_cycle=cycle_number,
                convergence_metrics={"last_delta": convergence_metric},
            )
        else:
            await self.repository.update_session_status(
                session_id,
                workspace_id,
                "active",
                current_cycle=cycle_number,
                convergence_metrics={"last_delta": convergence_metric},
            )
        completed = await self.repository.complete_cycle(
            cycle,
            status=status,
            generation_count=len(generated),
            refinement_count=0,
            debate_record=debate_record,
            convergence_metric=convergence_metric,
            converged=converged,
        )
        await self.publisher.cycle_completed(session_id, workspace_id, completed.id, converged)
        if converged:
            await self.publisher.session_converged(session_id, workspace_id, completed.id)
        return completed

    async def _generate_hypotheses(
        self,
        session: Any,
        cycle: GDECycle,
        actor_id: UUID,
    ) -> list[Hypothesis]:
        bias_signal = await self._derive_bias_signal(session)
        bias_metadata = _bias_metadata(bias_signal)
        if self.workflow_service is None:
            active = await self.repository.list_active_hypotheses(session.id, session.workspace_id)
            count = max(1, self.settings.discovery.min_hypotheses - len(active))
            generated: list[Hypothesis] = []
            for index in range(count):
                reasoning = "Generated by local GDE fallback"
                if not bias_signal.skipped:
                    reasoning += (
                        f" | explore={', '.join(bias_signal.explore_hints)}"
                        f" | avoid={', '.join(bias_signal.avoid_hints)}"
                    )
                hypothesis = await self.repository.create_hypothesis(
                    Hypothesis(
                        session_id=session.id,
                        cycle_id=cycle.id,
                        workspace_id=session.workspace_id,
                        title=f"Hypothesis {cycle.cycle_number}.{index + 1}",
                        description=f"Candidate explanation for {session.research_question}",
                        reasoning=reasoning,
                        confidence=0.6 + index * 0.05,
                        generating_agent_fqn="discovery.generator.local",
                        status="active",
                        rationale_metadata=bias_metadata,
                    )
                )
                await self._seed_elo(session, hypothesis)
                await self._index_hypothesis(hypothesis)
                generated.append(hypothesis)
            return generated
        payload: dict[str, Any] = {
            "task": "generate_discovery_hypotheses",
            "research_question": session.research_question,
            "corpus_refs": session.corpus_refs,
            "cycle_number": cycle.cycle_number,
        }
        if not bias_signal.skipped:
            payload["explore_hints"] = bias_signal.explore_hints
            payload["avoid_hints"] = bias_signal.avoid_hints
            payload["bias_signal"] = {
                "source": bias_signal.source,
                "generated_at": bias_signal.generated_at.isoformat(),
            }
        result = await self.workflow_service.create_execution(
            None,
            payload,
            session.workspace_id,
            actor_id,
        )
        workflow_payload = result if isinstance(result, dict) else getattr(result, "payload", {})
        raw_items = workflow_payload.get("hypotheses", [])
        generated = []
        for item in raw_items:
            hypothesis = await self.repository.create_hypothesis(
                Hypothesis(
                    session_id=session.id,
                    cycle_id=cycle.id,
                    workspace_id=session.workspace_id,
                    title=str(item.get("title", "Generated hypothesis")),
                    description=str(item.get("description", "")),
                    reasoning=str(item.get("reasoning", "")),
                    confidence=float(item.get("confidence", 0.5)),
                    generating_agent_fqn=str(
                        item.get("generating_agent_fqn", "discovery.generator.workflow")
                    ),
                    status="active",
                    rationale_metadata=bias_metadata,
                )
            )
            await self._seed_elo(session, hypothesis)
            await self._index_hypothesis(hypothesis)
            generated.append(hypothesis)
        return generated

    async def _seed_elo(self, session: Any, hypothesis: Hypothesis) -> None:
        await self.tournament.elo_engine.update_redis_leaderboard(
            session.id,
            hypothesis.id,
            self.settings.discovery.elo_default_score,
        )
        await self.tournament.elo_engine.persist_elo_score(
            hypothesis_id=hypothesis.id,
            session_id=session.id,
            workspace_id=session.workspace_id,
            new_score=self.settings.discovery.elo_default_score,
        )

    async def _index_hypothesis(self, hypothesis: Hypothesis) -> None:
        if self.proximity_graph_service is None:
            return
        try:
            result = await self.proximity_graph_service.index_hypothesis(hypothesis.id)
            hypothesis.embedding_status = result.status
        except Exception:
            LOGGER.exception("Hypothesis embedding failed for %s", hypothesis.id)
            hypothesis.embedding_status = "pending"
            await self.repository.session.flush()

    async def _derive_bias_signal(self, session: Any) -> BiasSignal:
        if self.proximity_graph_service is None:
            return BiasSignal(
                workspace_id=session.workspace_id,
                session_id=session.id,
                explore_hints=[],
                avoid_hints=[],
                source="session_scope",
                generated_at=cycle_time(),
                skipped=True,
                skip_reason="bias_disabled",
            )
        try:
            return await self.proximity_graph_service.derive_bias_signal(
                session.workspace_id,
                session.id,
            )
        except Exception:
            LOGGER.exception(
                "Failed to derive discovery bias signal for workspace %s session %s",
                session.workspace_id,
                session.id,
            )
            return BiasSignal(
                workspace_id=session.workspace_id,
                session_id=session.id,
                explore_hints=[],
                avoid_hints=[],
                source="session_scope",
                generated_at=cycle_time(),
                skipped=True,
                skip_reason="graph_stale",
            )

    async def _debate(
        self,
        hypotheses: list[Hypothesis],
        workspace_id: UUID,
        actor_id: UUID,
    ) -> dict[str, Any]:
        if not hypotheses:
            return {"arguments": []}
        if self.workflow_service is None:
            return {
                "arguments": [
                    {
                        "hypothesis_id": str(hypothesis.id),
                        "for_arguments": [hypothesis.reasoning],
                        "against_arguments": [],
                    }
                    for hypothesis in hypotheses[:3]
                ]
            }
        result = await self.workflow_service.create_execution(
            None,
            {"task": "debate_discovery_hypotheses", "hypotheses": [h.title for h in hypotheses]},
            workspace_id,
            actor_id,
        )
        return result if isinstance(result, dict) else dict(getattr(result, "payload", {}) or {})

    async def _check_convergence(self, session_id: UUID) -> tuple[float | None, bool]:
        leaderboard = await self.tournament.elo_engine.get_leaderboard(session_id, limit=1)
        if not leaderboard:
            return None, False
        top_score = leaderboard[0].elo_score
        if top_score <= 0:
            return None, False
        delta = abs(top_score - self.settings.discovery.elo_default_score) / top_score
        return delta, delta < self.settings.discovery.convergence_threshold


def _bias_metadata(signal: BiasSignal) -> dict[str, Any]:
    if signal.skipped:
        return {
            "bias_applied": False,
            "skip_reason": signal.skip_reason,
            "min_hypotheses_required": signal.min_hypotheses_required,
            "current_embedded_count": signal.current_embedded_count,
        }
    return {
        "bias_applied": True,
        "targeted_gap": signal.explore_hints[0] if signal.explore_hints else None,
        "avoided_clusters": signal.avoid_hints,
        "source": signal.source,
    }


def cycle_time() -> datetime:
    return datetime.now(UTC)
