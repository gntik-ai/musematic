# Data Model: Agent Registry and Ingest

**Feature**: 021-agent-registry-ingest  
**Date**: 2026-04-11  
**Phase**: 1 — Data model, schemas, service class signatures

---

## 1. PostgreSQL — SQLAlchemy Models

All models live in `apps/control-plane/src/platform/registry/models.py`.  
Alembic migration: `apps/control-plane/migrations/versions/006_registry_tables.py`

### Enums

```python
import enum

class LifecycleStatus(str, enum.Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PUBLISHED = "published"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"

class AgentRoleType(str, enum.Enum):
    EXECUTOR = "executor"
    PLANNER = "planner"
    ORCHESTRATOR = "orchestrator"
    OBSERVER = "observer"
    JUDGE = "judge"
    ENFORCER = "enforcer"
    CUSTOM = "custom"

class MaturityLevel(int, enum.Enum):
    UNVERIFIED = 0
    BASIC_COMPLIANCE = 1
    TESTED = 2
    CERTIFIED = 3

class AssessmentMethod(str, enum.Enum):
    MANIFEST_DECLARED = "manifest_declared"
    SYSTEM_ASSESSED = "system_assessed"

class EmbeddingStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
```

### AgentNamespace

```python
class AgentNamespace(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "registry_namespaces"

    name: Mapped[str]                          # unique per workspace, slug format
    description: Mapped[str | None]
    created_by: Mapped[UUID]                   # user_id

    # Constraints
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_registry_ns_workspace_name"),
    )
```

### AgentProfile

```python
class AgentProfile(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, WorkspaceScopedMixin):
    __tablename__ = "registry_agent_profiles"

    namespace_id: Mapped[UUID]                 # FK → registry_namespaces.id
    local_name: Mapped[str]                    # unique within namespace, slug format
    fqn: Mapped[str]                           # "{namespace_name}:{local_name}", globally unique
    display_name: Mapped[str | None]
    purpose: Mapped[str]                       # mandatory, non-empty
    approach: Mapped[str | None]               # optional, natural-language strategy
    role_types: Mapped[list[str]]              # JSONB array of AgentRoleType values
    custom_role_description: Mapped[str | None]# required when role_types contains "custom"
    visibility_agents: Mapped[list[str]]       # JSONB array of FQN patterns, default []
    visibility_tools: Mapped[list[str]]        # JSONB array of FQN patterns, default []
    tags: Mapped[list[str]]                    # JSONB array of tag strings
    status: Mapped[LifecycleStatus]            # default: draft
    maturity_level: Mapped[int]                # 0-3, default: 0
    embedding_status: Mapped[EmbeddingStatus]  # default: pending
    needs_reindex: Mapped[bool]                # flag for OpenSearch retry, default: False
    created_by: Mapped[UUID]                   # user_id

    # Constraints
    __table_args__ = (
        UniqueConstraint("namespace_id", "local_name", name="uq_registry_profile_ns_local"),
        UniqueConstraint("fqn", name="uq_registry_profile_fqn"),
        Index("ix_registry_profile_workspace_status", "workspace_id", "status"),
        Index("ix_registry_profile_fqn", "fqn"),
    )
```

### AgentRevision

```python
class AgentRevision(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "registry_agent_revisions"

    agent_profile_id: Mapped[UUID]             # FK → registry_agent_profiles.id
    version: Mapped[str]                       # semver string from manifest
    sha256_digest: Mapped[str]                 # hex-encoded SHA-256 of original archive
    storage_key: Mapped[str]                   # MinIO object key
    manifest_snapshot: Mapped[dict]            # JSONB — full manifest at upload time
    uploaded_by: Mapped[UUID]                  # user_id

    # Note: No UPDATE allowed after insert — enforced in repository layer
    __table_args__ = (
        Index("ix_registry_revision_profile_id", "agent_profile_id"),
        UniqueConstraint("agent_profile_id", "version", name="uq_registry_revision_profile_version"),
    )
```

### AgentMaturityRecord

