from __future__ import annotations

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_gid_propagates_to_events_and_database(http_client, kafka_consumer, db) -> None:
    gid = 'gid-open-001'
    interaction = await post_json(http_client, '/api/v1/interactions', {'workspace_id': 'test-workspace-alpha', 'gid': gid, 'content': 'correlate'})
    event = await kafka_consumer.expect_event('interaction.events', lambda payload: payload.get('gid') == gid)
    stored_gid = await db.fetchval('select gid from interaction_messages where id = $1', interaction.get('id'))
    assert event.get('gid') == stored_gid == gid
    downstream = await kafka_consumer.expect_event('execution.events', lambda payload: payload.get('gid') == gid)
    assert downstream.get('gid') == gid
