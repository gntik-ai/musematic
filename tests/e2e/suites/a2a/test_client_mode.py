from __future__ import annotations

import pytest

from suites._helpers import post_json, wait_for_state


@pytest.mark.asyncio
async def test_a2a_client_mode_dispatches_to_mock_remote_agent(http_client) -> None:
    task = await post_json(http_client, '/api/v1/a2a/client/tasks', {'remote_agent_url': 'http://mock-a2a-agent.platform.svc.cluster.local', 'input': 'remote task'})
    final = await wait_for_state(http_client, f"/api/v1/a2a/client/tasks/{task['id']}", {'completed'}, field='status')
    assert final.get('output') is not None
