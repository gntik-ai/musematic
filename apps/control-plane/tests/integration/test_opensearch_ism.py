from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.asyncio


@pytest.mark.skipif(
    os.environ.get("RUN_LONG_OPENSEARCH_TESTS") != "1",
    reason="Requires a full ISM lifecycle window to expire and delete an index.",
)
async def test_short_retention_ism_policy_can_delete_index(initialized_opensearch_client) -> None:
    await initialized_opensearch_client._client.transport.perform_request(
        method="PUT",
        url="/_plugins/_ism/policies/test-short-retention",
        body={
            "policy": {
                "description": "Delete test index quickly",
                "default_state": "hot",
                "states": [
                    {
                        "name": "hot",
                        "actions": [],
                        "transitions": [{"state_name": "delete", "conditions": {"min_index_age": "1m"}}],
                    },
                    {"name": "delete", "actions": [{"delete": {}}], "transitions": []},
                ],
                "ism_template": [{"index_patterns": ["audit-events-ism-test*"], "priority": 200}],
            }
        },
    )
    await initialized_opensearch_client._client.indices.create(
        index="audit-events-ism-test-000001",
        body={"settings": {"plugins.index_state_management.policy_id": "test-short-retention"}},
    )
    explain = await initialized_opensearch_client._client.transport.perform_request(
        method="GET",
        url="/_plugins/_ism/explain/audit-events-ism-test-000001",
    )
    assert explain["audit-events-ism-test-000001"]["policy_id"] == "test-short-retention"


async def test_marketplace_index_has_no_ism_policy_and_connector_template_does(initialized_opensearch_client) -> None:
    explain = await initialized_opensearch_client._client.transport.perform_request(
        method="GET",
        url="/_plugins/_ism/explain/marketplace-agents-000001",
    )
    assert explain["marketplace-agents-000001"]["policy_id"] in (None, "")

    template = await initialized_opensearch_client._client.indices.get_index_template(name="connector-payloads")
    settings = template["index_templates"][0]["index_template"]["template"]["settings"]
    assert settings["plugins.index_state_management.policy_id"] == "connector-payloads-policy"
