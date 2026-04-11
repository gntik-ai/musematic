# Research: Workspaces Bounded Context

**Feature**: 018-workspaces-bounded-context  
**Date**: 2026-04-11  
**Phase**: 0 — Pre-design research

---

## Decision 1: Workspace Data Isolation via WorkspaceScopedMixin

**Decision**: All workspace-scoped models inherit `WorkspaceScopedMixin` from `common/models/mixins.py` (feature 013). This mixin adds a `workspace_id: UUID` column and all repository queries include `WHERE workspace_id = :current_workspace_id` automatically. The `Workspace` model itself does NOT use the mixin (it is the workspace — it has its own `id`). `Membership`, `WorkspaceGoal`, `WorkspaceVisibilityGrant`, and `WorkspaceSettings` have explicit `workspace_id` FK columns.

**Rationale**: Constitution §IV mandates data isolation. The `WorkspaceScopedMixin` from feature 013 is the canonical mechanism for this. Workspace-internal entities (memberships, goals, settings) use explicit FKs back to the workspace table. Entities from other bounded contexts (agents, policies, etc.) use the mixin to scope themselves to a workspace.

**Alternatives considered**:
- Row-level security (RLS) in PostgreSQL: Higher operational complexity; mixin-level filtering is sufficient and matches existing patterns. Rejected.
- Separate databases per workspace: Extreme isolation but massive operational burden. Rejected — the platform targets 10,000 workspaces per instance.
- Schema-per-workspace: Same operational concern as separate databases. Rejected.

---

## Decision 2: Workspace Roles — Enum in Workspaces, Not Auth RBAC

**Decision**: Workspace roles (`owner`, `admin`, `member`, `viewer`) are defined as a `WorkspaceRole` enum in the workspaces bounded context. These are stored in the `Membership` model. They are **separate** from the platform-level RBAC roles defined in the auth bounded context (feature 014). A user can be a platform `admin` but a workspace `viewer`. Workspace role enforcement happens in the workspaces service layer — the service checks the requesting user's membership role before allowing workspace operations.

**Rationale**: Workspace roles govern workspace-scoped access. Platform RBAC roles govern platform-wide operations (e.g., managing signup modes, viewing all workspaces). Mixing these in a single system conflates two authorization domains. The spec assumptions confirm this separation.

**Alternatives considered**:
- Reuse auth RBAC roles for workspace access: Conflates platform and workspace scopes. A user who is a platform `member` might be a workspace `owner`. Rejected.
- ABAC (attribute-based): Overkill for 4 static roles. Rejected.

---

## Decision 3: Default Workspace Provisioning — Kafka Consumer for accounts.user.activated

**Decision**: The workspaces bounded context runs a Kafka consumer subscribed to `accounts.events` topic, filtering for `accounts.user.activated` events. On receiving this event, the workspaces service calls `create_default_workspace(user_id, display_name)`. The operation is idempotent — it checks if a default workspace already exists for the user (by `user_id` + `is_default=True` flag) before creating one.

**Rationale**: The spec assumes the accounts context emits `accounts.user.activated`. Constitution §III mandates Kafka for async event coordination. The workspace provisioning is a cross-context reaction — the accounts context should not know about workspaces. Kafka decouples this cleanly.

**Alternatives considered**:
- In-process service call from accounts to workspaces: Violates unidirectional dependency — accounts should not depend on workspaces. Rejected.
- HTTP webhook callback: Adds unnecessary network hop within the same monolith. Kafka is already the event backbone. Rejected.
- Synchronous provisioning during registration: Registration is in the accounts context; workspace creation is in the workspaces context. Cross-boundary sync calls are fragile. Rejected.

---

## Decision 4: Workspace Limits — Stored on User Profile or Workspace Settings?

**Decision**: Workspace limits are stored as a `max_workspaces` column on the accounts `User` model (feature 016). However, since we cannot modify another bounded context's tables (constitution §IV), the workspaces context reads this value via an in-process service interface: `accounts_service.get_user_workspace_limit(user_id) → int`. Default value: 0 (unlimited). The workspaces service counts existing owned workspaces and compares against the limit before creation.

**Rationale**: The workspace limit is a per-user attribute (not per-workspace). It belongs to the user's profile, which is owned by the accounts context. The workspaces context reads it via the established in-process service interface pattern (same as auth ↔ accounts in feature 016).

**Alternatives considered**:
- Store limit in the workspaces tables: The limit is about the user, not a workspace. This would create a shadow user record in the workspaces context. Rejected.
- Configuration-only (env var): Makes it the same for all users. Rejected — spec requires per-user configurability.
- Platform settings table: Per-user limits need user-level storage, not global config. Rejected.

---

## Decision 5: Workspace Settings — JSON Column vs. Separate Table

**Decision**: `WorkspaceSettings` is a **separate one-to-one table** (`workspaces_settings`) with a FK to `workspaces_workspaces`. Super-context subscription metadata (subscribed agent FQNs, fleet IDs, policy IDs, connector IDs) is stored as PostgreSQL `ARRAY` columns (one per subscription type). This avoids JSON querying complexity while keeping the schema explicit.

**Rationale**: Subscription lists are typed (UUIDs for fleet/policy/connector, strings for FQN patterns). Separate columns with PostgreSQL arrays allow straightforward indexing if needed. A JSON blob would require JSONB operators for every query. A separate table keeps the main workspace record lean.

**Alternatives considered**:
- JSONB column on workspace table: Flexible but loses type safety and makes queries harder. Rejected.
- Inline columns on workspace table: Too many columns on the main table. Rejected.
- Multiple join tables (one per subscription type): Over-normalized for simple lists. Rejected.

