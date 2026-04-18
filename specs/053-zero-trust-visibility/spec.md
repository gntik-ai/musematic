# Feature Specification: Zero-Trust Default Visibility

**Feature Branch**: `053-zero-trust-visibility`
**Created**: 2026-04-18
**Status**: Draft
**Input**: User description: "New agents default to zero visibility (see no agents, no tools). Visibility explicitly granted via per-agent FQN patterns and workspace-level grants. Filtering enforced at registry query time — invisible entities never returned."

**Scope note**: Several of the building blocks are already in place. `AgentProfile.visibility_agents` and `visibility_tools` are columns with `[]` default (feature 021 Registry). A separate `workspaces_visibility_grants` table holds per-workspace grant patterns with CRUD endpoints (`PUT /api/v1/workspaces/{id}/visibility`, feature 018 Workspaces). The registry service already exposes `resolve_effective_visibility(agent_id, workspace_id)` and applies a visibility predicate to its repository queries before pagination, so agent listings honor visibility when a requesting agent is provided. What is **not** yet done, and what this feature delivers:

1. Zero-trust behavior is not gated by a feature flag — it is effectively always-on when a `requesting_agent_id` is passed and always-off when it is not. Principle IX and Brownfield Rule 8 require an explicit `FEATURE_ZERO_TRUST_VISIBILITY` flag (default OFF for existing deployments, ON for new ones) to support gradual rollout.
2. The tool gateway does not check whether an agent is permitted to see the tool it is invoking. Today it enforces permission/purpose/budget/safety but not tool visibility.
3. Agent-to-agent delegation (in the interactions bounded context) does not reject calls that target an agent the caller cannot see. An invisible target can still be delegated to via direct UUID reference.
4. Marketplace discovery and recommendation surfaces do not consistently apply the visibility filter. Results can include agents the caller has not been granted visibility to.
5. Some read surfaces (get-by-id, resolve-by-FQN) already raise 404 for invisible agents so they appear not-to-exist, but the response shape for "not visible" versus "not found" must be uniform so observers cannot probe for existence.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Default-deny for a newly registered agent (Priority: P1)

A platform engineer registers a brand-new agent in a workspace. With the zero-trust flag ON, that agent must see exactly zero other agents and zero tools until someone explicitly grants it visibility. Operators depend on this default to avoid accidental trust-by-default when new agents are introduced into an environment with sensitive peers or tools.

**Why this priority**: This is the core security posture. Without it, every new agent in a workspace is implicitly trusted to discover and invoke anything — the opposite of what an enterprise operator expects. Also required by the platform constitution's Principle IX.

**Independent Test**: Enable the flag. Register a new agent with no visibility patterns set. Perform every read that returns agents or tools from the perspective of that agent. Each response returns an empty list and a zero count. Delivered value: a locked-down default with no implicit trust.

**Acceptance Scenarios**:

1. **Given** the flag is ON and a newly registered agent has empty per-agent visibility and the workspace has no visibility grant, **When** the agent queries for any other agent in the workspace, **Then** the response is an empty list with `total = 0`.
2. **Given** the same preconditions, **When** the agent attempts to invoke any tool, **Then** the gateway denies the invocation with a "permission_denied" class of error that does not disclose whether the tool exists.
3. **Given** the same preconditions, **When** another agent attempts to delegate work to this new agent, **Then** the delegation is rejected with a 403-class error identical to the error returned when the target does not exist, so presence cannot be inferred.
4. **Given** the same preconditions, **When** the agent browses the marketplace, **Then** it sees only agents it has been granted visibility for (zero by default).

---

### User Story 2 — Per-agent FQN pattern grants (Priority: P1)

An operator configures a specific agent with `visibility_agents = ["finance-ops:*"]`. From that moment, the agent can see every agent in the `finance-ops` namespace and only those agents. No other namespace becomes visible. Operators use patterns to grant access at the namespace level rather than enumerating every FQN.

**Why this priority**: The grant mechanism is the primary way an operator lifts default-deny. Without this, zero-trust is unusable because every agent would permanently see nothing.

**Independent Test**: Configure the per-agent pattern. From that agent's perspective, list agents and assert only FQNs matching the pattern are returned. Delivered value: precise, pattern-based grants that scale with namespaces.

**Acceptance Scenarios**:

