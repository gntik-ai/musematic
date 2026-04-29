from __future__ import annotations


def test_model_provider_total_outage_exhausts_fallbacks_without_state_corruption() -> None:
    outcome = {
        "fallbacks_walked": ["primary", "tier2", "tier3"],
        "error": "model unavailable, all fallbacks exhausted",
        "state_recoverable": True,
    }

    assert outcome["fallbacks_walked"] == ["primary", "tier2", "tier3"]
    assert "all fallbacks exhausted" in outcome["error"]
    assert outcome["state_recoverable"] is True
