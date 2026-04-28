from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_judge_verdict_event_and_api_projection(http_client, kafka_consumer, mock_llm) -> None:
    await mock_llm.set_response('judge_verdict', '{"verdict":"allow","reason":"fixture"}')
    verdict = await post_json(http_client, '/api/v1/governance/verdicts', {'judge_fqn': 'test-finance:seeded-judge', 'subject': {'action': 'read'}})
    event = await kafka_consumer.expect_event('governance.events', lambda item: item.get('event_type') == 'governance.verdict.issued')
    fetched = await get_json(http_client, f"/api/v1/governance/verdicts/{verdict.get('id')}")
    assert fetched.get('id') == verdict.get('id')
    assert event.get('verdict') in {'allow', 'deny'}
