from __future__ import annotations

import pytest

from suites._helpers import post_json, wait_for_state


@pytest.mark.asyncio
async def test_reprioritized_execution_finishes_before_low_priority(http_client, mock_llm) -> None:
    await mock_llm.set_response('agent_response', 'ok')
    low = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'low', 'priority': 1})
    high = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'high', 'priority': 1})
    await post_json(http_client, f"/api/v1/executions/{high['id']}/reprioritize", {'priority': 100})
    high_final = await wait_for_state(http_client, f"/api/v1/executions/{high['id']}", {'completed'})
    low_final = await wait_for_state(http_client, f"/api/v1/executions/{low['id']}", {'completed'})
    assert high_final.get('completed_at') <= low_final.get('completed_at')
