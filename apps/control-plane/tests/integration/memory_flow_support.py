from __future__ import annotations

from dataclasses import dataclass
from platform.memory.retrieval_coordinator import RetrievalCoordinator
from platform.memory.service import MemoryService
from platform.memory.write_gate import MemoryWriteGate
from platform.workspaces.models import WorkspaceRole

from tests.auth_support import RecordingProducer
from tests.memory_support import (
    MemoryRepoStub,
    Neo4jStub,
    QdrantStub,
    RedisRateLimitStub,
    RegistryServiceStub,
    WorkspacesServiceStub,
    build_settings,
)


@dataclass
class MemoryFlowStack:
    repo: MemoryRepoStub
    qdrant: QdrantStub
    neo4j: Neo4jStub
    producer: RecordingProducer
    write_gate: MemoryWriteGate
    retrieval: RetrievalCoordinator
    service: MemoryService


def build_memory_flow_stack(
    *,
    qdrant: QdrantStub | None = None,
    neo4j: Neo4jStub | None = None,
    registry_service: RegistryServiceStub | None = None,
    workspaces_service: WorkspacesServiceStub | None = None,
) -> MemoryFlowStack:
    repo = MemoryRepoStub()
    settings = build_settings()
    resolved_qdrant = qdrant or QdrantStub()
    resolved_neo4j = neo4j or Neo4jStub()
    resolved_registry = registry_service or RegistryServiceStub(
        role_types=["executor", "orchestrator"]
    )
    resolved_workspaces = workspaces_service or WorkspacesServiceStub(
        membership_role=WorkspaceRole.owner
    )
    producer = RecordingProducer()
    write_gate = MemoryWriteGate(
        repository=repo,
        qdrant=resolved_qdrant,
        redis_client=RedisRateLimitStub(),
        settings=settings,
        registry_service=resolved_registry,
        workspaces_service=resolved_workspaces,
        producer=producer,
    )
    retrieval = RetrievalCoordinator(
        repository=repo,
        qdrant=resolved_qdrant,
        neo4j=resolved_neo4j,
        settings=settings,
        registry_service=resolved_registry,
    )
    service = MemoryService(
        repository=repo,
        write_gate=write_gate,
        retrieval_coordinator=retrieval,
        neo4j=resolved_neo4j,
        qdrant=resolved_qdrant,
        settings=settings,
        producer=producer,
        workspaces_service=resolved_workspaces,
        registry_service=resolved_registry,
    )
    return MemoryFlowStack(
        repo=repo,
        qdrant=resolved_qdrant,
        neo4j=resolved_neo4j,
        producer=producer,
        write_gate=write_gate,
        retrieval=retrieval,
        service=service,
    )
