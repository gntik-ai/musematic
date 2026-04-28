from __future__ import annotations

import pytest

from suites._helpers import get_json


@pytest.mark.asyncio
async def test_fqn_resolution_known_unknown_and_wildcard(http_client) -> None:
    known = await get_json(http_client, '/api/v1/agents/resolve', params={'fqn': 'default:seeded-executor'})
    assert known.get('fqn') == 'default:seeded-executor'
    unknown = await http_client.get('/api/v1/agents/resolve', params={'fqn': 'default:missing-agent'})
    assert unknown.status_code == 404
    wildcard = await get_json(http_client, '/api/v1/agents/resolve', params={'fqn': 'test-eng:*'})
    assert wildcard.get('items') or isinstance(wildcard, list)
