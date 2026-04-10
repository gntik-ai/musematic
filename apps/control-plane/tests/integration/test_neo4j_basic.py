from __future__ import annotations

import pytest

from platform.common.exceptions import Neo4jConstraintViolationError, Neo4jNodeNotFoundError


pytestmark = pytest.mark.asyncio


async def test_workspace_isolation_and_basic_operations(neo4j_client) -> None:
    for agent_id, workspace_id in (
        ("agent-a-1", "ws-A"),
        ("agent-a-2", "ws-A"),
        ("agent-a-3", "ws-A"),
        ("agent-b-1", "ws-B"),
        ("agent-b-2", "ws-B"),
    ):
        await neo4j_client.create_node(
            "Agent",
            {
                "id": agent_id,
                "workspace_id": workspace_id,
                "fqn": f"{workspace_id}:{agent_id}",
                "lifecycle_state": "published",
            },
        )

    await neo4j_client.create_relationship("agent-a-1", "agent-a-2", "COORDINATES", {"weight": 1.0})
    await neo4j_client.create_relationship("agent-a-2", "agent-a-3", "COORDINATES", {"weight": 1.0})
    await neo4j_client.create_relationship("agent-b-1", "agent-b-2", "COORDINATES", {"weight": 1.0})

    ws_a_paths = await neo4j_client.traverse_path("agent-a-1", ["COORDINATES"], 3, "ws-A")
    ws_b_paths = await neo4j_client.traverse_path("agent-b-1", ["COORDINATES"], 2, "ws-B")
    health = await neo4j_client.health_check()

    assert ws_a_paths
    assert ws_b_paths
    assert all(node["workspace_id"] == "ws-A" for path in ws_a_paths for node in path.nodes)
    assert all(node["workspace_id"] == "ws-B" for path in ws_b_paths for node in path.nodes)
    assert health["status"] == "ok"
    assert health["mode"] == "neo4j"


async def test_duplicate_agent_id_raises_constraint_error(neo4j_client) -> None:
    payload = {
        "id": "agent-duplicate",
        "workspace_id": "ws-test",
        "fqn": "ws-test:agent-duplicate",
        "lifecycle_state": "published",
    }
    await neo4j_client.create_node("Agent", payload)

    with pytest.raises(Neo4jConstraintViolationError):
        await neo4j_client.create_node("Agent", payload)


async def test_missing_relationship_node_raises(neo4j_client) -> None:
    await neo4j_client.create_node(
        "Agent",
        {
            "id": "agent-existing",
            "workspace_id": "ws-test",
            "fqn": "ws-test:agent-existing",
            "lifecycle_state": "published",
        },
    )

    with pytest.raises(Neo4jNodeNotFoundError):
        await neo4j_client.create_relationship(
            "agent-existing",
            "missing-agent",
            "COORDINATES",
            {"weight": 1.0},
        )
