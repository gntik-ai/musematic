from __future__ import annotations

from platform.discovery.tournament.elo import EloRatingEngine
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


def test_compute_new_ratings_for_win_loss_and_draw() -> None:
    win_a, loss_b = EloRatingEngine.compute_new_ratings(1000.0, 1000.0, "a_wins", 32)
    loss_a, win_b = EloRatingEngine.compute_new_ratings(1000.0, 1000.0, "b_wins", 32)
    draw_a, draw_b = EloRatingEngine.compute_new_ratings(1200.0, 1000.0, "draw", 32)

    assert win_a == pytest.approx(1016.0)
    assert loss_b == pytest.approx(984.0)
    assert loss_a == pytest.approx(984.0)
    assert win_b == pytest.approx(1016.0)
    assert draw_a + draw_b == pytest.approx(2200.0)


@pytest.mark.asyncio
async def test_redis_leaderboard_is_updated_under_lock() -> None:
    session_id = uuid4()
    hypothesis_id = uuid4()
    redis = SimpleNamespace(
        acquire_lock=AsyncMock(return_value=SimpleNamespace(success=True, token="tok")),
        release_lock=AsyncMock(return_value=True),
        leaderboard_add=AsyncMock(),
        leaderboard_top=AsyncMock(return_value=[(str(hypothesis_id), 1016.0)]),
        leaderboard_score=AsyncMock(return_value=1016.0),
    )
    engine = EloRatingEngine(redis=redis, repository=None)

    await engine.update_redis_leaderboard(session_id, hypothesis_id, 1016.0)
    leaderboard = await engine.get_leaderboard(session_id, 5)

    redis.acquire_lock.assert_awaited_once_with("discovery:elo", str(session_id), ttl_seconds=10)
    redis.leaderboard_add.assert_awaited_once_with(str(session_id), str(hypothesis_id), 1016.0)
    redis.release_lock.assert_awaited_once_with("discovery:elo", str(session_id), "tok")
    assert leaderboard[0].hypothesis_id == hypothesis_id
    assert leaderboard[0].rank == 1


@pytest.mark.asyncio
async def test_apply_evidence_bonus_persists_score() -> None:
    session_id = uuid4()
    hypothesis_id = uuid4()
    workspace_id = uuid4()
    redis = SimpleNamespace(
        acquire_lock=AsyncMock(return_value=SimpleNamespace(success=True, token="tok")),
        release_lock=AsyncMock(return_value=True),
        leaderboard_add=AsyncMock(),
        leaderboard_score=AsyncMock(return_value=1000.0),
    )
    repo = SimpleNamespace(
        upsert_elo_score=AsyncMock(),
        get_elo_score=AsyncMock(return_value=None),
    )
    engine = EloRatingEngine(redis=redis, repository=repo)

    new_score = await engine.apply_evidence_bonus(
        session_id=session_id,
        hypothesis_id=hypothesis_id,
        workspace_id=workspace_id,
        bonus=10.0,
    )

    assert new_score == 1010.0
    repo.upsert_elo_score.assert_awaited_once()


@pytest.mark.asyncio
async def test_elo_repository_fallback_and_lock_failure() -> None:
    session_id = uuid4()
    hypothesis_id = uuid4()
    repo = SimpleNamespace(
        zadd_elo=AsyncMock(),
        zrevrange_leaderboard=AsyncMock(return_value=[(str(hypothesis_id), 900.0)]),
        zscore_hypothesis=AsyncMock(return_value=None),
        get_elo_score=AsyncMock(return_value=SimpleNamespace(current_score=875.0)),
        upsert_elo_score=AsyncMock(),
    )
    engine = EloRatingEngine(redis=None, repository=repo, default_score=1000.0)

    await engine.update_redis_leaderboard(session_id, hypothesis_id, 900.0)
    await engine.batch_update_redis_leaderboard(session_id, {hypothesis_id: 910.0})
    leaderboard = await engine.get_leaderboard(session_id, 1)
    score = await engine.current_score(session_id, hypothesis_id)

    assert leaderboard[0].elo_score == 900.0
    assert score == 875.0
    assert repo.zadd_elo.await_count == 2

    redis = SimpleNamespace(acquire_lock=AsyncMock(return_value=SimpleNamespace(success=False)))
    with pytest.raises(RuntimeError):
        await EloRatingEngine(redis=redis, repository=None).update_redis_leaderboard(
            session_id,
            hypothesis_id,
            1000.0,
        )


@pytest.mark.asyncio
async def test_elo_empty_defaults_and_batch_locking() -> None:
    session_id = uuid4()
    hypothesis_id = uuid4()
    assert await EloRatingEngine(redis=None, repository=None).get_leaderboard(session_id) == []
    assert (
        await EloRatingEngine(redis=None, repository=None).current_score(
            session_id,
            hypothesis_id,
        )
        == 1000.0
    )
    await EloRatingEngine(redis=None, repository=None).persist_elo_score(
        hypothesis_id=hypothesis_id,
        session_id=session_id,
        workspace_id=uuid4(),
        new_score=1000.0,
    )

    redis = SimpleNamespace(
        acquire_lock=AsyncMock(return_value=SimpleNamespace(success=True, token="tok")),
        release_lock=AsyncMock(),
        leaderboard_add=AsyncMock(),
    )
    engine = EloRatingEngine(redis=redis, repository=None)
    await engine.batch_update_redis_leaderboard(session_id, {hypothesis_id: 1001.0})
    assert redis.leaderboard_add.await_count == 1

    redis.acquire_lock.return_value = SimpleNamespace(success=True, token=None)
    with pytest.raises(RuntimeError):
        await engine.batch_update_redis_leaderboard(session_id, {hypothesis_id: 1002.0})
