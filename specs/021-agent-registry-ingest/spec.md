# Feature Specification: Agent Registry and Ingest

**Feature Branch**: `021-agent-registry-ingest`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "Implement agent package upload/validation pipeline, immutable revisions, registry metadata with maturity classification, OpenSearch indexing, Qdrant embedding storage, lifecycle state management, FQN system, zero-trust visibility, role types, and natural-language purpose/approach fields."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Namespace Management and Agent Registration (Priority: P1)

A platform administrator creates a namespace (e.g., "finance-ops") within a workspace to organize related agents. Once the namespace exists, an agent developer uploads an agent package containing a manifest file, configuration, and supporting assets. The system validates the package for correctness and security (rejecting malicious content such as path traversal attacks or oversized files), extracts the manifest, and registers the agent under the specified namespace with a Fully Qualified Name (e.g., "finance-ops:kyc-verifier"). The agent's profile includes mandatory fields: a natural-language purpose describing what the agent does, one or more declared role types (executor, planner, orchestrator, observer, judge, enforcer, or custom), and visibility configuration that defaults to zero visibility (can see no other agents or tools). Each upload creates an immutable revision with a unique content digest, preserving the complete history of all agent versions. The package itself is stored durably for later retrieval.

**Why this priority**: Without namespaces and agent registration, no other feature can function — agents cannot exist in the system, cannot be discovered, cannot be executed. This is the absolute foundation of the registry.

**Independent Test**: Create a namespace "test-ns" in a workspace. Upload a valid agent package with manifest declaring purpose, roles, and version. Verify the agent is registered with FQN "test-ns:test-agent" and status "draft". Verify an immutable revision is created with a content digest. Verify the package is stored and retrievable. Upload the same agent again with a new version — verify a second revision is created. Attempt to upload a package with path traversal in filenames — verify rejection with a specific security error. Attempt to upload a package missing the required "purpose" field — verify rejection with a validation error.

**Acceptance Scenarios**:

1. **Given** a workspace with no namespaces, **When** an administrator creates namespace "finance-ops", **Then** the namespace is created with a unique name scoped to the workspace
2. **Given** namespace "finance-ops" exists, **When** a developer uploads a valid agent package with manifest specifying local_name "kyc-verifier", **Then** the agent is registered with FQN "finance-ops:kyc-verifier", status "draft", and an immutable revision with SHA-256 digest
3. **Given** a valid agent upload, **When** the manifest declares purpose, approach, and role types, **Then** all fields are stored on the agent profile and the purpose is searchable
4. **Given** a package with `../../etc/passwd` in a file path, **When** the upload is processed, **Then** the upload is rejected with a security validation error before any data is stored
5. **Given** a package exceeding the maximum allowed size, **When** the upload is attempted, **Then** the upload is rejected with a clear size-limit error
6. **Given** a newly created agent, **When** no visibility configuration is provided, **Then** the agent defaults to zero visibility (empty agent and tool visibility lists)
7. **Given** namespace "finance-ops" already has agent "kyc-verifier", **When** a developer uploads a new version of the same agent, **Then** a new immutable revision is created; the previous revision remains accessible

---

### User Story 2 — Agent Discovery and FQN Resolution (Priority: P1)

A platform user or another system component needs to find agents — either by exact FQN, by FQN pattern matching, by name/purpose keyword search, or by semantic similarity to a description. The registry provides multiple discovery mechanisms: direct FQN resolution returns a single agent profile instantly; FQN pattern queries (e.g., "finance-ops:*") return all matching agents within a namespace; keyword searches match against agent name, purpose, and tags; and semantic search finds agents whose purpose is conceptually similar to a query even if the exact words differ. Discovery results are always filtered by the requesting agent's visibility configuration — an agent can only discover other agents it has been explicitly granted visibility to see. Human users (via the platform UI) see results filtered by their workspace memberships.

**Why this priority**: Discovery is how agents and users find each other. Without it, the registry is a write-only system. This is the primary read path and must ship alongside registration (US1).

