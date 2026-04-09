# Data Model: PostgreSQL Deployment and Schema Foundation

**Feature**: 001-postgresql-schema-foundation  
**Date**: 2026-04-09

---

## Entity Overview

```
users ──────────────────────────────────────────────┐
  │                                                  │
  │ 1                                               │ (audit FKs)
  ▼ *                                               │
memberships ◄──────── workspaces ◄─────────────────┤
                           │                        │
                           │ 1                      │
                           ▼ *                      │
                     agent_namespaces               │
                           │                        │
                           │ (used by future        │
                           │  agent_profiles        │
                           │  migration)            │
sessions ──────────────────┘ (user_id FK)           │
                                                    │
audit_events ───────────────────────────────────────┘ (APPEND-ONLY)
execution_events (APPEND-ONLY, no user FK required)
```

---

## Core Tables

### `users`

Central identity record. Referenced as FK target by most other tables.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | UUIDMixin |
| `email` | `VARCHAR(255)` | UNIQUE NOT NULL | Login identifier |
| `display_name` | `VARCHAR(255)` | NULL | Optional display name |
| `status` | `VARCHAR(50)` | NOT NULL DEFAULT `'pending_verification'` | `pending_verification`, `active`, `suspended` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | TimestampMixin |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | TimestampMixin, updated on write |
| `deleted_at` | `TIMESTAMPTZ` | NULL | SoftDeleteMixin |
| `deleted_by` | `UUID` | FK → `users.id` NULL | SoftDeleteMixin |
| `created_by` | `UUID` | FK → `users.id` NULL | AuditMixin (NULL for bootstrap user) |
| `updated_by` | `UUID` | FK → `users.id` NULL | AuditMixin |

**Indexes**: `idx_users_email` (unique), `idx_users_status`

**State transitions**:
- `pending_verification` → `active` (email confirmed)
- `active` → `suspended` (admin action)
- Any → soft-deleted via `deleted_at`

---

### `workspaces`

Tenant boundary. All tenant-scoped entities carry `workspace_id`.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | UUIDMixin |
| `name` | `VARCHAR(255)` | NOT NULL | Display name |
| `owner_id` | `UUID` | FK → `users.id` NOT NULL | Primary owner |
| `settings` | `JSONB` | NOT NULL DEFAULT `'{}'` | Workspace-level config bag |
| `version` | `INTEGER` | NOT NULL DEFAULT `1` | EventSourcedMixin (optimistic lock) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | TimestampMixin |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | TimestampMixin |
| `deleted_at` | `TIMESTAMPTZ` | NULL | SoftDeleteMixin |
| `deleted_by` | `UUID` | FK → `users.id` NULL | SoftDeleteMixin |

**Indexes**: `idx_workspaces_owner`

---

### `memberships`

Associates users with workspaces. Composite unique constraint enforces one role per user-workspace pair.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | UUIDMixin |
| `workspace_id` | `UUID` | FK → `workspaces.id` NOT NULL, INDEX | WorkspaceScopedMixin |
| `user_id` | `UUID` | FK → `users.id` NOT NULL | |
| `role` | `VARCHAR(50)` | NOT NULL DEFAULT `'member'` | `owner`, `admin`, `member`, `viewer` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | |

**Unique constraint**: `(workspace_id, user_id)`  
**Indexes**: `idx_memberships_user`, `idx_memberships_workspace`

---

### `sessions`

Tracks active user sessions. Revocation sets `revoked_at`; expiry is enforced by application logic.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | UUIDMixin |
| `user_id` | `UUID` | FK → `users.id` NOT NULL, INDEX | |
| `token_hash` | `VARCHAR(255)` | NOT NULL | SHA-256 of the session token |
| `expires_at` | `TIMESTAMPTZ` | NOT NULL | Application enforces expiry |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | |
| `revoked_at` | `TIMESTAMPTZ` | NULL | Set on logout or forced revocation |

**Indexes**: `idx_sessions_user`, `idx_sessions_expires`

---

## Append-Only Tables

### `audit_events`

