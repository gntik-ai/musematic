# Feature Specification: Workspaces Bounded Context

**Feature Branch**: `018-workspaces-bounded-context`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "Implement workspace CRUD, membership management, workspace roles, goals, super-context settings, isolation enforcement, and workspace subscription metadata."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Workspace CRUD and Data Isolation (Priority: P1)

An administrator or user creates a new workspace, providing a name, optional description, and display settings. The system creates the workspace and assigns the creating user as the workspace owner. The workspace is assigned a unique identifier that scopes all subsequent data operations. Every query within the workspace automatically filters by the workspace identifier, ensuring complete data isolation — users in workspace A never see data from workspace B. The workspace can be updated (name, description, settings), archived (soft-deleted, inaccessible but recoverable), restored from archive, and permanently deleted.

**Why this priority**: Workspaces are the foundational unit of multi-tenancy. No other feature in this context (membership, goals, visibility) functions without a workspace to attach to. This is the absolute minimum for a viable system.

**Independent Test**: Create a workspace via the API. Verify it returns a valid identifier. Update its name. List workspaces and verify only owned workspaces appear. Archive the workspace. Verify it no longer appears in standard listings. Restore it. Verify it reappears. Create a second workspace and verify data queries in workspace A return zero results from workspace B.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they create a workspace with a name and description, **Then** the workspace is created, the user is assigned as owner, and a workspace-created event is emitted
2. **Given** an existing workspace, **When** the owner updates its name or description, **Then** the changes are persisted and a workspace-updated event is emitted
3. **Given** an existing workspace, **When** the owner archives it, **Then** it is marked as archived, becomes inaccessible in standard listings, and a workspace-archived event is emitted
4. **Given** an archived workspace, **When** the owner restores it, **Then** it returns to active status and reappears in standard listings
5. **Given** an archived workspace, **When** the owner permanently deletes it, **Then** it and all associated data are removed (or marked for deferred cleanup)
6. **Given** two workspaces A and B, **When** a user queries data within workspace A, **Then** no records from workspace B appear in the results

---

### User Story 2 — Membership Management (Priority: P1)

A workspace owner or administrator adds other users to the workspace by email or user identifier, assigning them a workspace-level role (owner, admin, member, viewer). Members can be removed from the workspace. An existing member's role can be changed. The system lists all members of a workspace with their roles. Membership changes emit events that other bounded contexts can consume (e.g., to update session permissions, invalidate caches, or notify the user).

**Why this priority**: Membership is inseparable from workspace CRUD — a workspace without members is unusable. Role assignment governs access control for all subsequent operations. This must ship alongside workspace creation.

**Independent Test**: Create a workspace. Add a second user as a member with "member" role. List members — verify both owner and new member appear with correct roles. Change the member's role to "admin". List members again — verify the updated role. Remove the member. List members — verify only the owner remains. Verify events were emitted for each membership change.

**Acceptance Scenarios**:

1. **Given** a workspace with an owner, **When** the owner adds a user with role "member", **Then** the user becomes a member of the workspace and a membership-added event is emitted
2. **Given** a workspace member, **When** their role is changed from "member" to "admin", **Then** the role update is persisted and a membership-role-changed event is emitted
3. **Given** a workspace member, **When** they are removed from the workspace, **Then** they lose access to the workspace and a membership-removed event is emitted
4. **Given** a workspace, **When** an authorized user requests the member list, **Then** all members are returned with their roles, sorted by role then name
5. **Given** a workspace with one owner, **When** the owner attempts to remove themselves, **Then** the operation is rejected — a workspace must always have at least one owner
6. **Given** a user who is not a member of a workspace, **When** they attempt to access workspace data, **Then** the request is denied with an authorization error

---

### User Story 3 — Default Workspace Provisioning on User Activation (Priority: P1)

When a new user completes account activation (from the accounts bounded context, feature 016), the system automatically creates a personal default workspace for them. The user is set as the owner. This ensures every activated user has at least one workspace available immediately upon first login, without requiring any manual setup.

**Why this priority**: Without automatic provisioning, newly activated users land on an empty dashboard with no workspace. This is a critical onboarding step that must happen synchronously with activation.

