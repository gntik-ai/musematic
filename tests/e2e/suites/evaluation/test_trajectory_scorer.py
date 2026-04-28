from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_trajectory_scorer_persists_score(http_client) -> None:
    execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'input': 'score me'})
    score = await post_json(http_client, '/api/v1/evaluation/trajectory-scores', {'execution_id': execution.get('id')})
    fetched = await get_json(http_client, f"/api/v1/evaluation/scores/{execution.get('id')}")
    assert fetched.get('execution_id') == execution.get('id')
    assert score.get('dimensions') or fetched.get('dimensions')
