import os
from platform.search.projections import AgentSearchProjection
from uuid import uuid4

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.skipif(
    os.environ.get("RUN_LONG_OPENSEARCH_TESTS") != "1",
    reason="Snapshot create/restore is expensive and depends on runtime repository support.",
)
async def test_manual_snapshot_and_restore(initialized_opensearch_client) -> None:
    snapshot_name = f"manual-test-{uuid4().hex}"
    projection = AgentSearchProjection(initialized_opensearch_client)
    for index in range(25):
        await projection.index_agent(
            {
                "agent_id": f"snapshot-agent-{index}",
                "name": f"Snapshot Agent {index}",
                "purpose": "Snapshot coverage",
                "description": "Agent document for snapshot testing",
                "tags": ["snapshot"],
                "capabilities": ["backup"],
                "maturity_level": 2,
                "trust_score": 0.75,
                "workspace_id": "ws-snapshot",
                "lifecycle_state": "active",
                "certification_status": "certified",
                "publisher_id": "pub-snapshot",
                "fqn": f"test:snapshot:{index}",
            }
        )
    await initialized_opensearch_client._client.indices.refresh(index="marketplace-agents-000001")

    await initialized_opensearch_client._client.snapshot.create(
        repository="opensearch-backups",
        snapshot=snapshot_name,
        body={"indices": "*", "ignore_unavailable": True, "include_global_state": False},
        wait_for_completion=True,
    )
    await initialized_opensearch_client._client.indices.delete(index="marketplace-agents-000001")
    await initialized_opensearch_client._client.snapshot.restore(
        repository="opensearch-backups",
        snapshot=snapshot_name,
        body={"indices": "marketplace-agents-000001", "include_global_state": False},
        wait_for_completion=True,
    )
    await initialized_opensearch_client._client.indices.refresh(index="marketplace-agents-000001")
    restored = await initialized_opensearch_client.search(
        index="marketplace-agents-*",
        query={"match_all": {}},
        workspace_id="ws-snapshot",
        size=100,
    )
    assert restored.total == 25


async def test_snapshot_repository_and_sm_policy_exist(initialized_opensearch_client) -> None:
    repository = await initialized_opensearch_client._client.snapshot.get_repository(
        repository="opensearch-backups"
    )
    assert "opensearch-backups" in repository

    policy = await initialized_opensearch_client._client.transport.perform_request(
        method="GET",
        url="/_plugins/_sm/policies/daily-snapshot",
    )
    creation = policy["sm_policy"]["creation"]["schedule"]["cron"]["expression"]
    deletion = policy["sm_policy"]["deletion"]["condition"]["max_count"]
    assert creation == "0 5 * * *"
    assert deletion == 30