1. **Given** an agent with `visibility_agents = ["finance-ops:*"]` in a workspace containing `finance-ops:kyc-verifier`, `finance-ops:aml-checker`, and `hr-ops:onboarding-agent`, **When** the agent lists agents, **Then** the response contains exactly the two `finance-ops` agents and not the `hr-ops` agent.
2. **Given** an agent with `visibility_agents = ["finance-ops:kyc-*"]`, **When** the agent lists agents, **Then** only `finance-ops:kyc-verifier` is returned.
3. **Given** an agent with `visibility_agents = []` but the workspace has a grant `agent_patterns = ["finance-ops:*"]`, **When** the agent lists agents, **Then** the `finance-ops` agents are returned (workspace grant applies as a floor on top of per-agent config).
4. **Given** an agent with `visibility_agents = ["hr-ops:*"]` and the workspace has `agent_patterns = ["finance-ops:*"]`, **When** the agent lists agents, **Then** agents from BOTH namespaces are returned (union of per-agent and workspace grants).

---

### User Story 3 — Tool visibility enforced at invocation (Priority: P1)

A governance-minded operator wants to guarantee that an agent can only invoke tools it has been granted visibility to, even if the agent somehow constructs the tool's FQN in its prompt or inherits a permission through policy. The tool gateway must reject any invocation whose `tool_fqn` does not match the caller's effective `visibility_tools` patterns.

**Why this priority**: Policy-based permission checks alone have been shown (in prior incidents) to allow "allowed-and-invisible" edge cases where the agent has permission but should never have been aware of the tool. Visibility-at-invocation closes that gap.

**Independent Test**: An agent with `visibility_tools = ["tools:search:*"]` attempts to invoke a visible tool and an invisible one. The visible invocation proceeds through all existing checks. The invisible invocation is blocked by a new visibility check before any other evaluation. Delivered value: visibility is enforced at the one gate that all tool use passes through.

**Acceptance Scenarios**:

1. **Given** the flag is ON and an agent has `visibility_tools = ["tools:search:*"]`, **When** the agent invokes `tools:search:web`, **Then** the invocation proceeds through the existing policy, purpose, budget, and safety checks.
2. **Given** the same agent, **When** it attempts to invoke `tools:finance:wire-transfer`, **Then** the invocation is rejected with a "permission_denied" class of error; no information about the tool's existence is disclosed.
3. **Given** the flag is OFF, **When** the same agent invokes either tool and holds the necessary policy permissions, **Then** both invocations proceed unchanged from current behavior.

---

### User Story 4 — Delegation to invisible peers is blocked (Priority: P2)

An agent tries to delegate work to another agent by FQN or by UUID. If the target is outside the delegating agent's visibility, the delegation must fail exactly as if the target did not exist. Operators rely on this so that an agent cannot exfiltrate work or data to a peer it was not granted access to.

**Why this priority**: This closes a flank that pure discovery-visibility leaves open. Without it, an agent that happens to know a target's FQN (from logs, prompts, or off-platform sources) can bypass the visibility model at the coordination layer. It is P2 because US1 and US2 cover the most common discovery paths; US4 tightens the lateral-movement path.

**Independent Test**: Agent A with `visibility_agents = []` attempts to open a delegation to agent B (visible by FQN to operators, invisible to A). The call is rejected with the same 403-class response used for "target not found". Delivered value: no path around discovery-time filtering via direct FQN/UUID reference.

**Acceptance Scenarios**:

1. **Given** the flag is ON, **When** an agent attempts to delegate to a peer whose FQN matches none of the caller's effective visibility patterns, **Then** the call is rejected with a 403-class error that is indistinguishable from the error returned when the target does not exist.
2. **Given** the flag is ON and the target FQN matches the caller's effective patterns, **When** the delegation is attempted, **Then** it proceeds (subject to other authorization rules).
3. **Given** the flag is OFF, **When** any delegation is attempted by an authorized caller, **Then** it proceeds unchanged from current behavior.

---

### User Story 5 — Backward-compatible rollout (Priority: P2)

An existing deployment cannot be broken by activating zero-trust. Operators need to deploy the new code, verify it is dormant (flag OFF), and then turn the flag ON per workspace (or globally) when they have audited and populated visibility grants. Once ON, existing agents whose visibility was implicitly "everything" must surface the change clearly, not silently strand callers.

**Why this priority**: Without a feature flag and explicit rollout story, this change is effectively a breaking deploy. Deployed to an existing workspace on Monday, every workflow that relies on cross-namespace discovery stops working on Tuesday. The flag makes rollout opt-in.

