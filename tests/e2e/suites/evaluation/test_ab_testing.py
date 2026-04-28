from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_ab_testing_tracks_weighted_variant_metrics(http_client) -> None:
    test = await post_json(http_client, '/api/v1/evaluation/ab-tests', {'name': 'test-ab-e2e', 'variants': [{'agent_fqn': 'default:seeded-executor', 'weight': 50}, {'agent_fqn': 'test-eng:seeded-planner', 'weight': 50}]})
    for _ in range(4):
        await post_json(http_client, f"/api/v1/evaluation/ab-tests/{test['id']}/executions", {'input': 'ab sample'})
    metrics = await get_json(http_client, f"/api/v1/evaluation/ab-tests/{test['id']}/metrics")
    assert len(metrics.get('variants', [])) == 2
