from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.discovery.critique.evaluator import CritiqueEvaluator
from platform.discovery.events import DiscoveryEventPublisher
from platform.discovery.models import GDECycle, Hypothesis
from platform.discovery.repository import DiscoveryRepository
from platform.discovery.tournament.comparator import TournamentComparator, WorkflowServiceInterface
from typing import Any
from uuid import UUID


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
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.publisher = publisher
        self.tournament = tournament
        self.critique_evaluator = critique_evaluator
        self.workflow_service = workflow_service

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
        if self.workflow_service is None:
            active = await self.repository.list_active_hypotheses(session.id, session.workspace_id)
            count = max(1, self.settings.discovery.min_hypotheses - len(active))
            generated: list[Hypothesis] = []
            for index in range(count):
                hypothesis = await self.repository.create_hypothesis(
                    Hypothesis(
                        session_id=session.id,
                        cycle_id=cycle.id,
                        workspace_id=session.workspace_id,
                        title=f"Hypothesis {cycle.cycle_number}.{index + 1}",
                        description=f"Candidate explanation for {session.research_question}",
                        reasoning="Generated by local GDE fallback",
                        confidence=0.6 + index * 0.05,
                        generating_agent_fqn="discovery.generator.local",
                        status="active",
                    )
                )
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
                generated.append(hypothesis)
            return generated
        result = await self.workflow_service.create_execution(
            None,
            {
                "task": "generate_discovery_hypotheses",
                "research_question": session.research_question,
                "corpus_refs": session.corpus_refs,
                "cycle_number": cycle.cycle_number,
            },
            session.workspace_id,
            actor_id,
        )
        payload = result if isinstance(result, dict) else getattr(result, "payload", {})
        raw_items = payload.get("hypotheses", [])
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
                )
            )
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
            generated.append(hypothesis)
        return generated

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
        # The first completed cycle cannot prove stability.
        if top_score <= 0:
            return None, False
        delta = abs(top_score - self.settings.discovery.elo_default_score) / top_score
        return delta, delta < self.settings.discovery.convergence_threshold
