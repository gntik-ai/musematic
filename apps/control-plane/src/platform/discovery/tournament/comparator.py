from __future__ import annotations

from collections.abc import Sequence
from platform.discovery.events import DiscoveryEventPublisher
from platform.discovery.models import Hypothesis, TournamentRound
from platform.discovery.repository import DiscoveryRepository
from platform.discovery.tournament.elo import EloRatingEngine, Outcome
from typing import Any, Literal, Protocol
from uuid import UUID

EloResult = Literal["win", "loss", "draw"]


class WorkflowServiceInterface(Protocol):
    async def create_execution(
        self,
        workflow_definition_id: UUID | None,
        input_context: dict[str, Any],
        workspace_id: UUID,
        triggered_by: UUID,
    ) -> Any: ...


class TournamentComparator:
    """Dispatch pairwise comparisons and update Elo rankings."""

    def __init__(
        self,
        *,
        repository: DiscoveryRepository,
        elo_engine: EloRatingEngine,
        publisher: DiscoveryEventPublisher,
        workflow_service: WorkflowServiceInterface | None = None,
    ) -> None:
        self.repository = repository
        self.elo_engine = elo_engine
        self.publisher = publisher
        self.workflow_service = workflow_service

    @staticmethod
    def build_pairs(
        hypotheses: Sequence[Hypothesis],
    ) -> tuple[list[tuple[Hypothesis, Hypothesis]], Hypothesis | None]:
        """Build deterministic tournament pairs, carrying the last item as a bye."""
        items = list(hypotheses)
        bye = items.pop() if len(items) % 2 == 1 else None
        pairs = [(items[index], items[index + 1]) for index in range(0, len(items), 2)]
        return pairs, bye

    @staticmethod
    def build_all_pairs(hypotheses: Sequence[Hypothesis]) -> list[tuple[Hypothesis, Hypothesis]]:
        items = list(hypotheses)
        return [(left, right) for index, left in enumerate(items) for right in items[index + 1 :]]

    async def run_round(
        self,
        *,
        session_id: UUID,
        workspace_id: UUID,
        hypotheses: Sequence[Hypothesis],
        actor_id: UUID,
        cycle_id: UUID | None = None,
        all_pairs: bool = False,
    ) -> TournamentRound:
        pairs, bye = (
            (self.build_all_pairs(hypotheses), None) if all_pairs else self.build_pairs(hypotheses)
        )
        round_number = await self.repository.next_round_number(session_id)
        pairwise_results: list[dict[str, Any]] = []
        elo_changes: list[dict[str, Any]] = []
        redis_updates: dict[UUID, float] = {}

        for hyp_a, hyp_b in pairs:
            outcome, reasoning = await self._compare(hyp_a, hyp_b, workspace_id, actor_id)
            old_a = await self.elo_engine.current_score(session_id, hyp_a.id)
            old_b = await self.elo_engine.current_score(session_id, hyp_b.id)
            new_a, new_b = self.elo_engine.compute_new_ratings(
                old_a,
                old_b,
                outcome,
                self.elo_engine.k_factor,
            )
            redis_updates[hyp_a.id] = new_a
            redis_updates[hyp_b.id] = new_b
            result_a, result_b = _outcome_to_results(outcome)
            await self.elo_engine.persist_elo_score(
                hypothesis_id=hyp_a.id,
                session_id=session_id,
                workspace_id=workspace_id,
                new_score=new_a,
                result=result_a,
                round_number=round_number,
            )
            await self.elo_engine.persist_elo_score(
                hypothesis_id=hyp_b.id,
                session_id=session_id,
                workspace_id=workspace_id,
                new_score=new_b,
                result=result_b,
                round_number=round_number,
            )
            pairwise_results.append(
                {
                    "hyp_a_id": str(hyp_a.id),
                    "hyp_b_id": str(hyp_b.id),
                    "outcome": outcome,
                    "reasoning": reasoning,
                }
            )
            elo_changes.extend(
                [
                    {
                        "hypothesis_id": str(hyp_a.id),
                        "old_elo": old_a,
                        "new_elo": new_a,
                        "delta": new_a - old_a,
                    },
                    {
                        "hypothesis_id": str(hyp_b.id),
                        "old_elo": old_b,
                        "new_elo": new_b,
                        "delta": new_b - old_b,
                    },
                ]
            )

        if redis_updates:
            await self.elo_engine.batch_update_redis_leaderboard(session_id, redis_updates)

        tournament_round = await self.repository.create_tournament_round(
            TournamentRound(
                session_id=session_id,
                workspace_id=workspace_id,
                cycle_id=cycle_id,
                round_number=round_number,
                pairwise_results=pairwise_results,
                elo_changes=elo_changes,
                bye_hypothesis_id=None if bye is None else bye.id,
                status="completed",
            )
        )
        await self.publisher.tournament_round_completed(
            session_id,
            workspace_id,
            tournament_round.id,
        )
        return tournament_round

    async def _compare(
        self,
        hyp_a: Hypothesis,
        hyp_b: Hypothesis,
        workspace_id: UUID,
        actor_id: UUID,
    ) -> tuple[Outcome, str]:
        if self.workflow_service is None:
            if hyp_a.confidence > hyp_b.confidence:
                return "a_wins", "Higher confidence heuristic"
            if hyp_b.confidence > hyp_a.confidence:
                return "b_wins", "Higher confidence heuristic"
            return "draw", "Equal confidence heuristic"
        result = await self.workflow_service.create_execution(
            None,
            {
                "task": "compare_hypotheses",
                "hypothesis_a": _hypothesis_payload(hyp_a),
                "hypothesis_b": _hypothesis_payload(hyp_b),
            },
            workspace_id,
            actor_id,
        )
        payload = result if isinstance(result, dict) else getattr(result, "payload", {})
        raw_outcome = str(payload.get("outcome") or payload.get("winner") or "draw")
        if raw_outcome in {"a", "hypothesis_a", str(hyp_a.id), "a_wins"}:
            outcome: Outcome = "a_wins"
        elif raw_outcome in {"b", "hypothesis_b", str(hyp_b.id), "b_wins"}:
            outcome = "b_wins"
        else:
            outcome = "draw"
        return outcome, str(payload.get("reasoning") or "")


def _outcome_to_results(outcome: Outcome) -> tuple[EloResult, EloResult]:
    if outcome == "a_wins":
        return "win", "loss"
    if outcome == "b_wins":
        return "loss", "win"
    return "draw", "draw"


def _hypothesis_payload(hypothesis: Hypothesis) -> dict[str, Any]:
    return {
        "hypothesis_id": str(hypothesis.id),
        "title": hypothesis.title,
        "description": hypothesis.description,
        "reasoning": hypothesis.reasoning,
        "confidence": hypothesis.confidence,
    }