```python
class AgentMaturityRecord(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "registry_maturity_records"

    agent_profile_id: Mapped[UUID]             # FK → registry_agent_profiles.id
    previous_level: Mapped[int]                # 0-3
    new_level: Mapped[int]                     # 0-3
    assessment_method: Mapped[AssessmentMethod]
    reason: Mapped[str | None]
    actor_id: Mapped[UUID]                     # user_id or system_id
```

### LifecycleAuditEntry

```python
class LifecycleAuditEntry(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "registry_lifecycle_audit"

    agent_profile_id: Mapped[UUID]             # FK → registry_agent_profiles.id
    previous_status: Mapped[LifecycleStatus]
    new_status: Mapped[LifecycleStatus]
    actor_id: Mapped[UUID]                     # user_id
    reason: Mapped[str | None]

    __table_args__ = (
        Index("ix_registry_lifecycle_audit_profile", "agent_profile_id"),
    )
```

---

## 2. Lifecycle State Machine

Defined in `apps/control-plane/src/platform/registry/state_machine.py`:

```python
VALID_REGISTRY_TRANSITIONS: dict[LifecycleStatus, set[LifecycleStatus]] = {
    LifecycleStatus.DRAFT:       {LifecycleStatus.VALIDATED},
    LifecycleStatus.VALIDATED:   {LifecycleStatus.PUBLISHED},
    LifecycleStatus.PUBLISHED:   {LifecycleStatus.DISABLED, LifecycleStatus.DEPRECATED},
    LifecycleStatus.DISABLED:    {LifecycleStatus.PUBLISHED},
    LifecycleStatus.DEPRECATED:  {LifecycleStatus.ARCHIVED},
    LifecycleStatus.ARCHIVED:    set(),  # terminal state
}

# Event-emitting transitions
EVENT_TRANSITIONS: set[LifecycleStatus] = {
    LifecycleStatus.PUBLISHED,
    LifecycleStatus.DEPRECATED,
}
```

---

## 3. OpenSearch — `marketplace-agents` Index

Created by `registry_opensearch_setup.py` at startup (idempotent).

```json
{
  "settings": {
    "number_of_shards": 2,
    "number_of_replicas": 1,
    "analysis": {
      "analyzer": {
        "purpose_analyzer": {
          "type": "standard",
          "stopwords": "_english_"
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "agent_profile_id":  { "type": "keyword" },
      "fqn":               { "type": "keyword" },
      "namespace":         { "type": "keyword" },
      "local_name":        { "type": "keyword" },
      "display_name":      { "type": "text", "fields": { "keyword": { "type": "keyword" } } },
      "purpose":           { "type": "text", "analyzer": "purpose_analyzer" },
      "approach":          { "type": "text", "analyzer": "purpose_analyzer" },
      "tags":              { "type": "keyword" },
      "role_types":        { "type": "keyword" },
      "maturity_level":    { "type": "integer" },
      "status":            { "type": "keyword" },
      "workspace_id":      { "type": "keyword" },
      "created_at":        { "type": "date" }
    }
  }
}
```

---

## 4. Qdrant — `agent_embeddings` Collection

Created by `registry_qdrant_setup.py` at startup (idempotent).

```python
# Collection config (created via qdrant-client async gRPC)
collection_name = "agent_embeddings"
vector_size = settings.embedding_vector_size  # default: 1536 (OpenAI text-embedding-3-small)
distance = Distance.COSINE

# Point structure
# id: agent_profile_id (UUID)
# vector: float32 array, size = embedding_vector_size
# payload:
#   fqn: str
#   workspace_id: str
#   namespace: str
#   status: str  # for filtering by published-only in semantic search
```

---

## 5. MinIO — `agent-packages` Bucket

Object key pattern: `{workspace_id}/{namespace_name}/{local_name}/{revision_id}/package.tar.gz`

Example: `ws-abc123/finance-ops/kyc-verifier/rev-def456/package.tar.gz`

Bucket lifecycle: no automatic expiry (packages are immutable and retained indefinitely).

---

## 6. Pydantic Schemas

All in `apps/control-plane/src/platform/registry/schemas.py`.

### Request Schemas

