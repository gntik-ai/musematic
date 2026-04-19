# Feature Specification: MCP Integration

**Feature Branch**: `066-mcp-integration`  
**Created**: 2026-04-19  
**Status**: Draft  
**Input**: Brownfield addition — bidirectional integration with the Model Context Protocol (MCP) ecosystem. **Client mode**: platform agents connect to external MCP servers, discover their tools/resources/prompts, and invoke those tools through the platform's existing tool gateway so that every MCP tool call is subject to the same policy, visibility, sanitization, budget tracking, and audit rules as a native tool. **Server mode**: the platform exposes a subset of its internal tools to external MCP clients (operator-controlled), allowing third-party AI assistants that speak MCP to discover and invoke platform tools as if they were any MCP server. Both modes pass through the platform's existing safety surfaces; no MCP interaction bypasses policy enforcement.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Platform Agent Discovers and Invokes External MCP Tools (Priority: P1)

A platform agent needs capabilities provided by an external MCP server (e.g., a vendor's code-search server, a partner's specialized document-reading tools, a community MCP server that exposes a maps API). A platform operator has registered the external MCP server and associated it with the agent's configuration via a list of permitted MCP server references. When the agent starts execution, the platform connects to each listed MCP server, discovers the tools/resources/prompts the server exposes, and adds them to the agent's available toolset — with an identifier scheme that makes MCP tools distinguishable from native tools. During execution, the agent invokes MCP tools exactly as it invokes native tools; the tool gateway enforces policy (visibility, permission, budget, safety, output sanitization) on every call; results are audited identically to native tool calls.

**Why this priority**: MCP client mode is the primary value proposition — it unlocks the entire MCP tool ecosystem (thousands of community and vendor servers) for platform agents without hand-writing connectors for each one. Without client mode, every new external capability requires a bespoke platform tool; with it, a single registration makes a whole server's catalog available. P1 because (a) every downstream user story builds on a working client pipeline, and (b) the platform's policy contract (FR-144) explicitly mandates that all tools — including external MCP tools — flow through the tool gateway, which is implemented in this story.

**Independent Test**: Register a known external MCP test server (e.g., a reference MCP server exposing a handful of read-only tools). Attach the server to a test agent's configuration. Start an agent execution that requires one of the MCP tools. Verify: (a) the MCP tool appears in the agent's available toolset with a distinguishable identifier, (b) the agent successfully invokes it, (c) the invocation passed through the tool gateway (policy check logged), (d) the result was sanitized and returned to the agent, (e) the invocation produced an audit record with principal, agent, tool, outcome, and timestamp.

**Acceptance Scenarios**:

1. **Given** a platform operator has registered an external MCP server and attached it to an agent's configuration, **When** the agent begins execution, **Then** the platform connects to the MCP server, discovers its tools, and includes them in the agent's available toolset.
2. **Given** a platform agent with access to an external MCP tool, **When** the agent invokes the tool, **Then** the invocation passes through the tool gateway before any network call to the MCP server is made; policy checks (visibility, permission, budget, safety) apply identically to native tools.
3. **Given** a successful MCP tool invocation, **When** the result is returned, **Then** the result is passed through output sanitization and then delivered to the agent exactly as a native tool result would be.
4. **Given** an MCP tool that exceeds the calling agent's budget, **When** the agent attempts to invoke it, **Then** the invocation is denied by the tool gateway with a budget-exceeded decision; the MCP server is NOT contacted.
5. **Given** an MCP tool call that returns content violating platform safety rules (e.g., disallowed patterns or secret-like content), **When** the response is received, **Then** the violating content is redacted by output sanitization before reaching the agent context.
6. **Given** an MCP server that becomes unreachable or returns an error, **When** the agent attempts to invoke one of its tools, **Then** the agent receives a clear tool-failure result with a classification (transient vs. permanent); the agent's execution can proceed as it would for any other tool error.

---

### User Story 2 — External MCP Client Discovers and Invokes Platform Tools (Priority: P1)

