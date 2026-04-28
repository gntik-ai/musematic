from __future__ import annotations

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_contract_violation_publishes_surveillance_signal(http_client, kafka_consumer) -> None:
    contract = await post_json(http_client, '/api/v1/trust/contracts', {'agent_fqn': 'default:seeded-executor', 'deny_actions': ['secret*']})
    execution = await post_json(http_client, '/api/v1/executions', {'agent_fqn': 'default:seeded-executor', 'action': 'secret.lookup', 'contract_id': contract.get('id')})
    assert execution.get('id')
    event = await kafka_consumer.expect_event('trust.events', lambda payload: payload.get('event_type') == 'trust.contract.violated')
    assert event.get('agent_fqn') == 'default:seeded-executor'
