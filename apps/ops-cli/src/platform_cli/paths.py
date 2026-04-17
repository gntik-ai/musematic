"""Filesystem path helpers shared across the CLI package."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
APPS_ROOT = REPO_ROOT / "apps"
DEPLOY_ROOT = REPO_ROOT / "deploy"
HELM_ROOT = DEPLOY_ROOT / "helm"
CONTROL_PLANE_ROOT = APPS_ROOT / "control-plane"
CONTROL_PLANE_SRC = CONTROL_PLANE_ROOT / "src"


def helm_chart_path(chart_name: str) -> Path:
    """Return the absolute path to a Helm chart directory."""

    return HELM_ROOT / chart_name