An external AI assistant that speaks MCP (e.g., a desktop assistant, a third-party orchestration platform, a developer's local MCP-enabled editor) wants to use platform tools. A platform operator designates a subset of platform tools as MCP-exposable; the platform exposes an MCP server endpoint that external clients can connect to. The external client performs MCP handshake, discovers the exposed tools (with their schemas and descriptions), authenticates, and invokes tools. Every invocation passes through the tool gateway with the external client mapped to a workspace-scoped principal; policy, visibility, sanitization, and audit are enforced identically to internal invocations.

**Why this priority**: MCP server mode completes the bidirectional interoperability story — the platform becomes a first-class participant in MCP ecosystems that external AI assistants can consume. P1 because server mode has distinct security surface (external clients touching internal tools) and must land at the same time as client mode to avoid a partial implementation; operators need both directions to reason about MCP policy consistently.

**Independent Test**: Designate a small subset of platform tools as MCP-exposed (e.g., a read-only document-search tool and a calculator). Connect an external MCP client (e.g., an MCP-compatible reference client). Perform MCP handshake; verify the exposed tools appear in the client's discovery response with correct schemas. Authenticate; invoke a tool; verify the result returns in MCP canonical format. Verify the invocation produced an audit record and passed through the tool gateway.

**Acceptance Scenarios**:

1. **Given** a set of platform tools designated as MCP-exposed by an operator, **When** an external MCP client connects to the platform's MCP server endpoint, **Then** the client discovers exactly those tools with their MCP-compliant tool schemas.
2. **Given** an authenticated external MCP client, **When** the client invokes a platform tool, **Then** the invocation is mapped to a workspace-scoped principal and passes through the tool gateway before any tool code executes.
3. **Given** an external MCP client without authorization to invoke a specific tool, **When** it attempts to invoke the tool, **Then** the invocation is denied by the tool gateway; no tool code runs; the denial is audited.
4. **Given** a tool that is NOT designated as MCP-exposed, **When** an external MCP client requests it, **Then** the tool is not discoverable and cannot be invoked via MCP, even if the caller is authenticated.
5. **Given** a successful tool invocation via MCP, **When** the result is returned to the external client, **Then** the result is sanitized (secrets redacted) before leaving the platform and is delivered in MCP canonical response format.

---

### User Story 3 — All MCP Interactions Flow Through Tool Gateway (Priority: P1)

A security officer mandates that every MCP interaction — inbound (platform tools invoked by external MCP clients) and outbound (external MCP tools invoked by platform agents) — is governed by exactly the same enforcement surface as native tools. The tool gateway performs four checks on every call (permission, purpose, budget, safety) and writes audit records regardless of outcome. Output sanitization applies to all results crossing the MCP boundary in either direction. No MCP interaction produces a tool invocation that bypasses the gateway.

**Why this priority**: The constitution (Reminder 25 / 22) is explicit: "MCP tools go through tool gateway. Same policy, visibility, sanitization as native tools." A release that allowed MCP tools to bypass the gateway would violate the platform's security posture on day one. P1 because MCP is a dual-use surface (agents can exfiltrate data to external MCP servers, external clients can probe platform tools) and uniform gateway enforcement is the only safe boundary.

**Independent Test**: Configure a deny-all outbound policy for a test agent. Start execution; verify that external MCP tool invocations are denied by the gateway before any network call. Relax policy to allow one MCP server; verify invocations to that server succeed and to others fail. For inbound, submit an MCP tool invocation from an external client with a principal that lacks permission; verify denial. Verify all denials and successes produce audit records.

**Acceptance Scenarios**:

1. **Given** any MCP tool invocation (inbound or outbound), **When** the invocation is submitted, **Then** it passes through the tool gateway's four checks (permission, purpose, budget, safety) before any tool execution or external network request occurs.
2. **Given** a tool-gateway denial decision on an MCP invocation, **When** the decision is made, **Then** the invocation is stopped at the gateway; no tool code runs, no external MCP server is contacted, and a denial audit record is written.
3. **Given** any successful MCP tool invocation, **When** the tool returns a result, **Then** the result passes through output sanitization before being delivered to the calling context (agent, or external MCP client).
4. **Given** the same underlying policy bundle, **When** a platform agent invokes a tool natively and then via an external MCP server, **Then** both invocations produce identical gateway decisions under equivalent inputs.
5. **Given** a tool invocation across MCP (inbound or outbound), **When** any terminal state is reached (success, denial, or error), **Then** an audit record is written capturing principal, agent, tool identifier, MCP server reference (if applicable), outcome, and timestamp.

---

### User Story 4 — Error Handling and Resilience for MCP Failures (Priority: P2)

Platform agents and external MCP clients alike need predictable, auditable behavior when an MCP server is unreachable, returns a protocol-level error, or produces a malformed response. The platform classifies each failure as transient (connection refused, timeout, 5xx response) or permanent (invalid protocol handshake, schema violation, explicit MCP error payload). Transient failures are surfaced with retry-safe hints; permanent failures are surfaced as terminal tool errors. Operators can inspect MCP server health so chronic failures are visible before they affect executions broadly.

**Why this priority**: Error handling is table stakes for external integrations but is NOT a P1 gate because the client and server modes (US1, US2) can ship with a simple "classify and surface" error behavior; richer observability and operator inspection (e.g., health dashboards, retry policies) are hardening layers. P2 reflects the operational importance without blocking MVP.

**Independent Test**: Take down a registered external MCP server. Attempt a platform-agent invocation of one of its tools. Verify the agent receives a transient tool-failure result with a retry-safe hint. Re-enable the server. For a permanent error, configure the external server to return a malformed protocol response; verify the invocation is classified as permanent and surfaces as a terminal error. Verify both classifications appear in the audit log with distinct codes.

**Acceptance Scenarios**:

1. **Given** an external MCP server that is unreachable, **When** a platform agent invokes one of its tools, **Then** the agent receives a tool-failure result classified as transient, with a retry-safe indication; the gateway audit record captures the failure classification.
2. **Given** an external MCP server that returns a protocol-level error (explicit MCP error payload), **When** the platform agent invokes a tool, **Then** the error is surfaced to the agent in the platform's internal tool-error format with the original error code preserved for inspection.
3. **Given** an external MCP server that returns a malformed response (protocol violation), **When** the platform parses the response, **Then** the invocation is classified as permanent failure and the agent receives a terminal error.
4. **Given** an external MCP client invoking a platform tool that itself fails, **When** the failure is caught, **Then** the external client receives an MCP-compliant error response sanitized to not leak internal stack traces or non-MCP-exposed tool names.
5. **Given** repeated MCP server failures over a short window, **When** the platform observes the pattern, **Then** operators can view the server's health status through the existing operator-facing monitoring surface; no new bespoke UI is introduced.

---

### User Story 5 — External MCP Tool Catalog Caching and Refresh (Priority: P3)

Operators register external MCP servers; the platform fetches each server's tool/resource/prompt catalog on registration and periodically re-discovers it with a configurable TTL. Cached catalog entries are used on agent-execution start rather than a fresh fetch per execution; catalog changes on the external server (new tools added, tools removed, schemas changed) are picked up on the next refresh. Fetch failures fall back to the last-known catalog flagged as stale.

**Why this priority**: Catalog caching is an operational optimization — uncached fetch-per-execution works but is slow and pressures external MCP servers. Correctness of client mode (US1) does not depend on caching. P3 because this is a hardening/performance milestone.

**Independent Test**: Register an external MCP server. Start two agent executions that both use a tool from that server within the TTL; verify the catalog is fetched once and reused. Age the cache (or wait TTL); verify a fresh fetch occurs. Simulate a fetch failure on a cached entry; verify the cached catalog is returned with a staleness flag and the tool is still invocable.

**Acceptance Scenarios**:

1. **Given** a newly-registered external MCP server, **When** the first agent execution requires one of its tools, **Then** the platform fetches and caches the server's tool catalog.
2. **Given** a cached MCP catalog within its TTL, **When** a subsequent execution starts, **Then** the cached catalog is used without a fresh fetch.
3. **Given** a cached catalog whose TTL has expired, **When** the next execution starts, **Then** a fresh fetch is triggered and the cache is updated.
4. **Given** an external MCP server whose catalog has changed (tools added, removed, schema changed), **When** a refresh occurs, **Then** the cache entry is replaced; newly-added tools become available and removed tools become unavailable in dependent agent configurations.
5. **Given** a cache-refresh fetch that fails with a transient error, **When** a cached entry exists, **Then** the cached catalog is returned flagged as stale; the agent can still invoke cached tools; a retry is scheduled.

---

### Edge Cases

- **Agent configured with a non-existent or deregistered MCP server reference**: The server is skipped during discovery with an operator-visible warning; the agent's execution starts with the remaining tool set; no error cascades.
- **Two MCP servers expose tools with identical names**: Tools are namespaced by server reference in the agent's toolset so names do not collide; ambiguity is impossible at the gateway level.
- **An external MCP server declares a tool whose input schema conflicts with platform size limits**: The tool is excluded from the agent's available set with a log warning; other tools from the same server remain available.
- **An external MCP client attempts to invoke a platform tool that is NOT in the MCP-exposed subset**: The tool is not discoverable; an invocation attempt by guessed name is rejected with an MCP-compliant "tool not found" error that does not disclose whether the tool exists internally.
- **A platform agent's `mcp_servers` list includes a server flagged as suspended by operators**: Suspended servers are treated as absent during discovery; the agent sees only tools from non-suspended servers.
- **An MCP tool invocation result exceeds the platform's maximum MCP payload size**: The invocation fails with a "payload too large" classification; partial content is discarded; audit record captures the size violation.
- **Authentication token for an external MCP server has expired**: A re-authentication attempt occurs per the server's declared authentication scheme; if re-authentication fails, the tool is surfaced as permanently unavailable until operator intervention.
- **An external MCP client's session silently drops during a long-running tool invocation**: The platform finishes the invocation server-side (safely), writes the audit record, and discards the result; no re-delivery is attempted without an explicit client reconnect.
- **Duplicate MCP server registrations (same URL registered twice in the same workspace)**: The second registration is rejected with a clear error; operators must explicitly deregister before re-adding.
- **An external MCP client attempts to bypass the tool gateway by calling an internal endpoint directly**: All inbound MCP traffic enters through the MCP server endpoint exclusively; any direct internal endpoint is unreachable from the MCP boundary.
- **Outbound MCP call where the destination URL uses a non-secure transport**: The call is denied before any handshake; secure transport is mandatory regardless of allowed-list status.
- **MCP tool whose declared schema is malformed or ambiguous**: The tool is excluded from the agent's available set during discovery; the exclusion is logged and operators are notified via the existing monitoring surface.
- **An inbound MCP client invokes a platform tool that emits secret-bearing output (e.g., an internal config read)**: Output sanitization redacts the secrets before the response crosses the MCP boundary; redaction counts are recorded in the audit.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST allow operators to register external MCP servers (endpoint URL, authentication configuration) as workspace-scoped resources and associate them with agent configurations.
- **FR-002**: Agent configuration MUST include a list of permitted external MCP server references (`mcp_servers`), and this list MUST be resolved at agent execution time to the current set of non-suspended, non-deregistered server records.
- **FR-003**: On agent execution start, the platform MUST discover tools, resources, and prompts exposed by each permitted external MCP server, and include the discovered tools in the agent's available toolset with a distinguishable MCP-tool identifier scheme.
- **FR-004**: Every invocation of an external MCP tool MUST pass through the platform's existing tool gateway and be subject to the same four checks as native tools (permission, purpose, budget, safety) before any network request to the MCP server is made.
- **FR-005**: MCP tool invocation results MUST pass through the platform's output sanitization pipeline before being delivered to the calling agent context.
- **FR-006**: MCP tool invocations MUST be subject to the same per-execution and per-agent budget tracking as native tools; exceeding a budget MUST produce a gateway denial with a budget-exceeded decision.
- **FR-007**: The platform MUST produce an audit record for every MCP tool invocation (success, denial, or error) capturing principal, agent, MCP server reference, tool identifier, outcome, and timestamp.
- **FR-008**: Tool-name collisions across multiple MCP servers on the same agent MUST be avoided by namespacing tool identifiers in the agent's toolset by MCP server reference; collisions MUST be impossible at the gateway decision layer.
- **FR-009**: The platform MUST expose an MCP server endpoint allowing external MCP clients to discover and invoke a subset of platform tools designated by operators as "MCP-exposed"; tools not in that subset MUST NOT be discoverable via MCP.
- **FR-010**: Inbound MCP invocations from external clients MUST be authenticated and mapped to a workspace-scoped principal before any authorization check or tool execution occurs.
- **FR-011**: Inbound MCP invocations MUST pass through the same tool gateway as internal invocations; the gateway MUST enforce identical decisions given identical policy inputs regardless of whether the origin is internal or MCP-inbound.
- **FR-012**: Outputs returned to external MCP clients MUST pass through output sanitization; secret-like content and disallowed patterns MUST be redacted before leaving the platform.
- **FR-013**: MCP server failures (outbound) MUST be classified as transient (connection refused, timeout, 5xx) or permanent (handshake failure, schema violation, explicit error payload) and surfaced to the calling agent with the classification preserved.
- **FR-014**: MCP error responses returned to external clients (inbound) MUST use the MCP-compliant error format and MUST NOT disclose internal stack traces, internal tool names not present in the MCP-exposed subset, or secret values.
- **FR-015**: External MCP server tool catalogs MUST be cached with a configurable TTL; cached catalogs MUST be used on agent execution start within TTL; cache misses and expirations MUST trigger fresh fetches.
- **FR-016**: When a catalog refresh fetch fails and a cached catalog exists, the cached entry MUST be returned flagged as stale; retry MUST be scheduled.
- **FR-017**: Outbound MCP calls to non-secure transport destinations MUST be denied regardless of allowed-list membership.
- **FR-018**: The platform MUST prevent a platform agent from invoking an MCP tool on a server that is not in the agent's `mcp_servers` list; the gateway MUST reject any such invocation at the permission check step.
- **FR-019**: Operator-designated MCP-exposed tools MUST be configurable without code changes; toggling a tool's MCP-exposure MUST take effect without platform restart.
- **FR-020**: The platform MUST NOT permit MCP to become a covert channel for internal platform-to-platform tool access; MCP is strictly an external interoperability surface.
- **FR-021**: Rate limits applicable to native tool invocations MUST apply identically to MCP tool invocations (both inbound and outbound) on a per-principal basis.
- **FR-022**: The platform MUST surface MCP server health (reachable / degraded / unreachable, recent error counts) through the existing operator monitoring surface; no new bespoke UI is introduced.
- **FR-023**: The modification to the tool gateway to accommodate MCP tools MUST NOT change the decision semantics or outputs for any native tool call; backward compatibility with existing tool bindings MUST be preserved.
- **FR-024**: Duplicate MCP server registrations (same endpoint URL in the same workspace) MUST be rejected at registration time.
- **FR-025**: The MCP catalog caching layer MUST detect and invalidate entries when the server's declared version or capability set changes between fetches.
- **FR-026**: Suspended or deregistered MCP servers MUST be treated as absent during agent execution discovery; no tool from a suspended server MUST appear in the agent's available toolset.

### Key Entities

- **External MCP Server Registration**: Operator-controlled record of an approved external MCP endpoint — endpoint URL, authentication configuration, workspace scope, status (active/suspended/deregistered), cached catalog reference, catalog TTL.
- **MCP Tool Binding**: The mapping between an MCP tool discovered on an external server and the identifier scheme used in a platform agent's toolset (namespaced tool identifier, input schema, description, classification metadata).
- **MCP-Exposed Platform Tool**: A platform tool designated by operators as discoverable and invokable through the platform's MCP server endpoint by external clients.
- **MCP Catalog Cache Entry**: A cached external MCP server catalog — tools/resources/prompts, last-fetched timestamp, declared version snapshot, staleness flag, next-refresh schedule.
- **MCP Invocation Audit Record**: Record of a single MCP tool invocation (inbound or outbound) — principal, agent reference (outbound only), MCP server reference, tool identifier, direction, outcome, policy decision, timestamp, payload-size classification.
- **MCP Server Health Status**: Operator-facing aggregate indicating whether a registered external MCP server is currently healthy, degraded, or unreachable, with recent error counts and last-success timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of external MCP tool invocations pass through the tool gateway before any network request to the MCP server; zero MCP invocations bypass policy enforcement.
- **SC-002**: 100% of inbound MCP invocations are authenticated AND authorized before any tool execution; zero inbound MCP invocations reach internal tool code without both checks succeeding.
- **SC-003**: 100% of MCP tool invocation results (both directions) pass through output sanitization; zero secret-pattern matches appear in responses when tested against a synthetic secret corpus.
- **SC-004**: 100% of MCP interactions (inbound and outbound, success and failure) produce an audit record; zero interactions are unaudited.
- **SC-005**: Native tool-invocation decisions remain byte-identical before and after the MCP integration; 100% of pre-existing native-tool-call tests continue to pass (no regression from the tool-gateway modification).
- **SC-006**: Tool-name collisions across multiple MCP servers on the same agent occur at zero rate; namespaced identifiers prevent ambiguity in 100% of discovery responses.
- **SC-007**: External MCP catalog cache achieves at least 90% hit rate on repeated agent executions using the same server within TTL, as measured under typical operator usage.
- **SC-008**: MCP tools excluded from the MCP-exposed subset are not discoverable by external MCP clients; attempted invocations of non-exposed tools are rejected in 100% of attempts with an MCP-compliant "tool not found" error that reveals no metadata about internal tools.
- **SC-009**: MCP invocations denied by the gateway are surfaced to the caller within 100 milliseconds (p95), the same budget as native-tool denials.
- **SC-010**: Transient and permanent MCP failure classifications are distinguishable in the audit log with distinct codes in 100% of recorded failure events.
- **SC-011**: MCP tool invocation to decision-complete latency (gateway allow/deny) is equivalent to native tool invocations within a 10% tolerance band; MCP does not introduce meaningful latency at the gateway layer.
- **SC-012**: Agent configurations reference MCP servers through stable identifiers; 100% of `mcp_servers` references resolve correctly across agent revisions; zero execution starts fail due to stale MCP server references when the referenced server is active.
- **SC-013**: Operators can toggle an individual platform tool's MCP-exposure without restarting the platform; the change takes effect within 60 seconds of the toggle.
- **SC-014**: Health status for each registered external MCP server is visible on the operator monitoring surface within 30 seconds (p95) of a measured state change.

## Assumptions

- The MCP specification at the time of implementation defines a stable handshake, tool/resource/prompt schema, and error vocabulary; the platform adopts that specification faithfully without custom extensions.
- The existing agent registry and agent configuration layer supports adding a new configuration field (`mcp_servers: list[str]`) as an additive, backward-compatible change; existing agents without the field remain unchanged.
- The existing tool gateway can accept a new tool category (MCP) via an additive change in the identifier scheme; the four gateway checks (permission, purpose, budget, safety) apply to MCP tools without new gate types.
- The existing authentication layer supports the authentication schemes that inbound MCP clients require; no new authentication primitives are introduced as part of this feature.
- The existing output sanitization surface applies uniformly to MCP responses without needing MCP-specific sanitization rules.
- The existing audit log accepts structured records with MCP-specific fields; no new audit infrastructure is introduced.
- The existing caching infrastructure handles MCP catalog cache entries with TTL-based invalidation.
- MCP is strictly an external interoperability surface; internal platform tools MUST NOT be invoked across MCP boundaries for platform-to-platform coordination (parallels the A2A external-only principle).
- Default external MCP catalog cache TTL is 1 hour; default maximum MCP payload size is 10 MB; default per-principal MCP invocation rate limit matches native-tool limits — all configurable by operators.
- The MCP protocol version supported by this release is a single pinned version; multi-version support is out of scope.
- Registration of external MCP servers is a privileged operation performed by platform operators, not by arbitrary workspace members.
- Designating a platform tool as MCP-exposed is a privileged operator action; individual tool bindings govern MCP exposure, not workspace-wide defaults.
- Secure transport (e.g., TLS) is required for every external MCP destination; plain-text transport is denied regardless of allowed-list state.
- Platform agents invoked over MCP-exposed tools see the invocation as an ordinary tool call; agents are NOT MCP-aware and require no code changes to participate.

## Dependencies

- Existing tool gateway (permission, purpose, budget, safety checks; audit write; sanitization pipeline dispatch).
- Existing agent registry (agent configuration schema, revision model, visibility rules).
- Existing authentication system (token validation, revocation checking, principal resolution).
- Existing output sanitization pipeline (for secrets and disallowed-content redaction on MCP responses, both directions).
- Existing audit log (for recording every MCP invocation).
- Existing policy engine (for inbound and outbound decisions on MCP calls).
- Existing caching infrastructure (for external MCP catalog cache entries and TTL management).
- Existing operator monitoring surface (for MCP server health visibility).

## Out of Scope

- Invocation of internal platform tools across MCP for platform-to-platform coordination (MCP remains external-only by policy, mirroring A2A).
- Multi-version MCP protocol multiplexing (single pinned version this release).
- Hosting a public index of external MCP servers (federation/discovery across organizations is deferred).
- Auto-discovery of external MCP servers via network scanning or third-party registries; all external servers are explicitly operator-registered.
- An end-user UI for browsing the platform's MCP-exposed tools; external MCP clients are other programmatic assistants, not interactive end users.
- MCP-specific billing, metering, or quota management beyond the shared per-principal rate limits.
- Richer retry/backoff strategies for outbound MCP failures beyond transient/permanent classification; advanced retry policies are deferred.
- MCP-specific resource streaming semantics beyond the tool-invocation request/response surface (e.g., long-lived MCP resource subscriptions); deferred to a later iteration.
- Fine-grained per-tool MCP expose/hide policies attached to specific workspaces or roles; initial exposure is platform-wide operator toggle per tool.
- Cross-workspace sharing of external MCP server registrations (each workspace explicitly registers the servers it uses).
