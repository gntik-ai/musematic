# Feature Specification: Policy and Governance Engine

**Feature Branch**: `028-policy-governance-engine`  
**Created**: 2026-04-12  
**Status**: Draft  
**Input**: User description: "Implement policy CRUD, versioning, attachment to agents/fleets/workspaces, governance compiler (human-readable → machine-usable bundles), tool gateway with deterministic enforcement, memory write gate, maturity-gated access rules, and purpose-bound authorization checks."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Policy Lifecycle Management (Priority: P1)

A platform administrator needs to define governance policies that control what agents can do, what tools they can access, and what data they can write. The administrator creates a new policy through the platform, specifying rules such as "agents in the finance namespace may only call the calculator and spreadsheet tools" or "agents below maturity level 3 cannot perform external API calls." Each policy has a name, description, scope type (global, deployment, workspace, or agent), and a set of rules. When the administrator saves the policy, the system creates a versioned record so that previous policy definitions are never lost. The administrator can update the policy later, producing a new version while preserving the previous one for auditing. The administrator can list all policies, filter by scope type, and view the version history for any policy.

**Why this priority**: Without policies in the system, none of the enforcement mechanisms (tool gateway, memory write gate, maturity gates) have anything to enforce. Policy CRUD is the foundation all other stories depend on.

**Independent Test**: Create a policy via the API with a name, scope type "workspace", and a set of rules. Retrieve it — verify all fields are returned. Update the policy — verify a new version is created and the old version is retrievable. List policies with scope filter — verify correct filtering. Delete (archive) a policy — verify it no longer appears in active listings but remains in version history.

**Acceptance Scenarios**:

1. **Given** an administrator, **When** they create a policy with name, description, scope type, and rules, **Then** the policy is persisted with version 1 and a unique identifier
2. **Given** an existing policy at version 3, **When** the administrator updates the rules, **Then** a version 4 is created, version 3 remains accessible, and the policy's "current version" pointer advances to 4
3. **Given** 20 policies with mixed scope types, **When** the administrator lists policies filtered by scope "workspace", **Then** only workspace-scoped policies are returned
4. **Given** a policy with 5 versions, **When** the administrator requests the version history, **Then** all 5 versions are returned in chronological order with timestamps and change summaries
5. **Given** a policy attached to 3 agents, **When** the administrator archives the policy, **Then** the policy is marked inactive, existing attachments are flagged for review, and the policy no longer appears in active listings

---

### User Story 2 — Policy Attachment and Composition (Priority: P1)

A platform operator needs to attach policies to specific agents, fleets, workspaces, or define them as global defaults. When an agent executes, the system must resolve which policies apply by composing policies from multiple levels: global → deployment → workspace → agent → execution-specific. The composition follows a deterministic precedence order where more specific scopes override more general ones. For example, a global policy might allow all agents to use up to 10 tools, but a workspace-scoped policy narrows it to 5 tools for that workspace, and an agent-specific policy further restricts it to 3 named tools. The operator can view the "effective policy" for any agent — the merged result of all applicable policies — to understand exactly what rules govern that agent.

**Why this priority**: Attachment and composition are required for policies to take effect. The deterministic composition model is the core intellectual contribution of the governance system — without it, policies are just inert records.

**Independent Test**: Create a global policy, a workspace policy, and an agent-specific policy. Attach all three. Query the effective policy for the agent — verify the composition correctly merges rules with agent-specific overriding workspace which overrides global. Remove the agent-specific attachment — verify the effective policy falls back to workspace + global composition.

**Acceptance Scenarios**:

1. **Given** a policy, **When** the operator attaches it to an agent revision, **Then** the attachment is recorded with the policy version, target type, and target identifier
2. **Given** policies at global, workspace, and agent scopes, **When** the system resolves the effective policy for an agent, **Then** the composition follows global → deployment → workspace → agent precedence, with more specific scopes overriding less specific ones
3. **Given** an effective policy query, **When** the resolved policy is returned, **Then** it includes the merged rules, the provenance of each rule (which policy source it came from), and any conflicts detected
4. **Given** a policy attached to an agent at version 2, **When** the policy is updated to version 3, **Then** the attachment continues to reference version 2 until explicitly upgraded by the operator
5. **Given** conflicting rules between scopes (e.g., workspace allows tool X, agent denies tool X), **When** the system resolves the effective policy, **Then** the more specific scope (agent) wins deterministically and the conflict is logged

