from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


def test_oauth_provider_uniqueness_is_tenant_scoped() -> None:
    migration = (ROOT / "migrations/versions/102_oauth_provider_tenant_scope.py").read_text(
        encoding="utf-8"
    )
    model = (ROOT / "src/platform/auth/models.py").read_text(encoding="utf-8")
    repository = (ROOT / "src/platform/auth/repository_oauth.py").read_text(encoding="utf-8")

    assert "uq_oauth_providers_tenant_type" in migration
    assert '["tenant_id", "provider_type"]' in migration
    assert "UniqueConstraint(\"tenant_id\", \"provider_type\"" in model
    assert "OAuthProvider.tenant_id == tenant_id" in repository
    assert "index_elements=[OAuthProvider.tenant_id, OAuthProvider.provider_type]" in repository


def test_oauth_redirect_uri_is_derived_from_current_tenant() -> None:
    service = (ROOT / "src/platform/auth/services/oauth_service.py").read_text(encoding="utf-8")

    assert "current_tenant.get(None)" in service
    assert "https://{tenant.subdomain}.{domain}/auth/oauth/{provider_type}/callback" in service
