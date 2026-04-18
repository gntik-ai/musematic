# Feature Specification: FQN Namespace System and Agent Identity

**Feature Branch**: `051-fqn-namespace-agent-identity`
**Created**: 2026-04-18
**Status**: Draft
**Requirements Traceability**: FR-422, FR-423, FR-424, FR-045 (mod)

## User Scenarios & Testing

### User Story 1 — Namespace Management and Agent FQN Registration (Priority: P1)

A platform operator creates organizational namespaces to group related agents. When registering an agent, the operator assigns it to a namespace and gives it a local name. The system combines these into a Fully Qualified Name (FQN) in the format `namespace:local_name` (e.g., `finance-ops:kyc-verifier`). The FQN is globally unique across the platform and becomes the agent's primary identifier for all downstream operations — policy attachment, certification binding, discovery, and event correlation.

**Why this priority**: FQN is the foundational addressing scheme referenced by every other platform subsystem (policies, trust, fleet orchestration, visibility). Without FQN, no other agent identity feature can function.

**Independent Test**: Create a namespace "test-ns", register an agent with local name "agent-a", verify that the FQN "test-ns:agent-a" is assigned and retrievable. Attempting to register another agent with the same local name in the same namespace is rejected. Registering the same local name in a different namespace succeeds.

**Acceptance Scenarios**:

1. **Given** a workspace with no namespaces, **When** an operator creates a namespace named "finance-ops" with a description, **Then** the namespace is persisted and appears in the namespace list for that workspace.
2. **Given** an existing namespace "finance-ops", **When** an operator registers an agent with local name "kyc-verifier", **Then** the agent receives FQN "finance-ops:kyc-verifier" and this FQN is returned in all agent responses.
3. **Given** an agent with FQN "finance-ops:kyc-verifier" exists, **When** an operator attempts to register another agent with local name "kyc-verifier" in the same namespace, **Then** the system rejects the request with a uniqueness violation error.
4. **Given** an existing namespace "finance-ops", **When** an operator attempts to create another namespace with the same name, **Then** the system rejects the request with a uniqueness violation error.
5. **Given** a namespace "finance-ops" with active agents, **When** an operator attempts to delete the namespace, **Then** the system rejects the deletion and lists the agents that must be removed or reassigned first.

---

### User Story 2 — Agent Resolution and Discovery by FQN (Priority: P1)

An operator or automated system looks up a specific agent using its FQN (e.g., `finance-ops:kyc-verifier`) and receives the full agent profile. Alternatively, an operator searches for all agents matching a pattern (e.g., `finance-ops:*` to find all agents in the finance-ops namespace, or `*:kyc-*` to find all KYC-related agents across namespaces). Pattern-based discovery supports namespace-level and cross-namespace queries.

**Why this priority**: FQN resolution is the primary use case for the addressing scheme — every policy binding, fleet assignment, and inter-agent reference depends on resolving an FQN to a concrete agent. Without resolution, the FQN is just a label.

**Independent Test**: Register three agents (`finance-ops:kyc-verifier`, `finance-ops:aml-checker`, `hr-ops:onboarding-agent`). Resolve `finance-ops:kyc-verifier` by FQN and verify the correct agent is returned. Query with pattern `finance-ops:*` and verify only the two finance-ops agents are returned.

**Acceptance Scenarios**:

1. **Given** an agent with FQN "finance-ops:kyc-verifier", **When** a user resolves the FQN "finance-ops:kyc-verifier", **Then** the system returns the full agent profile.
2. **Given** no agent with FQN "finance-ops:nonexistent", **When** a user resolves that FQN, **Then** the system returns a not-found error.
3. **Given** multiple agents across namespaces, **When** a user queries with pattern "finance-ops:*", **Then** only agents in the "finance-ops" namespace are returned.
4. **Given** multiple agents across namespaces, **When** a user queries with pattern "*:kyc-*", **Then** all agents whose local name starts with "kyc-" are returned regardless of namespace.
5. **Given** a workspace with 100 agents, **When** a user queries with a broad pattern, **Then** results are paginated and returned within acceptable response time.

---

### User Story 3 — Agent Manifest Enrichment (Priority: P2)

When registering or updating an agent, the operator provides enriched manifest fields: a purpose statement (what the agent does, minimum 50 characters), an optional approach description (how the agent accomplishes its purpose), and a role type classification (e.g., executor, observer, judge, enforcer). These fields enable trust evaluation, marketplace discovery, and operational dashboards to provide meaningful context about each agent.

