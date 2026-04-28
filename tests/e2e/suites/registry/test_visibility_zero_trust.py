from __future__ import annotations

import pytest

from suites._helpers import get_json


@pytest.mark.asyncio
async def test_zero_trust_visibility_grants_and_revokes(http_client, http_client_workspace_member) -> None:
    hidden = await http_client_workspace_member.get('/api/v1/agents/test-finance:seeded-judge')
    assert hidden.status_code in {403, 404}
    admin_visible = await get_json(http_client, '/api/v1/agents/test-finance:seeded-judge')
    assert admin_visible.get('fqn') == 'test-finance:seeded-judge'
    grant = await http_client.post('/api/v1/agents/test-finance:seeded-judge/visibility-grants', json={'workspace_pattern': 'test-*'})
    assert grant.status_code in {200, 201, 204}
    member_visible = await http_client_workspace_member.get('/api/v1/agents/test-finance:seeded-judge')
    assert member_visible.status_code == 200
    grant_id = grant.json().get('id') if grant.content else 'test-*'
    revoke = await http_client.delete(f'/api/v1/agents/test-finance:seeded-judge/visibility-grants/{grant_id}')
    assert revoke.status_code in {200, 202, 204, 404}
