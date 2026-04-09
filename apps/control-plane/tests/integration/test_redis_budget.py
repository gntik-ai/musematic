from __future__ import annotations

import asyncio

import pytest

from platform.common.clients.redis import BudgetConfig


@pytest.mark.asyncio
async def test_budget_decrement_allowed(redis_client) -> None:
    await redis_client.init_budget(
        "exec-1",
        "step-1",
        BudgetConfig(max_tokens=1000, max_rounds=10, max_cost=5.0, max_time_ms=30000),
        ttl_seconds=30,
    )

    result = await redis_client.decrement_budget("exec-1", "step-1", "tokens", 100)

    assert result.allowed is True
    assert result.remaining_tokens == 900


@pytest.mark.asyncio
async def test_budget_decrement_rejected(redis_client) -> None:
    await redis_client.init_budget(
        "exec-2",
        "step-1",
        BudgetConfig(max_tokens=100, max_rounds=10, max_cost=5.0, max_time_ms=30000),
        ttl_seconds=30,
    )

    result = await redis_client.decrement_budget("exec-2", "step-1", "tokens", 101)
    budget = await redis_client.get_budget("exec-2", "step-1")

    assert result.allowed is False
    assert budget is not None
    assert budget["used_tokens"] == "0"


@pytest.mark.asyncio
async def test_budget_missing_key_fail_closed(redis_client) -> None:
    result = await redis_client.decrement_budget("missing", "step", "tokens", 10)

    assert result.allowed is False
    assert result.remaining_tokens == -1


@pytest.mark.asyncio
async def test_budget_time_limit(redis_client) -> None:
    await redis_client.init_budget(
        "exec-3",
        "step-1",
        BudgetConfig(max_tokens=100, max_rounds=10, max_cost=5.0, max_time_ms=1),
        ttl_seconds=30,
    )
    await asyncio.sleep(0.01)

    result = await redis_client.decrement_budget("exec-3", "step-1", "tokens", 1)

    assert result.allowed is False
    assert result.remaining_time_ms == 0


@pytest.mark.asyncio
async def test_budget_concurrent_no_race(redis_client) -> None:
    await redis_client.init_budget(
        "exec-4",
        "step-1",
        BudgetConfig(max_tokens=1000, max_rounds=200, max_cost=100.0, max_time_ms=30000),
        ttl_seconds=30,
    )

    async def decrement() -> bool:
        result = await redis_client.decrement_budget("exec-4", "step-1", "tokens", 10)
        return result.allowed

    outcomes = await asyncio.gather(*[decrement() for _ in range(110)])
    budget = await redis_client.get_budget("exec-4", "step-1")

    assert sum(outcomes) == 100
    assert budget is not None
    assert budget["used_tokens"] == "1000"

