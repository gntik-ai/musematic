from __future__ import annotations

from platform.trust.services.moderation_action_resolver import resolve_action
from types import SimpleNamespace


def test_single_category_uses_policy_action() -> None:
    policy = SimpleNamespace(action_map={"toxicity": "block"}, default_action="flag")

    assert resolve_action(["toxicity"], policy) == "block"


def test_multi_category_safer_action_wins() -> None:
    policy = SimpleNamespace(
        action_map={"toxicity": "flag", "hate_speech": "block", "pii_leakage": "redact"},
        default_action="flag",
    )

    assert resolve_action(["toxicity", "hate_speech", "pii_leakage"], policy) == "block"


def test_empty_triggered_returns_fallback() -> None:
    policy = SimpleNamespace(action_map={}, default_action="flag")

    assert resolve_action([], policy) == "flag"
