from __future__ import annotations

import pytest

from suites._helpers import get_json


@pytest.mark.asyncio
async def test_pattern_discovery_applies_visibility_filters(http_client) -> None:
    by_name = await get_json(http_client, '/api/v1/agents/search', params={'pattern': '*:seeded-executor'})
    assert by_name.get('items', by_name)
    by_namespace = await get_json(http_client, '/api/v1/agents/search', params={'pattern': 'test-eng:*'})
    assert by_namespace.get('items', by_namespace)
    no_matches = await get_json(http_client, '/api/v1/agents/search', params={'pattern': 'missing:*'})
    assert no_matches.get('items', no_matches) == []
