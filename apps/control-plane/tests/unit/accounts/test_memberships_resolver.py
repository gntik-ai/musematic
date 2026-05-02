from __future__ import annotations

from pathlib import Path


def test_memberships_resolver_uses_platform_staff_and_email_fanout() -> None:
    source = Path("src/platform/accounts/memberships.py").read_text(encoding="utf-8")

    assert "get_platform_staff_session" in source
    assert "lower(u.email) = lower(:email)" in source
    assert "LEFT JOIN memberships" in source
    assert "tenant_display_name" in source
    assert "login_url" in source
    assert "accounts.memberships.listed" in source
