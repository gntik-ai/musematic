# Data Model: Memory and Knowledge Subsystem

**Feature**: 023-memory-knowledge-subsystem  
**Date**: 2026-04-11  
**Migration**: `008_memory_knowledge.py`

---

## SQLAlchemy Models

### Enums

```python
class MemoryScope(str, enum.Enum):
    PER_AGENT = "per_agent"
    PER_WORKSPACE = "per_workspace"
    SHARED_ORCHESTRATOR = "shared_orchestrator"

class RetentionPolicy(str, enum.Enum):
    PERMANENT = "permanent"
    TIME_LIMITED = "time_limited"
    SESSION_ONLY = "session_only"

class EmbeddingStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"

class ConflictStatus(str, enum.Enum):
    OPEN = "open"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"

class EmbeddingJobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class PatternStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
```

### MemoryEntry

```python
class MemoryEntry(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "memory_entries"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    agent_fqn: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[MemoryScope] = mapped_column(SQLEnum(MemoryScope), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_tsv: Mapped[Any] = mapped_column(TSVECTOR, nullable=False)  # generated column, GIN index
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hex
    source_authority: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    retention_policy: Mapped[RetentionPolicy] = mapped_column(SQLEnum(RetentionPolicy), nullable=False, default=RetentionPolicy.PERMANENT)
    ttl_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_id: Mapped[UUID | None] = mapped_column(nullable=True)  # for session_only retention
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(SQLEnum(EmbeddingStatus), nullable=False, default=EmbeddingStatus.PENDING)
    qdrant_point_id: Mapped[UUID | None] = mapped_column(nullable=True)  # set after Qdrant write
    provenance_consolidated_by: Mapped[UUID | None] = mapped_column(ForeignKey("memory_entries.id"), nullable=True)
    tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_memory_entries_workspace_scope", "workspace_id", "scope"),
        Index("ix_memory_entries_agent_scope", "agent_fqn", "scope"),
        Index("ix_memory_entries_content_tsv", "content_tsv", postgresql_using="gin"),
    )
```

### EvidenceConflict

```python
class EvidenceConflict(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "evidence_conflicts"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    memory_entry_id_a: Mapped[UUID] = mapped_column(ForeignKey("memory_entries.id"), nullable=False)
    memory_entry_id_b: Mapped[UUID] = mapped_column(ForeignKey("memory_entries.id"), nullable=False)
    conflict_description: Mapped[str] = mapped_column(Text, nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[ConflictStatus] = mapped_column(SQLEnum(ConflictStatus), nullable=False, default=ConflictStatus.OPEN, index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)  # agent FQN or user ID
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_evidence_conflicts_pair", "memory_entry_id_a", "memory_entry_id_b", unique=True),
    )
```

### EmbeddingJob

```python
class EmbeddingJob(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "embedding_jobs"

    memory_entry_id: Mapped[UUID] = mapped_column(ForeignKey("memory_entries.id"), nullable=False, unique=True)
    status: Mapped[EmbeddingJobStatus] = mapped_column(SQLEnum(EmbeddingJobStatus), nullable=False, default=EmbeddingJobStatus.PENDING, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

### TrajectoryRecord

```python
class TrajectoryRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trajectory_records"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    execution_id: Mapped[UUID] = mapped_column(nullable=False, unique=True, index=True)
    agent_fqn: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # ordered list of {action_type, input, output, timestamp}
    tool_invocations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # {tool_fqn, input, output, timestamp}
    reasoning_snapshots: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # {step, content, timestamp}
    verdicts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # {verdict_type, content, timestamp}
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_trajectory_records_workspace_agent", "workspace_id", "agent_fqn"),
    )
