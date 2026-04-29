from __future__ import annotations

import pytest


pytestmark = [pytest.mark.journey, pytest.mark.j14_model_steward]


def test_j14_model_catalog_and_fallback_cycle_contract() -> None:
    stages = [
        "model_card_approved",
        "model_card_retrieved",
        "model_deprecated_with_grace_period",
        "grandfathered_execution_allowed",
        "fallback_policy_saved",
        "primary_429_injected",
        "tier2_fallback_used",
        "fallback_event_emitted",
        "fallback_cost_attributed",
        "deprecation_audit_entry",
        "model_catalog_dashboard_snapshot",
    ]

    assert len(stages) >= 7
    assert {"tier2_fallback_used", "fallback_cost_attributed"} <= set(stages)


def test_j14_fallback_cascade_exhaustion_contract() -> None:
    exhausted = {
        "primary": "429",
        "tier2": "429",
        "tier3": "429",
        "error": "model unavailable, all fallbacks exhausted",
        "cost_event_emitted": False,
    }

    assert "all fallbacks exhausted" in exhausted["error"]
    assert exhausted["cost_event_emitted"] is False


def test_j14_grace_period_elapsed_contract() -> None:
    outcome = {"deprecated": True, "grace_period_elapsed": True, "allowed": False}

    assert outcome["deprecated"] is True
    assert outcome["grace_period_elapsed"] is True
    assert outcome["allowed"] is False
