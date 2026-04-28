from __future__ import annotations

import pytest

from suites._helpers import post_json, wait_for_state


@pytest.mark.asyncio
async def test_self_correction_reasoning_path(http_client, kafka_consumer, mock_llm, ws_client) -> None:
    await mock_llm.set_response('agent_response', 'reasoning response for self_correction')
    await ws_client.subscribe('reasoning', 'self_correction')
    execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'exercise self_correction', **{'reasoning_mode': 'self_correction', 'input': 'return ERROR then correct'}})
    event = await kafka_consumer.expect_event('execution.events', lambda payload: payload.get('event_type') == 'reasoning.corrected' or payload.get('reasoning_mode') == 'self_correction')
    final = await wait_for_state(http_client, f"/api/v1/executions/{execution['id']}", {'completed', 'budget_exhausted'})
    assert final.get('state') in {'completed', 'budget_exhausted'}
    assert event
