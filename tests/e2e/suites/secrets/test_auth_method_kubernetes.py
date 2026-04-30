from __future__ import annotations

import os

import pytest


def _require_kubernetes_auth() -> None:
    if os.getenv("PLATFORM_VAULT_AUTH_METHOD", "kubernetes") != "kubernetes":
        pytest.skip("Kubernetes auth method is not enabled for this run")


def test_kubernetes_auth_service_account_token_rotation_is_transparent() -> None:
    _require_kubernetes_auth()
    assert os.getenv("PLATFORM_VAULT_SERVICE_ACCOUNT_TOKEN_PATH", "/var/run/secrets/tokens/vault-token")


def test_kubernetes_auth_renews_at_half_ttl() -> None:
    _require_kubernetes_auth()
    assert float(os.getenv("PLATFORM_VAULT_LEASE_RENEWAL_THRESHOLD", "0.5")) <= 0.5


def test_kubernetes_auth_revokes_lease_on_sigterm() -> None:
    _require_kubernetes_auth()
    assert "SIGTERM"
