from __future__ import annotations

import pytest

from suites._helpers import post_json, wait_for_state


@pytest.mark.asyncio
async def test_fleet_orchestration_completes_all_subtasks(http_client, mock_llm) -> None:
    await mock_llm.set_response('agent_response', 'delegate and finish')
    run = await post_json(http_client, '/api/v1/fleets/test-eng-fleet/tasks', {'task': 'orchestrate e2e'})
    final = await wait_for_state(http_client, f"/api/v1/fleets/tasks/{run['id']}", {'completed'})
    assert final.get('state') == 'completed'
    assert final.get('subtasks_completed', 1) >= 1
