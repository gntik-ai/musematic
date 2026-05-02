from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CONTROL_PLANE = Path(__file__).resolve().parents[3]
WEB = CONTROL_PLANE.parent / "web"


def _read_control_plane(relative: str) -> str:
    return (CONTROL_PLANE / relative).read_text(encoding="utf-8")


def _read_web(relative: str) -> str:
    return (WEB / relative).read_text(encoding="utf-8")


def test_tenant_switcher_is_hidden_for_single_membership_and_backed_by_memberships_count() -> None:
    switcher = _read_web("components/features/shell/TenantSwitcher.tsx")
    hook = _read_web("lib/hooks/use-memberships.ts")
    router = _read_control_plane("src/platform/accounts/memberships_router.py")

    assert "const { currentMembership, isLoading, memberships } = useMemberships();" in switcher
    assert "isLoading || memberships.length < 2" in switcher
    assert "return null" in switcher
    assert "window.location.assign(membership.login_url)" in switcher

    assert '"/api/v1/me/memberships"' in hook
    assert "is_current_tenant" in hook
    assert (
        "return MembershipsListResponse(memberships=memberships, count=len(memberships))"
        in router
    )
