from __future__ import annotations

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
            bucket="musematic-backups",
            base_path="backups/opensearch",
            endpoint=str(opensearch_server.get("snapshot_endpoint", "http://musematic-minio:9000")),
            location=(
                str(opensearch_server["snapshot_location"])
                if opensearch_server.get("snapshot_location") is not None
                else None
            ),
        ),
    )

    marketplace = await opensearch_client._client.indices.get_index_template(name="marketplace-agents")
    settings = marketplace["index_templates"][0]["index_template"]["template"]["settings"]
    assert settings["analysis"]["analyzer"]["agent_analyzer"]["filter"] == [
        "lowercase",
        "icu_folding",
        "synonym_filter",
    ]

    audit_policy = await opensearch_client._client.transport.perform_request(
        method="GET",
        url="/_plugins/_ism/policies/audit-events-policy",
    )
    assert audit_policy["policy"]["default_state"] == "hot"


async def test_init_is_idempotent(initialized_opensearch_client, opensearch_init_module, opensearch_server) -> None:
    repository = opensearch_init_module.SnapshotRepositorySettings(
        name="opensearch-backups",
        type=str(opensearch_server.get("snapshot_type", "fs")),
        bucket="musematic-backups",
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

    aliases = await initialized_opensearch_client._client.indices.get_alias(index="marketplace-agents-000001")
    assert "marketplace-agents" in aliases["marketplace-agents-000001"]["aliases"]
