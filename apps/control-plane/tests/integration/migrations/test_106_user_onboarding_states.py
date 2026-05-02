from __future__ import annotations

from pathlib import Path


def test_106_migration_declares_onboarding_rls_and_default_workspace_index() -> None:
    source = Path("migrations/versions/106_user_onboarding_states.py").read_text(
        encoding="utf-8"
    )

    assert '"user_onboarding_states"' in source
    assert "user_onboarding_states_user_unique" in source
    assert "user_onboarding_states_tenant_idx" in source
    assert "workspaces_user_default_unique" in source
    assert "is_default = true" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source


def test_106_migration_scopes_email_uniqueness_by_tenant() -> None:
    source = Path("migrations/versions/106_user_onboarding_states.py").read_text(
        encoding="utf-8"
    )

    assert "uq_accounts_users_tenant_email" in source
    assert "uq_users_tenant_email" in source
    assert "uq_user_credentials_tenant_email" in source
    assert "uq_accounts_users_email" in source
    assert "uq_users_email" in source
    assert "uq_user_credentials_email" in source
