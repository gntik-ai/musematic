"""UPD-050 — geo_block.is_blocked policy logic tests."""

from __future__ import annotations

from platform.security.abuse_prevention.geo_block import is_blocked


def test_disabled_mode_never_blocks() -> None:
    assert is_blocked(country="XX", mode="disabled", blocked_country_codes=["XX"]) is False


def test_deny_mode_blocks_listed() -> None:
    assert is_blocked(country="XX", mode="deny", blocked_country_codes=["XX"]) is True
    assert is_blocked(country="US", mode="deny", blocked_country_codes=["XX"]) is False


def test_allow_only_mode_blocks_unlisted() -> None:
    assert is_blocked(country="US", mode="allow_only", blocked_country_codes=["GB"]) is True
    assert is_blocked(country="GB", mode="allow_only", blocked_country_codes=["GB"]) is False


def test_unknown_country_fails_open() -> None:
    """When the IP can't be resolved (None country), don't block — the
    spec opts geo-block in explicitly; deny-on-unknown is a future
    option, not the default."""
    assert is_blocked(country=None, mode="deny", blocked_country_codes=["XX"]) is False
    assert is_blocked(country=None, mode="allow_only", blocked_country_codes=["GB"]) is False


def test_case_insensitive_match() -> None:
    assert is_blocked(country="us", mode="deny", blocked_country_codes=["US"]) is True
    assert is_blocked(country="US", mode="deny", blocked_country_codes=["us"]) is True
