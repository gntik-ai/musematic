from __future__ import annotations

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_ibor_sync_reconciles_mock_ldap_users(http_client, kafka_consumer, db) -> None:
    sync = await post_json(http_client, '/api/v1/ibor/sync', {'source': 'ldap://mock-ldap:389'})
    event = await kafka_consumer.expect_event('ibor.events', lambda payload: payload.get('event_type') == 'ibor.sync.completed')
    count = await db.fetchval("select count(*) from users where email like '%@e2e.test'")
    assert sync.get('id') or sync.get('status')
    assert event.get('event_type') == 'ibor.sync.completed'
    assert count >= 5
