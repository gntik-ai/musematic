from __future__ import annotations

from platform.admin.rbac import is_admin, is_superadmin, role_names


def test_role_names_accepts_string_and_structured_claims() -> None:
    assert role_names({"roles": ["platform_admin", {"role": "superadmin"}, object()]}) == {
        "platform_admin",
        "superadmin",
    }


def test_admin_role_helpers_accept_canonical_roles() -> None:
    assert is_admin({"roles": ["platform_admin"]}) is True
    assert is_admin({"roles": [{"role": "superadmin"}]}) is True
    assert is_superadmin({"roles": ["superadmin"]}) is True
    assert is_admin({"roles": ["viewer"]}) is False