**Independent Test**: Register three agents: "finance-ops:kyc-verifier", "finance-ops:risk-scorer", "hr-ops:onboarder". Resolve FQN "finance-ops:kyc-verifier" — verify exact match returns the profile. Query with pattern "finance-ops:*" — verify both finance-ops agents returned, hr-ops agent excluded. Search by keyword "verification" — verify kyc-verifier appears in results. Search semantically for "check customer identity documents" — verify kyc-verifier ranked highly even though the exact words differ. Configure agent A with visibility_agents ["finance-ops:*"] — query discovery as agent A — verify only finance-ops agents visible.

**Acceptance Scenarios**:

1. **Given** an agent registered with FQN "finance-ops:kyc-verifier", **When** a user resolves that exact FQN, **Then** the agent's full profile is returned within 200 milliseconds
2. **Given** multiple agents in namespace "finance-ops", **When** a user queries with FQN pattern "finance-ops:*", **Then** all agents in that namespace are returned
3. **Given** an agent with purpose "Verify KYC documents for compliance", **When** a user searches for "compliance verification", **Then** the agent appears in keyword search results
4. **Given** an agent with purpose "Verify KYC documents for compliance", **When** a user searches semantically for "check customer identity papers", **Then** the agent appears in the top results even though the exact words are different
5. **Given** agent A with visibility_agents ["finance-ops:*"], **When** agent A queries discovery, **Then** only agents matching the pattern are returned — agents outside that pattern are invisible
6. **Given** agent B with empty visibility_agents (zero-trust default), **When** agent B queries discovery, **Then** zero agents are returned

---

### User Story 3 — Lifecycle State Management (Priority: P1)

An agent moves through a defined lifecycle: draft (just uploaded), validated (passes automated checks), published (available for execution), disabled (temporarily unavailable), deprecated (being phased out), and archived (permanently removed from active use). Each transition is audited with the actor, timestamp, and reason. Only valid transitions are allowed — for example, an agent cannot move from "draft" directly to "deprecated" without first being published. When an agent is published, the system emits an event so other components can react. When deprecated, users of the agent are notified. The lifecycle state determines whether an agent is eligible for execution, discovery, and marketplace listing.

**Why this priority**: Lifecycle management is a safety mechanism. Without it, untested agents could be executed and deprecated agents could continue operating. This is essential for trust and governance from day one.

**Independent Test**: Register an agent (status: draft). Transition to "validated" — verify success and audit record. Transition to "published" — verify success, audit record, and event emitted. Attempt to transition from "draft" directly to "deprecated" — verify rejection with an error explaining the invalid transition. Transition published agent to "disabled" — verify it no longer appears in discovery for non-admin users. Transition to "deprecated" — verify event emitted. Transition to "archived" — verify the agent is no longer discoverable or executable but its revision history is preserved.

**Acceptance Scenarios**:

1. **Given** a newly registered agent in "draft" status, **When** an administrator transitions it to "validated", **Then** the status changes and an audit record captures the actor, timestamp, and reason
2. **Given** an agent in "validated" status, **When** transitioned to "published", **Then** the status changes, an event is emitted, and the agent becomes discoverable and executable
3. **Given** an agent in "draft" status, **When** a transition to "deprecated" is attempted, **Then** the transition is rejected with a clear error listing valid transitions from "draft"
4. **Given** a published agent, **When** it is deprecated, **Then** an event is emitted and the agent is marked with a deprecation notice visible in discovery results
5. **Given** an archived agent, **When** a user attempts to discover or execute it, **Then** it is not found in discovery and execution requests are rejected — but its revision history is still accessible via direct ID lookup

---

### User Story 4 — Maturity Classification (Priority: P2)

Each agent carries a maturity level (Level 0 through Level 3) that signals its trustworthiness and production readiness. Level 0 means unverified (the agent has no track record), Level 1 means basic compliance (meets minimum structural requirements), Level 2 means tested (has evaluation results proving quality), and Level 3 means certified (has passed formal trust certification). The maturity level can be declared in the agent's manifest or assessed automatically based on the agent's certification and evaluation history. Maturity is visible in discovery results and the marketplace, helping users choose agents appropriate for their risk tolerance.

