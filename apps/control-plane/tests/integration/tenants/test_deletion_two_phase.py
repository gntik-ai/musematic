from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


def test_deletion_lifecycle_uses_2pa_grace_scheduler_and_cascade() -> None:
    service = (ROOT / "src/platform/tenants/service.py").read_text(encoding="utf-8")
    scheduler = (ROOT / "src/platform/tenants/jobs/deletion_grace.py").read_text(
        encoding="utf-8"
    )

    assert "consume_challenge" in service
    assert "tenant_schedule_deletion" in service
    assert "TenantEventType.scheduled_for_deletion" in service
    assert "TenantEventType.deletion_cancelled" in service
    assert "TenantEventType.deleted" in service
    assert "tenant_cascade_handlers" in service
    assert "with_for_update(skip_locked=True)" in scheduler
