from __future__ import annotations

import pytest

from suites._helpers import post_json, wait_for_state


@pytest.mark.asyncio
async def test_cod_reasoning_path(http_client, kafka_consumer, mock_llm, ws_client) -> None:
    await mock_llm.set_response('agent_response', 'reasoning response for cod')
    await ws_client.subscribe('reasoning', 'cod')
    execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'exercise cod', **{'reasoning_mode': 'cod', 'debaters': ['test-eng:seeded-planner', 'test-eng:seeded-orchestrator']}})
    event = await kafka_consumer.expect_event('execution.events', lambda payload: payload.get('event_type') == 'governance.verdict.issued' or payload.get('reasoning_mode') == 'cod')
    final = await wait_for_state(http_client, f"/api/v1/executions/{execution['id']}", {'completed', 'budget_exhausted'})
    assert final.get('state') in {'completed', 'budget_exhausted'}
    assert event
