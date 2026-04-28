from __future__ import annotations

import pytest

from suites._helpers import post_json, wait_for_state


@pytest.mark.asyncio
async def test_react_reasoning_path(http_client, kafka_consumer, mock_llm, ws_client) -> None:
    await mock_llm.set_response('agent_response', 'reasoning response for react')
    await ws_client.subscribe('reasoning', 'react')
    execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'exercise react', **{'reasoning_mode': 'react', 'tools': ['mock-http-tool']}})
    event = await kafka_consumer.expect_event('execution.events', lambda payload: payload.get('event_type') == 'tool.call' or payload.get('reasoning_mode') == 'react')
    final = await wait_for_state(http_client, f"/api/v1/executions/{execution['id']}", {'completed', 'budget_exhausted'})
    assert final.get('state') in {'completed', 'budget_exhausted'}
    assert event
