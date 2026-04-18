# Data Model: IBOR Integration and Agent Decommissioning

**Feature**: `specs/056-ibor-agent-decommissioning/spec.md`
**Date**: 2026-04-18

---

## Alembic Migration 044

**File**: `apps/control-plane/migrations/versions/044_ibor_and_decommission.py`
**Revision**: `"044_ibor_and_decommission"`
**Down revision**: `"043_runtime_warm_pool_targets"`

### Upgrade operations (ordered)

1. **Add enum value** — `op.execute("ALTER TYPE registry_lifecycle_status ADD VALUE IF NOT EXISTS 'decommissioned'")`
2. **Extend `registry_agent_profiles`**:
   - `decommissioned_at TIMESTAMPTZ NULL`
   - `decommission_reason TEXT NULL`
   - `decommissioned_by UUID NULL`
3. **Extend `user_roles`**:
   - `source_connector_id UUID NULL` (references `ibor_connectors.id`; no FK constraint — soft reference to permit connector deletion while preserving history)
   - Index `ix_user_roles_source_connector` on `source_connector_id` (for revoke-by-connector queries)
4. **Create `ibor_connectors`**:
```
ibor_connectors
├── id                    UUID PK DEFAULT gen_random_uuid()
├── name                  VARCHAR(255) NOT NULL UNIQUE
├── source_type           VARCHAR(32) NOT NULL  -- ldap | oidc | scim
├── sync_mode             VARCHAR(16) NOT NULL  -- pull | push | both
├── cadence_seconds       INTEGER NOT NULL DEFAULT 3600
├── credential_ref        VARCHAR(255) NOT NULL
├── role_mapping_policy   JSONB NOT NULL DEFAULT '[]'
├── enabled               BOOLEAN NOT NULL DEFAULT true
├── created_by            UUID NOT NULL
├── created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
├── updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
├── last_run_at           TIMESTAMPTZ NULL
└── last_run_status       VARCHAR(32) NULL  -- succeeded | partial_success | failed | running
```
5. **Create `ibor_sync_runs`**:
```
ibor_sync_runs
├── id               UUID PK DEFAULT gen_random_uuid()
├── connector_id     UUID NOT NULL REFERENCES ibor_connectors(id) ON DELETE CASCADE
├── mode             VARCHAR(16) NOT NULL  -- pull | push
├── started_at       TIMESTAMPTZ NOT NULL DEFAULT now()
├── finished_at      TIMESTAMPTZ NULL
├── status           VARCHAR(32) NOT NULL  -- running | succeeded | partial_success | failed
├── counts           JSONB NOT NULL DEFAULT '{}'
├── error_details    JSONB NOT NULL DEFAULT '[]'
└── triggered_by     UUID NULL  -- null = scheduled
── INDEX ix_ibor_sync_runs_connector_started on (connector_id, started_at DESC)
```

### Downgrade operations

- Drop `ibor_sync_runs`, `ibor_connectors`.
- Drop column `user_roles.source_connector_id`.
- Drop columns `registry_agent_profiles.decommissioned_at`, `decommission_reason`, `decommissioned_by`.
- Note: PostgreSQL does not support removing enum values; `decommissioned` stays in `registry_lifecycle_status` after downgrade (documented in the migration comment).

---

## Python: Registry Enum Extension

**File**: `apps/control-plane/src/platform/registry/models.py`
**Modification**: Append one value to existing `LifecycleStatus` StrEnum (additive, Brownfield Rule 6).

```python
class LifecycleStatus(StrEnum):
    draft = "draft"
    validated = "validated"
    published = "published"
    disabled = "disabled"
    deprecated = "deprecated"
    archived = "archived"
    decommissioned = "decommissioned"  # NEW — terminal
```

---

## Python: AgentProfile Extension

**File**: `apps/control-plane/src/platform/registry/models.py`
**Modification**: Add 3 nullable columns to `AgentProfile` class (additive, Brownfield Rule 7).

```python
class AgentProfile(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    # ... existing columns unchanged ...
    decommissioned_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True,
    )
    decommission_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    decommissioned_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True,
    )
```