---

### User Story 3 — Tool Gateway Enforcement (Priority: P1)

When an agent attempts to invoke a tool (whether native, MCP, or A2A-proxied), the tool gateway intercepts the request and validates it against the agent's effective policy. The gateway checks: (1) Does the agent have permission to use this tool? (2) Is the invocation consistent with the agent's declared purpose? (3) Is the agent within its budget allocation? (4) Does any safety rule prohibit this specific invocation? If all checks pass, the tool invocation proceeds and a "gate allowed" event is emitted. If any check fails, the invocation is blocked, a "gate blocked" event is emitted, and the reason is recorded as a BlockedActionRecord with full context: which policy rule caused the block, which component requested it, and the outcome.

**Why this priority**: The tool gateway is the primary enforcement point — the platform constitution mandates that all enforcement happens through structured policies and the tool gateway. Without it, policies are defined but not enforced.

**Independent Test**: Configure an agent with a policy that allows tool A but denies tool B. Invoke tool A — verify it proceeds and a "gate allowed" event is emitted. Invoke tool B — verify it is blocked, a "gate blocked" event is emitted, and a BlockedActionRecord is persisted with the blocking policy rule reference. Invoke tool A with a purpose mismatch — verify it is blocked on purpose check.

**Acceptance Scenarios**:

1. **Given** an agent with an effective policy allowing tool "calculator", **When** the agent invokes "calculator", **Then** the invocation proceeds and a "gate allowed" event is emitted
2. **Given** an agent with an effective policy denying tool "external-api", **When** the agent invokes "external-api", **Then** the invocation is blocked, a "gate blocked" event is emitted, and a BlockedActionRecord is created
3. **Given** an agent with a purpose-bound policy for "financial-analysis", **When** the agent invokes a tool for a different purpose, **Then** the invocation is blocked with reason "purpose mismatch"
4. **Given** an agent that has exhausted its budget allocation, **When** it attempts to invoke any tool, **Then** the invocation is blocked with reason "budget exceeded"
5. **Given** a blocked invocation, **When** the BlockedActionRecord is queried, **Then** it includes the policy rule ID, the tool requested, the agent identity, the component that performed the check, the timestamp, and the block reason
6. **Given** an MCP or A2A tool invocation, **When** the gateway processes it, **Then** the same policy validation, visibility checks, and output sanitization apply as for native tools

---

### User Story 4 — Governance Compiler (Priority: P2)

A platform architect needs to transform human-readable policy definitions into machine-usable enforcement bundles. The governance compiler takes a set of policy sources (the effective policy for an agent or execution), validates them for internal consistency (no contradictory rules, no impossible constraints), and produces a typed enforcement bundle. The bundle contains: resolved permission lists, capability constraints per maturity level, purpose-scoped rules, budget limits, and safety invariants. The compiler also produces task-scoped shards — subsets of the bundle optimized for a specific execution step — so that the runtime only needs to evaluate relevant rules at each point. A validation manifest accompanies each bundle listing all source policies, their versions, and any warnings.

**Why this priority**: The compiler bridges the gap between human-authored policies and machine-enforced rules. It is needed for efficient runtime enforcement but can initially be replaced by direct policy evaluation (slower but functional), making it P2.

**Independent Test**: Provide the compiler with 3 policies (global, workspace, agent) that overlap. Verify the output bundle contains correctly merged rules. Provide policies with a contradiction (one allows, another denies the same tool) — verify the compiler resolves it per precedence and includes a warning. Request a task-scoped shard for a "data retrieval" step — verify only relevant rules are included. Provide an invalid policy (e.g., budget limit of -1) — verify the compiler rejects it with a validation error.

**Acceptance Scenarios**:

1. **Given** 3 overlapping policies, **When** the compiler produces a bundle, **Then** the bundle contains the deterministically merged result with provenance for each rule
2. **Given** contradictory rules between scopes, **When** the compiler resolves them, **Then** the more specific scope wins, and a "rule_conflict_resolved" warning is included in the validation manifest
3. **Given** a compiled bundle, **When** a task-scoped shard is requested for step type "tool_invocation", **Then** only permission rules, tool constraints, and budget limits relevant to tool invocations are included
4. **Given** an invalid policy (negative budget, empty permission list), **When** the compiler processes it, **Then** it rejects the input with a structured validation error before producing any bundle
5. **Given** a successfully compiled bundle, **When** the validation manifest is inspected, **Then** it lists all source policy IDs, their versions, compilation timestamp, and any warnings generated

