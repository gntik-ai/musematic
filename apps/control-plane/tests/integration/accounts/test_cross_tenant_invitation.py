from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_cross_tenant_invitation_creates_independent_tenant_scoped_identity() -> None:
    service = _read("src/platform/accounts/service.py")
    migration = _read("migrations/versions/106_user_onboarding_states.py")
    accept = service.split("async def accept_invitation", maxsplit=1)[1].split(
        "async def revoke_invitation", maxsplit=1
    )[0]

    assert 'str(current_tenant_id) != str(invitation.tenant_id)' in accept
    assert "raise CrossTenantInviteAcceptanceError()" in accept
    assert "await self.repo.create_user(" in accept
    assert "signup_source=SignupSource.invitation" in accept
    assert "await self.auth_service.create_user_credential(" in accept
    assert "await self.auth_service.assign_user_roles(" in accept
    assert "AccountsEventType.cross_tenant_invitation_accepted" in accept

    assert '"uq_accounts_users_tenant_email"' in migration
    assert '["tenant_id", "email"]' in migration
