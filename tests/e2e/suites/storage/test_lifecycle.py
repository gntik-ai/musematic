from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_storage_lifecycle_state_and_event(http_client, kafka_consumer) -> None:
    artifact = await post_json(http_client, '/api/v1/storage/artifacts', {'name': 'test-lifecycle.txt', 'content': 'lifecycle'})
    await post_json(http_client, f"/api/v1/storage/artifacts/{artifact['id']}/archive", {})
    event = await kafka_consumer.expect_event('storage.events', lambda payload: payload.get('artifact_id') == artifact.get('id'))
    archived = await get_json(http_client, f"/api/v1/storage/artifacts/{artifact['id']}")
    assert archived.get('state') in {'archived', 'expired'}
    assert event.get('artifact_id') == artifact.get('id')
