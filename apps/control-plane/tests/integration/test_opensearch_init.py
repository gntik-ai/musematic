from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

pytestmark = pytest.mark.asyncio


async def test_init_creates_templates_and_policies(
    opensearch_client,
    opensearch_init_module,
    opensearch_server,
) -> None:
    await opensearch_init_module.create_ism_policies(opensearch_client._client)
    await opensearch_init_module.create_index_templates(opensearch_client._client)
    await opensearch_init_module.setup_snapshot_management(
        opensearch_client._client,
        repository_settings=opensearch_init_module.SnapshotRepositorySettings(
            name="opensearch-backups",
            type=str(opensearch_server.get("snapshot_type", "fs")),
            bucket="backups",
            base_path="backups/opensearch",
            endpoint=str(opensearch_server.get("snapshot_endpoint", "http://musematic-minio:9000")),
            location=(
                str(opensearch_server["snapshot_location"])
                if opensearch_server.get("snapshot_location") is not None
                else None
            ),
        ),
    )

    marketplace = await opensearch_client._client.indices.get_index_template(
        name="marketplace-agents"
    )
    settings = marketplace["index_templates"][0]["index_template"]["template"]["settings"]["index"]
    mappings = marketplace["index_templates"][0]["index_template"]["template"]["mappings"]
    assert settings["analysis"]["analyzer"]["agent_index_analyzer"]["filter"] == [
        "lowercase",
        "icu_folding",
    ]
    assert settings["analysis"]["analyzer"]["agent_analyzer"]["filter"] == [
        "lowercase",
        "icu_folding",
        "synonym_filter",
    ]
    assert mappings["properties"]["name"]["analyzer"] == "agent_index_analyzer"
    assert mappings["properties"]["name"]["search_analyzer"] == "agent_analyzer"

    audit = await opensearch_client._client.indices.get_index_template(name="audit-events")
    connector = await opensearch_client._client.indices.get_index_template(
        name="connector-payloads"
    )
    assert (
        audit["index_templates"][0]["index_template"]["template"]["mappings"]["properties"][
            "goal_id"
        ]
        == {"type": "keyword"}
    )
    assert (
        connector["index_templates"][0]["index_template"]["template"]["mappings"]["properties"][
            "goal_id"
        ]
        == {"type": "keyword"}
    )

    audit_policy = await opensearch_client._client.transport.perform_request(
        method="GET",
        url="/_plugins/_ism/policies/audit-events-policy",
    )
    assert audit_policy["policy"]["default_state"] == "hot"


async def test_init_is_idempotent(
    initialized_opensearch_client,
    opensearch_init_module,
    opensearch_server,
) -> None:
    repository = opensearch_init_module.SnapshotRepositorySettings(
        name="opensearch-backups",
        type=str(opensearch_server.get("snapshot_type", "fs")),
        bucket="backups",
        base_path="backups/opensearch",
        endpoint=str(opensearch_server.get("snapshot_endpoint", "http://musematic-minio:9000")),
        location=(
            str(opensearch_server["snapshot_location"])
            if opensearch_server.get("snapshot_location") is not None
            else None
        ),
    )
    await opensearch_init_module.create_ism_policies(initialized_opensearch_client._client)
    await opensearch_init_module.create_index_templates(initialized_opensearch_client._client)
    await opensearch_init_module.setup_snapshot_management(
        initialized_opensearch_client._client,
        repository_settings=repository,
    )

    aliases = await initialized_opensearch_client._client.indices.get_alias(
        index="marketplace-agents-000001"
    )
    assert "marketplace-agents" in aliases["marketplace-agents-000001"]["aliases"]


async def test_setup_snapshot_management_posts_policy_when_missing(opensearch_init_module) -> None:
    missing_policy = Exception()
    missing_policy.status_code = 404
    client = SimpleNamespace(
        snapshot=SimpleNamespace(create_repository=AsyncMock()),
        transport=SimpleNamespace(
            perform_request=AsyncMock(
                side_effect=[
                    missing_policy,
                    {"_id": "daily-snapshot-sm-policy"},
                ]
            )
        ),
    )

    await opensearch_init_module.setup_snapshot_management(client)

    assert client.transport.perform_request.await_args_list[0].kwargs == {
        "method": "GET",
        "url": "/_plugins/_sm/policies/daily-snapshot",
    }
    assert client.transport.perform_request.await_args_list[1].kwargs["method"] == "POST"
    assert (
        client.transport.perform_request.await_args_list[1].kwargs["url"]
        == "/_plugins/_sm/policies/daily-snapshot"
    )

async def test_setup_snapshot_management_skips_create_when_policy_exists(
    opensearch_init_module,
) -> None:
    client = SimpleNamespace(
        snapshot=SimpleNamespace(create_repository=AsyncMock()),
        transport=SimpleNamespace(perform_request=AsyncMock(return_value={"policy": {}})),
    )

    await opensearch_init_module.setup_snapshot_management(client)

    client.transport.perform_request.assert_awaited_once_with(
        method="GET",
        url="/_plugins/_sm/policies/daily-snapshot",
    )


async def test_goal_id_searchable_on_rollover_index(initialized_opensearch_client) -> None:
    goal_id = uuid4()
    document = {
        "event_id": "evt-goal-search",
        "event_type": "GOAL_BOUND_EVENT",
        "actor_id": "system",
        "actor_type": "service",
        "timestamp": "2026-04-18T00:00:00Z",
        "workspace_id": "ws-goal",
        "goal_id": str(goal_id),
        "resource_type": "goal",
        "action": "observe",
        "details": "goal scoped event",
    }

    await initialized_opensearch_client._client.indices.create(index="audit-events-000002")
    await initialized_opensearch_client._client.index(
        index="audit-events-000002",
        id=document["event_id"],
        body=document,
        refresh="wait_for",
    )

    result = await initialized_opensearch_client._client.search(
        index="audit-events-*",
        body={"query": {"term": {"goal_id": str(goal_id)}}},
    )

    assert result["hits"]["total"]["value"] == 1
    assert result["hits"]["hits"][0]["_source"]["goal_id"] == str(goal_id)
