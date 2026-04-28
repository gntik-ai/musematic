from __future__ import annotations

import httpx
import pytest

from suites._helpers import assert_status


@pytest.mark.asyncio
async def test_local_auth_session_lifecycle(platform_api_url: str) -> None:
    async with httpx.AsyncClient(base_url=platform_api_url, timeout=30.0) as client:
        login = await client.post('/api/v1/auth/login', json={'email': 'admin@e2e.test', 'password': 'e2e-test-password'})
        token_payload = assert_status(login)
        assert token_payload.get('access_token') or token_payload.get('accessToken') or token_payload.get('token')

        wrong = await client.post('/api/v1/auth/login', json={'email': 'admin@e2e.test', 'password': 'wrong-password'})
        assert wrong.status_code == 401

        refresh_token = token_payload.get('refresh_token') or token_payload.get('refreshToken')
        if refresh_token:
            refreshed = await client.post('/api/v1/auth/refresh', json={'refresh_token': refresh_token})
            assert_status(refreshed)

        logout = await client.post('/api/v1/auth/logout', headers={'Authorization': f"Bearer {token_payload.get('access_token') or token_payload.get('accessToken') or token_payload.get('token')}"})
        assert logout.status_code in {200, 202, 204}
