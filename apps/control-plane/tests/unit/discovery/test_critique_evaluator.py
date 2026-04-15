from __future__ import annotations

from datetime import UTC, datetime
from platform.discovery.critique.evaluator import CritiqueEvaluator, normalize_scores
from platform.discovery.models import Hypothesis, HypothesisCritique
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_critique_hypothesis_aggregates_scores_and_flags_disagreement() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    hypothesis = Hypothesis(
        id=uuid4(),
        workspace_id=workspace_id,
        session_id=session_id,
        title="h",
        description="d",
        reasoning="r",
        confidence=0.8,
        generating_agent_fqn="agent",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    rows: list[HypothesisCritique] = []

    async def create_critique(row):
        row.id = uuid4()
        row.created_at = datetime.now(UTC)
        rows.append(row)
        return row

    repo = SimpleNamespace(
        create_critique=AsyncMock(side_effect=create_critique),
        list_critiques=AsyncMock(side_effect=lambda *_: rows),
    )
    publisher = SimpleNamespace(critique_completed=AsyncMock())
    workflow = SimpleNamespace(
        create_execution=AsyncMock(
            side_effect=[
                {"scores": {"consistency": 0.1, "novelty": 0.5}},
                {"scores": {"consistency": 0.9, "novelty": 0.5}},
            ]
        )
    )
    evaluator = CritiqueEvaluator(
        repository=repo,
        publisher=publisher,
        workflow_service=workflow,
    )

    result = await evaluator.critique_hypothesis(hypothesis, ["r1", "r2"], actor_id=uuid4())

    assert len(result) == 3
    assert result[-1].is_aggregated is True
    assert "consistency" in result[-1].composite_summary["disagreement_flags"]
    publisher.critique_completed.assert_awaited_once_with(session_id, workspace_id, hypothesis.id)


def test_normalize_scores_fills_all_dimensions() -> None:
    scores = normalize_scores({"impact": {"score": 2.0, "confidence": -1.0}})

    assert set(scores) == {"consistency", "novelty", "testability", "evidence_support", "impact"}
    assert scores["impact"]["score"] == 1.0
    assert scores["impact"]["confidence"] == 0.0