---

### User Story 5 — Memory Write Gate (Priority: P2)

When an agent attempts to write to long-term memory (vector store, knowledge graph, or any persistent memory layer), the memory write gate intercepts the request. The gate checks: (1) Is the agent authorized to write to this memory namespace? (2) Has the agent exceeded its write rate limit? (3) Does the proposed write contradict existing entries flagged as high-confidence? (4) Does the write comply with retention policies for this namespace? (5) Is the target namespace within the agent's allowed namespace scope? If all checks pass, the write proceeds. If any check fails, the write is blocked and a BlockedActionRecord is created with the specific gate rule that triggered the block.

**Why this priority**: The memory write gate protects the integrity of shared knowledge. While important, it can be implemented after the tool gateway since tool invocations are more frequent and higher risk than memory writes.

**Independent Test**: Configure an agent with a policy allowing writes to namespace "finance" but not "hr". Attempt a write to "finance" — verify it proceeds. Attempt a write to "hr" — verify it is blocked. Perform 10 rapid writes — verify rate limiting kicks in. Attempt a write that contradicts a high-confidence existing entry — verify contradiction check blocks it.

**Acceptance Scenarios**:

1. **Given** an agent authorized for namespace "finance", **When** it writes to "finance", **Then** the write proceeds and a "gate allowed" event is emitted
2. **Given** an agent not authorized for namespace "hr", **When** it writes to "hr", **Then** the write is blocked with reason "namespace unauthorized"
3. **Given** an agent with a rate limit of 10 writes per minute, **When** it exceeds the limit, **Then** subsequent writes are blocked until the window resets, with a BlockedActionRecord citing "rate limit exceeded"
4. **Given** a proposed write that contradicts a high-confidence existing entry in the same namespace, **When** the gate evaluates it, **Then** the write is blocked with reason "contradiction detected" and a reference to the conflicting entry
5. **Given** a namespace with a 90-day retention policy, **When** a write is accepted, **Then** the retention metadata is attached to the entry for future enforcement by the cleanup process

---

### User Story 6 — Maturity-Gated Access and Purpose-Bound Authorization (Priority: P3)

The platform restricts certain capabilities based on an agent's maturity level. A newly registered agent (maturity level 0) may only access basic tools and write to its own namespace. As the agent's maturity level increases through certification and evidence accumulation (managed by the trust bounded context), it gains access to more capabilities: level 1 allows external API calls, level 2 allows cross-namespace memory access, level 3 allows fleet coordination. Additionally, agents operate within a declared purpose scope — an agent registered for "customer support" cannot invoke tools designated for "financial trading" even if its maturity level would otherwise allow it. The platform enforces both maturity gates and purpose-bound authorization at every enforcement point (tool gateway, memory write gate).

**Why this priority**: Maturity gates and purpose-bound authorization are advanced governance features that layer on top of the basic policy and enforcement infrastructure. They provide defense-in-depth but are not required for the system to function at a basic level.

**Independent Test**: Register an agent at maturity level 0. Attempt to invoke an "external API" tool that requires level 1 — verify blocked. Promote the agent to level 1 — verify the tool invocation now succeeds. Declare the agent's purpose as "customer support". Attempt to invoke a "trading" tool — verify blocked with "purpose mismatch." Attempt a "support ticket" tool — verify allowed.

**Acceptance Scenarios**:

1. **Given** an agent at maturity level 0, **When** it attempts to use a capability requiring level 2, **Then** the invocation is blocked with reason "maturity level insufficient" and the required level is included in the response
2. **Given** an agent that is promoted from level 1 to level 2, **When** the maturity gate evaluates a level-2 capability request, **Then** the invocation is now allowed without any policy change needed
3. **Given** maturity gate rules, **When** the administrator queries which capabilities each level unlocks, **Then** a structured list is returned showing the progressive capability tiers
4. **Given** an agent with purpose scope "data-analysis", **When** it invokes a tool designated for purpose "marketing-automation", **Then** the invocation is blocked with reason "purpose mismatch"
5. **Given** an agent with purpose scope "data-analysis", **When** it invokes a tool designated for "data-analysis" or "general-purpose", **Then** the invocation is allowed

