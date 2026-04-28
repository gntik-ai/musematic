from __future__ import annotations

import pytest

from suites._helpers import post_json, wait_for_state


@pytest.mark.asyncio
async def test_checkpoint_created_then_rollback_resumes(http_client, kafka_consumer, mock_llm) -> None:
    await mock_llm.set_response('agent_response', 'checkpoint response')
    execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'checkpoint please', 'checkpoint': True})
    event = await kafka_consumer.expect_event('execution.events', lambda payload: payload.get('event_type') == 'checkpoint.created')
    rollback = await post_json(http_client, f"/api/v1/executions/{execution['id']}/rollback", {'checkpoint_id': event.get('checkpoint_id')})
    assert rollback.get('state') in {'queued', 'running', 'completed'}
    final = await wait_for_state(http_client, f"/api/v1/executions/{execution['id']}", {'completed'})
    assert final.get('state') == 'completed'
