from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_default_tenant_oauth_signup_triggers_workspace_completion_path() -> None:
    source = _read("src/platform/auth/services/oauth_service.py")

    assert "await self._complete_default_oauth_signup(" in source
    assert "UserStatus.pending_profile_completion" in source
    completion = source.split("async def _complete_default_oauth_signup", maxsplit=1)[1]

    for snippet in (
        'tenant.kind != "default"',
        "WorkspacesService(",
        ".create_default_workspace(",
        "SubscriptionService(",
        ".provision_for_default_workspace(",
        "AccountsEventType.signup_completed",
        "SignupCompletedPayload(",
        'signup_method=f"oauth-{provider_type}"',
        "AuditChainService(",
    ):
        assert snippet in completion
