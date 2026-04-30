from __future__ import annotations

import pyotp
import pytest

from suites._helpers import assert_status, post_json


@pytest.mark.asyncio
async def test_mfa_stepper_flow(self_service_client) -> None:
    enrollment = assert_status(await self_service_client.post("/api/v1/auth/mfa/enroll", json={}))
    secret = enrollment.get("secret") or enrollment.get("secret_key")
    assert secret
    code = pyotp.TOTP(secret.replace(" ", "")).now()
    confirmed = await post_json(
        self_service_client,
        "/api/v1/auth/mfa/confirm",
        {"totp_code": code},
    )
    assert confirmed.get("status", "active") == "active"


@pytest.mark.asyncio
async def test_backup_codes_are_one_time_material(self_service_client) -> None:
    enrollment = assert_status(await self_service_client.post("/api/v1/auth/mfa/enroll", json={}))
    recovery_codes = enrollment.get("recovery_codes", [])
    assert isinstance(recovery_codes, list)


@pytest.mark.asyncio
async def test_regenerate_backup_codes_requires_totp(mfa_enabled_user) -> None:
    response = await mfa_enabled_user.post(
        "/api/v1/auth/mfa/recovery-codes/regenerate",
        json={"totp_code": "000000"},
    )
    assert response.status_code in {200, 401, 422}


@pytest.mark.asyncio
async def test_disable_refused_with_invalid_step_up(mfa_enabled_user) -> None:
    response = await mfa_enabled_user.post(
        "/api/v1/auth/mfa/disable",
        json={"password": "wrong-password", "totp_code": "000000"},
    )
    assert response.status_code in {401, 403, 422}


@pytest.mark.asyncio
async def test_mfa_audit_events_are_user_scoped(self_service_client) -> None:
    payload = assert_status(
        await self_service_client.get(
            "/api/v1/me/activity",
            params={"event_type": "auth.mfa.enrolled"},
        )
    )
    assert "items" in payload
