from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]


def _read(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def test_first_agent_step_availability_is_controlled_by_feature_flag_and_echoed_in_state() -> None:
    service = _read("src/platform/accounts/onboarding.py")
    frontend = (
        CONTROL_PLANE.parent
        / "web/components/features/onboarding/OnboardingWizard.tsx"
    ).read_text(encoding="utf-8")

    assert "FEATURE_FIRST_AGENT_ONBOARDING" in service
    assert "first_agent_step_available=await self.is_first_agent_step_available()" in service
    assert 'to_step = "first_agent" if first_agent_available else "tour"' in service
    assert "state.first_agent_step_available" in frontend
    assert (
        'const BASE_STEPS: OnboardingStep[] = ["workspace_named", "invitations", "tour"]'
        in frontend
    )
    assert "state?.first_agent_step_available === false ? BASE_STEPS : FULL_STEPS" in frontend
