from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.context_engineering.models import ContextSourceType
from platform.context_engineering.quality_scorer import QualityScorer

import pytest

from tests.context_engineering_support import build_element


@pytest.mark.asyncio
async def test_quality_scorer_computes_expected_subscores() -> None:
    scorer = QualityScorer()
    now = datetime.now(UTC)
    elements = [
        build_element(
            source_type=ContextSourceType.system_instructions,
            content="verify payment exception and summarize outcome",
            timestamp=now - timedelta(minutes=5),
            authority_score=1.0,
            metadata={"claim_key": "summary"},
        ),
        build_element(
            source_type=ContextSourceType.tool_outputs,
            content="summary: payment exception resolved",
            timestamp=now - timedelta(hours=1),
            authority_score=0.9,
            metadata={"claim_key": "summary"},
        ),
    ]

    score = await scorer.score(elements, "verify payment exception")

    assert score.relevance > 0.5
    assert score.freshness > 0.8
    assert score.authority >= 0.9
    assert score.contradiction_density == 1.0
    assert score.token_efficiency > 0.0
    assert score.task_brief_coverage == 1.0
    assert 0.0 <= score.aggregate <= 1.0


@pytest.mark.asyncio
async def test_quality_scorer_detects_contradictions_and_empty_inputs() -> None:
    scorer = QualityScorer()
    contradictory = [
        build_element(content="status: approved", metadata={"claim_key": "status"}),
        build_element(content="status: denied", metadata={"claim_key": "status"}),
    ]

    conflict_score = await scorer.score(contradictory, "status")
    empty_score = await scorer.score([], "anything")

    assert conflict_score.contradiction_density < 1.0
    assert scorer.score_element_relevance(contradictory[0], "approved status") > 0.0
    assert empty_score.aggregate == 0.0
