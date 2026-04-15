from __future__ import annotations

from datetime import UTC, datetime
from platform.common.exceptions import Neo4jConstraintViolationError, Neo4jNodeNotFoundError
from platform.discovery.models import DiscoveryExperiment, Hypothesis
from platform.discovery.provenance.graph import ProvenanceGraph
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        id=uuid4(),
        workspace_id=uuid4(),
        session_id=uuid4(),
        title="h",
        description="d",
        reasoning="r",
        confidence=0.8,
        generating_agent_fqn="agent",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_write_generation_refinement_and_evidence() -> None:
    source = _hypothesis()
    refined = _hypothesis()
    refined.workspace_id = source.workspace_id
    refined.session_id = source.session_id
    experiment = DiscoveryExperiment(
        id=uuid4(),
        workspace_id=source.workspace_id,
        session_id=source.session_id,
        hypothesis_id=source.id,
        plan={},
        governance_status="approved",
        governance_violations=[],
        execution_status="completed",
        designed_by_agent_fqn="designer",
        results={"stdout": "ok"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    client = SimpleNamespace(create_node=AsyncMock(), create_relationship=AsyncMock())
    graph = ProvenanceGraph(client)

    await graph.write_generation_event(source, "agent.a", cycle_number=1)
    await graph.write_refinement(refined, source, cycle_number=2)
    await graph.write_evidence(experiment, source, "supports", summary="ok")

    assert client.create_node.await_count >= 5
    rel_types = [call.args[2] for call in client.create_relationship.await_args_list]
    assert "GENERATED_BY" in rel_types
    assert "REFINED_FROM" in rel_types
    assert "SUPPORTS" in rel_types


@pytest.mark.asyncio
async def test_query_provenance_returns_nodes_and_edges() -> None:
    hypothesis_id = uuid4()
    workspace_id = uuid4()
    path = SimpleNamespace(
        nodes=[
            {
                "id": str(hypothesis_id),
                "type": "hypothesis",
                "label": "H",
                "workspace_id": str(workspace_id),
            },
            {"id": "agent:a", "type": "agent", "label": "A", "workspace_id": str(workspace_id)},
        ],
        relationships=[{"type": "GENERATED_BY"}],
    )
    client = SimpleNamespace(traverse_path=AsyncMock(return_value=[path]))
    graph = ProvenanceGraph(client)

    response = await graph.query_provenance(hypothesis_id, workspace_id, depth=3)

    assert [node.type for node in response.nodes] == ["hypothesis", "agent"]
    assert response.edges[0].type == "GENERATED_BY"


@pytest.mark.asyncio
async def test_provenance_handles_no_client_duplicates_and_bad_relationships() -> None:
    hypothesis = _hypothesis()
    graph = ProvenanceGraph(None)
    assert (await graph.query_provenance(hypothesis.id, hypothesis.workspace_id)).nodes == []
    await graph.write_generation_event(hypothesis)

    client = SimpleNamespace(
        create_node=AsyncMock(side_effect=Neo4jConstraintViolationError("duplicate")),
        create_relationship=AsyncMock(side_effect=Neo4jNodeNotFoundError("missing")),
    )
    graph = ProvenanceGraph(client)
    await graph._ensure_node("HypothesisNode", {"id": "x", "workspace_id": "w"})
    with pytest.raises(Exception, match="missing"):
        await graph._ensure_relationship("a", "b", "SUPPORTS")


def test_node_type_normalization() -> None:
    from platform.discovery.provenance.graph import _node_from_properties

    node = _node_from_properties({"id": "x", "type": "unexpected", "label": "X"})

    assert node.type == "hypothesis"
