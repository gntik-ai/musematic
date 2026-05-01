from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


def test_rls_policy_is_generated_for_catalogued_tables() -> None:
    migration = (ROOT / "migrations/versions/100_tenant_rls_policies.py").read_text(
        encoding="utf-8"
    )

    assert "TENANT_SCOPED_TABLES" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "CREATE POLICY tenant_isolation" in migration
    assert "current_setting('app.tenant_id', true)::uuid" in migration


def test_failed_cross_tenant_probe_has_no_audit_hook() -> None:
    middleware = (
        ROOT / "src/platform/common/middleware/tenant_resolver.py"
    ).read_text(encoding="utf-8")

    assert "_build_opaque_404_response" in middleware
    assert "audit_chain" not in middleware
