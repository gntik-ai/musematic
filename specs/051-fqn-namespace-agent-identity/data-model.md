# Data Model: FQN Namespace System and Agent Identity

**Feature**: 051-fqn-namespace-agent-identity
**Phase**: 1 — Design
**Date**: 2026-04-18
**Brownfield**: Extending existing tables from feature 021 (Agent Registry & Ingest)

---

## Overview

Most of the data model already exists. This document records what's there, what changes, and what's new.

---

## Existing: AgentNamespace (registry_namespaces) — NO CHANGES

**File**: `apps/control-plane/src/platform/registry/models.py`

```python
class AgentNamespace(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "registry_namespaces"

    workspace_id: Mapped[UUID]       # indexed
    name: Mapped[str]                # String(63), unique across platform
    description: Mapped[str | None]
    created_by: Mapped[UUID]

    # Relationship
    profiles: Mapped[list["AgentProfile"]]  # cascade delete

    # Constraint
    UniqueConstraint("workspace_id", "name")
```

**Note**: The spec requires namespace names to be globally unique (not just per workspace). The current constraint is `UniqueConstraint(workspace_id, name)`. Research Decision 1 confirms this is an existing implementation choice — if global uniqueness is needed, the constraint would need to change. For this update pass, the existing workspace-scoped uniqueness is preserved per Brownfield Rule 7 (backward-compatible).

---

## Existing: AgentProfile (registry_agent_profiles) — MINOR VALIDATION CHANGE ONLY

**File**: `apps/control-plane/src/platform/registry/models.py`

No schema changes to the table or columns. All FQN-related fields already exist:

```python
class AgentProfile(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "registry_agent_profiles"

    workspace_id: Mapped[UUID]                        # indexed
    namespace_id: Mapped[UUID | None]                 # FK → registry_namespaces
    local_name: Mapped[str | None]                    # String(63)
    fqn: Mapped[str | None]                           # String(127), unique index
    display_name: Mapped[str | None]                  # String(255)
    purpose: Mapped[str]                              # Text, default ''
    approach: Mapped[str | None]                      # Text
    role_types: Mapped[list[AgentRoleType]]           # JSONB, min 1
    custom_role_description: Mapped[str | None]
    visibility_agents: Mapped[list[str]]              # JSONB — FQN patterns
    visibility_tools: Mapped[list[str]]               # JSONB — FQN patterns
    tags: Mapped[list[str]]                           # JSONB
    status: Mapped[LifecycleStatus]                   # default: draft
    maturity_level: Mapped[int]                       # 0–3
    embedding_status: Mapped[EmbeddingStatus]
    needs_reindex: Mapped[bool]                       # default: False
    created_by: Mapped[UUID]

    # Constraints
    UniqueConstraint("namespace_id", "local_name")
    UniqueConstraint("fqn")
    # Index on (workspace_id, status), (fqn), (needs_reindex)
```

**Enum**: `AgentRoleType` — executor, planner, orchestrator, observer, judge, enforcer, custom

---

## Existing: AgentRevision, AgentMaturityRecord, LifecycleAuditEntry — NO CHANGES

These tables support the revision and audit trail for agents. No modifications needed for this feature.

---

## CHANGED: CorrelationContext — Add agent_fqn (Optional)

**File**: `apps/control-plane/src/platform/common/events/envelope.py`

**Change**: Add `agent_fqn: str | None = None` as an optional field.

```python
class CorrelationContext(BaseModel):
    workspace_id: UUID | None = None
    conversation_id: UUID | None = None
    interaction_id: UUID | None = None
    execution_id: UUID | None = None
    fleet_id: UUID | None = None
    goal_id: UUID | None = None
    correlation_id: UUID
    agent_fqn: str | None = None    # NEW: format "namespace:local_name"
```

**Migration**: None required (this is a Pydantic model change only, not a database table).

**Backward compatibility**: All existing event producers continue to work. The field defaults to `None`.

---

## CHANGED: AgentManifest Schema — Purpose min_length 10 → 50

**File**: `apps/control-plane/src/platform/registry/schemas.py`

**Change**: Update `AgentManifest.purpose` field validator:

```python
# Before
purpose: str = Field(min_length=10)

# After
purpose: str = Field(min_length=50)
```

Also update `AgentPatch` if it includes a `purpose` field (check for consistency):