```

### PatternAsset

```python
class PatternAsset(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "pattern_assets"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    trajectory_record_id: Mapped[UUID | None] = mapped_column(ForeignKey("trajectory_records.id"), nullable=True)
    nominated_by: Mapped[str] = mapped_column(String(255), nullable=False)  # agent FQN or user ID
    content: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[PatternStatus] = mapped_column(SQLEnum(PatternStatus), nullable=False, default=PatternStatus.PENDING, index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_entry_id: Mapped[UUID | None] = mapped_column(ForeignKey("memory_entries.id"), nullable=True)  # set on approval
```

### KnowledgeNode

```python
class KnowledgeNode(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "knowledge_nodes"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    neo4j_element_id: Mapped[str] = mapped_column(String(255), nullable=False)  # Neo4j internal element ID
    node_type: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "Agent", "Tool", "Concept", "Fact"
    external_name: Mapped[str] = mapped_column(String(500), nullable=False)  # human-readable name
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by_fqn: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "neo4j_element_id"),
        Index("ix_knowledge_nodes_workspace_type", "workspace_id", "node_type"),
    )
```

### KnowledgeEdge

```python
class KnowledgeEdge(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "knowledge_edges"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    neo4j_element_id: Mapped[str] = mapped_column(String(255), nullable=False)  # Neo4j internal element ID
    source_node_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_nodes.id"), nullable=False)
    target_node_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_nodes.id"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "used", "produced", "has_terms"
    metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("workspace_id", "neo4j_element_id"),
        Index("ix_knowledge_edges_source_target", "source_node_id", "target_node_id"),
    )
```

---

## Qdrant Collection

**Collection name**: `platform_memory`  
**Vector dimension**: 1536 (configurable via `MEMORY_EMBEDDING_DIMENSIONS`)  
**Distance metric**: `Cosine`  
**On-disk payload index**: `workspace_id`, `agent_fqn`, `scope`

```python
# Payload structure stored per point
{
    "memory_entry_id": "uuid-string",      # FK back to PostgreSQL
    "workspace_id": "uuid-string",
    "agent_fqn": "namespace:agent-name",
    "scope": "per_agent" | "per_workspace" | "shared_orchestrator",
    "source_authority": 1.0,               # float [0.0, 1.0]
    "created_at_ts": 1712851200.0,         # Unix timestamp for recency scoring
    "tags": ["tag1", "tag2"],
}

# Indexes (for filter-accelerated search)
qdrant_client.create_payload_index(
    collection_name="platform_memory",
    field_name="workspace_id",
    field_schema=PayloadSchemaType.KEYWORD,
)
qdrant_client.create_payload_index(
    collection_name="platform_memory",
    field_name="agent_fqn",
    field_schema=PayloadSchemaType.KEYWORD,
)
qdrant_client.create_payload_index(
    collection_name="platform_memory",
    field_name="scope",
    field_schema=PayloadSchemaType.KEYWORD,
)
```

---

## Neo4j Schema

**Constraints and indexes** (idempotent setup at startup):

```cypher
// Workspace isolation index on all major labels
CREATE INDEX node_workspace IF NOT EXISTS FOR (n:MemoryNode) ON (n.workspace_id);
CREATE CONSTRAINT node_unique IF NOT EXISTS FOR (n:MemoryNode) REQUIRE (n.workspace_id, n.pg_id) IS UNIQUE;

// Relationship type index
CREATE INDEX rel_workspace IF NOT EXISTS FOR ()-[r:MEMORY_REL]-() ON (r.workspace_id);
```

**Node structure** (all Neo4j nodes use label `MemoryNode`; `node_type` stored as property):

```cypher
CREATE (n:MemoryNode {
    pg_id: $pg_id,               // UUID from PostgreSQL knowledge_nodes.id
    workspace_id: $workspace_id,
    node_type: $node_type,       // "Agent" | "Tool" | "Concept" | "Fact" | "Organization" | ...
    external_name: $name,
    attributes: $attributes_json, // serialized JSON string
    created_by_fqn: $fqn,
    created_at: $created_at_iso
})
```

**Edge structure** (all Neo4j edges use type `MEMORY_REL`; `relationship_type` stored as property):

```cypher
MATCH (a:MemoryNode {pg_id: $source_pg_id, workspace_id: $workspace_id})
MATCH (b:MemoryNode {pg_id: $target_pg_id, workspace_id: $workspace_id})
CREATE (a)-[r:MEMORY_REL {
    pg_id: $pg_id,
    workspace_id: $workspace_id,
    relationship_type: $rel_type,
    metadata: $metadata_json,
    created_at: $created_at_iso
}]->(b)
```

**Multi-hop traversal query (example, 3 hops)**:

```cypher
MATCH path = (start:MemoryNode {pg_id: $start_id, workspace_id: $workspace_id})
             -[:MEMORY_REL*1..3]->
             (end:MemoryNode {workspace_id: $workspace_id})
WHERE all(n IN nodes(path) WHERE n.workspace_id = $workspace_id)
RETURN path
LIMIT 100
```

---

## Pydantic Schemas

### Request Schemas

```python
class MemoryWriteRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50_000)
    scope: MemoryScope
    namespace: str = Field(..., min_length=1, max_length=255)
    source_authority: float = Field(default=1.0, ge=0.0, le=1.0)
    retention_policy: RetentionPolicy = RetentionPolicy.PERMANENT
    ttl_seconds: int | None = Field(default=None, gt=0)
    execution_id: UUID | None = None  # required for session_only retention
    tags: list[str] = Field(default_factory=list)

