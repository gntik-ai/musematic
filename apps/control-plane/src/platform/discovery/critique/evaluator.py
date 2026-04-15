from __future__ import annotations

from platform.discovery.events import DiscoveryEventPublisher
from platform.discovery.models import Hypothesis, HypothesisCritique
from platform.discovery.repository import DiscoveryRepository
from platform.discovery.tournament.comparator import WorkflowServiceInterface
from statistics import fmean, pstdev
from typing import Any
from uuid import UUID

CRITIQUE_DIMENSIONS = ("consistency", "novelty", "testability", "evidence_support", "impact")


class CritiqueEvaluator:
    """Run reviewer-agent critiques and aggregate dimension scores."""

    def __init__(
        self,
        *,
        repository: DiscoveryRepository,
        publisher: DiscoveryEventPublisher,
        workflow_service: WorkflowServiceInterface | None = None,
    ) -> None:
        self.repository = repository
        self.publisher = publisher
        self.workflow_service = workflow_service

    async def critique_hypothesis(
        self,
        hypothesis: Hypothesis,
        reviewer_agents: list[str],
        *,
        actor_id: UUID | None = None,
    ) -> list[HypothesisCritique]:
        critiques: list[HypothesisCritique] = []
        for reviewer in reviewer_agents:
            scores = await self._run_reviewer(hypothesis, reviewer, actor_id)
            critiques.append(
                await self.repository.create_critique(
                    HypothesisCritique(
                        hypothesis_id=hypothesis.id,
                        session_id=hypothesis.session_id,
                        workspace_id=hypothesis.workspace_id,
                        reviewer_agent_fqn=reviewer,
                        scores=scores,
                        composite_summary=None,
                        is_aggregated=False,
                    )
                )
            )
        if critiques:
            critiques.append(await self.aggregate_critiques(hypothesis.id, hypothesis.workspace_id))
            await self.publisher.critique_completed(
                hypothesis.session_id,
                hypothesis.workspace_id,
                hypothesis.id,
            )
        return critiques

    async def aggregate_critiques(
        self,
        hypothesis_id: UUID,
        workspace_id: UUID,
    ) -> HypothesisCritique:
        rows = [
            row
            for row in await self.repository.list_critiques(hypothesis_id, workspace_id)
            if not row.is_aggregated
        ]
        if not rows:
            raise ValueError("Cannot aggregate zero critiques")
        per_dimension: dict[str, float] = {}
        disagreements: list[str] = []
        for dimension in CRITIQUE_DIMENSIONS:
            values = [float(row.scores[dimension]["score"]) for row in rows]
            per_dimension[dimension] = fmean(values)
            if len(values) > 1 and pstdev(values) > 0.3:
                disagreements.append(dimension)
        aggregate_scores = {
            dimension: {
                "score": value,
                "confidence": fmean(float(row.scores[dimension]["confidence"]) for row in rows),
                "reasoning": "Aggregated reviewer score",
            }
            for dimension, value in per_dimension.items()
        }
        summary = {
            "per_dimension_averages": per_dimension,
            "disagreement_flags": disagreements,
            "reviewer_count": len(rows),
        }
        first = rows[0]
        return await self.repository.create_critique(
            HypothesisCritique(
                hypothesis_id=hypothesis_id,
                session_id=first.session_id,
                workspace_id=workspace_id,
                reviewer_agent_fqn="aggregate",
                scores=aggregate_scores,
                composite_summary=summary,
                is_aggregated=True,
            )
        )

    async def _run_reviewer(
        self,
        hypothesis: Hypothesis,
        reviewer: str,
        actor_id: UUID | None,
    ) -> dict[str, dict[str, Any]]:
        if self.workflow_service is None:
            base = max(0.0, min(1.0, hypothesis.confidence))
            return {
                dimension: {
                    "score": base,
                    "confidence": 0.8,
                    "reasoning": f"Heuristic {dimension} score",
                }
                for dimension in CRITIQUE_DIMENSIONS
            }
        result = await self.workflow_service.create_execution(
            None,
            {
                "task": "critique_hypothesis",
                "reviewer_agent_fqn": reviewer,
                "hypothesis": {
                    "hypothesis_id": str(hypothesis.id),
                    "title": hypothesis.title,
                    "description": hypothesis.description,
                    "reasoning": hypothesis.reasoning,
                },
            },
            hypothesis.workspace_id,
            actor_id or hypothesis.id,
        )
        payload = result if isinstance(result, dict) else getattr(result, "payload", {})
        scores = payload.get("scores", payload)
        return normalize_scores(scores)


def normalize_scores(raw_scores: dict[str, Any]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for dimension in CRITIQUE_DIMENSIONS:
        value = raw_scores.get(dimension, {})
        if isinstance(value, int | float):
            value = {"score": float(value), "confidence": 0.8, "reasoning": ""}
        normalized[dimension] = {
            "score": _clamp(float(value.get("score", 0.5))),
            "confidence": _clamp(float(value.get("confidence", 0.8))),
            "reasoning": str(value.get("reasoning", "")),
        }
    return normalized


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