---

## Python: State Machine Extension

**File**: `apps/control-plane/src/platform/registry/state_machine.py`
**Modification**: Update `VALID_REGISTRY_TRANSITIONS` dict (additive).

```python
VALID_REGISTRY_TRANSITIONS: dict[LifecycleStatus, set[LifecycleStatus]] = {
    LifecycleStatus.draft: {LifecycleStatus.validated, LifecycleStatus.decommissioned},
    LifecycleStatus.validated: {LifecycleStatus.published, LifecycleStatus.decommissioned},
    LifecycleStatus.published: {LifecycleStatus.disabled, LifecycleStatus.deprecated, LifecycleStatus.decommissioned},
    LifecycleStatus.disabled: {LifecycleStatus.published, LifecycleStatus.decommissioned},
    LifecycleStatus.deprecated: {LifecycleStatus.archived, LifecycleStatus.decommissioned},
    LifecycleStatus.archived: {LifecycleStatus.decommissioned},
    LifecycleStatus.decommissioned: set(),  # terminal — FR-013
}
```

Note: `archived → decommissioned` is allowed so soft-deleted agents can be formally decommissioned for compliance. The only prohibited direction is OUT of `decommissioned` (enforces FR-013 irreversibility).

---

## Python: UserRole Extension for IBOR provenance

**File**: `apps/control-plane/src/platform/auth/models.py`
**Modification**: Add nullable `source_connector_id` column (additive).

```python
class UserRole(Base, UUIDMixin, TimestampMixin):
    # ... existing columns unchanged ...
    source_connector_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True,
    )
```

`source_connector_id IS NULL` indicates a manually-created role assignment (preserved by IBOR revocation logic, FR-003).
`source_connector_id IS NOT NULL` indicates an IBOR-sourced assignment (revocable by the connector that created it).

---

## Python: New auth models — IBORConnector + IBORSyncRun

**File**: `apps/control-plane/src/platform/auth/models.py`
**Modification**: Add two new model classes (additive).

```python
class IBORSourceType(StrEnum):
    ldap = "ldap"
    oidc = "oidc"
    scim = "scim"

class IBORSyncMode(StrEnum):
    pull = "pull"
    push = "push"
    both = "both"

class IBORSyncRunStatus(StrEnum):
    running = "running"
    succeeded = "succeeded"
    partial_success = "partial_success"
    failed = "failed"

class IBORConnector(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "ibor_connectors"
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    source_type: Mapped[IBORSourceType]
    sync_mode: Mapped[IBORSyncMode]
    cadence_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    credential_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    role_mapping_policy: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[UUID]
    last_run_at: Mapped[datetime | None]
    last_run_status: Mapped[str | None]

class IBORSyncRun(Base, UUIDMixin):
    __tablename__ = "ibor_sync_runs"
    connector_id: Mapped[UUID] = mapped_column(
        ForeignKey("ibor_connectors.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    mode: Mapped[IBORSyncMode]
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]
    status: Mapped[IBORSyncRunStatus]
    counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_details: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    triggered_by: Mapped[UUID | None]
```

---

## Python: New schemas

**File**: `apps/control-plane/src/platform/auth/schemas.py`

```python
class IBORRoleMappingRule(BaseModel):
    directory_group: str = Field(min_length=1, max_length=512)
    platform_role: str = Field(min_length=1, max_length=50)
    workspace_scope: UUID | None = None

class IBORConnectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: IBORSourceType
    sync_mode: IBORSyncMode
    cadence_seconds: int = Field(ge=60, le=86400, default=3600)
    credential_ref: str = Field(min_length=1, max_length=255)
    role_mapping_policy: list[IBORRoleMappingRule] = Field(default_factory=list)
    enabled: bool = True

class IBORConnectorResponse(BaseModel):
    id: UUID
    name: str
    source_type: IBORSourceType
    sync_mode: IBORSyncMode
    cadence_seconds: int
    credential_ref: str  # redacted in REST response (name only)
    role_mapping_policy: list[IBORRoleMappingRule]
    enabled: bool
    last_run_at: datetime | None
    last_run_status: str | None

class IBORSyncRunResponse(BaseModel):
    id: UUID
    connector_id: UUID
    mode: IBORSyncMode
    started_at: datetime
    finished_at: datetime | None
    status: IBORSyncRunStatus
    counts: dict[str, int]  # users_created, users_updated, roles_added, roles_revoked, errors
    error_details: list[dict]
    triggered_by: UUID | None
```