```python
class NamespaceCreate(BaseModel):
    name: str                          # slug regex: ^[a-z][a-z0-9-]{1,62}$
    description: str | None = None

class AgentUploadParams(BaseModel):
    """Parsed from multipart form data"""
    namespace_name: str                # must already exist in this workspace

class AgentPatch(BaseModel):
    display_name: str | None = None
    approach: str | None = None
    tags: list[str] | None = None
    visibility_agents: list[str] | None = None
    visibility_tools: list[str] | None = None
    role_types: list[AgentRoleType] | None = None
    custom_role_description: str | None = None

class LifecycleTransitionRequest(BaseModel):
    target_status: LifecycleStatus
    reason: str | None = None

class MaturityUpdateRequest(BaseModel):
    maturity_level: MaturityLevel
    reason: str | None = None

class AgentDiscoveryParams(BaseModel):
    workspace_id: UUID | None = None   # required if human user, resolved from auth if agent
    fqn_pattern: str | None = None
    keyword: str | None = None
    maturity_min: int = 0
    status: LifecycleStatus = LifecycleStatus.PUBLISHED
    limit: int = Field(default=20, le=100)
    offset: int = 0
```

### Response Schemas

```python
class NamespaceResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    workspace_id: UUID
    created_at: datetime
    created_by: UUID

class AgentRevisionResponse(BaseModel):
    id: UUID
    agent_profile_id: UUID
    version: str
    sha256_digest: str
    storage_key: str
    manifest_snapshot: dict[str, Any]
    uploaded_by: UUID
    created_at: datetime

class AgentProfileResponse(BaseModel):
    id: UUID
    namespace_id: UUID
    fqn: str
    display_name: str | None
    purpose: str
    approach: str | None
    role_types: list[str]
    custom_role_description: str | None
    visibility_agents: list[str]
    visibility_tools: list[str]
    tags: list[str]
    status: LifecycleStatus
    maturity_level: int
    embedding_status: EmbeddingStatus
    workspace_id: UUID
    created_at: datetime
    current_revision: AgentRevisionResponse | None = None

class AgentUploadResponse(BaseModel):
    agent_profile: AgentProfileResponse
    revision: AgentRevisionResponse
    created: bool                      # True if new agent, False if new revision of existing

class AgentListResponse(BaseModel):
    items: list[AgentProfileResponse]
    total: int
    limit: int
    offset: int

class LifecycleAuditResponse(BaseModel):
    id: UUID
    agent_profile_id: UUID
    previous_status: LifecycleStatus
    new_status: LifecycleStatus
    actor_id: UUID
    reason: str | None
    created_at: datetime

class PackageValidationError(BaseModel):
    """Returned when package validation fails — 422"""
    error_type: str                    # "path_traversal", "symlink", "size_limit", "manifest_invalid", etc.
    detail: str
    field: str | None = None           # for manifest validation errors
```

### Manifest Model (internal)

```python
class AgentManifest(BaseModel):
    local_name: str = Field(pattern=r'^[a-z][a-z0-9-]{1,62}$')
    version: str = Field(pattern=r'^\d+\.\d+\.\d+')
    purpose: str = Field(min_length=10)
    role_types: list[AgentRoleType] = Field(min_length=1)
    approach: str | None = None
    maturity_level: MaturityLevel = MaturityLevel.UNVERIFIED
    reasoning_modes: list[str] = []
    context_profile: dict[str, Any] | None = None
    tags: list[str] = []
    display_name: str | None = None
    custom_role_description: str | None = None

    @model_validator(mode='after')
    def custom_role_requires_description(self) -> 'AgentManifest':
        if AgentRoleType.CUSTOM in self.role_types and not self.custom_role_description:
            raise ValueError("custom_role_description is required when role_types contains 'custom'")
        return self
```

---

## 7. Service Classes

### RegistryService

`apps/control-plane/src/platform/registry/service.py`

