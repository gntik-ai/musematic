from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_onboarding_state_creation_and_workspace_step_are_idempotent() -> None:
    source = _read("src/platform/accounts/onboarding.py")
    migration = _read("migrations/versions/106_user_onboarding_states.py")

    get_or_create = source.split("async def get_or_create_state", maxsplit=1)[1].split(
        "async def advance_step", maxsplit=1
    )[0]
    workspace_step = source.split('if step == "workspace-name":', maxsplit=1)[1].split(
        'elif step == "invitations":', maxsplit=1
    )[0]

    assert "if state is None:" in get_or_create
    assert "UserOnboardingState(user_id=user_id, tenant_id=tenant_id)" in get_or_create
    assert "await self.session.flush()" in get_or_create
    assert 'sa.UniqueConstraint("user_id", name="user_onboarding_states_user_unique")' in migration

    assert "await self._rename_default_workspace(user_id, payload)" in workspace_step
    assert "state.step_workspace_named = True" in workspace_step
    assert 'to_step = "invitations"' in workspace_step
