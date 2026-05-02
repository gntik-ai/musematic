from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_resend_invalidates_prior_token_creates_fresh_token_and_audits_both_ids() -> None:
    source = _read("src/platform/accounts/first_admin_invite.py")
    resend = source.split("async def resend", maxsplit=1)[1].split(
        "async def resend_for_tenant", maxsplit=1
    )[0]

    for snippet in (
        "prior.prior_token_invalidated_at = datetime.now(UTC)",
        "fresh, token = await self.issue(",
        "AccountsEventType.first_admin_invitation_resent",
        '"prior_invitation_id": str(prior.id)',
        '"new_invitation_id": str(fresh.id)',
        "accounts_first_admin_invitation_resent_total.inc()",
    ):
        assert snippet in resend
