from __future__ import annotations

from pathlib import Path


def test_first_admin_invite_lifecycle_contract_is_present() -> None:
    source = Path("src/platform/accounts/first_admin_invite.py").read_text(encoding="utf-8")

    for method in ("issue", "validate", "consume", "resend", "resend_for_tenant"):
        assert f"async def {method}" in source
    assert "prior_token_invalidated_at" in source
    assert "send_invitation_email" in source
    assert "accounts_first_admin_invitation_issued_total" in source
    assert "accounts_first_admin_invitation_resent_total" in source
    assert "accounts_first_admin_invitation_consumed_seconds" in source