class RetrievalQuery(BaseModel):
    query_text: str = Field(..., min_length=1, max_length=5_000)
    scope_filter: MemoryScope | None = None
    agent_fqn_filter: str | None = None
    top_k: int = Field(default=10, ge=1, le=50)
    include_contradictions: bool = True
    rrf_k: int = Field(default=60, ge=1, le=1000)

class CrossScopeTransferRequest(BaseModel):
    memory_entry_id: UUID
    target_scope: MemoryScope
    target_namespace: str

class KnowledgeNodeCreate(BaseModel):
    node_type: str = Field(..., min_length=1, max_length=100)
    external_name: str = Field(..., min_length=1, max_length=500)
    attributes: dict = Field(default_factory=dict)

class KnowledgeEdgeCreate(BaseModel):
    source_node_id: UUID
    target_node_id: UUID
    relationship_type: str = Field(..., min_length=1, max_length=100)
    metadata: dict = Field(default_factory=dict)

class GraphTraversalQuery(BaseModel):
    start_node_id: UUID
    max_hops: int = Field(default=3, ge=1, le=5)
    relationship_type_filter: str | None = None

class TrajectoryRecordCreate(BaseModel):
    execution_id: UUID
    agent_fqn: str
    actions: list[dict]
    tool_invocations: list[dict]
    reasoning_snapshots: list[dict]
    verdicts: list[dict]
    started_at: datetime
    completed_at: datetime | None = None

class PatternNomination(BaseModel):
    trajectory_record_id: UUID
    content: str = Field(..., min_length=1, max_length=100_000)
    description: str = Field(..., min_length=1, max_length=2_000)
    tags: list[str] = Field(default_factory=list)

class PatternReview(BaseModel):
    approved: bool
    rejection_reason: str | None = None

class ConflictResolution(BaseModel):
    action: Literal["dismiss", "resolve"]
    resolution_notes: str | None = None
```

### Response Schemas

```python
class MemoryEntryResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    agent_fqn: str
    namespace: str
    scope: MemoryScope
    content: str
    source_authority: float
    retention_policy: RetentionPolicy
    ttl_expires_at: datetime | None
    embedding_status: EmbeddingStatus
    tags: list[str]
    created_at: datetime
    updated_at: datetime

class RetrievalResult(BaseModel):
    memory_entry_id: UUID
    content: str
    scope: MemoryScope
    agent_fqn: str
    source_authority: float
    rrf_score: float
    recency_factor: float
    final_score: float
    sources_contributed: list[Literal["vector", "keyword", "graph"]]
    contradiction_flag: bool
    conflict_ids: list[UUID]  # references to EvidenceConflict records

class RetrievalResponse(BaseModel):
    results: list[RetrievalResult]
    partial_sources: list[Literal["vector", "keyword", "graph"]]  # sources that were unavailable
    query_time_ms: float

class WriteGateResult(BaseModel):
    memory_entry_id: UUID
    contradiction_detected: bool
    conflict_id: UUID | None
    privacy_applied: bool
    rate_limit_remaining_min: int
    rate_limit_remaining_hour: int

class EvidenceConflictResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    memory_entry_id_a: UUID
    memory_entry_id_b: UUID
    conflict_description: str
    similarity_score: float
    status: ConflictStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime

class TrajectoryRecordResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    execution_id: UUID
    agent_fqn: str
    actions: list[dict]
    tool_invocations: list[dict]
    reasoning_snapshots: list[dict]
    verdicts: list[dict]
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime

class PatternAssetResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    trajectory_record_id: UUID | None
    nominated_by: str
    content: str
    description: str
    tags: list[str]
    status: PatternStatus
    reviewed_by: str | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    memory_entry_id: UUID | None  # set when approved
    created_at: datetime

class KnowledgeNodeResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    node_type: str
    external_name: str
    attributes: dict
    created_by_fqn: str
    created_at: datetime

class KnowledgeEdgeResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    source_node_id: UUID
    target_node_id: UUID
    relationship_type: str
    metadata: dict
    created_at: datetime

class GraphTraversalResponse(BaseModel):
    paths: list[list[dict]]  # list of paths, each path is a list of alternating nodes/edges
    node_count: int
    edge_count: int
    query_time_ms: float
```

---

## Service Class Signatures

```python
class MemoryService:
    # Write gate + storage
    async def write_memory(
        self, request: MemoryWriteRequest, agent_fqn: str, workspace_id: UUID
    ) -> WriteGateResult: ...

    async def get_memory_entry(self, entry_id: UUID, workspace_id: UUID) -> MemoryEntryResponse: ...
    async def list_memory_entries(
        self, workspace_id: UUID, agent_fqn: str | None, scope: MemoryScope | None,
        page: int, page_size: int
    ) -> tuple[list[MemoryEntryResponse], int]: ...
    async def delete_memory_entry(self, entry_id: UUID, workspace_id: UUID, agent_fqn: str) -> None: ...
    async def transfer_memory_scope(
        self, request: CrossScopeTransferRequest, agent_fqn: str, workspace_id: UUID
    ) -> WriteGateResult: ...

    # Retrieval
    async def retrieve(self, query: RetrievalQuery, agent_fqn: str, workspace_id: UUID) -> RetrievalResponse: ...

    # Conflicts
    async def list_conflicts(
        self, workspace_id: UUID, status: ConflictStatus | None, page: int, page_size: int
    ) -> tuple[list[EvidenceConflictResponse], int]: ...
    async def resolve_conflict(
        self, conflict_id: UUID, resolution: ConflictResolution, reviewer_fqn: str, workspace_id: UUID
    ) -> EvidenceConflictResponse: ...

    # Trajectories
    async def record_trajectory(
        self, record: TrajectoryRecordCreate, workspace_id: UUID
    ) -> TrajectoryRecordResponse: ...
    async def get_trajectory(self, trajectory_id: UUID, workspace_id: UUID) -> TrajectoryRecordResponse: ...

    # Patterns
    async def nominate_pattern(
        self, nomination: PatternNomination, nominated_by: str, workspace_id: UUID
    ) -> PatternAssetResponse: ...
    async def review_pattern(
        self, pattern_id: UUID, review: PatternReview, reviewer_fqn: str, workspace_id: UUID
    ) -> PatternAssetResponse: ...
    async def list_patterns(
        self, workspace_id: UUID, status: PatternStatus | None, page: int, page_size: int
    ) -> tuple[list[PatternAssetResponse], int]: ...

    # Knowledge graph
    async def create_knowledge_node(
        self, node: KnowledgeNodeCreate, created_by_fqn: str, workspace_id: UUID
    ) -> KnowledgeNodeResponse: ...
    async def create_knowledge_edge(
        self, edge: KnowledgeEdgeCreate, workspace_id: UUID
    ) -> KnowledgeEdgeResponse: ...
    async def traverse_graph(
        self, query: GraphTraversalQuery, workspace_id: UUID
    ) -> GraphTraversalResponse: ...
    async def get_provenance_chain(
        self, node_id: UUID, workspace_id: UUID
    ) -> GraphTraversalResponse: ...

    # Internal interface (used by context engineering service)
    async def retrieve_for_context(
        self,
        query_text: str,
        agent_fqn: str,
        workspace_id: UUID,
        goal_id: UUID | None,
        top_k: int = 10,
    ) -> list[RetrievalResult]: ...