---

### User Story 7 — Visibility-Aware Discovery Enforcement (Priority: P3)

When an agent queries the registry to discover available agents or tools, the policy engine filters results at the discovery level. An agent's visibility configuration defines FQN patterns (exact match or regex) for which agents and tools it can see. The registry query API applies these patterns before returning results, ensuring that agents cannot even discover the existence of resources outside their visibility scope. This is a security posture requirement aligned with the zero-trust default visibility principle — agents see nothing by default and must be explicitly granted visibility.

**Why this priority**: Visibility enforcement is a security hardening feature. The platform functions without it (agents simply see all registered agents/tools), but it violates the zero-trust principle. It layers on top of the core tool gateway enforcement.

**Independent Test**: Register agent A with visibility allowing `finance-ops:*` and agent B with visibility allowing `marketing:*`. Query the registry as agent A — verify only `finance-ops:*` agents/tools appear. Query as agent B — verify only `marketing:*` appear. Register a new agent in `finance-ops` namespace — verify agent A can discover it but agent B cannot.

**Acceptance Scenarios**:

1. **Given** an agent with `visibility_agents: ["finance-ops:*"]`, **When** it queries the registry, **Then** only agents matching the pattern are returned
2. **Given** an agent with no visibility configuration (default), **When** it queries the registry, **Then** zero agents and zero tools are returned (zero-trust default)
3. **Given** an agent with `visibility_tools: ["calculator", "spreadsheet"]`, **When** it queries for tools, **Then** only "calculator" and "spreadsheet" are returned regardless of how many tools exist
4. **Given** workspace-level visibility grants, **When** the agent's visibility is evaluated, **Then** the union of per-agent and workspace-level visibility patterns is used
5. **Given** visibility filtering, **When** the registry API returns results, **Then** the filtering occurs within the query itself, not as a post-filter on the full result set

---

### User Story 8 — Tool Output Sanitization (Priority: P3)

When a tool execution returns its output, the tool gateway scans the output for sensitive patterns before it is injected into the agent's context. The sanitizer detects known secret formats: API keys (patterns like `Bearer`, `sk-`, `key-`), JWT tokens, passwords, database connection strings, and other credential patterns. Detected secrets are replaced with `[REDACTED:secret_type]` markers. Every redaction event is logged for security audit purposes. This is a defense-in-depth measure — the primary control is never injecting secrets into the LLM context, but the sanitizer catches leaks from tool outputs.

**Why this priority**: Output sanitization is a defense-in-depth security layer. The primary secret isolation mechanism (runtime injection bypassing the LLM context) handles the common case. This story handles the edge case of secrets appearing in tool outputs, making it a P3 hardening feature.

**Independent Test**: Invoke a tool that returns output containing `Bearer abc123token` and a JDBC connection string. Verify the output is sanitized to `[REDACTED:bearer_token]` and `[REDACTED:connection_string]`. Verify a redaction audit log entry is created for each redaction. Invoke a tool with clean output — verify no redaction occurs and no audit entry is created.

**Acceptance Scenarios**:

1. **Given** tool output containing "Bearer sk-abc123", **When** the sanitizer processes it, **Then** it is replaced with "[REDACTED:api_key]"
2. **Given** tool output containing a JWT token (`eyJ...`), **When** the sanitizer processes it, **Then** it is replaced with "[REDACTED:jwt_token]"
3. **Given** tool output containing a connection string (`postgres://user:pass@host/db`), **When** the sanitizer processes it, **Then** it is replaced with "[REDACTED:connection_string]"
4. **Given** any redaction event, **When** it is logged, **Then** the audit record includes the agent identity, tool name, secret type detected, timestamp, and the execution context (but NOT the actual secret value)
5. **Given** tool output with no secrets, **When** the sanitizer processes it, **Then** the output is returned unmodified and no audit entry is created
6. **Given** tool output with multiple secrets of different types, **When** the sanitizer processes it, **Then** each secret is independently detected and replaced with the appropriate type marker

---

### Edge Cases

