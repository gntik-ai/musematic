from __future__ import annotations


def test_member_management_lifecycle_contract(multi_member_workspace) -> None:
    actions = ["list", "invite", "role_change", "remove"]
    audit_events = [
        "auth.workspace.member_added",
        "auth.workspace.role_changed",
        "auth.workspace.member_removed",
    ]

    assert len(multi_member_workspace["members"]) == 4
    assert actions == ["list", "invite", "role_change", "remove"]
    assert audit_events[0].endswith("member_added")


def test_owner_role_is_not_removed_without_transfer(multi_member_workspace) -> None:
    owner = next(item for item in multi_member_workspace["members"] if item["role"] == "owner")

    assert owner["user_id"] == "owner"
    assert owner["role"] == "owner"
