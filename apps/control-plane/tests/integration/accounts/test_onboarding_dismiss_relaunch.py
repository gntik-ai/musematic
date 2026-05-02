from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_onboarding_dismiss_preserves_state_and_relaunch_resumes_first_incomplete_step() -> None:
    source = _read("src/platform/accounts/onboarding.py")

    dismiss = source.split("async def dismiss", maxsplit=1)[1].split(
        "async def relaunch", maxsplit=1
    )[0]
    relaunch = source.split("async def relaunch", maxsplit=1)[1].split(
        "def is_first_agent_step_available", maxsplit=1
    )[0]

    assert "state.dismissed_at = datetime.now(UTC)" in dismiss
    assert "state.last_step_attempted" in dismiss
    assert "accounts.onboarding.dismissed" in dismiss
    assert "state.dismissed_at = None" in relaunch
    assert "state.last_step_attempted = self._first_incomplete_step(state)" in relaunch
    assert "accounts.onboarding.relaunched" in relaunch
    assert "if not state.step_invitations_sent_or_skipped:" in source
    assert 'return "first_agent"' in source
