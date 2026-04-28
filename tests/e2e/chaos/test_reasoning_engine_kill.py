from __future__ import annotations

import pytest

from suites._helpers import post_json, wait_for_state


@pytest.mark.asyncio
async def test_reasoning_engine_kill_preserves_trace_continuity(http_client, ws_client, mock_llm) -> None:
    await mock_llm.set_response('agent_response', 'trace complete', streaming_chunks=['trace', ' complete'])
    await ws_client.subscribe('reasoning', 'trace')
    execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'stream cot', 'reasoning_mode': 'cot', 'stream': True})
    first = await ws_client.expect_event('reasoning', 'trace.step')
    await post_json(http_client, '/api/v1/_e2e/chaos/kill-pod', {'namespace': 'platform-execution', 'label_selector': 'app.kubernetes.io/name=reasoning-engine', 'count': 1})
    final = await wait_for_state(http_client, f"/api/v1/executions/{execution['id']}", {'completed'}, timeout=60)
    assert final.get('trace_ack') >= first.get('payload', {}).get('sequence', 0)
