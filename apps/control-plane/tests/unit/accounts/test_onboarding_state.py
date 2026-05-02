from __future__ import annotations

from pathlib import Path


def test_onboarding_service_contract_and_metrics_are_present() -> None:
    source = Path("src/platform/accounts/onboarding.py").read_text(encoding="utf-8")

    for method in (
        "get_or_create_state",
        "advance_step",
        "dismiss",
        "relaunch",
        "is_first_agent_step_available",
    ):
        assert f"async def {method}" in source
    assert "accounts_onboarding_step_advanced_total" in source
    assert "accounts_onboarding_dismissed_total" in source
    assert "accounts.onboarding.step_advanced" in source
    assert "accounts.onboarding.dismissed" in source