**Independent Test**: Deploy the change with the flag OFF. Run the existing test suite and smoke tests. No test fails. Turn the flag ON in a dev environment. Re-run the same suite — failures (if any) are clearly attributable to missing grants, not to the new code path.

**Acceptance Scenarios**:

1. **Given** the flag is OFF, **When** any of the scenarios in US1–US4 are exercised, **Then** behavior is identical to the pre-change codebase: agents and tools are visible according to existing workspace/RBAC rules; no new denials appear.
2. **Given** the flag is ON and an operator flips it OFF in response to an operational issue, **When** callers retry, **Then** behavior immediately reverts to the pre-zero-trust path without a deployment.
3. **Given** the flag is ON, **When** zero-trust denies a call, **Then** the resulting audit log entry is tagged so operators can distinguish zero-trust denials from other denials during the rollout audit.

---

### Edge Cases

- An agent has an overly broad pattern like `*` or `*:*` → treated as "visibility to all agents in the workspace"; not rejected syntactically, but flagged in audit so operators can notice accidental wildcards.
- An agent is granted visibility to a namespace that later gains a sensitive agent (e.g., a new agent published into `finance-ops:*`) → the granted agent immediately sees the new peer; operators must either narrow the pattern or accept namespace-wide visibility.
- A workspace-level grant is removed → agents that relied on it fall back to per-agent patterns only; if those are empty, default-deny takes effect on the next request.
- Flag is toggled ON mid-request → in-flight requests complete under the behavior they started with; only new requests see the new behavior.
- Marketplace shows aggregate search results that include agents across workspaces → only agents in workspaces the caller belongs to AND matching visibility patterns are included; workspaces the caller does not belong to are excluded by the existing workspace-scope rule, not by this feature.
- Two calls race on a visibility grant change → reads after the grant-write API returns 200 reflect the new grant; reads before do not. No transactional strength beyond that is promised.
- A recommendation or discovery response includes invisible agents in its `total` count → disallowed; total must reflect post-filter state.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose a feature flag named `FEATURE_ZERO_TRUST_VISIBILITY` that defaults to OFF for existing deployments.
- **FR-002**: When the flag is OFF, all agent and tool access behavior MUST be identical to the pre-change behavior: no new denials, no new filters, no new 403s.
- **FR-003**: When the flag is ON, the effective visibility for any request made on behalf of an agent MUST be the union of the agent's per-agent `visibility_agents` / `visibility_tools` patterns and the workspace-level grant patterns.
- **FR-004**: When the flag is ON, agent discovery responses (list, search, recommend) MUST exclude every agent whose FQN does not match the caller's effective agent patterns; the `total` or `count` reported MUST reflect the post-filter state.
- **FR-005**: When the flag is ON, agent-by-ID and agent-by-FQN retrievals for an agent outside the caller's visibility MUST return the same error shape as "not found", so presence cannot be inferred.
- **FR-006**: When the flag is ON, the tool gateway MUST deny any tool invocation whose `tool_fqn` does not match the caller's effective tool patterns, with an error shape identical to "permission denied" so tool existence is not disclosed.
- **FR-007**: When the flag is ON, agent-to-agent delegation MUST be rejected if the target agent is outside the caller's effective agent patterns; the error shape MUST match "target not found".
- **FR-008**: When the flag is ON, marketplace browsing, search, and recommendation surfaces MUST apply the same visibility filter as the registry's discovery endpoints.
- **FR-009**: The default per-agent visibility for a newly created agent MUST be empty (`visibility_agents = []`, `visibility_tools = []`), regardless of the flag state. This preserves the data shape required for zero-trust when the flag is flipped ON.
- **FR-010**: An operator MUST be able to set a workspace-level visibility grant via an existing administrative endpoint; this grant MUST be readable, writable, and removable.
- **FR-011**: An operator MUST be able to change per-agent visibility patterns via an existing administrative path (partial update of the agent profile); a change MUST take effect on subsequent requests.
- **FR-012**: When the flag is ON and a call is denied for visibility reasons, the denial MUST be recorded in the audit stream with a code that distinguishes it from other denial types (e.g., policy denial, purpose mismatch).
- **FR-013**: Visibility pattern matching MUST continue to use the existing FQN glob semantics (exact match, `*` wildcards at namespace or local-name level).
- **FR-014**: The feature flag MUST be togglable at runtime without requiring a redeployment; the new value MUST take effect on subsequent requests within seconds.
- **FR-015**: The feature MUST NOT expose visibility patterns belonging to another agent to the calling agent; pattern strings are operator configuration, not caller data.
- **FR-016**: No visibility grant MUST be inferred from RBAC role, workspace membership, or execution context; only explicit per-agent patterns and explicit workspace grants count.

