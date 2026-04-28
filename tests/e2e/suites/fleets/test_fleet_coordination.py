from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_fleet_coordination_event_and_health_projection(http_client, kafka_consumer) -> None:
    signal = await post_json(http_client, '/api/v1/fleets/test-eng-fleet/events', {'member_fqn': 'default:seeded-executor', 'progress': 50})
    event = await kafka_consumer.expect_event('fleet.events', lambda payload: payload.get('fleet') == 'test-eng-fleet')
    health = await get_json(http_client, '/api/v1/fleets/test-eng-fleet/health')
    assert event.get('member_fqn') == signal.get('member_fqn')
    assert 'health' in health
