from __future__ import annotations

import pytest

from suites._helpers import post_json, wait_for_state


@pytest.mark.asyncio
async def test_compute_budget_reasoning_path(http_client, kafka_consumer, mock_llm, ws_client) -> None:
    await mock_llm.set_response('agent_response', 'reasoning response for compute_budget')
    await ws_client.subscribe('reasoning', 'compute_budget')
    execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'exercise compute_budget', **{'reasoning_mode': 'cot', 'max_tokens': 100}})
    event = await kafka_consumer.expect_event('execution.events', lambda payload: payload.get('event_type') == 'budget.exhausted' or payload.get('reasoning_mode') == 'compute_budget')
    final = await wait_for_state(http_client, f"/api/v1/executions/{execution['id']}", {'completed', 'budget_exhausted'})
    assert final.get('state') in {'completed', 'budget_exhausted'}
    assert event
