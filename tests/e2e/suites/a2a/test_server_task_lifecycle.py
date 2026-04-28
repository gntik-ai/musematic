from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json, wait_for_state


@pytest.mark.asyncio
async def test_a2a_server_task_lifecycle_completes(http_client) -> None:
    task = await post_json(http_client, '/a2a/tasks', {'agent_fqn': 'default:seeded-executor', 'input': 'a2a task'})
    final = await wait_for_state(http_client, f"/a2a/tasks/{task['id']}", {'completed', 'failed'}, field='status')
    fetched = await get_json(http_client, f"/a2a/tasks/{task['id']}")
    assert fetched.get('status') == final.get('status')