**Why this priority**: Maturity is important for governance but not blocking — agents can be registered, discovered, and executed without maturity classification. It becomes critical once the trust and evaluation frameworks are integrated.

**Independent Test**: Upload an agent with maturity_level 0 in the manifest — verify it is stored. Manually update the maturity level to 2 — verify audit trail. Query agents filtered by maturity_level ≥ 2 — verify only agents at level 2 or above are returned. Upload an agent without maturity_level in the manifest — verify it defaults to Level 0.

**Acceptance Scenarios**:

1. **Given** an agent manifest declaring maturity_level 1, **When** the agent is registered, **Then** the maturity level is stored as Level 1
2. **Given** an agent with no maturity_level in its manifest, **When** it is registered, **Then** it defaults to Level 0
3. **Given** agents at maturity levels 0, 1, 2, and 3, **When** a user filters by maturity ≥ 2, **Then** only level 2 and 3 agents are returned
4. **Given** an agent's maturity level is updated, **When** the change occurs, **Then** an audit record captures the previous level, new level, actor, and reason

---

### User Story 5 — Visibility Configuration Management (Priority: P2)

A platform administrator configures which agents and tools a given agent can see and interact with. Visibility is managed through FQN pattern lists (exact matches or wildcard/regex patterns) stored on the agent profile. Additionally, workspace-level visibility grants can override individual agent defaults — granting broader visibility to all agents within a workspace. The platform supports a full spectrum from zero visibility (default) to full visibility (pattern "*") for orchestrator agents. Changes to visibility configuration take effect immediately for subsequent discovery queries.

**Why this priority**: Visibility management is security-critical but builds on top of the basic zero-trust default already established in US1. More nuanced configuration management can be incrementally added after the registry core is working.

**Independent Test**: Register agent A with default zero visibility. Set visibility_agents to ["finance-ops:*"]. Query discovery as agent A — verify only finance-ops agents visible. Add a workspace-level visibility grant for ["hr-ops:onboarder"]. Query discovery as agent A again — verify finance-ops agents + hr-ops:onboarder are all visible (union of per-agent and workspace-level grants). Set visibility_agents to ["*"] — verify all agents are visible.

**Acceptance Scenarios**:

1. **Given** an agent with visibility_agents ["finance-ops:kyc-*"], **When** the agent queries discovery, **Then** only agents matching "finance-ops:kyc-*" are returned
2. **Given** an agent with visibility_agents ["finance-ops:*"] and a workspace grant for ["hr-ops:*"], **When** the agent queries discovery, **Then** agents from both finance-ops and hr-ops namespaces are returned (union)
3. **Given** an administrator updates an agent's visibility_agents, **When** the next discovery query is made, **Then** the updated visibility is applied immediately
4. **Given** an orchestrator agent with visibility_agents ["*"], **When** it queries discovery, **Then** all published agents across all namespaces are returned

---

### User Story 6 — Agent Update and Revision History (Priority: P3)

A developer or administrator updates an agent's mutable metadata — display name, description, tags, approach text, visibility configuration, or role types — without uploading a new package. These changes do not create a new revision (revisions are immutable snapshots of the package content). The full revision history of an agent is accessible, showing all uploaded versions with their digests, upload timestamps, and manifest snapshots. Users can compare revisions to understand what changed between versions.

**Why this priority**: Metadata updates and revision browsing are valuable but not required for the core upload → discover → execute flow. They enhance the developer experience over the initial MVP.

**Independent Test**: Register an agent. Update its display_name and tags via PATCH — verify the profile changes but no new revision is created. Upload a new version of the same agent — verify a new revision is created. List revisions — verify both revisions are returned in chronological order with correct digests. Attempt to modify a revision's content — verify the operation is rejected (immutability enforced).

**Acceptance Scenarios**:

1. **Given** an agent profile, **When** an administrator patches the display_name and tags, **Then** the profile is updated and no new revision is created
2. **Given** an agent with two uploaded revisions, **When** a user lists revisions, **Then** both are returned in chronological order with digests, timestamps, and manifest data
3. **Given** an immutable revision, **When** any attempt to modify its content is made, **Then** the modification is rejected with an error
4. **Given** an agent with multiple revisions, **When** a user requests a specific revision by ID, **Then** the full manifest snapshot and metadata for that revision are returned

---

### Edge Cases

- What happens when a namespace name conflicts with an existing namespace in the same workspace? The creation is rejected with a duplicate-name error. Namespace names are unique per workspace.
- What happens when an FQN conflicts with an existing agent? If the agent already exists, the upload creates a new revision of the existing agent (not a duplicate). If the local_name is new within the namespace, a new agent is created.
- What happens when a package contains symlinks? Symlinks are rejected during validation to prevent symlink-based path traversal.
- What happens when the object storage service is temporarily unavailable during upload? The upload fails with a service-unavailable error. No partial state is persisted — the upload is atomic (all-or-nothing).
- What happens when the search index or embedding store is temporarily unavailable during registration? The agent is registered in the primary data store and a background retry mechanism ensures indexing eventually completes. The agent is discoverable by direct ID/FQN lookup immediately, but keyword and semantic search may be delayed.
- What happens when a visibility pattern is malformed (invalid regex)? The pattern is rejected at configuration time with a validation error, before it is stored. This prevents silent discovery failures.
- What happens when an agent with active executions is deprecated? The deprecation succeeds (it is a registry-level state change). Active executions continue to completion. New execution requests for the agent are rejected. An event is emitted so downstream systems can react.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support creating namespaces scoped to a workspace, with unique names per workspace
- **FR-002**: The system MUST accept agent package uploads as archive files, validate them for security threats (path traversal, symlinks, oversized files), structural correctness, and required manifest fields
- **FR-003**: The system MUST compute a SHA-256 content digest for each uploaded package and create an immutable revision record
- **FR-004**: The system MUST store uploaded agent packages in durable object storage for later retrieval
- **FR-005**: The system MUST register agents with a Fully Qualified Name (namespace:local_name) that is globally unique
- **FR-006**: The system MUST require a natural-language "purpose" field on every agent profile (mandatory) and support an optional "approach" field
- **FR-007**: The system MUST support agent role type declarations: executor, planner, orchestrator, observer, judge, enforcer, and custom (with description)
- **FR-008**: The system MUST default newly registered agents to zero visibility (empty visibility_agents and visibility_tools lists)
- **FR-009**: The system MUST support FQN resolution — given an exact FQN, return the agent profile within 200 milliseconds
- **FR-010**: The system MUST support FQN pattern matching in discovery queries using wildcard/regex syntax
- **FR-011**: The system MUST index agent metadata for keyword search (name, purpose, tags, role types)
- **FR-012**: The system MUST store agent description embeddings to enable semantic similarity search
- **FR-013**: The system MUST filter all discovery results by the requesting agent's visibility configuration, returning only agents the requester is authorized to see
- **FR-014**: The system MUST support workspace-level visibility grants that are unioned with per-agent visibility to determine effective visibility
- **FR-015**: The system MUST enforce a lifecycle state machine with valid transitions: draft → validated → published ↔ disabled, published → deprecated → archived
- **FR-016**: The system MUST audit every lifecycle transition with actor identity, timestamp, previous state, new state, and reason
- **FR-017**: The system MUST emit events when agents are created, published, and deprecated
- **FR-018**: The system MUST support maturity classification (Levels 0–3) with a default of Level 0 for agents without an explicit maturity declaration
- **FR-019**: The system MUST support updating mutable agent metadata (display name, tags, description, approach, visibility, role types) without creating a new revision
- **FR-020**: The system MUST preserve the complete revision history of every agent, with each revision being immutable and accessible by ID
- **FR-021**: The system MUST reject malformed visibility patterns (invalid regex) at configuration time with a clear validation error
- **FR-022**: The system MUST support listing namespaces and deleting empty namespaces within a workspace
- **FR-023**: The system MUST handle search/embedding service outages gracefully — agent registration succeeds and indexing completes via background retry
- **FR-024**: All registry endpoints MUST enforce workspace-scoped access control — users only see and manage agents in workspaces they belong to

