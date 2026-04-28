from __future__ import annotations

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_observer_judge_enforcer_pipeline_end_to_end(http_client, kafka_consumer, mock_llm) -> None:
    await mock_llm.set_response('judge_verdict', '{"verdict":"deny","reason":"e2e"}')
    execution = await post_json(http_client, '/api/v1/governance/pipeline/run', {'observer_fqn': 'test-finance:seeded-observer', 'judge_fqn': 'test-finance:seeded-judge', 'enforcer_fqn': 'test-finance:seeded-enforcer', 'action': 'tool.call'})
    assert execution.get('id')
    verdict = await kafka_consumer.expect_event('governance.events', lambda event: event.get('event_type') == 'governance.verdict.issued')
    enforcement = await kafka_consumer.expect_event('governance.events', lambda event: event.get('event_type') == 'governance.enforcement.executed')
    assert verdict.get('verdict') in {'allow', 'deny'}
    assert enforcement.get('execution_id') == execution.get('id')
