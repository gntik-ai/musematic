from __future__ import annotations

import statistics
from platform.common.tagging.label_expression.cache import LabelExpressionCache
from platform.common.tagging.label_expression.evaluator import LabelExpressionEvaluator
from time import perf_counter
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_cached_label_expression_path_stays_within_gateway_latency_budget() -> None:
    cache = LabelExpressionCache(None, lru_size=4)
    evaluator = LabelExpressionEvaluator()
    policy_id = uuid4()
    expression = "env=production AND tier=critical"
    labels = {"env": "production", "tier": "critical"}

    ast = await cache.get_or_compile(policy_id, 1, expression)
    assert ast is not None

    baseline_samples: list[float] = []
    expression_samples: list[float] = []
    for _ in range(250):
        started = perf_counter()
        await cache.get_or_compile(policy_id, 1, None)
        baseline_samples.append(perf_counter() - started)

        started = perf_counter()
        cached = await cache.get_or_compile(policy_id, 1, expression)
        assert cached is ast
        assert await evaluator.evaluate(cached, labels) is True
        expression_samples.append(perf_counter() - started)

    baseline_p95 = statistics.quantiles(baseline_samples, n=20)[18]
    expression_p95 = statistics.quantiles(expression_samples, n=20)[18]

    assert expression_p95 < baseline_p95 + 0.005