**Why this priority**: Purpose and role type are required for trust certification and marketplace listing, but the core FQN addressing scheme works without them. They enrich the agent profile after the foundational identity is in place.

**Independent Test**: Create an agent with a purpose statement under 50 characters and verify the system rejects it. Create an agent with a valid purpose (50+ chars), approach, and role type. Verify all fields are persisted and returned in agent responses. Update the purpose and verify the change is reflected.

**Acceptance Scenarios**:

1. **Given** an agent registration form, **When** the operator submits a purpose with fewer than 50 characters, **Then** the system rejects the request with a validation error specifying the minimum length requirement.
2. **Given** an agent registration form, **When** the operator submits a valid purpose (50+ characters), an approach description, and role type "observer", **Then** the agent is created with all manifest fields persisted.
3. **Given** an existing agent, **When** the operator updates the purpose to a new value (50+ characters), **Then** the updated purpose is returned in subsequent queries.
4. **Given** an agent registration without an explicit role type, **When** the agent is created, **Then** the system assigns the default role type "executor".

---

### User Story 4 — Agent Visibility Configuration (Priority: P2)

An operator configures what each agent can see — both other agents and tools — through explicit visibility lists. By default, a newly registered agent has empty visibility: it can see zero other agents and zero tools (zero-trust posture). The operator grants visibility by specifying FQN patterns (exact match like `finance-ops:aml-checker` or wildcard like `finance-ops:*`). Workspace-level visibility grants can override per-agent defaults to provide broader access.

**Why this priority**: Zero-trust visibility is a core security posture (Constitution Principle IX). However, visibility enforcement is downstream — policies and the tool gateway enforce it. This story defines how visibility is *declared* on the agent, not how it is enforced.

**Independent Test**: Create an agent with no visibility grants. Verify it sees zero agents and zero tools. Add an agent visibility pattern `finance-ops:*`. Verify it now sees agents in the finance-ops namespace.

**Acceptance Scenarios**:

1. **Given** a newly registered agent with no visibility configuration, **When** querying what the agent can see, **Then** the response shows zero visible agents and zero visible tools.
2. **Given** an agent, **When** the operator adds an agent visibility pattern "finance-ops:*", **Then** the agent can discover agents matching that pattern.
3. **Given** an agent with visibility pattern "finance-ops:kyc-verifier", **When** the operator removes that pattern, **Then** the agent can no longer discover "finance-ops:kyc-verifier".
4. **Given** a workspace-level visibility grant for pattern "shared:*", **When** an agent in that workspace queries for visible agents, **Then** agents matching "shared:*" are included regardless of per-agent visibility configuration.

---

### User Story 5 — Backward-Compatible Agent Migration (Priority: P3)

When the FQN system is deployed, all existing agents that were registered before this feature automatically receive an FQN. The system creates a "default" namespace for each workspace and assigns existing agents to it, using their existing name as the local name. The migration runs without downtime and without requiring operator intervention. Existing workflows, policies, and references to agents by their original identifiers continue to work.

**Why this priority**: Migration is essential for production rollout but is a one-time operation. The FQN system must work for new agents first (US1-US4). Migration can happen after the core features are validated.

**Independent Test**: Pre-populate the system with 10 agents (no namespace). Run the migration. Verify all 10 agents now have FQNs in the "default" namespace. Verify all existing queries and references still work.

**Acceptance Scenarios**:

1. **Given** an existing workspace with 5 agents and no namespaces, **When** the migration runs, **Then** a "default" namespace is created for the workspace and all 5 agents are assigned FQNs using `default:{existing_name}`.
2. **Given** an existing agent with a name containing characters not valid for a local name, **When** the migration runs, **Then** the system sanitizes the name to produce a valid local name and logs the transformation.
3. **Given** an agent whose existing description is shorter than 50 characters, **When** the migration assigns it as the purpose, **Then** the system marks the agent for manual review rather than rejecting the migration.
4. **Given** the migration has completed, **When** an operator queries agents using the original identifier, **Then** the system still resolves to the correct agent (backward compatibility preserved).

---

### Edge Cases

