from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_workspace_goal_lifecycle_tracks_gid(http_client, db) -> None:
    goal = await get_json(http_client, '/api/v1/workspaces/test-workspace-alpha/goals/gid-open-001')
    interaction = await post_json(http_client, '/api/v1/interactions', {'workspace_id': 'test-workspace-alpha', 'gid': goal.get('gid'), 'content': 'start goal'})
    updated = await get_json(http_client, '/api/v1/workspaces/test-workspace-alpha/goals/gid-open-001')
    assert updated.get('state') in {'in_progress', 'completed'}
    stored_gid = await db.fetchval('select gid from interaction_messages where id = $1', interaction.get('id'))
    assert stored_gid == goal.get('gid')
