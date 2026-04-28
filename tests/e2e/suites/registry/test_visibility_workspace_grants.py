from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_workspace_grants_do_not_leak_across_workspaces(http_client, http_client_workspace_member, workspace) -> None:
    grant = await http_client.post('/api/v1/agents/test-eng:seeded-planner/visibility-grants', json={'workspace_id': workspace['id'], 'patterns': ['test-eng:*']})
    assert grant.status_code in {200, 201, 204}
    visible = await http_client_workspace_member.get('/api/v1/agents', params={'workspace_id': workspace['id'], 'namespace': 'test-eng'})
    assert visible.status_code == 200
    isolated = await http_client_workspace_member.get('/api/v1/agents', params={'workspace_id': 'other-workspace', 'namespace': 'test-eng'})
    assert isolated.status_code in {200, 403}
    if isolated.status_code == 200:
        assert all(item.get('workspace_id') != workspace['id'] for item in isolated.json().get('items', []))
