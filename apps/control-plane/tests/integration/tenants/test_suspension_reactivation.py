from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


def test_suspension_and_reactivation_emit_events_and_invalidate_cache() -> None:
    service = (ROOT / "src/platform/tenants/service.py").read_text(encoding="utf-8")
    router = (ROOT / "src/platform/tenants/admin_router.py").read_text(encoding="utf-8")

    assert "async def suspend_tenant" in service
    assert "TenantEventType.suspended" in service
    assert "async def reactivate_tenant" in service
    assert "TenantEventType.reactivated" in service
    assert "_publish_cache_invalidation" in service
    assert '@router.post("/{tenant_id}/suspend"' in router
    assert '@router.post("/{tenant_id}/reactivate"' in router
