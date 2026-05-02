from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_verify_email_path_uses_idempotent_default_workspace_creation() -> None:
    accounts_service = _read("src/platform/accounts/service.py")
    workspaces_service = _read("src/platform/workspaces/service.py")
    migration = _read("migrations/versions/106_user_onboarding_states.py")

    assert ".create_default_workspace(" in accounts_service
    assert "get_default_workspace_for_owner(user_id)" in workspaces_service
    assert "if existing is not None:" in workspaces_service
    assert "return self._workspace_response(existing)" in workspaces_service

    assert '"workspaces_user_default_unique"' in migration
    assert '["owner_id"]' in migration
    assert "unique=True" in migration
    assert "is_default = true" in migration
