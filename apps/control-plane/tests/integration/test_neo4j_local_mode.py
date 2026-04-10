from __future__ import annotations

import pytest

from platform.common.clients.neo4j import AsyncNeo4jClient, PathResult
from platform.common.config import Settings
from platform.common.exceptions import HopLimitExceededError


pytestmark = pytest.mark.asyncio


async def test_local_mode_traversal_and_limits(async_engine) -> None:
    client = AsyncNeo4jClient(Settings(GRAPH_MODE="local"), engine=async_engine)

    await client.create_node(
        "Workflow",
        {"id": "wf-local-1", "workspace_id": "ws-test", "name": "wf-local-1", "status": "active"},
    )
    await client.create_node(
        "Workflow",
        {"id": "wf-local-2", "workspace_id": "ws-test", "name": "wf-local-2", "status": "active"},
    )
    await client.create_node(
        "Agent",
        {
            "id": "agent-local-1",
            "workspace_id": "ws-test",
            "fqn": "ws-test:agent-local-1",
            "lifecycle_state": "published",
        },
    )
    await client.create_relationship("wf-local-1", "wf-local-2", "DEPENDS_ON", {"weight": 1.0})
    await client.create_relationship("wf-local-2", "agent-local-1", "DEPENDS_ON", {"weight": 1.0})

    health = await client.health_check()
    paths = await client.traverse_path("wf-local-1", ["DEPENDS_ON"], 2, "ws-test")

    assert health == {"status": "ok", "mode": "local"}
    assert paths
    assert isinstance(paths[0], PathResult)
    assert isinstance(paths[0].nodes, list)
    assert isinstance(paths[0].relationships, list)
    assert paths[0].length >= 1

    with pytest.raises(HopLimitExceededError):
        await client.traverse_path("wf-local-1", ["DEPENDS_ON"], 4, "ws-test")

    with pytest.raises(NotImplementedError):
        await client.shortest_path("wf-local-1", "agent-local-1")

    await client.close()
