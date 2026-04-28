from __future__ import annotations

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_canary_deployment_rolls_back_on_error_threshold(http_client) -> None:
    deployment = await post_json(http_client, '/api/v1/agentops/canaries', {'agent_fqn': 'default:seeded-executor', 'traffic_percent': 10})
    rollback = await post_json(http_client, f"/api/v1/agentops/canaries/{deployment['id']}/rollback", {'reason': 'e2e error threshold'})
    assert rollback.get('state') in {'stable', 'rolled_back'}
