from __future__ import annotations

from platform.memory.schemas import GraphTraversalQuery, KnowledgeEdgeCreate, KnowledgeNodeCreate
from uuid import uuid4

import pytest

from tests.integration.memory_flow_support import build_memory_flow_stack
from tests.memory_support import Neo4jPathStub

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_memory_graph_operations_flow_traverses_and_returns_provenance() -> None:
    stack = build_memory_flow_stack()
    workspace_id = uuid4()
    source = await stack.service.create_knowledge_node(
        KnowledgeNodeCreate(
            node_type="Agent",
            external_name="finance:writer",
            attributes={"kind": "agent"},
        ),
        "finance:writer",
        workspace_id,
    )
    target = await stack.service.create_knowledge_node(
        KnowledgeNodeCreate(
            node_type="Fact",
            external_name="NET-30",
            attributes={"kind": "payment_terms"},
        ),
        "finance:writer",
        workspace_id,
    )
    edge = await stack.service.create_knowledge_edge(
        KnowledgeEdgeCreate(
            source_node_id=source.id,
            target_node_id=target.id,
            relationship_type="produced",
            metadata={"source": "memory"},
        ),
        workspace_id,
    )
    stack.neo4j.traverse_results = [
        Neo4jPathStub(
            nodes=[
                {"id": str(source.id), "external_name": source.external_name},
                {"id": str(target.id), "external_name": target.external_name},
            ],
            relationships=[{"id": str(edge.id), "relationship_type": edge.relationship_type}],
        )
    ]

    traversal = await stack.service.traverse_graph(
        GraphTraversalQuery(start_node_id=source.id, max_hops=2),
        workspace_id,
    )
    provenance = await stack.service.get_provenance_chain(target.id, workspace_id)

    assert traversal.partial_sources == []
    assert traversal.paths
    assert provenance.paths[0][0]["id"] == str(source.id)
    assert provenance.paths[0][-1]["id"] == str(target.id)