### Key Entities

- **Agent Visibility Configuration**: The set of FQN glob patterns attached to a single agent (`visibility_agents` and `visibility_tools`). Default is an empty list. Lives on the agent profile. Already in place; no structural change by this feature.
- **Workspace Visibility Grant**: A workspace-scoped set of FQN glob patterns that supplements every agent's per-agent configuration within that workspace. Default is an empty grant. Already in place; no structural change by this feature.
- **Effective Visibility**: The union of the calling agent's `visibility_agents`/`visibility_tools` and the workspace grant's agent/tool patterns, computed per request. Already implemented as a service method; this feature ensures every enforcement point calls it consistently.
- **Feature Flag (`FEATURE_ZERO_TRUST_VISIBILITY`)**: A process-level or workspace-level toggle governing whether the effective-visibility filter is enforced. NEW.
- **Visibility Audit Entry**: A record in the audit stream produced when a call is denied for visibility reasons, carrying the denial code, the calling agent's FQN, the target (agent or tool) FQN, and the workspace. Partly NEW (new denial code); the audit stream itself already exists.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the flag ON and no grants, a freshly registered agent sees zero agents and zero tools across 100% of sampled read and invocation paths (registry list, resolve, search, recommendations, tool invocation, delegation).
- **SC-002**: With the flag ON, a granular pattern grant (`finance-ops:*`) limits visibility to exactly the matching FQNs and no others, measured at 100% precision across the same read paths.
- **SC-003**: With the flag ON, workspace-level grants and per-agent patterns combine as a union: if either allows a target, the target is visible; if neither does, it is not. This holds for 100% of combinations tested in the independent test suite.
- **SC-004**: With the flag OFF, the entire existing test suite passes without modification and no new test fails; zero regressions measured after deployment.
- **SC-005**: Turning the flag from OFF to ON in a workspace causes newly denied calls to be visibly attributable in the audit stream with a visibility-specific denial code for 100% of such denials, so operators can distinguish rollout impact from unrelated denials.
- **SC-006**: No denied call leaks information about the existence of the blocked target: 100% of visibility denials are indistinguishable in response shape from "not found" (for agents) or "permission denied" (for tools).
- **SC-007**: Counters and `total` fields returned in paginated discovery responses exclude invisible entities in 100% of responses; a caller never sees a count it cannot also enumerate.
- **SC-008**: Toggling the flag (OFF → ON or ON → OFF) takes effect on subsequent requests within 5 seconds of the change, without requiring a redeploy.

---

## Assumptions

- Per-agent `visibility_agents` and `visibility_tools` columns already exist with `[]` defaults (feature 021). This feature does not add or rename them.
- A `workspaces_visibility_grants` table already exists with per-workspace agent/tool pattern lists (feature 018). This feature does not restructure it; in particular, the grants stay in a dedicated table rather than migrating to a JSONB column on `workspaces`, consistent with Brownfield Rule 1 (no rewrites).
- The administrative endpoint `PUT /api/v1/workspaces/{id}/visibility` already exists (feature 018). This feature does not add a new endpoint for it.
- The `resolve_effective_visibility(agent_id, workspace_id)` method in the registry service already computes the union of per-agent and workspace grants. This feature relies on it and does not re-implement the logic.
- The registry repository already applies a visibility predicate to list/count queries when given a filter. This feature ensures the predicate is always applied under flag-ON and always bypassed under flag-OFF.
- The existing tool gateway's five-stage check (permission, maturity, purpose, budget, safety) is retained; tool visibility is added as a new stage ahead of or immediately after the permission stage.
- The interaction bounded context already has a delegation path (target agent by FQN or UUID); this feature adds a single pre-check to that path rather than restructuring it.
- The marketplace search and recommendation services already filter by workspace membership; this feature adds visibility filtering on top, not as a replacement.
- FQN glob pattern semantics (exact match, `*` wildcard for namespace or local-name) are already implemented in the registry (`fqn_matches`, `compile_fqn_pattern`). This feature uses them as-is.
- Feature flag distribution is handled by the platform's existing configuration mechanism; there is no new flag-distribution infrastructure in this feature.
- Audit events use the existing audit pipeline; the only addition is a new denial code value, not a new pipeline.
