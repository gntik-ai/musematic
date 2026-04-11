from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.memory.events import PatternPromotedPayload, publish_pattern_promoted
from platform.memory.exceptions import (
    EvidenceConflictNotFoundError,
    GraphUnavailableError,
    KnowledgeNodeNotFoundError,
    MemoryEntryNotFoundError,
    PatternNotFoundError,
    ScopeIsolationError,
    TrajectoryNotFoundError,
)
from platform.memory.models import (
    ConflictStatus,
    KnowledgeNode,
    MemoryEntry,
    MemoryScope,
    PatternStatus,
)
from platform.memory.repository import MemoryRepository
from platform.memory.retrieval_coordinator import RetrievalCoordinator
from platform.memory.schemas import (
    ConflictResolution,
    CrossScopeTransferRequest,
    EvidenceConflictResponse,
    GraphTraversalQuery,
    GraphTraversalResponse,
    KnowledgeEdgeCreate,
    KnowledgeEdgeResponse,
    KnowledgeNodeCreate,
    KnowledgeNodeResponse,
    MemoryEntryResponse,
    MemoryWriteRequest,
    PatternAssetResponse,
    PatternNomination,
    PatternReview,
    RetrievalQuery,
    RetrievalResponse,
    RetrievalResult,
    TrajectoryRecordCreate,
    TrajectoryRecordResponse,
    WriteGateResult,
)
from platform.memory.write_gate import MemoryWriteGate
from platform.workspaces.models import WorkspaceRole
from typing import Any
from uuid import UUID, uuid4

LOGGER = logging.getLogger(__name__)