**Independent Test**: Activate a new user account. Verify that a default workspace named "Personal" (or the user's display name + "'s Workspace") is created with the user as owner. Verify the user can immediately access this workspace after login. Verify the workspace has default settings applied.

**Acceptance Scenarios**:

1. **Given** a user whose account has just been activated, **When** the workspace system receives the activation event, **Then** a default workspace is created for the user with the user as owner
2. **Given** the default workspace creation, **When** it completes, **Then** a workspace-created event is emitted with metadata indicating it is a default workspace
3. **Given** a user with a configurable workspace limit, **When** the default workspace is created, **Then** it counts toward the user's workspace limit
4. **Given** the default workspace provisioning fails (e.g., database error), **When** the system retries, **Then** it is idempotent — if the workspace already exists, no duplicate is created

---

### User Story 4 — Workspace Goals (Priority: P2)

A workspace member creates goals within a workspace to define shared objectives for agents and humans working within that workspace. Goals have a title, description, status (open, in_progress, completed, cancelled), and a unique Goal ID (GID). The GID is a first-class correlation dimension — it connects all agent activity, execution traces, and workspace messages related to that objective. Goals can be listed, updated, and completed. When a goal status changes, an event is emitted.

**Why this priority**: Goals enhance collaboration by giving agents and humans a shared objective to rally around, but the workspace and its members can function without goals. This is an enrichment feature that builds on the workspace foundation.

**Independent Test**: Create a workspace and add a member. Create a goal with title "Q4 Revenue Analysis". Verify it gets a GID. List goals — verify it appears. Update its status to "in_progress". Verify the status change is persisted and an event is emitted. Complete the goal. Verify status is "completed" and event fires.

**Acceptance Scenarios**:

1. **Given** a workspace member, **When** they create a goal with title and description, **Then** the goal is created with a unique GID, status "open", and a goal-created event is emitted
2. **Given** an existing goal, **When** a member updates its status from "open" to "in_progress", **Then** the status change is persisted and a goal-status-changed event is emitted containing the GID
3. **Given** a workspace with multiple goals, **When** a member lists goals, **Then** all goals for that workspace are returned with their GIDs and current statuses
4. **Given** a goal in status "in_progress", **When** a member marks it "completed", **Then** the goal is completed and a goal-completed event is emitted
5. **Given** a goal, **When** a member cancels it, **Then** the goal status changes to "cancelled" and no further status changes are allowed

---

### User Story 5 — Workspace Visibility Grants (Priority: P2)

A workspace administrator configures workspace-wide visibility grants that define which agents and tools are visible to all agents operating within the workspace. By default (zero-trust), a new agent sees zero agents and zero tools. Workspace visibility grants override this default — every agent in the workspace sees the agents and tools listed in the workspace grant in addition to whatever is in their own per-agent visibility configuration. Grants are defined as lists of FQN patterns (exact match or regex). An administrator can update or remove workspace visibility grants.

**Why this priority**: Visibility grants are an important ergonomic optimization (one configuration point instead of N per-agent configurations) but agents can function with per-agent visibility alone. This enriches the workspace but is not a prerequisite for basic operation.

**Independent Test**: Create a workspace. Set a visibility grant with `visibility_agents: ["finance-ops:*"]` and `visibility_tools: ["data-tools:csv-reader"]`. Verify the grant is persisted. Query the effective visibility for an agent in the workspace — verify it includes the workspace grant patterns. Update the grant to add another pattern. Verify the update. Remove the grant. Verify the workspace returns to zero-trust default for workspace-level visibility.

**Acceptance Scenarios**:

1. **Given** a workspace with no visibility grant, **When** an admin sets visibility grants with agent and tool FQN patterns, **Then** the grant is persisted and a visibility-grant-updated event is emitted
2. **Given** a workspace with a visibility grant, **When** an agent in the workspace queries its effective visibility, **Then** the result includes the union of the workspace grant patterns and the agent's own per-agent patterns
3. **Given** a workspace with a visibility grant, **When** an admin updates the grant patterns, **Then** the new patterns replace the old ones and an event is emitted
4. **Given** a workspace with a visibility grant, **When** an admin removes the grant, **Then** the workspace returns to zero-trust default (no workspace-level visibility) and an event is emitted
5. **Given** a workspace grant with pattern `finance-ops:*`, **When** an agent queries visible agents, **Then** all agents matching `finance-ops:*` are included regardless of the agent's per-agent config

---

### User Story 6 — Workspace Limits and Settings (Priority: P3)

The platform enforces configurable workspace limits per user — a maximum number of workspaces a user can own (0 means unlimited). When a user attempts to create a workspace beyond their limit, the operation is rejected with a clear error. Workspace settings control workspace-level configuration such as super-context metadata (which agents, fleets, policies, and connectors are subscribed to the workspace).

**Why this priority**: Limits and advanced settings are governance/operational features that are important for production multi-tenancy but not required for the core workspace workflow. The system functions without limits (all users unlimited) and without subscription metadata.

**Independent Test**: Set a user's workspace limit to 2. Create two workspaces — verify both succeed. Attempt to create a third — verify it is rejected with a "workspace limit reached" error. Set the limit to 0 (unlimited). Create a third workspace — verify it succeeds. Update workspace settings to subscribe to a set of agents and fleets. Retrieve workspace settings — verify the subscriptions are present.

**Acceptance Scenarios**:

1. **Given** a user with a workspace limit of 2 who owns 2 workspaces, **When** they attempt to create a third, **Then** the operation is rejected with a "workspace limit reached" error
2. **Given** a user with a workspace limit of 0 (unlimited), **When** they create any number of workspaces, **Then** all creations succeed
3. **Given** a workspace, **When** an admin updates its settings with super-context subscriptions (agent FQNs, fleet IDs, policy IDs, connector IDs), **Then** the subscriptions are persisted
4. **Given** a workspace with settings, **When** a member retrieves workspace settings, **Then** all subscription metadata is returned
5. **Given** a workspace, **When** an owner changes the workspace limit for a member, **Then** the new limit applies to future workspace creation by that member

---

### Edge Cases

- What happens when a user is a member of a workspace that gets archived? The user retains their membership record but cannot access the workspace. If the workspace is restored, access resumes automatically.
- What happens when the last owner of a workspace is deleted (account archived)? The workspace becomes orphaned. An admin can reassign ownership via a platform-level operation. The system does not allow the last owner to voluntarily leave.
- What happens when a membership event fails to emit? The membership change is committed transactionally to the database. Event emission retries via the dead-letter queue mechanism. The event is eventually delivered.
- What happens when two admins update workspace visibility grants concurrently? The last write wins (timestamp-based). No locking is needed since visibility grants are replaced atomically.
- What happens when the default workspace provisioning event is received twice? The operation is idempotent — the system checks if a default workspace already exists for the user before creating one.
- What happens when a goal is created with a GID that matches an existing goal? GIDs are system-generated UUIDs — collisions are practically impossible and would be rejected by the uniqueness constraint.
- What happens when a user with workspace limit 2 has 2 workspaces and the limit is lowered to 1? Existing workspaces are not deleted. The user cannot create new workspaces until they archive one. The limit applies only to new creations.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide CRUD operations for workspaces: create, get (by ID), list (paginated, for current user), update, archive, restore, and permanent delete
- **FR-002**: Every workspace MUST have a unique identifier that scopes all data operations within it
- **FR-003**: All data queries within a workspace MUST automatically filter by workspace identifier, ensuring complete data isolation between workspaces
- **FR-004**: System MUST support adding, removing, and changing roles of workspace members
- **FR-005**: Workspace roles MUST include at minimum: owner, admin, member, viewer — with decreasing levels of access
- **FR-006**: A workspace MUST always have at least one owner — the system MUST reject removal of the last owner
- **FR-007**: System MUST emit events on all workspace lifecycle transitions: created, updated, archived, restored, deleted
- **FR-008**: System MUST emit events on all membership changes: added, role-changed, removed
- **FR-009**: When a new user account is activated, the system MUST automatically create a default workspace for that user with the user as owner
- **FR-010**: Default workspace provisioning MUST be idempotent — duplicate activation events produce at most one workspace
- **FR-011**: System MUST enforce configurable workspace limits per user, where 0 means unlimited
- **FR-012**: When a user exceeds their workspace limit, workspace creation MUST be rejected with a clear error message
- **FR-013**: System MUST support workspace goals with title, description, status (open, in_progress, completed, cancelled), and a unique Goal ID (GID)
- **FR-014**: Goal status changes MUST emit events containing the GID for correlation with agent activity and execution traces
- **FR-015**: System MUST support workspace-wide visibility grants: lists of agent FQN patterns and tool FQN patterns that apply to all agents in the workspace
- **FR-016**: Workspace visibility grants MUST combine with per-agent visibility configuration via union — agents see workspace-level grants plus their own per-agent grants
- **FR-017**: System MUST support workspace settings including super-context subscription metadata: subscribed agents, fleets, policies, and connectors
- **FR-018**: Workspace archival MUST be a soft delete — the workspace and its data are preserved but inaccessible until restored
- **FR-019**: Non-members MUST NOT be able to access any workspace data — the system MUST return an authorization error
- **FR-020**: System MUST support paginated listing of workspace members with role information

### Key Entities

- **Workspace**: The fundamental tenant container — has a name, description, status (active, archived), owner, settings, and creation timestamp. All data within the platform is scoped to a workspace.
- **Membership**: The relationship between a user and a workspace — associates a user with a workspace and assigns a role (owner, admin, member, viewer). A user can be a member of multiple workspaces.
- **WorkspaceGoal**: A shared objective within a workspace — has a title, description, status, and a unique Goal ID (GID) used for correlation across the platform.
- **WorkspaceVisibilityGrant**: The workspace-level override for agent visibility — defines lists of agent FQN patterns and tool FQN patterns that all agents in the workspace can see, layered on top of per-agent zero-trust defaults.
- **WorkspaceSettings**: Configuration metadata for a workspace — includes super-context subscription lists (agent FQNs, fleet IDs, policy IDs, connector IDs) and workspace-level preferences.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Workspace creation, update, archive, and restore operations complete in under 2 seconds
- **SC-002**: Data isolation is 100% enforced — zero cross-workspace data leakage in any query
- **SC-003**: Membership changes (add, remove, role change) complete in under 2 seconds and emit events within 5 seconds
- **SC-004**: Default workspace provisioning for newly activated users completes within 3 seconds of receiving the activation event
- **SC-005**: Workspace limits are enforced on 100% of creation attempts — no bypasses possible
- **SC-006**: Goal CRUD operations complete in under 2 seconds
- **SC-007**: Workspace visibility grant queries (computing effective visibility for an agent) return in under 1 second
- **SC-008**: All workspace and membership events are delivered reliably (with retry) — zero silent event loss
- **SC-009**: Paginated workspace member listing supports workspaces with up to 1,000 members without performance degradation
- **SC-010**: The workspace system handles up to 10,000 workspaces per platform instance without degradation in listing or query performance

## Assumptions

- The accounts bounded context (feature 016) emits an `accounts.user.activated` event on the `accounts.events` Kafka topic. The workspaces context consumes this event to trigger default workspace provisioning.
- User identity and authentication are handled by the auth bounded context (feature 014). The workspaces context receives the authenticated user identity via the request context (JWT claims, injected by middleware).
- Workspace roles (owner, admin, member, viewer) are workspace-scoped — they are separate from the platform-level RBAC roles defined in the auth bounded context. A user's workspace role governs what they can do within that workspace.
- The `WorkspaceScopedMixin` from the common models (feature 013) is used by all workspace-scoped entities. This mixin adds a `workspace_id` column and ensures all repository queries filter by it.
- Workspace visibility grants are stored in the workspaces tables. The registry bounded context (agent discovery) is responsible for reading these grants when computing effective visibility for an agent. The workspaces context provides a query interface for this.
- Super-context subscription metadata (subscribed agents, fleets, policies, connectors) is stored as structured data within workspace settings. The workspaces context does not validate that the referenced agent FQNs, fleet IDs, etc. actually exist — that validation is the responsibility of the consuming bounded context.
- Events are published to a `workspaces.events` Kafka topic using the canonical `EventEnvelope` from feature 013.
- Workspace permanent delete is an admin-only operation that schedules deferred cleanup of associated data. The actual cleanup is handled by a background worker, not synchronously during the delete request.
