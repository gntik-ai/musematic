from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_shortest_path_and_apoc_availability(neo4j_client) -> None:
    for node_id in ("a", "b", "c"):
        await neo4j_client.create_node(
            "Agent",
            {
                "id": node_id,
                "workspace_id": "ws-apoc",
                "fqn": f"ws-apoc:{node_id}",
                "lifecycle_state": "published",
            },
        )

    await neo4j_client.create_relationship("a", "b", "COORDINATES", {"weight": 1.0})
    await neo4j_client.create_relationship("b", "c", "COORDINATES", {"weight": 1.0})
    await neo4j_client.create_relationship("a", "c", "COORDINATES", {"weight": 1.0})

    path = await neo4j_client.shortest_path("a", "c", rel_types=["COORDINATES"])
    apoc_rows = await neo4j_client.run_query("CALL apoc.help('path') YIELD name RETURN name LIMIT 1")
    neighborhood = await neo4j_client.run_query(
        "MATCH (n {id: $id})-[*1..2]-(neighbor) RETURN DISTINCT neighbor ORDER BY neighbor.id",
        params={"id": "a"},
    )

    assert path is not None
    assert path.length == 1
    assert apoc_rows
    assert neighborhood


async def test_shortest_path_returns_none_when_no_path_exists(neo4j_client) -> None:
    await neo4j_client.create_node(
        "Agent",
        {"id": "a", "workspace_id": "ws-apoc", "fqn": "ws-apoc:a", "lifecycle_state": "published"},
    )
    await neo4j_client.create_node(
        "Agent",
        {"id": "z", "workspace_id": "ws-apoc", "fqn": "ws-apoc:z", "lifecycle_state": "published"},
    )

    assert await neo4j_client.shortest_path("a", "z") is None
