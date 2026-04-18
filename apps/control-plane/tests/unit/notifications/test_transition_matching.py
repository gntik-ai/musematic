from __future__ import annotations

from platform.notifications.service import AlertService


def test_matches_transition_pattern_with_aliases_and_any_prefix() -> None:
    assert (
        AlertService.matches_transition_pattern("working_to_pending", "running", "waiting") is True
    )
    assert AlertService.matches_transition_pattern("any_to_complete", "paused", "completed") is True
    assert AlertService.matches_transition_pattern("any_to_failed", "ready", "failed") is True


def test_invalid_patterns_are_ignored_when_valid_pattern_exists() -> None:
    patterns = ["broken", "unknown_to_invalid", "any_to_failed"]

    assert (
        any(
            AlertService.matches_transition_pattern(pattern, "running", "failed")
            for pattern in patterns
        )
        is True
    )
    assert (
        AlertService.matches_transition_pattern("working_to_pending", "running", "failed") is False
    )


def test_matches_transition_pattern_rejects_unknown_states() -> None:
    assert (
        AlertService.matches_transition_pattern(
            "review_to_pending",
            "running",
            "waiting",
        )
        is False
    )
    assert (
        AlertService.matches_transition_pattern(
            "working_to_pending",
            "mystery",
            "waiting",
        )
        is False
    )
