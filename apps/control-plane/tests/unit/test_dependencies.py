from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.common.dependencies import (
    get_coordination_test_service_interface,
    get_current_user,
    get_db,
    get_eval_suite_service_interface,
    get_opensearch_client,
    get_workspace,
)
from platform.common.exceptions import AuthorizationError, NotFoundError
from types import SimpleNamespace

import jwt
import pytest


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
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(clients={"opensearch": "client"}))
    )

    assert get_opensearch_client(request) == "client"


class _SessionLifecycleStub:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_get_db_and_dependency_builders_cover_additional_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _SessionLifecycleStub()
    monkeypatch.setattr("platform.common.dependencies.database.AsyncSessionLocal", lambda: session)
    provider = get_db()
    yielded = await provider.__anext__()
    assert yielded is session
    with pytest.raises(StopAsyncIteration):
        await provider.__anext__()
    assert session.committed is True
    assert session.closed is True

    session_error = _SessionLifecycleStub()
    monkeypatch.setattr(
        "platform.common.dependencies.database.AsyncSessionLocal", lambda: session_error
    )
    provider = get_db()
    await provider.__anext__()
    with pytest.raises(RuntimeError):
        await provider.athrow(RuntimeError("boom"))
    assert session_error.rolled_back is True
    assert session_error.closed is True

    request = _request({}, PlatformSettings())
    expired_token = jwt.encode(
        {"sub": "user-1", "exp": 1},
        "a" * 32,
        algorithm="HS256",
    )
    expired_request = _request(
        {"Authorization": f"Bearer {expired_token}"},
        PlatformSettings(AUTH_JWT_SECRET_KEY="a" * 32, AUTH_JWT_ALGORITHM="HS256"),
    )
    with pytest.raises(AuthorizationError):
        await get_current_user(expired_request)

    secret = "b" * 32
    refresh_token = jwt.encode({"sub": "user-1", "type": "refresh"}, secret, algorithm="HS256")
    refresh_request = _request(
        {"Authorization": f"Bearer {refresh_token}"},
        PlatformSettings(AUTH_JWT_SECRET_KEY=secret, AUTH_JWT_ALGORITHM="HS256"),
    )
    with pytest.raises(AuthorizationError):
        await get_current_user(refresh_request)

    sentinel_eval = object()
    sentinel_coord = object()
    monkeypatch.setattr(
        "platform.evaluation.dependencies.build_eval_suite_service",
        lambda **kwargs: sentinel_eval,
    )
    monkeypatch.setattr(
        "platform.testing.dependencies.build_coordination_service",
        lambda **kwargs: sentinel_coord,
    )
    request.app.state.clients = {
        "kafka": object(),
        "redis": object(),
        "object_storage": object(),
        "runtime_controller": object(),
        "reasoning_engine": object(),
    }
    assert await get_eval_suite_service_interface(request, session=object()) is sentinel_eval
    assert (
        await get_coordination_test_service_interface(request, session=object()) is sentinel_coord
    )


@pytest.mark.asyncio
async def test_get_current_user_rejects_non_mapping_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = PlatformSettings(AUTH_JWT_SECRET_KEY="c" * 32, AUTH_JWT_ALGORITHM="HS256")
    request = _request({"Authorization": "Bearer token"}, settings)
    monkeypatch.setattr(
        "platform.common.dependencies.jwt.decode", lambda *args, **kwargs: "bad-payload"
    )

    with pytest.raises(AuthorizationError):
        await get_current_user(request)
