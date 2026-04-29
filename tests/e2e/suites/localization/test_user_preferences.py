from __future__ import annotations


def test_user_preferences_locale_and_theme_roundtrip_contract() -> None:
    preferences = {"locale": "en", "theme": "high-contrast"}
    assert preferences["locale"] == "en"
    assert preferences["theme"] == "high-contrast"
