from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(decoded)
    except (IndexError, ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


class AuthenticatedAsyncClient(httpx.AsyncClient):
    def __init__(self, base_url: str, **kwargs: Any) -> None:
        super().__init__(base_url=base_url, timeout=30.0, **kwargs)
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.current_user_id: str | None = None
        self.current_workspace_id: str | None = None

    async def login_as(self, email: str, password: str) -> None:
        response = await super().post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        response.raise_for_status()
        payload = response.json()
        self.access_token = (
            payload.get("access_token")
            or payload.get("accessToken")
            or payload.get("token")
            or payload.get("access", {}).get("token")
        )
        self.refresh_token = payload.get("refresh_token") or payload.get(
            "refreshToken",
        )
        if not self.access_token:
            if payload.get("mfa_required"):
                raise RuntimeError(f"login for {email} requires MFA")
            raise RuntimeError(f"login for {email} did not return an access token")
        token_payload = _decode_jwt_payload(self.access_token)
        user = payload.get("user") or payload.get("account") or {}
        self.current_user_id = user.get("id") or token_payload.get("sub")
        self.current_workspace_id = (
            payload.get("workspace_id")
            or payload.get("workspaceId")
            or user.get("workspace_id")
            or token_payload.get("workspace_id")
        )

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if self.access_token and "authorization" not in {
            key.lower() for key in headers
        }:
            headers["Authorization"] = f"Bearer {self.access_token}"
        response = await super().request(method, url, headers=headers, **kwargs)
        if response.status_code == 401 and self.refresh_token:
            refreshed = await self._refresh_access_token()
            if refreshed:
                headers["Authorization"] = f"Bearer {self.access_token}"
                response = await super().request(
                    method,
                    url,
                    headers=headers,
                    **kwargs,
                )
        return response

    async def _refresh_access_token(self) -> bool:
        response = await super().post(
            "/api/v1/auth/refresh",
            json={"refresh_token": self.refresh_token},
        )
        if response.status_code >= 400:
            return False
        payload = response.json()
        self.access_token = payload.get("access_token") or payload.get("accessToken")
        self.refresh_token = payload.get("refresh_token") or payload.get(
            "refreshToken",
            self.refresh_token,
        )
        return self.access_token is not None

    async def json_request(
        self,
        method: str,
        path: str,
        *,
        expected: set[int] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response = await self.request(method, path, **kwargs)
        expected_codes = expected or {200, 201, 202, 204}
        assert response.status_code in expected_codes, response.text
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()


@pytest.fixture(scope="session")
async def http_client(platform_api_url: str) -> AsyncIterator[AuthenticatedAsyncClient]:
    async with AuthenticatedAsyncClient(platform_api_url) as client:
        await client.login_as("admin@e2e.test", "e2e-test-password")
        yield client


@pytest.fixture(scope="function")
async def http_client_superadmin(
    platform_api_url: str,
) -> AsyncIterator[AuthenticatedAsyncClient]:
    async with AuthenticatedAsyncClient(platform_api_url) as client:
        await client.login_as("superadmin@e2e.test", "e2e-test-password")
        yield client


@pytest.fixture(scope="function")
async def http_client_workspace_member(
    platform_api_url: str,
) -> AsyncIterator[AuthenticatedAsyncClient]:
    async with AuthenticatedAsyncClient(platform_api_url) as client:
        await client.login_as("end_user1@e2e.test", "e2e-test-password")
        yield client