```python
# AgentPatch — add length validation if purpose is patchable
purpose: str | None = Field(default=None, min_length=50)
```

**Migration**: None required (schema validation change only). Existing agents with `len(purpose) < 50` are not retroactively invalidated.

---

## NEW: Alembic Migration 041 — Backfill Default Namespaces and FQNs

**File**: `apps/control-plane/migrations/versions/041_fqn_backfill.py`

**Purpose**: Assign FQNs to any agents that were created before the FQN system (namespace_id IS NULL).

```python
revision = "041_fqn_backfill"
down_revision = "040_simulation_digital_twins"

def upgrade() -> None:
    # 1. For each workspace with namespace-less agents, create "default" namespace
    #    (ON CONFLICT DO NOTHING for idempotency)
    op.execute("""
        INSERT INTO registry_namespaces (id, workspace_id, name, created_by, created_at, updated_at)
        SELECT gen_random_uuid(), a.workspace_id, 'default',
               a.created_by, now(), now()
        FROM registry_agent_profiles a
        WHERE a.namespace_id IS NULL
          AND a.deleted_at IS NULL
        GROUP BY a.workspace_id, a.created_by
        ON CONFLICT DO NOTHING
    """)

    # 2. Assign namespace_id + local_name + fqn to agents without them
    #    local_name derived from display_name (slugified) with collision handling
    op.execute("""
        WITH namespaces AS (
            SELECT id, workspace_id FROM registry_namespaces WHERE name = 'default'
        ),
        ranked AS (
            SELECT a.id, n.id AS ns_id,
                   LOWER(REGEXP_REPLACE(COALESCE(a.display_name, a.id::text),
                         '[^a-z0-9-]', '-', 'g')) AS base_local_name
            FROM registry_agent_profiles a
            JOIN namespaces n ON n.workspace_id = a.workspace_id
            WHERE a.namespace_id IS NULL AND a.deleted_at IS NULL
        )
        UPDATE registry_agent_profiles p
        SET namespace_id = r.ns_id,
            local_name   = r.base_local_name,
            fqn          = 'default:' || r.base_local_name,
            updated_at   = now()
        FROM ranked r
        WHERE p.id = r.id
    """)

    # 3. Flag agents needing purpose review (purpose too short for new validation)
    op.execute("""
        UPDATE registry_agent_profiles
        SET needs_reindex = true
        WHERE length(purpose) < 50
          AND deleted_at IS NULL
          AND needs_reindex = false
    """)

def downgrade() -> None:
    pass  # Data migration; one-way
```

**Note**: The `local_name` derivation above is simplified. A production migration would handle slug collisions within a namespace (e.g., appending `-2`, `-3`). The full implementation is in the tasks.

---

## Validation Rules

| Field | Rule | Location |
|-------|------|----------|
| `namespace.name` | Slug: `[a-z0-9-]+`, 1–63 chars, starts with letter | `NamespaceCreate` schema |
| `agent.local_name` | Same slug rules as namespace name | `AgentManifest` schema |
| `agent.purpose` | `min_length=50` | `AgentManifest` schema (updated) |
| `agent.role_types` | Non-empty list, values from `AgentRoleType` enum | `AgentManifest` schema |
| `fqn` | Computed: `f"{namespace}:{local_name}"`, globally unique | Set by service on create |
| `agent_fqn` in event | Optional, `None` if not from an identified agent | `CorrelationContext` |

---

## State Transitions

No new state machines. The existing `LifecycleStatus` flow for agents is unchanged:

```
draft → validated → published → disabled → deprecated → archived
```

---

## Existing Indexes (No New Indexes Needed)

| Table | Index | Type |
|-------|-------|------|
| `registry_namespaces` | `UNIQUE(workspace_id, name)` | Unique B-tree |
| `registry_agent_profiles` | `UNIQUE(fqn)` | Unique B-tree |
| `registry_agent_profiles` | `UNIQUE(namespace_id, local_name)` | Unique B-tree |
| `registry_agent_profiles` | `INDEX(workspace_id, status)` | B-tree |
| `registry_agent_profiles` | `INDEX(needs_reindex)` | B-tree |
| `registry_agent_profiles` | `INDEX USING gin(to_tsvector('english', purpose))` | GIN FTS |
