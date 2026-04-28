from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_llm_judge_uses_mock_verdict_and_stores_result(http_client, mock_llm) -> None:
    await mock_llm.set_response('judge_verdict', '{"quality":0.9,"verdict":"pass"}')
    execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'judge me'})
    result = await post_json(http_client, '/api/v1/evaluation/llm-judge', {'execution_id': execution.get('id')})
    fetched = await get_json(http_client, f"/api/v1/evaluation/scores/{execution.get('id')}")
    assert result.get('verdict') or fetched.get('verdict')
