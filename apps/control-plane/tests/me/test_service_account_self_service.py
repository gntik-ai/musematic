from __future__ import annotations

from platform.auth.exceptions import InvalidMfaCodeError, InvalidMfaTokenError
from platform.auth.schemas import MfaStatus
from platform.auth.service import AuthService
from platform.common.config import AuthSettings
from platform.common.exceptions import AuthorizationError, ValidationError
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from tests.unit.test_me_service_router import AuthRepositoryForSelfService


class ActiveMfaRepository(AuthRepositoryForSelfService):
    async def get_mfa_enrollment(self, user_id: UUID) -> SimpleNamespace:
        assert user_id == self.user_id
        return SimpleNamespace(status=MfaStatus.ACTIVE.value, encrypted_secret="encrypted")


@pytest.mark.asyncio
async def test_personal_api_key_create_enforces_mfa_and_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    service = AuthService(
        repository=ActiveMfaRepository(user_id),
        redis_client=object(),
        settings=AuthSettings(jwt_secret_key="test-secret", jwt_algorithm="HS256"),
        producer=None,
    )

    monkeypatch.setattr("platform.auth.service.decrypt_secret", lambda *_: "totp-secret")
    monkeypatch.setattr("platform.auth.service.verify_totp_code", lambda _, code: code == "123456")

    with pytest.raises(InvalidMfaTokenError):
        await service.create_for_current_user(user_id, "missing-mfa")
    with pytest.raises(InvalidMfaCodeError):
        await service.create_for_current_user(user_id, "bad-mfa", mfa_token="000000")

    async def allow_scope(
        *,
        user_id: UUID,
        resource_type: str,
        action: str,
        workspace_id: UUID | None,
        **_: Any,
    ) -> SimpleNamespace:
        assert resource_type == "agents"
        assert action == "read"
        assert workspace_id is None
        return SimpleNamespace(allowed=True)

    service.check_permission = allow_scope  # type: ignore[method-assign]
    created = await service.create_for_current_user(
        user_id,
        "cli",
        scopes=["agents:read"],
        mfa_token="123456",
    )
    assert created.api_key.startswith("msk_")


@pytest.mark.asyncio
async def test_personal_api_key_scope_errors_are_platform_errors() -> None:
    user_id = uuid4()
    service = AuthService(
        repository=AuthRepositoryForSelfService(user_id),
        redis_client=object(),
        settings=AuthSettings(jwt_secret_key="test-secret", jwt_algorithm="HS256"),
        producer=None,
    )

    async def deny_scope(**_: Any) -> SimpleNamespace:
        return SimpleNamespace(allowed=False)

    service.check_permission = deny_scope  # type: ignore[method-assign]
    with pytest.raises(AuthorizationError):
        await service.create_for_current_user(user_id, "forbidden", scopes=["admin:write"])
    with pytest.raises(ValidationError):
        await service.create_for_current_user(user_id, "malformed", scopes=["admin"])
