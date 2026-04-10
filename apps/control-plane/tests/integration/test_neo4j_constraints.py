from __future__ import annotations

import pytest

from platform.common.exceptions import Neo4jConstraintViolationError
from tests.conftest import _apply_neo4j_init


pytestmark = pytest.mark.asyncio


async def test_constraints_indexes_and_idempotent_init(neo4j_client) -> None:
    constraints = await neo4j_client.run_query("SHOW CONSTRAINTS YIELD name RETURN name ORDER BY name")
    indexes = await neo4j_client.run_query("SHOW INDEXES YIELD name RETURN name ORDER BY name")

    constraint_names = {row["name"] for row in constraints}
    index_names = {row["name"] for row in indexes}

    assert {"agent_id", "workflow_id", "fleet_id", "hypothesis_id", "memory_id"}.issubset(
        constraint_names
    )
    assert {"memory_workspace", "evidence_hypothesis", "relationship_type"}.issubset(index_names)

    payload = {
        "id": "agent-constraint",
        "workspace_id": "ws-constraints",
        "fqn": "ws-constraints:agent-constraint",
        "lifecycle_state": "published",
    }
    await neo4j_client.create_node("Agent", payload)
    with pytest.raises(Neo4jConstraintViolationError):
        await neo4j_client.create_node("Agent", payload)

    await _apply_neo4j_init(neo4j_client)
