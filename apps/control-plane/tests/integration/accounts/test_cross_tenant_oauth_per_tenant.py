from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_oauth_provider_lookup_state_and_uniqueness_are_tenant_scoped() -> None:
    repository = _read("src/platform/auth/repository_oauth.py")
    service = _read("src/platform/auth/services/oauth_service.py")
    models = _read("src/platform/auth/models.py")

    assert "OAuthProvider.tenant_id == tenant_id" in repository
    assert "UniqueConstraint(\"tenant_id\", \"provider_type\"" in models
    assert "current_tenant.get(None)" in service
    assert 'str(payload.get("tenant_id")) != str(tenant.id)' in service
    assert "raise OAuthStateInvalidError()" in service
