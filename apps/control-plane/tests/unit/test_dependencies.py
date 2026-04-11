from __future__ import annotations

from types import SimpleNamespace

import jwt
import pytest

from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user, get_workspace
from platform.common.dependencies import get_opensearch_client
from platform.common.exceptions import AuthorizationError, NotFoundError


def _request(headers: dict[str, str], settings: PlatformSettings, user=None):
    return SimpleNamespace(
        headers=headers,
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
        state=SimpleNamespace(user=user),
    )


@pytest.mark.asyncio
async def test_get_current_user_prefers_request_state() -> None:
    request = _request({}, PlatformSettings(), user={"sub": "state-user"})

    assert await get_current_user(request) == {"sub": "state-user"}


@pytest.mark.asyncio
async def test_get_current_user_decodes_bearer_token() -> None:
    secret = "a" * 32
    settings = PlatformSettings(AUTH_JWT_SECRET_KEY=secret, AUTH_JWT_ALGORITHM="HS256")
    token = jwt.encode({"sub": "user-1"}, secret, algorithm="HS256")
    request = _request({"Authorization": f"Bearer {token}"}, settings)

    payload = await get_current_user(request)

    assert payload["sub"] == "user-1"


@pytest.mark.asyncio
async def test_get_current_user_rejects_invalid_token() -> None:
    settings = PlatformSettings(AUTH_JWT_SECRET_KEY="a" * 32, AUTH_JWT_ALGORITHM="HS256")
    request = _request({"Authorization": "Bearer invalid"}, settings)

    with pytest.raises(AuthorizationError):
        await get_current_user(request)


@pytest.mark.asyncio
async def test_get_current_user_requires_bearer_header() -> None:
    request = _request({}, PlatformSettings())

    with pytest.raises(AuthorizationError):
        await get_current_user(request)


@pytest.mark.asyncio
async def test_get_current_user_rejects_empty_bearer_token() -> None:
    request = _request({"Authorization": "Bearer "}, PlatformSettings())

    with pytest.raises(AuthorizationError):
        await get_current_user(request)


@pytest.mark.asyncio
async def test_get_workspace_requires_header() -> None:
    request = _request({}, PlatformSettings())

    with pytest.raises(NotFoundError):
        await get_workspace(request, db=object())


@pytest.mark.asyncio
async def test_get_workspace_returns_workspace_context() -> None:
    request = _request({"X-Workspace-ID": "workspace-1"}, PlatformSettings())

    assert await get_workspace(request, db=object()) == {"workspace_id": "workspace-1"}


def test_get_opensearch_client_reads_from_app_state() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(clients={"opensearch": "client"})))

    assert get_opensearch_client(request) == "client"
