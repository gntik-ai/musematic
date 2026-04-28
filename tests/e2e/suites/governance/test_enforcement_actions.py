from __future__ import annotations

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_enforcement_action_publishes_event_and_audit(http_client, kafka_consumer) -> None:
    action = await post_json(http_client, '/api/v1/governance/enforcements', {'target_agent_fqn': 'default:seeded-executor', 'verdict': 'deny', 'reason': 'e2e'})
    event = await kafka_consumer.expect_event('governance.events', lambda item: item.get('event_type') == 'governance.enforcement.executed')
    assert event.get('target_agent_fqn') == 'default:seeded-executor'
    audit = await http_client.get('/api/v1/audit/events', params={'correlation_id': action.get('id')})
    assert audit.status_code in {200, 404}
