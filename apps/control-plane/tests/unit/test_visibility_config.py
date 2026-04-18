from __future__ import annotations

from platform.common.config import PlatformSettings, VisibilitySettings

import pytest
from pydantic import ValidationError


def test_visibility_settings_defaults_to_disabled() -> None:
    settings = VisibilitySettings()

    assert settings.zero_trust_enabled is False


def test_visibility_settings_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VISIBILITY_ZERO_TRUST_ENABLED", "true")

    settings = VisibilitySettings()

    assert settings.zero_trust_enabled is True


def test_visibility_settings_rejects_invalid_environment_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VISIBILITY_ZERO_TRUST_ENABLED", "not-a-bool")

    with pytest.raises(ValidationError):
        VisibilitySettings()


def test_platform_settings_exposes_visibility_configuration() -> None:
    settings = PlatformSettings(VISIBILITY_ZERO_TRUST_ENABLED=True)

    assert settings.visibility.zero_trust_enabled is True
