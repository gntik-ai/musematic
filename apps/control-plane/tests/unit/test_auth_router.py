from __future__ import annotations

from platform.auth.router import (
    confirm_mfa,
    create_service_account,
    enroll_mfa,
    login,
    logout,
    logout_all,
    refresh_token,
    revoke_service_account,
    rotate_service_account_key,
    verify_mfa,
)
from platform.auth.schemas import (
    LoginRequest,
    LoginResponse,
    LogoutAllResponse,
    MessageResponse,
    MfaConfirmRequest,
    MfaConfirmResponse,
    MfaEnrollResponse,
    MfaVerifyRequest,
    RefreshRequest,
    ServiceAccountCreateRequest,
    ServiceAccountCreateResponse,
    TokenPair,
)
from platform.common.exceptions import AuthorizationError
from types import SimpleNamespace
from uuid import uuid4

import pytest


class RouterServiceStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []
        self.service_account_id = uuid4()

    async def login(self, *args):
        self.calls.append(("login", args, {}))
        return LoginResponse(access_token="access", refresh_token="refresh", expires_in=900)

    async def refresh_token(self, *args):
        self.calls.append(("refresh_token", args, {}))
        return TokenPair(access_token="new-access", refresh_token="refresh", expires_in=900)

    async def logout(self, *args):
        self.calls.append(("logout", args, {}))

    async def logout_all(self, *args):
        self.calls.append(("logout_all", args, {}))
        return 3

    async def enroll_mfa(self, *args):
        self.calls.append(("enroll_mfa", args, {}))
        return MfaEnrollResponse(
            secret="secret",
            provisioning_uri="otpauth://example",
            recovery_codes=["A1"],
        )

    async def confirm_mfa(self, *args):
        self.calls.append(("confirm_mfa", args, {}))
        return MfaConfirmResponse()

    async def verify_mfa(self, *args):
        self.calls.append(("verify_mfa", args, {}))
        return TokenPair(access_token="access", refresh_token="refresh", expires_in=900)

    async def create_service_account(self, *args, **kwargs):
        self.calls.append(("create_service_account", args, kwargs))
        return ServiceAccountCreateResponse(
            service_account_id=self.service_account_id,
            name="ci-bot",
            api_key="msk_key",
            role="service_account",
        )

    async def rotate_api_key(self, *args):
        self.calls.append(("rotate_api_key", args, {}))
        return "msk_rotated"

    async def revoke_service_account(self, *args):
        self.calls.append(("revoke_service_account", args, {}))


def _request() -> SimpleNamespace:
    return SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"User-Agent": "pytest"},
    )


@pytest.mark.asyncio
async def test_router_functions_handle_requests_and_responses() -> None:
    service = RouterServiceStub()
    current_user = {
        "sub": str(uuid4()),
        "email": "admin@example.com",
        "session_id": str(uuid4()),
        "roles": [{"role": "platform_admin", "workspace_id": None}],
    }

    login_response = await login(
        LoginRequest(email="user@example.com", password="secret"),
        _request(),
        auth_service=service,
    )
    refresh_response = await refresh_token(
        RefreshRequest(refresh_token="refresh"),
        auth_service=service,
    )
    logout_response = await logout(current_user=current_user, auth_service=service)
    logout_all_response = await logout_all(current_user=current_user, auth_service=service)
    enroll_response = await enroll_mfa(current_user=current_user, auth_service=service)
    confirm_response = await confirm_mfa(
        MfaConfirmRequest(totp_code="123456"),
        current_user=current_user,
        auth_service=service,
    )
    verify_response = await verify_mfa(
        MfaVerifyRequest(mfa_token="token", totp_code="123456"),
        auth_service=service,
    )
    create_response = await create_service_account(
        ServiceAccountCreateRequest(name="ci-bot", role="service_account"),
        current_user=current_user,
        auth_service=service,
    )
    rotate_response = await rotate_service_account_key(
        service.service_account_id,
        current_user=current_user,
        auth_service=service,
    )
    revoke_response = await revoke_service_account(
        service.service_account_id,
        current_user=current_user,
        auth_service=service,
    )

    assert login_response.token_type == "bearer"
    assert refresh_response.token_type == "bearer"
    assert logout_response == MessageResponse(message="Session terminated")
    assert logout_all_response == LogoutAllResponse(
        message="All sessions terminated",
        sessions_revoked=3,
    )
    assert enroll_response.provisioning_uri == "otpauth://example"
    assert confirm_response == MfaConfirmResponse()
    assert verify_response.token_type == "bearer"
    assert create_response.api_key == "msk_key"
    assert rotate_response == MessageResponse(message="msk_rotated")
    assert revoke_response == MessageResponse(message="Service account revoked")
    assert {name for name, _, _ in service.calls} == {
        "login",
        "refresh_token",
        "logout",
        "logout_all",
        "enroll_mfa",
        "confirm_mfa",
        "verify_mfa",
        "create_service_account",
        "rotate_api_key",
        "revoke_service_account",
    }


@pytest.mark.asyncio
async def test_router_requires_platform_admin_for_service_accounts() -> None:
    service = RouterServiceStub()
    current_user = {
        "sub": str(uuid4()),
        "email": "viewer@example.com",
        "session_id": str(uuid4()),
        "roles": [{"role": "viewer", "workspace_id": None}],
    }

    with pytest.raises(AuthorizationError):
        await create_service_account(
            ServiceAccountCreateRequest(name="ci-bot", role="service_account"),
            current_user=current_user,
            auth_service=service,
        )
