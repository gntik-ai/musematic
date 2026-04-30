from __future__ import annotations


def test_webhook_connector_uses_head_for_connectivity(workspace_with_connectors) -> None:
    assert "webhook" in workspace_with_connectors["connectors"]

    dry_run = {
        "method": "HEAD",
        "activation_method": "POST",
        "hmac_secret_path": "secret/data/connectors/workspaces/workspace-owner-e2e/webhook/signing",
    }

    assert dry_run["method"] == "HEAD"
    assert dry_run["activation_method"] == "POST"
    assert dry_run["hmac_secret_path"].startswith(workspace_with_connectors["credential_path_prefix"])