- What happens when a policy attachment references a policy version that no longer exists? The system stores version references as immutable snapshots. Archived policy versions are never deleted — they are retained for audit. If a referenced version is corrupted (data integrity failure), the system falls back to the latest known-good version and emits a "policy_version_fallback" warning event.
- What happens when the governance compiler encounters a circular dependency between policies? Policies are scoped hierarchically (global → deployment → workspace → agent → execution). Circular dependencies are impossible in this model because composition is strictly top-down. If a user attempts to create a self-referencing policy (a policy that references itself), the validation step rejects it.
- What happens when the tool gateway cannot determine the effective policy for an agent? If policy resolution fails (e.g., database unavailable), the gateway defaults to "deny all" — no tool invocations are permitted. A critical alert is raised and a BlockedActionRecord is created with reason "policy resolution failure."
- What happens when the memory write gate receives a write to a namespace that does not exist? The write is blocked with reason "namespace not found." Agents cannot create namespaces implicitly through writes — namespace creation is an explicit administrative action.
- What happens when the sanitizer encounters an unknown pattern that looks like a secret but does not match known formats? The sanitizer only redacts known, well-defined patterns to avoid false positives that would corrupt legitimate tool output. Unknown suspicious patterns are logged as "potential_secret_unredacted" warnings for security team review but are not redacted.
- What happens when multiple policies at the same scope level apply to the same target? Policies at the same scope level are composed additively — all rules from all policies at that level are collected. If rules within the same scope contradict each other, the most restrictive interpretation wins (deny takes precedence over allow at the same level).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support creating policies with a name, description, scope type (global, deployment, workspace, agent), and a set of typed rules
- **FR-002**: The system MUST version all policy changes, creating a new immutable version on each update while preserving all previous versions
- **FR-003**: The system MUST support listing policies with filtering by scope type, status (active/archived), and search by name
- **FR-004**: The system MUST support archiving policies, which marks them inactive while retaining all versions for audit
- **FR-005**: The system MUST support attaching a specific policy version to a target entity (agent revision, fleet, workspace, or global scope)
- **FR-006**: The system MUST resolve the effective policy for any agent by composing policies across scopes in deterministic precedence order: global → deployment → workspace → agent → execution
- **FR-007**: The system MUST include provenance information in the effective policy — which source policy and version each rule originated from
- **FR-008**: The system MUST detect and log rule conflicts during composition, resolving them deterministically (more specific scope wins)
- **FR-009**: The tool gateway MUST intercept every tool invocation (native, MCP, and A2A) and validate it against the agent's effective policy before allowing execution
- **FR-010**: The tool gateway MUST validate tool invocations against four dimensions: permission (is the tool allowed?), purpose (is the invocation consistent with the agent's declared purpose?), budget (is the agent within allocation?), and safety (does any safety rule prohibit this?)
- **FR-011**: The tool gateway MUST emit a "gate allowed" event for permitted invocations and a "gate blocked" event for denied invocations
- **FR-012**: The system MUST persist a BlockedActionRecord for every blocked invocation, including the blocking policy rule, the requesting component, the agent identity, the tool requested, and the block reason
- **FR-013**: The governance compiler MUST transform a set of policy sources into a typed enforcement bundle containing resolved permissions, capability constraints, purpose rules, budget limits, and safety invariants
- **FR-014**: The governance compiler MUST validate policy inputs for internal consistency and reject invalid policies with structured error messages
- **FR-015**: The governance compiler MUST produce task-scoped shards — subsets of the full bundle optimized for specific execution step types
- **FR-016**: The governance compiler MUST produce a validation manifest listing all source policies, their versions, compilation timestamp, and any warnings
- **FR-017**: The memory write gate MUST intercept memory write operations and validate them against namespace authorization, rate limits, contradiction checks, retention policies, and namespace scope restrictions
- **FR-018**: The memory write gate MUST block writes that contradict high-confidence existing entries in the same namespace
- **FR-019**: The memory write gate MUST enforce per-agent write rate limits
- **FR-020**: The system MUST restrict agent capabilities based on maturity level, where higher levels progressively unlock more capabilities
- **FR-021**: The system MUST enforce purpose-bound authorization — agents cannot invoke tools outside their declared purpose scope
- **FR-022**: The registry discovery API MUST filter results by the requesting agent's visibility configuration (FQN patterns) before returning
- **FR-023**: Agents with no visibility configuration MUST see zero agents and zero tools (zero-trust default)
- **FR-024**: Visibility filtering MUST occur within the query itself, not as a post-filter on the full result set
- **FR-025**: The tool output sanitizer MUST detect and replace known secret patterns (API keys, JWT tokens, passwords, connection strings) with `[REDACTED:secret_type]` markers before tool output enters the agent context
- **FR-026**: The tool output sanitizer MUST log every redaction event for security audit, including agent identity, tool name, and secret type — but never the actual secret value
- **FR-027**: All policy-related events MUST be emitted to a dedicated event topic for downstream consumption by audit and analytics systems

### Key Entities

- **Policy**: A named governance document with a scope type (global/deployment/workspace/agent), description, status (active/archived), and a reference to its current version. Contains a set of typed enforcement rules.
- **PolicyVersion**: An immutable snapshot of a policy at a point in time. Includes the full rule set, version number, creation timestamp, and change summary. Previous versions are never modified or deleted.
- **PolicyAttachment**: A binding between a specific policy version and a target entity (agent revision, fleet, workspace, or global scope). Includes the attachment timestamp and the operator who created it.
- **CapabilityConstraint**: A rule within a policy that restricts or allows specific capabilities. Can be scoped by tool name/pattern, action type, or resource category.
- **EnforcementRule**: A single rule within a policy specifying a permission (allow/deny), conditions under which it applies, and its enforcement behavior (block, warn, audit-only).
- **PurposeScope**: A declaration of an agent's intended purpose (e.g., "financial-analysis", "customer-support"). Tools and capabilities are tagged with compatible purposes. Purpose mismatches trigger enforcement.
- **MaturityGateRule**: A rule that maps capability tiers to minimum maturity levels. Defines which capabilities are unlocked at each level of agent maturity.
- **BlockedActionRecord**: A persistent record of a denied action. Contains the policy rule that caused the block, the requesting agent, the requested action, the enforcement component (tool gateway or memory write gate), the timestamp, and the block reason.
- **EnforcementBundle**: The compiled output of the governance compiler. Contains resolved permissions, constraints, purpose rules, budget limits, and safety invariants — ready for runtime evaluation.
- **ValidationManifest**: Metadata accompanying a compiled bundle. Lists all source policies, their versions, compilation timestamp, and any warnings or conflicts detected during compilation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Policy creation, update, and retrieval operations complete within 500 milliseconds
- **SC-002**: The effective policy for any agent is resolved within 100 milliseconds, including composition across all applicable scopes
- **SC-003**: Tool gateway enforcement adds no more than 10 milliseconds of latency to tool invocations when using a pre-compiled enforcement bundle
- **SC-004**: 100% of tool invocations (native, MCP, and A2A) pass through the tool gateway — no bypass paths exist
- **SC-005**: 100% of blocked actions produce a BlockedActionRecord with complete context (policy rule, agent, tool, reason, timestamp)
- **SC-006**: The governance compiler processes a bundle of 20 overlapping policies within 2 seconds
- **SC-007**: The memory write gate evaluates writes within 20 milliseconds, including rate limit and contradiction checks
- **SC-008**: Visibility-filtered registry queries return results within the same latency bounds as unfiltered queries (no measurable degradation)
- **SC-009**: The tool output sanitizer processes outputs of up to 100KB within 5 milliseconds
- **SC-010**: Test coverage of the policy and governance engine is at least 95%
- **SC-011**: The system defaults to "deny all" when policy resolution fails — zero permissive failures

## Assumptions

- The auth bounded context (feature 014) provides user identity, roles, and session validation. The policy engine consumes these but does not manage them.
- The agent registry (feature 021) manages agent profiles, maturity levels, and FQN resolution. The policy engine queries maturity levels and FQN patterns but does not modify them.
- The trust bounded context manages maturity level promotion/demotion. The policy engine enforces rules based on the current maturity level as provided by the trust context.
- The memory bounded context (feature 023) provides the memory write operations that the write gate intercepts. The gate is implemented as a middleware/interceptor within the memory service's write path.
- Budget tracking is managed by the reasoning engine (feature 011) via Redis. The tool gateway queries remaining budget but does not manage budget allocation.
- The connector plugin framework (feature 025) and MCP/A2A gateways route tool invocations through the tool gateway — they do not implement separate enforcement.
- Event infrastructure is available for emission (dedicated topic for policy lifecycle, gate allowed, and gate blocked events).
- The policy engine is part of the `policies/` bounded context within the control plane.
- Initial maturity level tiers (0–3) and their capability mappings are configurable by administrators but ship with sensible defaults.
- Blocked action records are retained indefinitely for audit purposes.
