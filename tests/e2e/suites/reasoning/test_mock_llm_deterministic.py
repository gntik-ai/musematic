from __future__ import annotations

import pytest

from suites._helpers import post_json, wait_for_state


@pytest.mark.asyncio
async def test_mock_llm_deterministic_across_repeated_runs(http_client, mock_llm) -> None:
    responses = ['fixed-alpha', 'fixed-beta', 'fixed-gamma']
    await mock_llm.set_responses({'agent_response': responses * 10})
    outputs = []
    for index in range(10):
        execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': f'determinism {index}', 'prompt_pattern': 'agent_response'})
        final = await wait_for_state(http_client, f"/api/v1/executions/{execution['id']}", {'completed'})
        outputs.append(final.get('response') or final.get('output'))
    assert len({repr(item) for item in outputs}) == 1
    calls = await mock_llm.get_calls(pattern='agent_response')
    if calls:
        returned = [call.get('response') for call in calls[-10:]]
        assert len({repr(item) for item in returned}) == 1