- What happens when a namespace name contains invalid characters (e.g., spaces, special characters)? System validates and rejects with a descriptive error. Valid characters: lowercase letters, digits, hyphens. Must start with a letter.
- What happens when two agents in different namespaces have the same local name? This is valid — FQNs are unique per namespace:local_name combination.
- What happens when an FQN pattern matches zero agents? An empty result set is returned, not an error.
- What happens when the same agent is referenced by its pre-migration ID and its new FQN simultaneously? Both identifiers resolve to the same agent during the transition period.
- How does the system handle very large namespaces (1000+ agents)? Pagination is enforced on all list operations.
- What happens if the "default" namespace name is already taken when migration runs? The migration uses the existing namespace instead of creating a duplicate.

## Requirements

### Functional Requirements

- **FR-001**: System MUST support creating namespaces within a workspace, each with a unique name (case-insensitive, lowercase letters + digits + hyphens, 1-128 characters, starting with a letter).
- **FR-002**: System MUST support listing, retrieving, and deleting namespaces within a workspace. Deletion MUST be blocked if the namespace contains any agents.
- **FR-003**: System MUST assign every agent a Fully Qualified Name in the format `namespace:local_name`. The FQN MUST be globally unique (one agent per namespace:local_name combination).
- **FR-004**: System MUST support resolving a single agent by its exact FQN, returning the full agent profile or a not-found error.
- **FR-005**: System MUST support discovering agents by FQN pattern. Patterns support namespace-scoped wildcards (e.g., `finance-ops:*`) and cross-namespace wildcards (e.g., `*:kyc-*`).
- **FR-006**: System MUST validate that agent local names are unique within their namespace on registration and update.
- **FR-007**: System MUST require a purpose field on every agent, validated at minimum 50 characters on creation and update.
- **FR-008**: System MUST support an optional approach field (free-text) on every agent.
- **FR-009**: System MUST assign a role type to every agent. Valid role types: executor, observer, judge, enforcer, coordinator, planner. Default: executor.
- **FR-010**: System MUST support per-agent visibility configuration for agents and tools, expressed as lists of FQN patterns. Default: empty lists (zero visibility).
- **FR-011**: Workspace-level visibility grants MUST be combined (unioned) with per-agent visibility to compute effective visibility.
- **FR-012**: System MUST include the agent's FQN in all event payloads originating from that agent, as a first-class field in the event context.
- **FR-013**: System MUST provide a data migration that assigns FQNs to all existing agents without downtime, using a "default" namespace per workspace and deriving local names from existing agent names.
- **FR-014**: System MUST flag migrated agents with purpose shorter than 50 characters for manual review rather than rejecting the migration.
- **FR-015**: Local name validation: lowercase letters, digits, hyphens, 1-128 characters, starting with a letter. Same rules as namespace names.

### Key Entities

- **Namespace**: An organizational grouping for agents within a workspace. Has a unique name (per platform), belongs to a workspace, has a creator and description.
- **Agent (extended)**: An autonomous software entity registered in the platform. Now includes namespace membership, local name, computed FQN, purpose statement, approach description, role type classification, and visibility configuration (agent patterns + tool patterns).
- **Event Context (extended)**: The correlation metadata attached to every event in the system. Now includes the agent's FQN alongside existing fields (workspace_id, conversation_id, interaction_id, execution_id, fleet_id).

## Success Criteria

### Measurable Outcomes

- **SC-001**: Every agent in the system has a unique, human-readable FQN assigned within 1 second of registration.
- **SC-002**: Agent resolution by FQN returns the complete profile within 200ms under normal load (up to 10,000 agents per workspace).
- **SC-003**: FQN pattern discovery returns paginated results within 500ms for namespaces containing up to 1,000 agents.
- **SC-004**: 100% of existing agents are addressable by FQN after migration, with zero downtime and zero operator intervention.
- **SC-005**: All events produced after deployment include the originating agent's FQN in the event context.
- **SC-006**: Zero-trust visibility default is enforced: newly registered agents see zero agents and zero tools until explicitly configured.
- **SC-007**: Namespace operations (create, list, delete) complete within 1 second under normal load.

## Assumptions

- The existing agent profiles table is the source of truth for agent data. This feature extends it without replacing it.
- Namespace names are globally unique across the entire platform (not just per workspace) to ensure FQN global uniqueness.
- The FQN format `namespace:local_name` uses a single colon as the separator. The colon character is not permitted in namespace or local names.
- Visibility enforcement (checking visibility when an agent queries for other agents) is handled by the existing policy engine and tool gateway. This feature only defines the visibility *declaration* on the agent profile.
- The backfill migration is a one-time operation executed as part of the deployment. It is idempotent (running it twice produces the same result).
- Role type values are a fixed set in this version. Adding new role types requires a schema change.
