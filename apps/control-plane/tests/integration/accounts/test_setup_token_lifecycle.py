from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_first_admin_token_validation_rejects_expired_consumed_and_superseded_tokens() -> None:
    source = _read("src/platform/accounts/first_admin_invite.py")
    active_lookup = source.split("async def _active_by_token", maxsplit=1)[1]

    for snippet in (
        "invitation.expires_at <= now",
        "invitation.consumed_at is not None",
        "invitation.prior_token_invalidated_at is not None",
        "raise SetupTokenInvalidError()",
    ):
        assert snippet in active_lookup

    validate = source.split("async def validate", maxsplit=1)[1].split(
        "async def consume", maxsplit=1
    )[0]
    assert "TenantFirstAdminInviteValidationResponse(" in validate
    assert "current_step=self.current_step(invitation)" in validate
    assert "completed_steps=completed" in validate
