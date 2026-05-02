from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_setup_step_state_persists_each_completed_step_and_drives_resume_position() -> None:
    source = _read("src/platform/accounts/first_admin_invite.py")
    record_step = source.split("async def record_step", maxsplit=1)[1].split(
        "async def _active_by_token", maxsplit=1
    )[0]

    assert "invitation.setup_step_state = {" in record_step
    assert "**(invitation.setup_step_state or {})" in record_step
    assert "step: True" in record_step
    assert 'f"{step}_payload": payload' in record_step
    assert "await self.session.flush()" in record_step

    assert 'for step in ("tos", "credentials", "mfa", "workspace", "invitations")' in source
    assert "if not state.get(step):" in source
    assert "return step" in source
