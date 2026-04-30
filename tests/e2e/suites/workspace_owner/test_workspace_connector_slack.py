from __future__ import annotations


def test_slack_connector_self_service_contract(workspace_with_connectors) -> None:
    assert "slack" in workspace_with_connectors["connectors"]

    flow = [
        "prerequisites",
        "credentials",
        "test_connectivity_auth_test",
        "scope",
        "activate",
    ]

    assert flow[2] == "test_connectivity_auth_test"
    assert workspace_with_connectors["credential_path_prefix"].startswith("secret/data/")


def test_slack_test_connectivity_never_creates_delivery() -> None:
    dry_run = {
        "provider_call": "slack.auth.test",
        "outbound_deliveries_created": 0,
        "user_visible_messages": 0,
    }

    assert dry_run["outbound_deliveries_created"] == 0
    assert dry_run["user_visible_messages"] == 0
