from __future__ import annotations

from platform.tenants.vault_paths import legacy_vault_path, platform_vault_path, tenant_vault_path

import pytest


def test_tenant_vault_path() -> None:
    assert (
        tenant_vault_path("dev", "acme", "oauth", "google/client")
        == "secret/data/musematic/dev/tenants/acme/oauth/google/client"
    )


def test_platform_vault_path() -> None:
    assert (
        platform_vault_path("production", "_internal", "cert-manager")
        == "secret/data/musematic/production/_platform/_internal/cert-manager"
    )


def test_legacy_vault_path_remains_valid() -> None:
    assert (
        legacy_vault_path("test", "connectors", "github/token")
        == "secret/data/musematic/test/connectors/github/token"
    )


@pytest.mark.parametrize(
    ("env", "slug", "domain", "resource"),
    [
        ("prod", "acme", "oauth", "google"),
        ("dev", "Acme", "oauth", "google"),
        ("dev", "acme", "unknown", "google"),
        ("dev", "acme", "oauth", "../google"),
    ],
)
def test_tenant_vault_path_rejects_invalid_segments(
    env: str,
    slug: str,
    domain: str,
    resource: str,
) -> None:
    with pytest.raises(ValueError, match=r"unsupported|invalid|relative"):
        tenant_vault_path(env, slug, domain, resource)
