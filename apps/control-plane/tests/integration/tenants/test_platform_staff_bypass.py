from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


def test_platform_staff_workspace_bypass_uses_bypass_session_and_audits() -> None:
    router = (ROOT / "src/platform/workspaces/platform_router.py").read_text(encoding="utf-8")

    assert 'prefix="/api/v1/platform/workspaces"' in router
    assert "get_platform_staff_session" in router
    assert "platform.tenants.workspace_read" in router
    assert "actor_role=\"platform_staff\"" in router
    assert "await session.commit()" in router
