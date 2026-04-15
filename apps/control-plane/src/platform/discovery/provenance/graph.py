from __future__ import annotations

from datetime import UTC, datetime
from platform.common.clients.neo4j import AsyncNeo4jClient
from platform.common.exceptions import Neo4jConstraintViolationError, Neo4jNodeNotFoundError
from platform.discovery.exceptions import ProvenanceQueryError
from platform.discovery.models import DiscoveryExperiment, Hypothesis
from platform.discovery.schemas import ProvenanceEdge, ProvenanceGraphResponse, ProvenanceNode
from typing import Any
from uuid import UUID


class ProvenanceGraph:
    """Write and query discovery provenance in the platform graph client."""

    def __init__(self, client: AsyncNeo4jClient | None) -> None:
        self.client = client

    async def write_generation_event(
        self,
        hypothesis: Hypothesis,
        agent_fqn: str | None = None,
        *,
        cycle_number: int | None = None,
    ) -> None:
        if self.client is None:
            return
        hypothesis_id = str(hypothesis.id)
        agent_id = f"agent:{hypothesis.workspace_id}:{agent_fqn or hypothesis.generating_agent_fqn}"
        await self._ensure_node(
            "HypothesisNode",
            {
                "id": hypothesis_id,
                "hypothesis_id": hypothesis_id,
                "workspace_id": str(hypothesis.workspace_id),
                "session_id": str(hypothesis.session_id),
                "title": hypothesis.title,
                "status": hypothesis.status,
                "type": "hypothesis",
                "label": hypothesis.title,
            },
        )
        await self._ensure_node(
            "DiscoveryAgentNode",
            {
                "id": agent_id,
                "agent_fqn": agent_fqn or hypothesis.generating_agent_fqn,
                "workspace_id": str(hypothesis.workspace_id),
                "type": "agent",
                "label": agent_fqn or hypothesis.generating_agent_fqn,
            },
        )
        await self._ensure_relationship(
            hypothesis_id,
            agent_id,
            "GENERATED_BY",
            {"cycle_number": cycle_number, "timestamp": _now()},
        )

    async def write_refinement(
        self,
        new_hypothesis: Hypothesis,
        source_hypothesis: Hypothesis,
        *,
        cycle_number: int,
        changes_summary: str = "",
    ) -> None:
        if self.client is None:
            return
        await self.write_generation_event(new_hypothesis)
        await self.write_generation_event(source_hypothesis)
        await self._ensure_relationship(
            str(new_hypothesis.id),
            str(source_hypothesis.id),
            "REFINED_FROM",
            {"cycle_number": cycle_number, "changes_summary": changes_summary},
        )

    async def write_evidence(
        self,
        experiment: DiscoveryExperiment,
        hypothesis: Hypothesis,
        relationship_type: str,
        *,
        summary: str = "",
        confidence: float = 1.0,
    ) -> None:
        if self.client is None:
            return
        rel_type = relationship_type.upper()
        if rel_type not in {"SUPPORTS", "CONTRADICTS", "INCONCLUSIVE_FOR"}:
            rel_type = "INCONCLUSIVE_FOR"
        evidence_id = f"evidence:{experiment.id}"
        await self.write_generation_event(hypothesis)
        await self._ensure_node(
            "EvidenceNode",
            {
                "id": evidence_id,
                "evidence_id": str(experiment.id),
                "workspace_id": str(experiment.workspace_id),
                "session_id": str(experiment.session_id),
                "source_type": "experiment",
                "summary": summary or str(experiment.results or {}),
                "confidence": confidence,
                "type": "evidence",
                "label": summary or f"Experiment {experiment.id}",
            },
        )
        await self._ensure_relationship(
            str(hypothesis.id),
            evidence_id,
            rel_type,
            {"confidence": confidence},
        )

    async def query_provenance(
        self,
        hypothesis_id: UUID,
        workspace_id: UUID,
        *,
        depth: int = 3,
    ) -> ProvenanceGraphResponse:
        if self.client is None:
            return ProvenanceGraphResponse(hypothesis_id=hypothesis_id, nodes=[], edges=[])
        try:
            paths = await self.client.traverse_path(
                str(hypothesis_id),
                [
                    "GENERATED_BY",
                    "SUPPORTS",
                    "CONTRADICTS",
                    "INCONCLUSIVE_FOR",
                    "REFINED_FROM",
                    "SIMILAR_TO",
                ],
                min(depth, 10),
                str(workspace_id),
            )
        except Exception as exc:
            raise ProvenanceQueryError(str(exc)) from exc

        nodes_by_id: dict[str, ProvenanceNode] = {}
        edges: list[ProvenanceEdge] = []
        for path in paths:
            previous_id: str | None = None
            for raw_node in path.nodes:
                node = _node_from_properties(raw_node)
                nodes_by_id[node.id] = node
                if previous_id is not None:
                    edge_props = (
                        path.relationships[len(edges)]
                        if len(path.relationships) > len(edges)
                        else {}
                    )
                    edges.append(
                        ProvenanceEdge(
                            from_id=previous_id,
                            to=node.id,
                            type=str(edge_props.get("rel_type", edge_props.get("type", "RELATED"))),
                            properties=edge_props,
                        )
                    )
                previous_id = node.id
        return ProvenanceGraphResponse(
            hypothesis_id=hypothesis_id,
            nodes=list(nodes_by_id.values()),
            edges=edges,
        )

    async def _ensure_node(self, label: str, properties: dict[str, Any]) -> None:
        assert self.client is not None
        try:
            await self.client.create_node(label, properties)
        except Neo4jConstraintViolationError:
            return

    async def _ensure_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        assert self.client is not None
        payload = {"type": rel_type, **(properties or {})}
        try:
            await self.client.create_relationship(from_id, to_id, rel_type, payload)
        except Neo4jNodeNotFoundError as exc:
            raise ProvenanceQueryError(str(exc)) from exc


def _node_from_properties(properties: dict[str, Any]) -> ProvenanceNode:
    raw_type = str(properties.get("type") or "hypothesis")
    if raw_type not in {"hypothesis", "evidence", "agent", "experiment", "critique", "debate"}:
        raw_type = "hypothesis"
    return ProvenanceNode(
        id=str(properties.get("id") or properties.get("hypothesis_id")),
        type=raw_type,
        label=str(properties.get("label") or properties.get("title") or properties.get("id")),
        properties=properties,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
