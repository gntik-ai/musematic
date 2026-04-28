from __future__ import annotations

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_kafka_broker_restart_preserves_event_burst(http_client, kafka_consumer) -> None:
    expected = 10
    burst = await post_json(http_client, '/api/v1/_e2e/kafka/burst', {'topic': 'execution.events', 'count': expected})
    restart = await post_json(http_client, '/api/v1/_e2e/chaos/restart-statefulset', {'namespace': 'platform-data', 'name': 'kafka'})
    assert restart.get('restarted', True)
    events = await kafka_consumer.collect('execution.events', duration=10.0)
    ids = {event.get('id') for event in events if event.get('burst_id') == burst.get('id')}
    assert len(ids) == expected
