from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_github_oauth_mock_login_flow_rejects_bad_state(http_client) -> None:
    redirect = await http_client.get('/api/v1/auth/github', follow_redirects=False)
    assert redirect.status_code in {302, 303}
    assert 'location' in redirect.headers

    callback = await http_client.get('/api/v1/auth/github/callback', params={'code': 'e2e-github-code', 'state': 'e2e-state'})
    assert callback.status_code in {200, 302, 303}

    invalid = await http_client.get('/api/v1/auth/github/callback', params={'code': 'e2e-github-code', 'state': 'tampered'})
    assert invalid.status_code in {400, 401, 403}
