from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[3]
PLATFORM_CHART = ROOT / "deploy/helm/platform"
VALUES_OVERLAY = ROOT / "tests/e2e/cluster/values-e2e.yaml"


def test_values_overlay_declares_both_mock_oauth_providers() -> None:
    contents = VALUES_OVERLAY.read_text(encoding="utf-8")
    assert "mockOAuth:" in contents
    assert "google:" in contents
    assert "github:" in contents
    assert "mock-google-oidc" in contents
    assert "mock-github-oauth" in contents


def test_mock_oauth_disabled_in_production() -> None:
    if shutil.which("helm") is None:
        pytest.skip("helm is required for production-safety rendering checks")

    rendered = subprocess.run(
        [
            "helm",
            "template",
            "release",
            str(PLATFORM_CHART),
            "--set",
            "global.environment=production",
            "--set",
            "controlPlane.common.featureE2EMode=false",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    output = rendered.stdout
    assert "mock-google-oidc" not in output
    assert "mock-github-oauth" not in output
