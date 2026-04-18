from __future__ import annotations

from platform.auth.dependencies import (
    build_auth_service,
    build_ibor_service,
    build_ibor_sync_service,
    get_auth_service,
    require_permission,
    resolve_api_key_identity,
)
from platform.auth.ibor_service import IBORConnectorService
from platform.auth.ibor_sync import IBORSyncService
from platform.auth.repository import AuthRepository
from platform.auth.schemas import PermissionCheckResponse
from platform.auth.service import AuthService
from platform.common.exceptions import AuthorizationError
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


class AsyncSessionFactoryStub:
    def __init__(self) -> None:
        self._session = object()

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _request(settings, clients=None):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients=clients or {"redis": FakeAsyncRedisClient(), "kafka": RecordingProducer()},
            )
        ),
        headers={},
    )


def test_build_auth_service_returns_wired_service(auth_settings) -> None:
    request = _request(auth_settings)
    db = object()

    service = build_auth_service(request, db)

    assert isinstance(service, AuthService)
    assert isinstance(service.repository, AuthRepository)
    assert service.redis_client is request.app.state.clients["redis"]
    assert service.producer is request.app.state.clients["kafka"]


@pytest.mark.asyncio
async def test_get_auth_service_uses_builder(monkeypatch, auth_settings) -> None:
    sentinel = object()
    request = _request(auth_settings)
    monkeypatch.setattr(
        "platform.auth.dependencies.build_auth_service",
        lambda incoming_request, db: sentinel,
    )

    service = await get_auth_service(request=request, db=object())

    assert service is sentinel


@pytest.mark.asyncio
async def test_resolve_api_key_identity_returns_claims(monkeypatch, auth_settings) -> None:
    credential = SimpleNamespace(
        service_account_id=uuid4(),
        name="ci-bot",
        role="service_account",
        workspace_id=uuid4(),
    )

    class FakeService:
        async def verify_api_key(self, raw_key: str):
            return credential if raw_key == "msk_valid" else None

    monkeypatch.setattr(
        "platform.auth.dependencies.build_auth_service",
        lambda request, db: FakeService(),
    )
    monkeypatch.setattr(
        "platform.auth.dependencies.database.AsyncSessionLocal",
        lambda: AsyncSessionFactoryStub(),
    )

    identity = await resolve_api_key_identity(_request(auth_settings), "msk_valid")

    assert identity is not None
    assert identity["sub"] == str(credential.service_account_id)
    assert identity["identity_type"] == "service_account"


@pytest.mark.asyncio
async def test_resolve_api_key_identity_returns_none_for_invalid_key(
    monkeypatch,
    auth_settings,
) -> None:
    class FakeService:
        async def verify_api_key(self, raw_key: str):
            del raw_key
            return None

    monkeypatch.setattr(
        "platform.auth.dependencies.build_auth_service",
        lambda request, db: FakeService(),
    )
    monkeypatch.setattr(
        "platform.auth.dependencies.database.AsyncSessionLocal",
        lambda: AsyncSessionFactoryStub(),
    )

    identity = await resolve_api_key_identity(_request(auth_settings), "msk_invalid")

    assert identity is None


@pytest.mark.asyncio
async def test_require_permission_returns_current_user_on_allow(auth_settings) -> None:
    dependency = require_permission("agent", "read")

    class FakeService:
        async def check_permission(self, **kwargs):
            return PermissionCheckResponse(
                allowed=True,
                role="viewer",
                resource_type="agent",
                action="read",
                scope="workspace",
            )

    current_user = {"sub": str(uuid4()), "identity_type": "user"}
    request = _request(auth_settings)

    result = await dependency(
        request=request,
        current_user=current_user,
        auth_service=FakeService(),
    )

    assert result == current_user


@pytest.mark.asyncio
async def test_require_permission_raises_on_deny(auth_settings) -> None:
    dependency = require_permission("agent", "write")

    class FakeService:
        async def check_permission(self, **kwargs):
            return PermissionCheckResponse(
                allowed=False,
                role="viewer",
                resource_type="agent",
                action="write",
                scope="workspace",
                reason="rbac_denied",
            )

    with pytest.raises(AuthorizationError):
        await dependency(
            request=_request(auth_settings),
            current_user={"sub": str(uuid4()), "identity_type": "user"},
            auth_service=FakeService(),
        )


@pytest.mark.asyncio
async def test_require_permission_rejects_missing_subject(auth_settings) -> None:
    dependency = require_permission("agent", "read")

    class FakeService:
        async def check_permission(self, **kwargs):
            del kwargs
            raise AssertionError("check_permission should not be called")

    with pytest.raises(AuthorizationError):
        await dependency(
            request=_request(auth_settings),
            current_user={"identity_type": "user"},
            auth_service=FakeService(),
        )


def auth_settings_fixture():
    from platform.common.config import PlatformSettings

    return PlatformSettings(AUTH_JWT_SECRET_KEY="test-secret", AUTH_JWT_ALGORITHM="HS256")


def test_build_ibor_service_returns_connector_service() -> None:
    request = _request(auth_settings_fixture())
    service = build_ibor_service(request, object())

    assert isinstance(service, IBORConnectorService)


def test_build_ibor_sync_service_returns_sync_service() -> None:
    request = _request(auth_settings_fixture())

    service = build_ibor_sync_service(request, object())

    assert isinstance(service, IBORSyncService)
    assert service.redis_client is request.app.state.clients["redis"]
    assert service.producer is request.app.state.clients["kafka"]