```python
class RegistryService:
    def __init__(
        self,
        repository: RegistryRepository,
        object_storage: ObjectStorageClient,
        opensearch: OpenSearchClient,
        qdrant: QdrantClient,
        workspaces_service: WorkspacesService,
        event_producer: KafkaProducer,
    ): ...

    async def create_namespace(
        self,
        workspace_id: UUID,
        params: NamespaceCreate,
        actor_id: UUID,
    ) -> AgentNamespace: ...

    async def upload_agent(
        self,
        workspace_id: UUID,
        namespace_name: str,
        package_bytes: bytes,
        filename: str,
        actor_id: UUID,
    ) -> AgentUploadResponse: ...
    # Internally calls: PackageValidator.validate() → MinIO upload → PostgreSQL upsert
    # → OpenSearch sync index → background embedding task dispatch

    async def get_agent(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        requesting_agent_id: UUID | None = None,
    ) -> AgentProfileResponse: ...

    async def resolve_fqn(
        self,
        fqn: str,
        workspace_id: UUID | None = None,
    ) -> AgentProfileResponse: ...

    async def list_agents(
        self,
        params: AgentDiscoveryParams,
        requesting_agent_id: UUID | None = None,
        actor_id: UUID | None = None,
    ) -> AgentListResponse: ...
    # Applies visibility filtering (union of agent patterns + workspace grants)

    async def patch_agent(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        patch: AgentPatch,
        actor_id: UUID,
    ) -> AgentProfileResponse: ...

    async def transition_lifecycle(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        request: LifecycleTransitionRequest,
        actor_id: UUID,
    ) -> AgentProfileResponse: ...

    async def update_maturity(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        request: MaturityUpdateRequest,
        actor_id: UUID,
    ) -> AgentProfileResponse: ...

    async def list_revisions(
        self,
        workspace_id: UUID,
        agent_id: UUID,
    ) -> list[AgentRevisionResponse]: ...

    async def list_namespaces(
        self,
        workspace_id: UUID,
    ) -> list[NamespaceResponse]: ...

    async def delete_namespace(
        self,
        workspace_id: UUID,
        namespace_id: UUID,
        actor_id: UUID,
    ) -> None: ...
    # Fails with RegistryError if namespace has registered agents
```

### PackageValidator

`apps/control-plane/src/platform/registry/package_validator.py`

```python
@dataclass
class ValidationResult:
    sha256_digest: str
    manifest: AgentManifest
    temp_dir: Path                    # caller must cleanup

class PackageValidator:
    def __init__(self, max_size_bytes: int = 50 * 1024 * 1024): ...

    async def validate(
        self,
        package_bytes: bytes,
        filename: str,
    ) -> ValidationResult:
        """
        Raises PackageValidationError on any security or structure violation.
        Steps:
        1. Extension check (.tar.gz, .zip)
        2. Size check
        3. Extract to temp dir (isolated)
        4. Path traversal check (all members resolve within temp dir)
        5. Symlink rejection
        6. Required file check (manifest.yaml or manifest.json)
        7. Manifest parse + AgentManifest validation
        8. SHA-256 digest computation
        """
```

### RegistryIndexWorker

`apps/control-plane/src/platform/registry/index_worker.py`

```python
class RegistryIndexWorker:
    """Background worker — registered in worker_main.py lifespan.
    Polls registry_agent_profiles WHERE needs_reindex = true every 30s.
    Retries OpenSearch indexing. Marks needs_reindex = false on success.
    """
    async def run(self) -> None: ...
    async def _retry_index_batch(self) -> None: ...
```

---

## 8. Events

`apps/control-plane/src/platform/registry/events.py`

```python
# Topic: registry.events

class AgentCreatedPayload(BaseModel):
    agent_profile_id: str
    fqn: str
    namespace: str
    workspace_id: str
    revision_id: str
    version: str
    maturity_level: int
    role_types: list[str]

class AgentPublishedPayload(BaseModel):
    agent_profile_id: str
    fqn: str
    workspace_id: str
    published_by: str

class AgentDeprecatedPayload(BaseModel):
    agent_profile_id: str
    fqn: str
    workspace_id: str
    deprecated_by: str
    reason: str | None

async def publish_agent_created(producer: KafkaProducer, payload: AgentCreatedPayload, correlation: CorrelationContext) -> None: ...
async def publish_agent_published(producer: KafkaProducer, payload: AgentPublishedPayload, correlation: CorrelationContext) -> None: ...
async def publish_agent_deprecated(producer: KafkaProducer, payload: AgentDeprecatedPayload, correlation: CorrelationContext) -> None: ...
```
