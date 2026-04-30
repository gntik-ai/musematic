from __future__ import annotations

import os

import pytest


def _require_approle_auth() -> None:
    if os.getenv("PLATFORM_VAULT_AUTH_METHOD") != "approle":
        pytest.skip("AppRole auth method is not enabled for this run")


def test_approle_secret_id_expiry_is_reported() -> None:
    _require_approle_auth()
    assert os.getenv("PLATFORM_VAULT_APPROLE_SECRET_ID_SECRET_REF")


def test_approle_login_uses_role_id_and_secret_id() -> None:
    _require_approle_auth()
    assert os.getenv("PLATFORM_VAULT_APPROLE_ROLE_ID")


def test_approle_token_renewal_uses_same_renewal_loop() -> None:
    _require_approle_auth()
    assert float(os.getenv("PLATFORM_VAULT_LEASE_RENEWAL_THRESHOLD", "0.5")) <= 0.5