### Key Entities

- **AgentNamespace**: An organizational container for agents within a workspace. Has a unique name per workspace, description, and ownership metadata. Groups related agents under a common prefix for FQN addressing.
- **AgentProfile**: The primary record for a registered agent. Contains the FQN (namespace:local_name), mandatory purpose text, optional approach text, declared role types, visibility configuration (agent and tool FQN pattern lists), lifecycle status, maturity level, tags, and display metadata. Linked to its namespace and workspace.
- **AgentRevision**: An immutable snapshot of an uploaded agent package version. Contains the SHA-256 digest, manifest data at upload time, version string, storage reference to the package in object storage, and upload metadata. Revisions are never modified or deleted.
- **AgentMaturityRecord**: Tracks changes to an agent's maturity level over time. Records the previous and new level, the assessment method (manifest-declared or system-assessed), and audit metadata.
- **ReasoningModeDescriptor**: Metadata about which reasoning modes an agent supports (e.g., chain-of-thought, tree-of-thought), declared in the manifest. Stored as part of the agent profile for discovery and execution planning.
- **LifecycleAuditEntry**: A record of a lifecycle state transition for an agent. Captures the previous state, new state, actor identity, timestamp, and reason. Used for governance reporting and accountability.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Valid agent packages are registered and an immutable revision is created within 10 seconds of upload completion
- **SC-002**: Invalid packages (security threats, missing fields, malformed content) are rejected with specific error details within 5 seconds — zero invalid packages reach storage
- **SC-003**: FQN resolution returns the agent profile within 200 milliseconds
- **SC-004**: Keyword search returns relevant agents within 1 second
- **SC-005**: Semantic search returns conceptually similar agents within 2 seconds
- **SC-006**: Visibility filtering is applied to 100% of discovery queries — zero unauthorized agents are ever returned
- **SC-007**: Every lifecycle transition is audited with complete actor, timestamp, and reason — zero unaudited transitions
- **SC-008**: All registered agents default to zero visibility until explicitly configured — zero agents start with open visibility
- **SC-009**: The system supports at least 10,000 registered agents without degradation in search or discovery performance
- **SC-010**: Test coverage of the agent registry and ingest system is at least 95%

## Assumptions

- The object storage service (MinIO, feature 004) is operational and accessible for storing agent packages. Packages are stored in a dedicated `agent-packages` bucket.
- The full-text search service (OpenSearch, feature 008) is operational for keyword indexing. The `marketplace-agents` index is created at application startup if it does not exist.
- The vector search service (Qdrant, feature 005) is operational for embedding storage. The `agent_embeddings` collection is created at startup if it does not exist. Embeddings are generated by calling a model provider (e.g., OpenAI embeddings API) with the agent's purpose + approach text.
- Workspace membership and authorization are provided by the workspaces bounded context (feature 018) via in-process service interface.
- Workspace-level visibility grants are managed by the workspaces bounded context (feature 018, `WorkspaceVisibilityGrant` entity). The registry reads these grants via the workspaces service interface.
- The maximum agent package size is 50 MB (configurable). Packages exceeding this limit are rejected at upload time.
- Manifest files use a standard format (YAML or JSON) with a defined schema. The schema is validated during upload and includes required fields: local_name, version, purpose, and at least one role type.
- Agent embeddings are generated asynchronously after registration to avoid blocking the upload response. The embedding may not be immediately available for semantic search (eventual consistency, typically within 30 seconds).
- Lifecycle state transitions are validated by a state machine in the service layer. The valid transition graph is: draft → validated → published ↔ disabled, published → deprecated → archived.
- The Kafka event topic for registry events is `registry.events` (using the canonical EventEnvelope from feature 013).
