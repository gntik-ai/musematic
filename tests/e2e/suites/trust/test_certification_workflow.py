from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_certification_status_transitions_pending_active_revoked(http_client) -> None:
    request = await post_json(http_client, '/api/v1/trust/certifications', {'agent_fqn': 'default:seeded-executor', 'evidence_ref': 'e2e://certification'})
    cert_id = request.get('id')
    approved = await post_json(http_client, f'/api/v1/trust/certifications/{cert_id}/approve', {'evidence_ref': 'e2e://approved'})
    assert approved.get('status') == 'active'
    fetched = await get_json(http_client, f'/api/v1/trust/certifications/{cert_id}')
    assert fetched.get('status') == 'active'
    revoked = await post_json(http_client, f'/api/v1/trust/certifications/{cert_id}/revoke', {'reason': 'e2e cleanup'})
    assert revoked.get('status') == 'revoked'