Immutable log of security and compliance events. UPDATE and DELETE are blocked at the database level via PostgreSQL rules.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | |
| `event_type` | `VARCHAR(100)` | NOT NULL | e.g., `user.login`, `workspace.deleted` |
| `actor_id` | `UUID` | NULL | Who triggered the event (NULL for system events) |
| `actor_type` | `VARCHAR(50)` | NOT NULL | `user`, `agent`, `system` |
| `workspace_id` | `UUID` | NULL | Workspace context (NULL for platform events) |
| `resource_type` | `VARCHAR(100)` | NULL | e.g., `user`, `workspace`, `agent` |
| `resource_id` | `UUID` | NULL | ID of affected resource |
| `action` | `VARCHAR(100)` | NOT NULL | e.g., `create`, `update`, `delete`, `login` |
| `details` | `JSONB` | NULL | Structured event payload |
| `occurred_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | Event timestamp |

**Append-only enforcement**:
```sql
CREATE RULE audit_no_update AS ON UPDATE TO audit_events DO INSTEAD NOTHING;
CREATE RULE audit_no_delete AS ON DELETE TO audit_events DO INSTEAD NOTHING;
```

**Indexes**: `idx_audit_events_workspace` (workspace_id, occurred_at), `idx_audit_events_actor` (actor_id, occurred_at)

---

### `execution_events`

Append-only journal for agent execution steps. Supports event sourcing and replay.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | |
| `execution_id` | `UUID` | NOT NULL, INDEX | Groups events by execution run |
| `event_type` | `VARCHAR(100)` | NOT NULL | e.g., `step.started`, `step.completed`, `execution.failed` |
| `step_id` | `VARCHAR(255)` | NULL | Identifier of the specific step |
| `payload` | `JSONB` | NULL | Step input/output data |
| `correlation` | `JSONB` | NULL | Tracing IDs, causation chains |
| `occurred_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | |

**Append-only enforcement**:
```sql
CREATE RULE exec_events_no_update AS ON UPDATE TO execution_events DO INSTEAD NOTHING;
CREATE RULE exec_events_no_delete AS ON DELETE TO execution_events DO INSTEAD NOTHING;
```

**Indexes**: `idx_exec_events_execution` (execution_id, occurred_at)

---

## Agentic Mesh Table

### `agent_namespaces`

Named groupings for agents within a workspace. The `name` field is unique across the entire platform (not scoped to workspace), enabling the FQN addressing scheme.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK, `DEFAULT gen_random_uuid()` | |
| `name` | `VARCHAR(255)` | UNIQUE NOT NULL | Platform-unique, e.g., `finance-ops` |
| `workspace_id` | `UUID` | FK → `workspaces.id` NOT NULL, INDEX | |
| `description` | `TEXT` | NULL | Human-readable description |
| `created_at` | `TIMESTAMPTZ` | NOT NULL DEFAULT `now()` | |
| `created_by` | `UUID` | FK → `users.id` NULL | |

**Unique constraint**: `name` (platform-global)  
**Index**: `idx_agent_namespaces_workspace`

**FQN pattern** (enforced in future `agent_profiles` migration):
```
fqn = agent_namespaces.name + ":" + agent_profiles.local_name
```
Uniqueness guaranteed by: `UNIQUE(name)` on `agent_namespaces` + `UNIQUE(namespace_id, local_name)` on `agent_profiles`.

---

## SQLAlchemy Mixin Reference

| Mixin | Columns | Behavior |
|-------|---------|----------|
| `UUIDMixin` | `id UUID PK` | `gen_random_uuid()` server default |
| `TimestampMixin` | `created_at`, `updated_at` | `now()` server default; `updated_at` updated on every write |
| `SoftDeleteMixin` | `deleted_at`, `deleted_by` | `is_deleted` hybrid property; `filter_deleted()` classmethod |
| `AuditMixin` | `created_by`, `updated_by` | FK to `users.id` |
| `WorkspaceScopedMixin` | `workspace_id` | FK to `workspaces.id` with index |
| `EventSourcedMixin` | `version INTEGER` | `__mapper_args__ = {"version_id_col": version}` → `StaleDataError` on conflict |

---

## Migration Sequence

```
001_initial_schema
  └── creates: users, workspaces, memberships, sessions,
               audit_events, execution_events, agent_namespaces
```

Future migrations (out of scope for this feature):
```
002_agent_registry
  └── creates: agent_profiles (with namespace_id FK, local_name, FQN unique constraint)
               visibility_agents JSONB, visibility_tools JSONB
```
