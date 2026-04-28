from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_response_decision_creates_attention_alert(http_client) -> None:
    decision = await post_json(http_client, '/api/v1/interactions/response-decisions', {'workspace_id': 'test-workspace-alpha', 'agent_fqn': 'default:seeded-executor', 'attention_required': True, 'message': 'needs review'})
    assert decision.get('attention_required') is True
    alerts = await get_json(http_client, '/api/v1/interactions/alerts', params={'workspace_id': 'test-workspace-alpha'})
    assert any(item.get('source_id') == decision.get('id') for item in alerts.get('items', []))
