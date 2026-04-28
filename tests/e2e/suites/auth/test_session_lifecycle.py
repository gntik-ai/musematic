from __future__ import annotations

import httpx
import pytest

from suites._helpers import assert_status


@pytest.mark.asyncio
async def test_session_refresh_rotation_and_logout(platform_api_url: str) -> None:
    async with httpx.AsyncClient(base_url=platform_api_url, timeout=30.0) as client:
        first = assert_status(await client.post('/api/v1/auth/login', json={'email': 'operator1@e2e.test', 'password': 'e2e-test-password'}))
        refresh_token = first.get('refresh_token') or first.get('refreshToken')
        assert refresh_token

        second = assert_status(await client.post('/api/v1/auth/refresh', json={'refresh_token': refresh_token}))
        assert second.get('access_token') or second.get('accessToken')

        bearer = second.get('access_token') or second.get('accessToken')
        sessions = await client.get('/api/v1/auth/sessions', headers={'Authorization': f'Bearer {bearer}'})
        assert sessions.status_code == 200

        logout = await client.post('/api/v1/auth/logout', headers={'Authorization': f'Bearer {bearer}'})
        assert logout.status_code in {200, 202, 204}
