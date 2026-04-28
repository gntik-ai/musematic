from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_warm_pool_allocation_and_replenishment(http_client, ws_client) -> None:
    await ws_client.subscribe('runtime', 'warm_pool')
    filled = await get_json(http_client, '/api/v1/runtime/warm-pool')
    assert filled.get('ready', 0) >= 1
    allocation = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'warm pool'})
    event = await ws_client.expect_event('runtime', 'warm_pool.replenished')
    assert allocation.get('id')
    assert event.get('payload', {}).get('ready', 0) >= 1
