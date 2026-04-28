from __future__ import annotations

import pytest

from suites._helpers import post_json, wait_for_state


@pytest.mark.asyncio
async def test_runtime_pod_kill_recovers_checkpointed_execution(http_client, kafka_consumer, mock_llm) -> None:
    await mock_llm.set_response('agent_response', 'long running complete')
    execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'long-running', 'checkpoint': True})
    await kafka_consumer.expect_event('execution.events', lambda payload: payload.get('event_type') == 'checkpoint.created')
    killed = await post_json(http_client, '/api/v1/_e2e/chaos/kill-pod', {'namespace': 'platform-execution', 'label_selector': 'app.kubernetes.io/name=runtime-controller', 'count': 1})
    assert killed.get('killed')
    not_failed = await http_client.get(f"/api/v1/executions/{execution['id']}")
    assert not_failed.json().get('state') != 'failed'
    final = await wait_for_state(http_client, f"/api/v1/executions/{execution['id']}", {'completed'}, timeout=60)
    assert final.get('state') == 'completed'