---

## Decision 6: Workspace Visibility Grants — Separate Table with Array Columns

**Decision**: `WorkspaceVisibilityGrant` is a **one-to-one table** (`workspaces_visibility_grants`) with FK to `workspaces_workspaces`. It has two `TEXT[]` array columns: `visibility_agents` (list of FQN patterns) and `visibility_tools` (list of FQN patterns). Updates are atomic (full replace). The workspaces context exposes a query interface `get_workspace_visibility_grant(workspace_id) → VisibilityGrant | None` for the registry bounded context to call.

**Rationale**: Visibility grants are atomically replaced (last write wins per spec edge case). PostgreSQL arrays store ordered lists of patterns efficiently. The registry context reads this via in-process service interface (constitution §IV — no cross-boundary DB access).

**Alternatives considered**:
- JSONB column on workspace table: Mixing visibility config with workspace metadata. Rejected.
- Separate rows per pattern: Over-normalized — the entire grant is replaced atomically. Rejected.
- Redis for visibility grants: Visibility grants change infrequently; PostgreSQL is the system of record. Redis cache is unnecessary complexity. Rejected.

---

## Decision 7: Goal Status State Machine

**Decision**: Goal statuses follow a simple state machine:
- `open` → `in_progress` → `completed`
- `open` → `cancelled`
- `in_progress` → `cancelled`
- `completed` and `cancelled` are terminal — no further transitions allowed.

Enforcement is in the service layer via a `VALID_GOAL_TRANSITIONS` dict (same pattern as feature 016 `state_machine.py`).

**Rationale**: The spec states "no further status changes are allowed" for cancelled goals. Completed goals are also terminal. This is a simple 4-state machine.

**Alternatives considered**:
- Allowing reopening of completed goals: Not in spec. Could be added later if needed. Rejected for now.
- Free-form status changes: The spec defines specific statuses with terminal states. Rejected.

---

## Decision 8: Kafka Topic — workspaces.events (New Topic)

**Decision**: All workspace events are published to a new `workspaces.events` Kafka topic. Event types: `workspaces.workspace.created`, `workspaces.workspace.updated`, `workspaces.workspace.archived`, `workspaces.workspace.restored`, `workspaces.workspace.deleted`, `workspaces.membership.added`, `workspaces.membership.role_changed`, `workspaces.membership.removed`, `workspaces.goal.created`, `workspaces.goal.status_changed`, `workspaces.visibility_grant.updated`. Key: `workspace_id`. Uses canonical `EventEnvelope` from feature 013.

**Rationale**: Constitution §III mandates Kafka for async events. The `workspace.goal` topic in the Kafka registry is for workspace goal *messages* (agent-to-agent coordination), not workspace context lifecycle events. A new `workspaces.events` topic follows the same pattern as `accounts.events` (feature 016) and `auth.events` (feature 014). **Note**: This topic needs to be added to the constitution Kafka Topics Registry.

**Alternatives considered**:
- Reuse `workspace.goal` topic: That topic serves a different purpose (goal messages between agents, not workspace lifecycle events). Rejected.
- One topic per event type: Too many topics for a single bounded context. Rejected.

---

## Decision 9: Workspace Permanent Delete — Deferred Cleanup

**Decision**: Permanent delete is an admin-only operation. The workspace status changes to `deleted` and the workspace is immediately invisible. A background worker (or scheduled task) later cleans up associated data (memberships, goals, settings, visibility grants). This avoids long-running synchronous deletes.

**Rationale**: A workspace may have thousands of associated records across multiple tables. Synchronous cascading delete would block the request. The deferred pattern keeps the API response fast (<2s per SC-001).

**Alternatives considered**:
- Synchronous CASCADE delete: Could block the API for seconds on large workspaces. Rejected.
- Never allow permanent delete: Spec includes permanent delete as a requirement (FR-001). Rejected.
- Immediate hard delete with ON DELETE CASCADE: Fast but irreversible and no audit trail. The `deleted` status preserves the record briefly for audit. Rejected.

---

## Decision 10: Membership Authorization Check — Service Layer Guard

**Decision**: Every workspace operation checks the requesting user's membership and role before proceeding. This is done in the service layer, not middleware. The service calls `repository.get_membership(workspace_id, user_id)` and checks the returned role against the required minimum role for the operation (e.g., `add_member` requires `admin` or `owner`). If no membership exists, the service raises `AuthorizationError`.

**Rationale**: Workspace-level authorization is context-specific business logic. It does not belong in generic middleware (which handles platform-level auth via JWT). The service layer already has the workspace context and can make granular decisions.

**Alternatives considered**:
- FastAPI dependency that checks workspace membership: Would need to be parameterized per route with required role — complex dependency chain. Service layer is cleaner. Rejected.
- Decorator-based authorization: Python decorators lose type safety and are harder to test. Rejected.

---

## Decision 11: Workspace Name Uniqueness — Per User, Not Global

**Decision**: Workspace names must be unique per owner (not globally unique). Two different users can have workspaces named "Personal". Uniqueness is enforced by a composite unique index on `(owner_id, name, status)` where `status != 'deleted'`.

**Rationale**: Global uniqueness would create naming conflicts across thousands of users. Per-owner uniqueness prevents a single user from having duplicate workspace names while allowing independent naming.

**Alternatives considered**:
- Globally unique names: Would require slugs or suffixes to avoid conflicts. Rejected.
- No uniqueness constraint: Users could create multiple workspaces with identical names, causing confusion. Rejected.
