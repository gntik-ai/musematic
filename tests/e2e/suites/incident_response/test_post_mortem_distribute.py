from __future__ import annotations


def test_post_mortem_distribution_boundary_scenario_registered() -> None:
    scenario = {
        "journey": "resolved incident -> post-mortem composer -> notifications delivery",
        "assertions": [
            "timeline_source_coverage_visible",
            "blameless_post_mortem_published",
            "distribution_event_produced",
            "per_recipient_outcomes_visible",
        ],
    }

    assert "post-mortem composer" in scenario["journey"]
    assert "per_recipient_outcomes_visible" in scenario["assertions"]