class MemoryWriteGate:
    async def validate_and_write(
        self, request: MemoryWriteRequest, agent_fqn: str, workspace_id: UUID, db: AsyncSession
    ) -> WriteGateResult: ...
    async def _check_authorization(self, agent_fqn: str, namespace: str, scope: MemoryScope, workspace_id: UUID) -> None: ...
    async def _check_rate_limit(self, agent_fqn: str) -> tuple[int, int]: ...  # (remaining_min, remaining_hour)
    async def _check_contradiction(self, content: str, scope: MemoryScope, agent_fqn: str, workspace_id: UUID) -> UUID | None: ...
    async def _validate_retention(self, policy: RetentionPolicy, scope: MemoryScope, execution_id: UUID | None) -> None: ...
    async def _apply_differential_privacy(self, content: str, workspace_id: UUID) -> str: ...


class RetrievalCoordinator:
    async def retrieve(self, query: RetrievalQuery, agent_fqn: str, workspace_id: UUID) -> RetrievalResponse: ...
    async def _vector_search(self, query_text: str, scope_filter: str | None, agent_fqn: str, workspace_id: UUID, top_k: int) -> list[dict]: ...
    async def _keyword_search(self, query_text: str, scope_filter: str | None, agent_fqn: str, workspace_id: UUID, top_k: int) -> list[dict]: ...
    async def _graph_search(self, query_text: str, workspace_id: UUID, top_k: int) -> list[dict]: ...
    def _reciprocal_rank_fusion(self, result_lists: list[list[dict]], k: int) -> list[dict]: ...
    def _apply_recency_weight(self, results: list[dict]) -> list[dict]: ...
    def _apply_authority_weight(self, results: list[dict]) -> list[dict]: ...
    async def _flag_contradictions(self, results: list[dict], workspace_id: UUID) -> list[dict]: ...


class ConsolidationWorker:
    async def run(self) -> None: ...  # called by APScheduler every 15 min
    async def _find_consolidation_candidates(self, workspace_id: UUID) -> list[list[UUID]]: ...  # clusters of similar entries
    async def _distill(self, memory_ids: list[UUID], workspace_id: UUID) -> str: ...
    async def _promote(self, content: str, source_ids: list[UUID], workspace_id: UUID) -> None: ...


class EmbeddingWorker:
    async def run(self) -> None: ...  # called by APScheduler every 30 sec
    async def _process_pending_jobs(self, limit: int = 50) -> None: ...
    async def _generate_embedding(self, content: str) -> list[float]: ...
    async def _upsert_to_qdrant(self, memory_entry_id: UUID, embedding: list[float], payload: dict) -> None: ...
```

---

## Kafka Events (`memory.events`)

```python
class MemoryWrittenPayload(BaseModel):
    memory_entry_id: UUID
    workspace_id: UUID
    agent_fqn: str
    scope: MemoryScope
    namespace: str
    contradiction_detected: bool
    conflict_id: UUID | None

class ConflictDetectedPayload(BaseModel):
    conflict_id: UUID
    workspace_id: UUID
    memory_entry_id_a: UUID
    memory_entry_id_b: UUID
    similarity_score: float

class PatternPromotedPayload(BaseModel):
    pattern_asset_id: UUID
    workspace_id: UUID
    trajectory_record_id: UUID | None
    memory_entry_id: UUID
    approved_by: str

class ConsolidationCompletedPayload(BaseModel):
    workspace_id: UUID
    entries_consolidated: int
    entries_promoted: int
    duration_seconds: float
    run_at: datetime
```

---

## Memory Module Setup (`memory_setup.py`)

Idempotent startup function called from `api_main.py`, `worker_main.py` lifespan:

```python
async def setup_memory_collections() -> None:
    """Create Qdrant collection and Neo4j indexes if they do not exist."""
    # Qdrant
    existing = await qdrant_client.get_collections()
    if "platform_memory" not in [c.name for c in existing.collections]:
        await qdrant_client.create_collection(
            collection_name="platform_memory",
            vectors_config=VectorParams(size=settings.memory_embedding_dimensions, distance=Distance.COSINE),
        )
        # Create payload indexes
        ...

    # Neo4j
    async with neo4j_driver.session() as session:
        await session.run("CREATE INDEX node_workspace IF NOT EXISTS FOR (n:MemoryNode) ON (n.workspace_id)")
        await session.run("CREATE CONSTRAINT node_unique IF NOT EXISTS FOR (n:MemoryNode) REQUIRE (n.workspace_id, n.pg_id) IS UNIQUE")
```
