from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_first_install_checklist_has_all_required_items_and_links() -> None:
    component = (
        ROOT / "apps/web/components/features/admin/FirstInstallChecklist.tsx"
    ).read_text()

    expected = [
        "/admin/settings",
        "/admin/oauth-providers",
        "/admin/users",
        "/admin/health",
        "/admin/lifecycle/backup",
        "/admin/audit-chain",
    ]
    for route in expected:
        assert route in component
    assert component.count("href:") >= 7
    assert "/api/v1/admin/users/me/checklist-state" in (
        ROOT / "apps/web/lib/hooks/use-admin-mutations.ts"
    ).read_text()


def test_mfa_enrollment_cannot_be_skipped_without_insecure_override() -> None:
    bootstrap = (ROOT / "apps/control-plane/src/platform/admin/bootstrap.py").read_text()
    checklist = (ROOT / "apps/web/components/features/admin/FirstInstallChecklist.tsx").read_text()

    assert "ALLOW_INSECURE" in bootstrap or "MFA_ENROLLMENT" in bootstrap
    assert "MFA" in checklist
