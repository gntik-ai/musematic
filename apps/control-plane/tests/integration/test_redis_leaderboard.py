from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_add_and_rank(redis_client) -> None:
    scores = {
        "hyp-a": 1500,
        "hyp-b": 1650,
        "hyp-c": 1400,
        "hyp-d": 1720,
        "hyp-e": 1600,
    }
    for hypothesis_id, score in scores.items():
        await redis_client.leaderboard_add("t1", hypothesis_id, score)

    top = await redis_client.leaderboard_top("t1", 5)
    rank = await redis_client.leaderboard_rank("t1", "hyp-c")

    assert len(top) == 5
    assert top[0][0] == "hyp-d"
    assert rank == 4


@pytest.mark.asyncio
async def test_score_update(redis_client) -> None:
    await redis_client.leaderboard_add("t2", "hyp-a", 1500)
    await redis_client.leaderboard_add("t2", "hyp-b", 1600)
    await redis_client.leaderboard_add("t2", "hyp-a", 1400)

    assert await redis_client.leaderboard_rank("t2", "hyp-a") == 1


@pytest.mark.asyncio
async def test_top_n(redis_client) -> None:
    for index in range(10):
        await redis_client.leaderboard_add("t3", f"hyp-{index}", 1000 + index)

    top = await redis_client.leaderboard_top("t3", 3)

    assert len(top) == 3
    assert [entry[0] for entry in top] == ["hyp-9", "hyp-8", "hyp-7"]


@pytest.mark.asyncio
async def test_remove_entry(redis_client) -> None:
    await redis_client.leaderboard_add("t4", "hyp-a", 1500)
    await redis_client.leaderboard_add("t4", "hyp-b", 1600)

    assert await redis_client.leaderboard_remove("t4", "hyp-a") is True
    assert await redis_client.leaderboard_rank("t4", "hyp-a") is None


@pytest.mark.asyncio
async def test_rank_of_specific(redis_client) -> None:
    scores = [1700, 1650, 1600, 1550, 1500]
    for index, score in enumerate(scores):
        await redis_client.leaderboard_add("t5", f"hyp-{index}", score)

    assert await redis_client.leaderboard_rank("t5", "hyp-2") == 2

