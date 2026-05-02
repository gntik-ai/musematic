from __future__ import annotations

from pathlib import Path


def test_107_migration_declares_first_admin_invitation_storage() -> None:
    source = Path("migrations/versions/107_tenant_first_admin_invitations.py").read_text(
        encoding="utf-8"
    )

    assert '"tenant_first_admin_invitations"' in source
    assert "tenant_first_admin_invitations_token_unique" in source
    assert "tenant_first_admin_invitations_tenant_active_idx" in source
    assert "tenant_first_admin_invitations_target_email_idx" in source
    assert "setup_step_state" in source
    assert "mfa_required" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
