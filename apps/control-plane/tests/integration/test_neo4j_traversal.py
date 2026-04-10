from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_traverse_hypothesis_chain(neo4j_client) -> None:
    await neo4j_client.create_node(
        "Hypothesis",
        {"id": "h-001", "workspace_id": "ws-test", "status": "open", "confidence": 0.8},
    )
    await neo4j_client.create_node(
        "Evidence",
        {
            "id": "ev-001",
            "workspace_id": "ws-test",
            "hypothesis_id": "h-001",
            "polarity": "supporting",
            "confidence": 0.9,
        },
    )
    await neo4j_client.create_node(
        "Evidence",
        {
            "id": "ev-002",
            "workspace_id": "ws-test",
            "hypothesis_id": "h-001",
            "polarity": "supporting",
            "confidence": 0.7,
        },
    )
    await neo4j_client.create_node(
        "Evidence",
        {
            "id": "ev-003",
            "workspace_id": "ws-test",
            "hypothesis_id": "h-001",
            "polarity": "supporting",
            "confidence": 0.6,
        },
    )

    await neo4j_client.create_relationship("h-001", "ev-001", "SUPPORTS", {"confidence": 0.9})
    await neo4j_client.create_relationship("ev-001", "ev-002", "DERIVED_FROM", {})
    await neo4j_client.create_relationship("ev-002", "ev-003", "DERIVED_FROM", {})

    paths = await neo4j_client.traverse_path(
        start_id="h-001",
        rel_types=["SUPPORTS", "DERIVED_FROM"],
        max_hops=3,
        workspace_id="ws-test",
    )

    assert paths
    assert any(path.length >= 2 for path in paths)


async def test_run_query_respects_workspace_param(neo4j_client) -> None:
    await neo4j_client.create_node(
        "Agent",
        {"id": "agent-a", "workspace_id": "ws-A", "fqn": "ws-A:agent-a", "lifecycle_state": "published"},
    )
    await neo4j_client.create_node(
        "Agent",
        {"id": "agent-b", "workspace_id": "ws-B", "fqn": "ws-B:agent-b", "lifecycle_state": "published"},
    )

    rows = await neo4j_client.run_query(
        "MATCH (n) WHERE n.workspace_id = $workspace_id RETURN n ORDER BY n.id",
        workspace_id="ws-A",
    )

    assert rows
    assert all(row["n"]["workspace_id"] == "ws-A" for row in rows)


async def test_traverse_path_supports_more_than_three_hops_in_neo4j_mode(neo4j_client) -> None:
    node_ids = ["wf-0", "wf-1", "wf-2", "wf-3", "wf-4"]
    for node_id in node_ids:
        await neo4j_client.create_node(
            "Workflow",
            {"id": node_id, "workspace_id": "ws-test", "name": node_id, "status": "active"},
        )

    for source, target in zip(node_ids, node_ids[1:], strict=False):
        await neo4j_client.create_relationship(source, target, "DEPENDS_ON", {"weight": 1.0})

    paths = await neo4j_client.traverse_path(
        start_id="wf-0",
        rel_types=["DEPENDS_ON"],
        max_hops=5,
        workspace_id="ws-test",
    )

    assert paths
    assert max(path.length for path in paths) >= 4
