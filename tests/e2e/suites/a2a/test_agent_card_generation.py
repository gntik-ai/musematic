from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_agent_card_generation_contains_required_a2a_fields(http_client) -> None:
    response = await http_client.get('/.well-known/agent.json', params={'agent_fqn': 'default:seeded-executor'})
    assert response.status_code == 200
    card = response.json()
    assert {'skills', 'endpoints', 'auth_schemes'} <= set(card)
