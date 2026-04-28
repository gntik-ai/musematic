from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_user_alert_broadcast_and_dismissal(http_client, ws_client) -> None:
    await ws_client.subscribe('alerts', 'user')
    alert = await post_json(http_client, '/api/v1/interactions/alerts', {'target_user_id': http_client.current_user_id, 'message': 'e2e alert'})
    received = await ws_client.expect_event('alerts', 'alert.created')
    assert received.get('payload', {}).get('id') == alert.get('id')
    dismissed = await post_json(http_client, f"/api/v1/interactions/alerts/{alert['id']}/dismiss", {})
    assert dismissed.get('state') in {'dismissed', 'closed'}
    pending = await get_json(http_client, '/api/v1/interactions/alerts', params={'state': 'pending'})
    assert all(item.get('id') != alert['id'] for item in pending.get('items', []))