**File**: `apps/control-plane/src/platform/registry/schemas.py`

```python
class AgentDecommissionRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)

class AgentDecommissionResponse(BaseModel):
    agent_id: UUID
    agent_fqn: str
    decommissioned_at: datetime
    decommission_reason: str
    decommissioned_by: UUID
    active_instances_stopped: int
```

---

## Python: New service — IBOR sync

**File**: `apps/control-plane/src/platform/auth/ibor_sync.py` (NEW)

Service class `IBORSyncService` with methods:
- `async def run_sync(connector_id: UUID, triggered_by: UUID | None) -> IBORSyncRunResponse` — main entry point; acquires Redis lock `ibor:sync:{connector_id}` (TTL = cadence + 60s); dispatches to LDAP/OIDC/SCIM adapter based on `source_type`; reconciles roles per-user; persists `IBORSyncRun` record; publishes `ibor_sync_completed` event.
- `async def _pull_ldap(connector) -> dict` — LDAP adapter (`ldap3` library — add to dependencies).
- `async def _pull_oidc(connector) -> dict` — OIDC adapter via httpx (uses connector's credential_ref to authenticate to the OIDC admin/userinfo API).
- `async def _pull_scim(connector) -> dict` — SCIM adapter via httpx (GET `/Users`, GET `/Groups`).
- `async def _push_scim(connector) -> dict` — SCIM outbound push for FR-004.
- `async def _reconcile_user_roles(user_email: str, directory_groups: list[str], policy: list[dict], connector_id: UUID) -> dict` — per-user reconciliation; returns counts.
- `async def _resolve_credential(credential_ref: str) -> dict[str, str]` — reads Kubernetes Secret (or equivalent) using the project's existing secret-resolution pattern.

---

## Python: New service — IBOR connector management

**File**: `apps/control-plane/src/platform/auth/ibor_service.py` (NEW)

Service class `IBORConnectorService` with methods:
- `async def create_connector(payload, actor_id) -> IBORConnectorResponse`
- `async def list_connectors() -> list[IBORConnectorResponse]`
- `async def get_connector(connector_id) -> IBORConnectorResponse`
- `async def update_connector(connector_id, payload, actor_id) -> IBORConnectorResponse`
- `async def delete_connector(connector_id, actor_id) -> None` (soft disable; preserves sync-run history)
- `async def list_sync_runs(connector_id, limit=90) -> list[IBORSyncRunResponse]`

---

## Python: Registry service extensions

**File**: `apps/control-plane/src/platform/registry/service.py`
**Modification**: Two changes.

### 1. New `decommission_agent()` method

```python
async def decommission_agent(
    self,
    workspace_id: UUID,
    agent_id: UUID,
    reason: str,
    actor_id: UUID,
    *,
    runtime_controller: Any,  # RuntimeControllerClient
) -> AgentDecommissionResponse:
    """Formally decommission an agent. FR-007, FR-008, FR-009, FR-010, FR-011, FR-012."""
    # Authorization: workspace_owner OR platform_admin (FR-009)
    await self._assert_decommission_authorized(workspace_id, agent_id, actor_id)

    profile = await self._get_agent_or_raise(workspace_id, agent_id)

    # Idempotency: already decommissioned → return existing record
    if profile.status is LifecycleStatus.decommissioned:
        return AgentDecommissionResponse(... existing values ...)

    # Validate transition via existing state machine (allows from any non-terminal state)
    if not is_valid_transition(profile.status, LifecycleStatus.decommissioned):
        raise InvalidTransitionError(...)

    # Stop running instances via Runtime Controller (FR-010)
    active_instances = await self._list_active_instances(profile.fqn, runtime_controller)
    stopped_count = await self._stop_instances(active_instances, runtime_controller)

    # Persist terminal state
    profile.status = LifecycleStatus.decommissioned
    profile.decommissioned_at = datetime.now(UTC)
    profile.decommission_reason = reason
    profile.decommissioned_by = actor_id

    # Audit (reuses existing lifecycle_audit table)
    await self.repository.insert_lifecycle_audit(
        workspace_id=workspace_id, agent_profile_id=profile.id,
        previous_status=profile.status,  # pre-transition
        new_status=LifecycleStatus.decommissioned,
        actor_id=actor_id, reason=reason,
    )
    await self._commit()

    # Trigger OpenSearch re-index (exclude from marketplace)
    await self._index_or_flag(profile.id)

    # Publish event
    await publish_agent_decommissioned(
        self.event_producer,
        AgentDecommissionedPayload(
            agent_profile_id=str(profile.id), fqn=profile.fqn,
            workspace_id=str(profile.workspace_id),
            decommissioned_by=str(actor_id), reason=reason,
            active_instance_count=stopped_count,
        ),
        self._correlation(workspace_id, profile.fqn),
    )

    return AgentDecommissionResponse(...)
```

### 2. List/search predicate extension

Every public-facing list/search method (marketplace, discovery, workflow-builder, fleet-composition) that currently filters out `LifecycleStatus.archived` also filters out `LifecycleStatus.decommissioned`. Audit/admin paths do NOT filter (FR-012).

---

## Python: Registry router extension

**File**: `apps/control-plane/src/platform/registry/router.py`
**Modification**: Add one endpoint.

```python
@router.post(
    "/{workspace_id}/agents/{agent_id}/decommission",
    response_model=AgentDecommissionResponse,
    status_code=200,
)
async def decommission_agent(
    workspace_id: UUID,
    agent_id: UUID,
    payload: AgentDecommissionRequest,
    actor: AuthContext = Depends(require_authenticated),
    service: AgentService = Depends(get_agent_service),
    runtime_controller: RuntimeControllerClient = Depends(get_runtime_controller),
) -> AgentDecommissionResponse:
    return await service.decommission_agent(
        workspace_id=workspace_id, agent_id=agent_id,
        reason=payload.reason, actor_id=actor.user_id,
        runtime_controller=runtime_controller,
    )
```

---

## Python: New auth router endpoints

**File**: `apps/control-plane/src/platform/auth/router.py`
**Modification**: Add CRUD + sync-trigger endpoints (additive; all require `platform_admin`).

```
POST   /api/v1/auth/ibor/connectors                — create
GET    /api/v1/auth/ibor/connectors                — list
GET    /api/v1/auth/ibor/connectors/{id}            — get
PUT    /api/v1/auth/ibor/connectors/{id}            — update
DELETE /api/v1/auth/ibor/connectors/{id}            — soft-delete (sets enabled=false)
POST   /api/v1/auth/ibor/connectors/{id}/sync       — trigger sync on-demand
GET    /api/v1/auth/ibor/connectors/{id}/runs       — list recent sync runs (90)
```

---

## Python: RBACEngine extension

**File**: `apps/control-plane/src/platform/auth/rbac.py`
**Modification**: Add helper method for connector-scoped revocation (used by `IBORSyncService._reconcile_user_roles`).

```python
async def revoke_connector_sourced_roles(
    self,
    repository: AuthRepository,
    user_id: UUID,
    connector_id: UUID,
    kept_roles: set[str],
) -> int:
    """Revoke all roles for user_id sourced from connector_id except those in kept_roles.
    Returns count of revoked roles. Never touches rows with source_connector_id IS NULL.
    """
```

---

## Python: Events extension

**File**: `apps/control-plane/src/platform/registry/events.py`
**Modification**: Add `publish_agent_decommissioned()` helper + `AgentDecommissionedPayload` dataclass. Topic: `registry.events`.

**File**: `apps/control-plane/src/platform/auth/events.py`
**Modification**: Add `publish_ibor_sync_completed()` helper + `IBORSyncCompletedPayload` dataclass. Topic: `auth.events`.
