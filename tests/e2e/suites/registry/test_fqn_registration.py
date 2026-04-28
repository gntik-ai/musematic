from __future__ import annotations

import pytest

from suites._helpers import get_json, unique_name


@pytest.mark.asyncio
async def test_fqn_registration_duplicate_and_validation(http_client, agent) -> None:
    local_name = unique_name('executor')
    created = await agent.register('test-eng', local_name, 'executor')
    fqn = created.get('fqn') or f"test-eng:{created['local_name']}"
    fetched = await get_json(http_client, f'/api/v1/agents/{fqn}')
    assert fetched.get('fqn') == fqn
    duplicate = await http_client.post('/api/v1/agents', json={**created, 'id': None})
    assert duplicate.status_code == 409
    invalid = await http_client.post('/api/v1/agents', json={'namespace': 'bad namespace', 'local_name': 'bad/name', 'role_type': 'executor'})
    assert invalid.status_code in {400, 422}
