from __future__ import annotations

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_policy_timeout_fails_closed_and_audits(http_client, db) -> None:
    policy = await post_json(http_client, '/api/v1/_e2e/policies/slow', {'delay_seconds': 60})
    try:
        denied = await http_client.post('/api/v1/executions', json={'agent_fqn': 'default:seeded-executor', 'input': 'slow policy'})
        assert denied.status_code in {403, 408, 503}
        audit_reason = await db.fetchval('select timeout_reason from audit_events where correlation_id = $1', policy.get('id'))
        assert audit_reason
    finally:
        await http_client.delete(f"/api/v1/_e2e/policies/slow/{policy.get('id')}")
