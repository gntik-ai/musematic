from __future__ import annotations

from datetime import UTC, datetime
from platform.discovery.models import Hypothesis
from platform.discovery.tournament.comparator import TournamentComparator
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


def _hypothesis(title: str, confidence: float = 0.5) -> Hypothesis:
    return Hypothesis(
        id=uuid4(),
        workspace_id=uuid4(),
        session_id=uuid4(),
        title=title,
        description=title,
        reasoning="r",
        confidence=confidence,
        generating_agent_fqn="agent",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_build_pairs_handles_odd_bye_and_all_pairs() -> None:
    hypotheses = [_hypothesis(str(index)) for index in range(5)]

    pairs, bye = TournamentComparator.build_pairs(hypotheses)
    all_pairs = TournamentComparator.build_all_pairs(hypotheses[:4])

    assert len(pairs) == 2
    assert bye is hypotheses[-1]
    assert len(all_pairs) == 6


@pytest.mark.asyncio
async def test_run_round_writes_round_and_publishes_event() -> None:
    workspace_id = uuid4()
    session_id = uuid4()
    hypotheses = [_hypothesis("a", 0.9), _hypothesis("b", 0.4)]
    for hypothesis in hypotheses:
        hypothesis.workspace_id = workspace_id
        hypothesis.session_id = session_id
    repo = SimpleNamespace(
        next_round_number=AsyncMock(return_value=1),
        create_tournament_round=AsyncMock(side_effect=lambda row: row),
    )
    elo = SimpleNamespace(
        k_factor=32,
        current_score=AsyncMock(return_value=1000.0),
        compute_new_ratings=lambda a, b, outcome, k: (1016.0, 984.0),
        persist_elo_score=AsyncMock(),
        batch_update_redis_leaderboard=AsyncMock(),
    )
    publisher = SimpleNamespace(tournament_round_completed=AsyncMock())
    comparator = TournamentComparator(repository=repo, elo_engine=elo, publisher=publisher)

    row = await comparator.run_round(
        session_id=session_id,
        workspace_id=workspace_id,
        hypotheses=hypotheses,
        actor_id=uuid4(),
    )

    assert row.status == "completed"
    assert row.pairwise_results[0]["outcome"] == "a_wins"
    assert row.elo_changes[0]["new_elo"] == 1016.0
    publisher.tournament_round_completed.assert_awaited_once()


@pytest.mark.asyncio
async def test_workflow_comparison_normalizes_outcomes() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    hyp_a = _hypothesis("a", 0.1)
    hyp_b = _hypothesis("b", 0.9)
    hyp_a.workspace_id = workspace_id
    hyp_b.workspace_id = workspace_id
    workflow = SimpleNamespace(
        create_execution=AsyncMock(
            side_effect=[
                {"outcome": "hypothesis_a", "reasoning": "a"},
                {"winner": str(hyp_b.id), "reasoning": "b"},
                {"winner": "bad"},
            ]
        )
    )
    comparator = TournamentComparator(
        repository=SimpleNamespace(),
        elo_engine=SimpleNamespace(),
        publisher=SimpleNamespace(),
        workflow_service=workflow,
    )

    assert await comparator._compare(hyp_a, hyp_b, workspace_id, actor_id) == ("a_wins", "a")
    assert await comparator._compare(hyp_a, hyp_b, workspace_id, actor_id) == ("b_wins", "b")
    assert await comparator._compare(hyp_a, hyp_b, workspace_id, actor_id) == ("draw", "")


@pytest.mark.asyncio
async def test_heuristic_compare_covers_b_wins_and_draw() -> None:
    comparator = TournamentComparator(
        repository=SimpleNamespace(),
        elo_engine=SimpleNamespace(),
        publisher=SimpleNamespace(),
    )
    workspace_id = uuid4()
    actor_id = uuid4()

    assert (
        await comparator._compare(
            _hypothesis("a", 0.1), _hypothesis("b", 0.9), workspace_id, actor_id
        )
    )[0] == "b_wins"
    assert (
        await comparator._compare(
            _hypothesis("a", 0.5), _hypothesis("b", 0.5), workspace_id, actor_id
        )
    )[0] == "draw"


@pytest.mark.asyncio
async def test_run_round_with_no_pairs_skips_redis_updates() -> None:
    session_id = uuid4()
    workspace_id = uuid4()
    hypothesis = _hypothesis("bye", 0.5)
    hypothesis.session_id = session_id
    hypothesis.workspace_id = workspace_id
    repo = SimpleNamespace(
        next_round_number=AsyncMock(return_value=1),
        create_tournament_round=AsyncMock(side_effect=lambda row: row),
    )
    elo = SimpleNamespace(
        k_factor=32,
        current_score=AsyncMock(),
        compute_new_ratings=lambda *args: (0.0, 0.0),
        persist_elo_score=AsyncMock(),
        batch_update_redis_leaderboard=AsyncMock(),
    )
    comparator = TournamentComparator(
        repository=repo,
        elo_engine=elo,
        publisher=SimpleNamespace(tournament_round_completed=AsyncMock()),
    )

    row = await comparator.run_round(
        session_id=session_id,
        workspace_id=workspace_id,
        hypotheses=[hypothesis],
        actor_id=uuid4(),
    )

    assert row.bye_hypothesis_id == hypothesis.id
    elo.batch_update_redis_leaderboard.assert_not_awaited()
