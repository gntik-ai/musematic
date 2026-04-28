from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_surveillance_signal_ws_db_and_score(http_client, ws_client, db) -> None:
    await ws_client.subscribe('trust', 'signals')
    signal = await post_json(http_client, '/api/v1/trust/signals', {'agent_fqn': 'default:seeded-executor', 'signal_type': 'e2e', 'severity': 'low'})
    received = await ws_client.expect_event('trust', 'signal.created')
    assert received.get('payload', {}).get('agent_fqn') == 'default:seeded-executor'
    stored = await db.fetchval('select count(*) from trust_surveillance_signals where id = $1', signal.get('id'))
    assert stored == 1
    score = await get_json(http_client, '/api/v1/trust/agents/default:seeded-executor/score')
    assert 'score' in score
