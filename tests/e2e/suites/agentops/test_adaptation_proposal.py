from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_adaptation_proposal_generated_from_drift(http_client) -> None:
    drift = await post_json(http_client, '/api/v1/agentops/drift-signals', {'agent_fqn': 'default:seeded-executor', 'outcome': 'divergent'})
    proposal = await post_json(http_client, '/api/v1/agentops/proposals', {'drift_signal_id': drift.get('id')})
    fetched = await get_json(http_client, f"/api/v1/agentops/proposals/{proposal['id']}")
    assert fetched.get('id') == proposal.get('id')
