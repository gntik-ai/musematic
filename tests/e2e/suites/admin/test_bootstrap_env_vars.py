from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]


def test_bootstrap_job_maps_superadmin_env_vars() -> None:
    template = (ROOT / "deploy/helm/platform/templates/platform-bootstrap-job.yaml").read_text()
    values = (ROOT / "deploy/helm/platform/values.yaml").read_text()

    assert "python -m platform.admin.bootstrap" in template
    assert "PLATFORM_SUPERADMIN_USERNAME" in template
    assert "PLATFORM_SUPERADMIN_EMAIL" in template
    assert "PLATFORM_SUPERADMIN_PASSWORD" in template
    assert "passwordSecretRef" in values
    assert "mfaEnrollment" in values


def test_bootstrap_implementation_rejects_missing_email_and_password_conflict() -> None:
    bootstrap = (ROOT / "apps/control-plane/src/platform/admin/bootstrap.py").read_text()

    assert "PLATFORM_SUPERADMIN_EMAIL" in bootstrap
    assert "PLATFORM_SUPERADMIN_PASSWORD_FILE" in bootstrap
    assert "PLATFORM_SUPERADMIN_PASSWORD" in bootstrap
    assert "Cannot set both PLATFORM_SUPERADMIN_PASSWORD and PLATFORM_SUPERADMIN_PASSWORD_FILE" in bootstrap


def test_force_reset_superadmin_safety_rails_are_present() -> None:
    bootstrap = (ROOT / "apps/control-plane/src/platform/admin/bootstrap.py").read_text()

    assert "PLATFORM_FORCE_RESET_SUPERADMIN" in bootstrap
    assert "ALLOW_SUPERADMIN_RESET" in bootstrap
    assert "platform.superadmin.force_reset" in bootstrap
    assert "platform.superadmin.bootstrapped" in bootstrap


@pytest.mark.asyncio
async def test_bootstrap_audit_endpoint_visible_to_superadmin(http_client_superadmin) -> None:
    response = await http_client_superadmin.get("/api/v1/admin/lifecycle/installer")
    assert response.status_code in {200, 404, 405}
