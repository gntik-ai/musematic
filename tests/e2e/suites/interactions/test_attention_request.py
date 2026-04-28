from __future__ import annotations

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_attention_request_publishes_kafka_and_ws(http_client, kafka_consumer, ws_client) -> None:
    await ws_client.subscribe('attention', 'requests')
    request = await post_json(http_client, '/api/v1/interactions/attention', {'target_id': http_client.current_user_id, 'message': 'e2e attention'})
    event = await kafka_consumer.expect_event('interaction.events', lambda payload: payload.get('event_type') == 'interaction.attention')
    received = await ws_client.expect_event('attention', 'request.created')
    assert event.get('target_id') == request.get('target_id')
    assert received.get('payload', {}).get('target_id') == request.get('target_id')
