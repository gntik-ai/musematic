from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_google_oidc_mock_login_flow(http_client) -> None:
    redirect = await http_client.get('/api/v1/auth/google', follow_redirects=False)
    assert redirect.status_code in {302, 303}
    assert 'location' in redirect.headers

    callback = await http_client.get('/api/v1/auth/google/callback', params={'code': 'e2e-google-code', 'state': 'e2e-state'})
    assert callback.status_code in {200, 302, 303}

    me = await http_client.get('/api/v1/me')
    assert me.status_code == 200
