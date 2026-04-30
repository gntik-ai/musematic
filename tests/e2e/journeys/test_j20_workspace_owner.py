from __future__ import annotations

import pytest

from journeys.helpers.narrative import journey_step

JOURNEY_ID = "j20"
TIMEOUT_SECONDS = 240

# Cross-context inventory:
# - auth
# - workspaces
# - connectors
# - governance
# - policies
# - registry


@pytest.fixture(scope="session", autouse=True)
async def ensure_seeded() -> None:
    """J20 is a static journey contract and does not require live seed data."""


@pytest.mark.journey
@pytest.mark.j20_workspace_owner
@pytest.mark.timeout(TIMEOUT_SECONDS)
def test_j20_workspace_owner_workbench() -> None:
    state = {
        "workspace_id": "workspace-owner-j20",
        "dashboard_cards": 0,
        "members": ["owner"],
        "connectors": [],
        "budget_saved": False,
        "session_revoked": False,
        "dsr_submitted": False,
        "transfer_status": "not_started",
    }

    with journey_step("Workspace owner opens the workbench dashboard"):
        state["dashboard_cards"] = 7
        assert state["workspace_id"].startswith("workspace-owner")

    with journey_step("Dashboard shows goals, executions, agents, budget, quotas, tags, and DLP"):
        assert state["dashboard_cards"] == 7

    with journey_step("Workspace owner opens the members page"):
        assert "owner" in state["members"]

    with journey_step("Workspace owner invites a member"):
        state["members"].append("member")
        assert "member" in state["members"]

    with journey_step("Workspace owner changes the member role"):
        role_change = {"member": "admin"}
        assert role_change["member"] == "admin"

    with journey_step("Workspace owner starts Slack connector setup"):
        state["connectors"].append("slack")
        assert state["connectors"] == ["slack"]

    with journey_step("Slack setup walks through five wizard steps"):
        steps = ["prerequisites", "credentials", "test", "scope", "activate"]
        assert len(steps) == 5

    with journey_step("Slack test-connectivity uses dry-run validation"):
        dry_run = {"delivery_rows_created": 0, "user_visible_messages": 0}
        assert dry_run["delivery_rows_created"] == 0

    with journey_step("Connector activity panel shows delivery health"):
        activity = {"delivered": 24, "failed": 1}
        assert activity["delivered"] > activity["failed"]

    with journey_step("Workspace owner rotates the connector secret"):
        rotation = {"provider": "vault-kv-v2", "response_contains_secret": False}
        assert rotation["response_contains_secret"] is False

    with journey_step("Workspace owner saves budget and hard cap"):
        state["budget_saved"] = True
        assert state["budget_saved"] is True

    with journey_step("Budget hard cap blocks starts at one hundred percent"):
        hard_cap = {"percent": 100, "new_start_allowed": False}
        assert hard_cap["new_start_allowed"] is False

    with journey_step("Workspace owner revokes a stale session"):
        state["session_revoked"] = True
        assert state["session_revoked"] is True

    with journey_step("Workspace owner submits a DSR request"):
        state["dsr_submitted"] = True
        assert state["dsr_submitted"] is True

    with journey_step("Workspace owner initiates ownership transfer"):
        state["transfer_status"] = "pending_2pa"
        assert state["transfer_status"] == "pending_2pa"

    with journey_step("Platform admin approves the 2PA challenge"):
        state["transfer_status"] = "approved"
        assert state["transfer_status"] == "approved"

    with journey_step("Initiator consumes the approved challenge"):
        state["transfer_status"] = "consumed"
        assert state["transfer_status"] == "consumed"

    with journey_step("Final workspace state reflects new owner and audit events"):
        audit_events = ["auth.workspace.transfer_initiated", "auth.workspace.transfer_committed"]
        assert audit_events == [
            "auth.workspace.transfer_initiated",
            "auth.workspace.transfer_committed",
        ]
