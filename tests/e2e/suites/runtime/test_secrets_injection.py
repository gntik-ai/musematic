from __future__ import annotations

import pytest

from suites._helpers import post_json, wait_for_state


@pytest.mark.asyncio
async def test_secret_injection_never_reaches_mock_llm_prompt(http_client, mock_llm) -> None:
    await post_json(http_client, '/api/v1/secrets', {'name': 'test-secret-e2e', 'value': 'super-secret-value'})
    execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'tool': 'mock-code-tool', 'secret_name': 'test-secret-e2e'})
    await wait_for_state(http_client, f"/api/v1/executions/{execution['id']}", {'completed'})
    calls = await mock_llm.get_calls()
    assert 'super-secret-value' not in str(calls)
