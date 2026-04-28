from __future__ import annotations

import pytest

from suites._helpers import post_json


@pytest.mark.asyncio
async def test_third_party_certifier_stub_issues_or_rejects(http_client) -> None:
    result = await post_json(http_client, '/api/v1/trust/certifications/third-party', {'agent_fqn': 'default:seeded-executor', 'certifier': 'third-party-cert'})
    assert result.get('status') in {'active', 'rejected', 'pending'}
    assert result.get('certifier') in {'third-party-cert', None}
