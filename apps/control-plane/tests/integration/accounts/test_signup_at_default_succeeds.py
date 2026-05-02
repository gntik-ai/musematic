from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_verify_email_completes_signup_with_workspace_subscription_event_and_audit() -> None:
    source = _read("src/platform/accounts/service.py")

    assert "await self._complete_default_signup(updated_user, correlation)" in source
    completion = source.split("async def _complete_default_signup", maxsplit=1)[1]

    for snippet in (
        "WorkspacesService(",
        ".create_default_workspace(",
        "SubscriptionService(",
        ".provision_for_default_workspace(",
        "AccountsEventType.signup_completed",
        "SignupCompletedPayload(",
        "AuditChainService(",
        "event_type=AccountsEventType.signup_completed.value",
    ):
        assert snippet in completion

    assert completion.index(".create_default_workspace(") < completion.index(
        "AccountsEventType.signup_completed"
    )
    assert completion.index(".provision_for_default_workspace(") < completion.index(
        "AccountsEventType.signup_completed"
    )
