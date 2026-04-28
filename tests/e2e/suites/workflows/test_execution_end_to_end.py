from __future__ import annotations

import pytest

from suites._helpers import post_json, wait_for_state


@pytest.mark.asyncio
async def test_execution_dispatch_completes_and_persists(http_client, db, mock_llm) -> None:
    await mock_llm.set_response('agent_response', 'execution complete')
    execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'run trivial task'})
    final = await wait_for_state(http_client, f"/api/v1/executions/{execution['id']}", {'completed'})
    assert final.get('state') == 'completed'
    stored = await db.fetchval('select state from executions where id = $1', execution['id'])
    assert stored == 'completed'