class MemoryService:
    def __init__(
        self,
        *,
        repository: MemoryRepository,
        write_gate: MemoryWriteGate,
        retrieval_coordinator: RetrievalCoordinator,
        neo4j: Any,
        qdrant: Any,
        settings: Any,
        producer: Any | None,
        workspaces_service: Any | None,
        registry_service: Any | None,
    ) -> None:
        self.repository = repository
        self.write_gate = write_gate
        self.retrieval_coordinator = retrieval_coordinator
        self.neo4j = neo4j
        self.qdrant = qdrant
        self.settings = settings
        self.producer = producer
        self.workspaces_service = workspaces_service
        self.registry_service = registry_service

    async def write_memory(
        self,
        request: MemoryWriteRequest,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> WriteGateResult:
        result = await self.write_gate.validate_and_write(request, agent_fqn, workspace_id)
        await self._commit()
        return result

    async def get_memory_entry(self, entry_id: UUID, workspace_id: UUID) -> MemoryEntryResponse:
        entry = await self.repository.get_memory_entry(entry_id, workspace_id)
        if entry is None:
            raise MemoryEntryNotFoundError(entry_id)
        return MemoryEntryResponse.model_validate(entry)

    async def get_memory_entry_for_requester(
        self,
        entry_id: UUID,
        workspace_id: UUID,
        requester_identity: str,
    ) -> MemoryEntryResponse:
        entry = await self.repository.get_memory_entry(entry_id, workspace_id)
        if entry is None:
            raise MemoryEntryNotFoundError(entry_id)
        if not await self._can_view_entry(entry, requester_identity, workspace_id):
            raise ScopeIsolationError()
        return MemoryEntryResponse.model_validate(entry)

    async def list_memory_entries(
        self,
        workspace_id: UUID,
        requester_identity: str,
        scope: MemoryScope | None,
        page: int,
        page_size: int,
        agent_fqn_filter: str | None = None,
    ) -> tuple[list[MemoryEntryResponse], int]:
        entries, total = await self.repository.list_memory_entries(
            workspace_id=workspace_id,
            agent_fqn=requester_identity,
            is_orchestrator=await self._is_orchestrator(requester_identity, workspace_id),
            scope=scope,
            agent_fqn_filter=agent_fqn_filter,
            page=page,
            page_size=page_size,
        )
        return [MemoryEntryResponse.model_validate(entry) for entry in entries], total

    async def delete_memory_entry(
        self,
        entry_id: UUID,
        workspace_id: UUID,
        requester_identity: str,
    ) -> None:
        entry = await self.repository.get_memory_entry(entry_id, workspace_id)
        if entry is None:
            raise MemoryEntryNotFoundError(entry_id)
        if requester_identity != entry.agent_fqn and not await self._is_workspace_admin(
            requester_identity, workspace_id
        ):
            raise ScopeIsolationError()
        await self.repository.soft_delete_memory_entry(entry)
        if entry.qdrant_point_id is not None:
            try:
                await self.qdrant.delete_points("platform_memory", [str(entry.qdrant_point_id)])
            except Exception:
                LOGGER.warning("Failed to delete Qdrant point for memory %s", entry.id)
        await self._commit()

    async def transfer_memory_scope(
        self,
        request: CrossScopeTransferRequest,
        requester_identity: str,
        workspace_id: UUID,
    ) -> WriteGateResult:
        if request.memory_entry_id is None:
            raise MemoryEntryNotFoundError(UUID(int=0))
        original = await self.repository.get_memory_entry(request.memory_entry_id, workspace_id)
        if original is None:
            raise MemoryEntryNotFoundError(request.memory_entry_id)
        if requester_identity != original.agent_fqn and not await self._is_workspace_admin(
            requester_identity, workspace_id
        ):
            raise ScopeIsolationError()
        result = await self.write_gate.validate_and_write(
            MemoryWriteRequest(
                content=original.content,
                scope=request.target_scope,
                namespace=request.target_namespace,
                source_authority=original.source_authority,
                retention_policy=original.retention_policy,
                execution_id=original.execution_id,
                tags=list(original.tags),
            ),
            original.agent_fqn,
            workspace_id,
        )
        transferred = await self.repository.get_memory_entry(result.memory_entry_id, workspace_id)
        if transferred is not None:
            transferred.provenance_consolidated_by = original.id
        await self._commit()
        return result

    async def retrieve(
        self,
        query: RetrievalQuery,
        requester_identity: str,
        workspace_id: UUID,
    ) -> RetrievalResponse:
        return await self.retrieval_coordinator.retrieve(query, requester_identity, workspace_id)

    async def retrieve_for_context(
        self,
        query_text: str,
        agent_fqn: str,
        workspace_id: UUID,
        goal_id: UUID | None,
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        del goal_id
        query = RetrievalQuery(query_text=query_text, top_k=top_k)
        try:
            response = await asyncio.wait_for(
                self.retrieve(query, agent_fqn, workspace_id),
                timeout=0.8,
            )
        except Exception as exc:
            LOGGER.warning("retrieve_for_context degraded for %s: %s", agent_fqn, exc)
            return []
        return response.results

    async def search_agent_memory(
        self,
        *,
        workspace_id: UUID,
        agent_fqn: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        results = await self.retrieve_for_context(
            query_text=query,
            agent_fqn=agent_fqn,
            workspace_id=workspace_id,
            goal_id=None,
            top_k=limit,
        )
        return [
            {
                "id": item.memory_entry_id,
                "content": item.content,
                "created_at": datetime.now(UTC),
                "metadata": {"score": item.final_score},
            }
            for item in results
        ]

    async def list_conflicts(
        self,
        workspace_id: UUID,
        status: ConflictStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[EvidenceConflictResponse], int]:
        items, total = await self.repository.list_conflicts(
            workspace_id=workspace_id,
            status=status,
            page=page,
            page_size=page_size,
        )
        return [EvidenceConflictResponse.model_validate(item) for item in items], total

    async def resolve_conflict(
        self,
        conflict_id: UUID,
        resolution: ConflictResolution,
        reviewer_identity: str,
        workspace_id: UUID,
    ) -> EvidenceConflictResponse:
        if not await self._is_workspace_admin(reviewer_identity, workspace_id):
            raise ScopeIsolationError()
        conflict = await self.repository.get_conflict(conflict_id, workspace_id)
        if conflict is None:
            raise EvidenceConflictNotFoundError(conflict_id)
        status = (
            ConflictStatus.dismissed
            if resolution.action == "dismiss"
            else ConflictStatus.resolved
        )
        updated = await self.repository.update_conflict_status(
            conflict,
            status=status,
            reviewed_by=reviewer_identity,
            resolution_notes=resolution.resolution_notes,
        )
        await self._commit()
        return EvidenceConflictResponse.model_validate(updated)

    async def record_trajectory(
        self,
        record: TrajectoryRecordCreate,
        workspace_id: UUID,
    ) -> TrajectoryRecordResponse:
        created = await self.repository.create_trajectory_record(
            workspace_id=workspace_id,
            execution_id=record.execution_id,
            agent_fqn=record.agent_fqn,
            actions=record.actions,
            tool_invocations=record.tool_invocations,
            reasoning_snapshots=record.reasoning_snapshots,
            verdicts=record.verdicts,
            started_at=record.started_at,
            completed_at=record.completed_at,
        )
        await self._commit()
        return TrajectoryRecordResponse.model_validate(created)

    async def get_trajectory(
        self,
        trajectory_id: UUID,
        workspace_id: UUID,
    ) -> TrajectoryRecordResponse:
        record = await self.repository.get_trajectory_record(trajectory_id, workspace_id)
        if record is None:
            raise TrajectoryNotFoundError(trajectory_id)
        return TrajectoryRecordResponse.model_validate(record)

    async def nominate_pattern(
        self,
        nomination: PatternNomination,
        nominated_by: str,
        workspace_id: UUID,
    ) -> PatternAssetResponse:
        pattern = await self.repository.create_pattern_asset(
            workspace_id=workspace_id,
            trajectory_record_id=nomination.trajectory_record_id,
            nominated_by=nominated_by,
            content=nomination.content,
            description=nomination.description,
            tags=nomination.tags,
        )
        await self._commit()
        return PatternAssetResponse.model_validate(pattern)

    async def review_pattern(
        self,
        pattern_id: UUID,
        review: PatternReview,
        reviewer_identity: str,
        workspace_id: UUID,
    ) -> PatternAssetResponse:
        if not await self._is_workspace_admin(reviewer_identity, workspace_id):
            raise ScopeIsolationError()
        pattern = await self.repository.get_pattern_asset(pattern_id, workspace_id)
        if pattern is None:
            raise PatternNotFoundError(pattern_id)
        if review.approved:
            result = await self.write_gate.validate_and_write(
                MemoryWriteRequest(
                    content=pattern.content,
                    scope=MemoryScope.per_workspace,
                    namespace=pattern.nominated_by.split(":", 1)[0]
                    if ":" in pattern.nominated_by
                    else "patterns",
                    source_authority=1.0,
                    tags=list(pattern.tags),
                ),
                pattern.nominated_by,
                workspace_id,
            )
            updated = await self.repository.update_pattern_status(
                pattern,
                status=PatternStatus.approved,
                reviewed_by=reviewer_identity,
                reviewed_at=datetime.now(UTC),
                rejection_reason=None,
                memory_entry_id=result.memory_entry_id,
            )
            await publish_pattern_promoted(
                self.producer,
                PatternPromotedPayload(
                    pattern_asset_id=updated.id,
                    workspace_id=workspace_id,
                    trajectory_record_id=updated.trajectory_record_id,
                    memory_entry_id=result.memory_entry_id,
                    approved_by=reviewer_identity,
                ),
                self._correlation(workspace_id),
            )
        else:
            updated = await self.repository.update_pattern_status(
                pattern,
                status=PatternStatus.rejected,
                reviewed_by=reviewer_identity,
                reviewed_at=datetime.now(UTC),
                rejection_reason=review.rejection_reason,
            )
        await self._commit()
        return PatternAssetResponse.model_validate(updated)

    async def list_patterns(
        self,
        workspace_id: UUID,
        status: PatternStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[PatternAssetResponse], int]:
        items, total = await self.repository.list_pattern_assets(
            workspace_id=workspace_id,
            status=status,
            page=page,
            page_size=page_size,
        )
        return [PatternAssetResponse.model_validate(item) for item in items], total

    async def create_knowledge_node(
        self,
        node: KnowledgeNodeCreate,
        created_by_fqn: str,
        workspace_id: UUID,
    ) -> KnowledgeNodeResponse:
        created = await self.repository.create_knowledge_node(
            workspace_id=workspace_id,
            neo4j_element_id="pending",
            node_type=node.node_type,
            external_name=node.external_name,
            attributes=node.attributes,
            created_by_fqn=created_by_fqn,
        )
        try:
            neo4j_id = await self.neo4j.create_node(
                "MemoryNode",
                {
                    "id": str(created.id),
                    "pg_id": str(created.id),
                    "workspace_id": str(workspace_id),
                    "node_type": node.node_type,
                    "external_name": node.external_name,
                    "attributes": dict(node.attributes),
                    "created_by_fqn": created_by_fqn,
                    "created_at": created.created_at.isoformat(),
                },
            )
            created.neo4j_element_id = str(neo4j_id)
            await self._commit()
        except Exception as exc:
            await self._rollback()
            raise GraphUnavailableError(str(exc)) from exc
        return KnowledgeNodeResponse.model_validate(created)

    async def create_knowledge_edge(
        self,
        edge: KnowledgeEdgeCreate,
        workspace_id: UUID,
    ) -> KnowledgeEdgeResponse:
        source = await self.repository.get_knowledge_node(edge.source_node_id, workspace_id)
        target = await self.repository.get_knowledge_node(edge.target_node_id, workspace_id)
        if source is None:
            raise KnowledgeNodeNotFoundError(edge.source_node_id)
        if target is None:
            raise KnowledgeNodeNotFoundError(edge.target_node_id)
        created = await self.repository.create_knowledge_edge(
            workspace_id=workspace_id,
            neo4j_element_id="pending",
            source_node_id=source.id,
            target_node_id=target.id,
            relationship_type=edge.relationship_type,
            edge_metadata=edge.metadata,
        )
        try:
            await self.neo4j.create_relationship(
                str(source.id),
                str(target.id),
                "MEMORY_REL",
                {
                    "pg_id": str(created.id),
                    "workspace_id": str(workspace_id),
                    "relationship_type": edge.relationship_type,
                    "metadata": dict(edge.metadata),
                    "created_at": created.created_at.isoformat(),
                },
            )
            created.neo4j_element_id = str(created.id)
            await self._commit()
        except Exception as exc:
            await self._rollback()
            raise GraphUnavailableError(str(exc)) from exc
        return KnowledgeEdgeResponse(
            id=created.id,
            workspace_id=created.workspace_id,
            source_node_id=created.source_node_id,
            target_node_id=created.target_node_id,
            relationship_type=created.relationship_type,
            metadata=dict(created.edge_metadata),
            created_at=created.created_at,
        )

    async def traverse_graph(
        self,
        query: GraphTraversalQuery,
        workspace_id: UUID,
    ) -> GraphTraversalResponse:
        start = await self.repository.get_knowledge_node(query.start_node_id, workspace_id)
        if start is None:
            raise KnowledgeNodeNotFoundError(query.start_node_id)
        started = datetime.now(UTC)
        try:
            rel_types = ["MEMORY_REL"]
            paths = await self.neo4j.traverse_path(
                str(start.id),
                rel_types,
                query.max_hops,
                str(workspace_id),
            )
        except Exception as exc:
            LOGGER.warning("Graph traversal degraded for workspace %s: %s", workspace_id, exc)
            return GraphTraversalResponse(partial_sources=["graph"])
        payload_paths = [self._serialize_path(path) for path in paths]
        duration_ms = (datetime.now(UTC) - started).total_seconds() * 1000
        return GraphTraversalResponse(
            paths=payload_paths,
            node_count=sum(len(path.nodes) for path in paths),
            edge_count=sum(len(path.relationships) for path in paths),
            query_time_ms=duration_ms,
        )

    async def get_provenance_chain(
        self,
        node_id: UUID,
        workspace_id: UUID,
    ) -> GraphTraversalResponse:
        node = await self.repository.get_knowledge_node(node_id, workspace_id)
        if node is None:
            raise KnowledgeNodeNotFoundError(node_id)
        chain = await self._build_provenance_chain(node, workspace_id)
        return GraphTraversalResponse(
            paths=[chain],
            node_count=sum(1 for item in chain if item.get("kind") == "node"),
            edge_count=sum(1 for item in chain if item.get("kind") == "edge"),
            query_time_ms=0.0,
        )

    async def _build_provenance_chain(
        self,
        node: KnowledgeNode,
        workspace_id: UUID,
    ) -> list[dict[str, Any]]:
        chain: list[dict[str, Any]] = [
            {
                "kind": "node",
                "id": str(node.id),
                "external_name": node.external_name,
                "node_type": node.node_type,
            }
        ]
        current = node
        visited = {node.id}
        while True:
            incoming = await self.repository.list_incoming_edges(current.id, workspace_id)
            if not incoming:
                break
            edge = incoming[0]
            source = await self.repository.get_knowledge_node(edge.source_node_id, workspace_id)
            if source is None or source.id in visited:
                break
            chain.insert(
                0,
                {
                    "kind": "edge",
                    "id": str(edge.id),
                    "relationship_type": edge.relationship_type,
                    "metadata": dict(edge.edge_metadata),
                },
            )
            chain.insert(
                0,
                {
                    "kind": "node",
                    "id": str(source.id),
                    "external_name": source.external_name,
                    "node_type": source.node_type,
                },
            )
            visited.add(source.id)
            current = source
        return chain

    async def _is_orchestrator(self, identity: str, workspace_id: UUID) -> bool:
        if self.registry_service is None or not hasattr(self.registry_service, "get_by_fqn"):
            return False
        profile = await self.registry_service.get_by_fqn(workspace_id, identity)
        if profile is None:
            return False
        return "orchestrator" in set(getattr(profile, "role_types", []) or [])

    async def _is_workspace_admin(self, identity: str, workspace_id: UUID) -> bool:
        try:
            user_id = UUID(identity)
        except ValueError:
            return False
        repo = getattr(self.workspaces_service, "repo", None)
        if repo is None or not hasattr(repo, "get_membership"):
            return False
        membership = await repo.get_membership(workspace_id, user_id)
        if membership is None:
            return False
        return membership.role in {WorkspaceRole.admin, WorkspaceRole.owner}

    async def _can_view_entry(
        self,
        entry: MemoryEntry,
        requester_identity: str,
        workspace_id: UUID,
    ) -> bool:
        if entry.scope is MemoryScope.per_workspace:
            return True
        if entry.scope is MemoryScope.per_agent:
            return entry.agent_fqn == requester_identity
        return await self._is_orchestrator(requester_identity, workspace_id)

    async def _commit(self) -> None:
        if hasattr(self.repository.session, "commit"):
            await self.repository.session.commit()

    async def _rollback(self) -> None:
        if hasattr(self.repository.session, "rollback"):
            await self.repository.session.rollback()

    def _serialize_path(self, path: Any) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        nodes = list(getattr(path, "nodes", []))
        relationships = list(getattr(path, "relationships", []))
        for index, node in enumerate(nodes):
            serialized.append({"kind": "node", **dict(node)})
            if index < len(relationships):
                serialized.append({"kind": "edge", **dict(relationships[index])})
        return serialized

    def _correlation(self, workspace_id: UUID) -> CorrelationContext:
        return CorrelationContext(correlation_id=uuid4(), workspace_id=workspace_id)
