# Feature Specification: A2A Protocol Gateway

**Feature Branch**: `065-a2a-protocol-gateway`  
**Created**: 2026-04-19  
**Status**: Draft  
**Input**: Brownfield addition — a new bounded context that implements the A2A (Agent-to-Agent) open protocol for interoperability with external AI agents outside the platform. Provides two directions: **server mode** (external clients discover and invoke platform agents as if they were any A2A-compliant service) and **client mode** (platform agents invoke external A2A-compliant agents). Agent Cards (the A2A discovery documents) are auto-generated from existing registry metadata so operators never hand-author them. A2A task lifecycle, SSE streaming, and multi-turn conversations are all supported. All interactions — inbound and outbound — pass through the platform's existing authentication, authorization, and policy enforcement surfaces so the A2A boundary never bypasses security controls.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — External Client Discovers and Invokes a Platform Agent (Priority: P1)

An external A2A-compliant client (another organization's agent, a third-party orchestrator, an integration partner) wants to use a platform agent to fulfill a task. The external client first fetches the platform's public Agent Card at the well-known discovery URL, which lists the available platform agents, their purposes, authentication schemes, and skills. The client authenticates, submits an A2A task containing the user's request, and tracks the task's lifecycle (accepted → working → completed or failed) via status polling or streaming. The task result is returned in the A2A canonical response format.

**Why this priority**: Server-mode A2A is the primary value proposition of the feature — it turns the platform into an interoperable agent service that other AI systems can consume. Without it, the platform remains a closed ecosystem. P1 because every downstream user story builds on a working server-mode pipeline (Agent Card auto-gen, task lifecycle, policy enforcement, streaming, and multi-turn all manifest here first).

**Independent Test**: From outside the platform, issue a `GET` to the published Agent Card URL, parse the returned Agent Card JSON, authenticate using one of the declared schemes, submit a task targeting a known platform agent FQN, and poll the task status until it terminates. Verify the task transitions through the A2A-defined states, that the final result matches what the platform agent would have produced for an equivalent internal interaction, and that no A2A-specific behavior leaked into the internal execution path.

**Acceptance Scenarios**:

1. **Given** a platform agent exists with an Agent Card declaration, **When** an external client fetches the public Agent Card discovery URL, **Then** the response contains a valid A2A Agent Card JSON document listing the agent's name (derived from its fully-qualified name), purpose, endpoint URL, capabilities, authentication schemes, and skills.
2. **Given** an authenticated external client, **When** the client submits an A2A task targeting a platform agent, **Then** the task is accepted with a unique task identifier and the platform maps the task to an internal interaction record.
3. **Given** an in-progress A2A task, **When** the external client polls the task status endpoint, **Then** the status reflects the current lifecycle state (submitted, working, input-required, completed, failed, cancelled).
4. **Given** a completed A2A task, **When** the external client fetches the task result, **Then** the response matches the A2A canonical format and carries the platform agent's final output sanitized per the platform's output sanitization rules.
5. **Given** a failed A2A task, **When** the external client fetches the task status, **Then** the response contains the failure state with a machine-readable error code that does NOT disclose internal stack traces, internal agent names not exposed in the Agent Card, or secrets.
6. **Given** an Agent Card request for an agent that is archived or whose visibility is not public, **When** the discovery endpoint is queried, **Then** that agent is excluded from the Agent Card; no metadata leaks about non-public agents.

---

### User Story 2 — Platform Agent Invokes an External A2A Agent (Priority: P1)

A platform agent needs to use an external A2A-compliant agent to accomplish a sub-task (e.g., a translation agent published by a partner organization, a domain-specific reasoning agent from an allied platform). The platform agent describes the external A2A endpoint (either pre-configured or resolved by URL). The gateway fetches the external Agent Card, validates the external agent is allowed by policy, submits an A2A task, and returns the result to the calling platform agent as if it had invoked any other tool. Outbound calls are policy-checked, authenticated, and audited identically to other external integrations.

**Why this priority**: Client-mode A2A completes the bidirectional interoperability story — platform agents become first-class citizens of the broader agentic ecosystem, not just service providers. P1 because client mode has distinct security surface (outbound calls can exfiltrate data) and must land at the same time as server mode to avoid a partial implementation that is operationally confusing.

**Independent Test**: Configure an external A2A agent reference (a known test endpoint running an A2A mock). From a platform agent, invoke the external A2A agent via the gateway's client interface. Verify the gateway fetched the external Agent Card, submitted a task, retrieved the result, and surfaced it to the calling platform agent. Verify the outbound call appeared in the audit log and passed through policy checks.

**Acceptance Scenarios**:

1. **Given** a platform agent wishing to call an external A2A endpoint, **When** the gateway is invoked in client mode, **Then** the gateway fetches the external Agent Card, validates it, and uses the declared endpoint and authentication scheme to submit the task.
2. **Given** an external A2A agent that returns a task result, **When** the result is received, **Then** the gateway parses it into the platform's internal result format and returns it to the calling platform agent.
3. **Given** an outbound A2A call attempt to a destination blocked by policy (e.g., the destination is not on the allowed-list, or the calling agent lacks the necessary outbound permission), **When** the call is attempted, **Then** the call is denied before any external request is made and the denial is recorded in the audit log.
4. **Given** an external A2A agent that becomes unreachable mid-task, **When** the gateway polls for status, **Then** the calling platform agent receives a clear failure result with a retry-safe error classification (transient vs. permanent).
5. **Given** an external A2A agent whose response contains content that would violate platform policy (e.g., secret patterns, disallowed content), **When** the response is received, **Then** the content is sanitized before being returned to the calling platform agent.

---

### User Story 3 — All A2A Interactions Enforced by Policy (Priority: P1)

A security officer mandates that every A2A interaction — inbound and outbound — is subject to the same authentication, authorization, rate-limiting, and output-sanitization rules as native platform interactions. The gateway integrates with the existing policy enforcement layer so that: (a) inbound A2A tasks are authenticated, mapped to a workspace-scoped principal, and checked against per-agent permissions and rate limits; (b) outbound A2A calls are checked against the calling agent's outbound-call policy (destination allowed-list, data classification) before any external request is made; (c) all outputs — inbound results returned to external clients and inbound results from external agents returned to platform agents — are sanitized to strip secret patterns and disallowed content.

**Why this priority**: The constitution (Principle XIV) mandates that all A2A interactions go through authentication, RBAC, policy enforcement, and output sanitization. A release that skipped policy would immediately violate the platform's security posture and would need to be rolled back. P1 because security is non-negotiable for any external integration surface.

**Independent Test**: Configure a deny-all outbound A2A policy. Attempt to invoke an external A2A agent from a platform agent; verify the call is denied with an audit record. Relax policy to allow one destination. Repeat; verify the call succeeds. For inbound, submit an unauthenticated A2A task request; verify it is rejected. Authenticate as a principal without permission to invoke the targeted platform agent; verify the task is rejected. Submit a task whose platform agent response contains a synthetic secret; verify the response returned to the external client has the secret redacted.

**Acceptance Scenarios**:

1. **Given** an inbound A2A task request, **When** the request lacks valid authentication, **Then** the task is rejected with an A2A-compliant authentication error and no internal invocation occurs.
2. **Given** an authenticated inbound A2A task, **When** the authenticated principal does not have permission to invoke the targeted agent, **Then** the task is rejected with an authorization error disclosed at the A2A protocol level.
3. **Given** an outbound A2A call attempt, **When** the calling agent's outbound policy forbids the destination, **Then** the call is denied before any network request is made.
4. **Given** a platform agent response being returned to an external A2A client, **When** the response contains secret-like content (API key patterns, tokens), **Then** the content is redacted by output sanitization before being emitted.
5. **Given** an inbound A2A task request exceeding the per-principal rate limit, **When** the request arrives, **Then** it is rejected with a rate-limit error and the breach is logged.
6. **Given** any A2A interaction (inbound or outbound), **When** it completes (success or failure), **Then** an audit record is written capturing principal, agent, action, result, and timestamp.

---

### User Story 4 — SSE Streaming and Multi-Turn A2A Conversations (Priority: P2)

An external client invoking a long-running platform agent task wants to receive incremental updates rather than poll for completion. The gateway exposes Server-Sent Events streaming on the A2A task status endpoint, emitting lifecycle events (working, output-chunk, input-required, completed, failed) as they occur. For multi-turn conversations (where the platform agent needs clarification), the gateway exposes the A2A "input-required" state, accepts the client's follow-up message, and resumes the interaction as part of the same task.

**Why this priority**: Streaming and multi-turn are A2A protocol features that dramatically improve user experience on long-running or interactive tasks. They are P2 (not P1) because polling-based status retrieval (US1) already delivers a functionally complete server-mode experience for the majority of use cases; streaming is an enhancement layer.

**Independent Test**: Submit a long-running A2A task and subscribe to the streaming endpoint. Verify that working-state events are emitted incrementally and that a final completed event is emitted when the task finishes. For multi-turn, submit a task that causes the platform agent to request clarification. Verify the task transitions to input-required state and is exposed as an SSE event. Submit a follow-up message; verify the task resumes and completes.

**Acceptance Scenarios**:

1. **Given** an external client that subscribes to the streaming endpoint for a running A2A task, **When** the platform agent emits incremental progress, **Then** the client receives A2A-compliant SSE events for each progress milestone.
2. **Given** a streaming subscription, **When** the task terminates (completed or failed), **Then** a terminal SSE event is emitted and the stream is closed.
3. **Given** a platform agent that requires additional input from the external client, **When** the agent signals input-required, **Then** the task status transitions to input-required and the stream emits the corresponding event.
4. **Given** a task in input-required state, **When** the external client submits a follow-up message referencing the task identifier, **Then** the task resumes with the new input folded into the interaction history.
5. **Given** an SSE subscriber that disconnects mid-stream, **When** the subscriber reconnects and provides the last received event identifier, **Then** the stream resumes from the next unseen event (no missed lifecycle transitions).

---

### User Story 5 — External Agent Card Registry with Caching (Priority: P3)

A platform operator registers a set of trusted external A2A endpoints that platform agents are allowed to call. The gateway fetches and caches each external Agent Card with a configurable TTL, invalidates cache entries when the external agent's declared version changes, and surfaces the cached Agent Card to downstream policy and invocation layers. Cache misses trigger a fresh fetch; fetch failures return a cached stale copy with a staleness flag when available.

**Why this priority**: External Agent Card caching is an operational optimization that reduces external API pressure and improves latency on repeated calls. P3 because correctness of client mode (US2) does not depend on caching — uncached fetch-per-call works but is slow. Caching is a hardening / performance milestone, not a functional milestone.

**Independent Test**: Register three external A2A endpoints. Invoke an external agent via the gateway; verify the Agent Card is fetched and cached. Invoke the same agent a second time within the TTL; verify the fetch does NOT occur (cache hit). Age the cache (or wait out the TTL); verify a fresh fetch occurs. Force a fetch failure on a cached entry; verify the cached copy is returned with a staleness indicator.

**Acceptance Scenarios**:

1. **Given** a newly-registered external A2A endpoint, **When** a platform agent invokes it for the first time, **Then** the gateway fetches and caches the external Agent Card.
2. **Given** a cached Agent Card within its TTL, **When** the same endpoint is invoked again, **Then** the cached Agent Card is used without a fresh fetch.
3. **Given** a cached Agent Card whose TTL has expired, **When** an invocation occurs, **Then** a fresh fetch is triggered and the cache is updated.
4. **Given** an external endpoint that returns an Agent Card whose declared version differs from the cached version, **When** the new card is fetched, **Then** the cache entry is replaced and dependent policy state is recomputed.
5. **Given** a cache-refresh fetch that fails with a transient error, **When** the cached entry exists, **Then** the cached entry is returned with a staleness flag and the fetch is scheduled for retry.

---

### Edge Cases

- **Archived or revoked platform agent referenced in an active A2A task**: The task is terminated with a clear "agent no longer available" failure; the Agent Card discovery endpoint excludes the agent from subsequent responses.
- **External A2A agent returns an Agent Card with an unrecognized capability or unsupported authentication scheme**: The gateway refuses to invoke that agent, records the incompatibility in the audit log, and surfaces a descriptive error to the calling platform agent.
- **Inbound A2A task that targets a non-existent platform agent FQN**: Rejected with a specific "agent not found" A2A error code; no information is leaked about which agents do exist beyond the public Agent Card.
- **A2A task cancellation initiated by the external client on a task whose internal interaction is non-cancellable mid-step**: The task is marked cancellation-pending; the internal interaction completes its current step, the final result is discarded, and the task terminates with cancelled state.
- **SSE stream subscriber exceeds per-connection duration limit**: Stream is closed with a terminal event indicating subscriber should reconnect with last-event identifier; the underlying task continues.
- **Multi-turn conversation where the external client abandons the task in input-required state**: After a configurable idle timeout, the task is auto-cancelled and a cancellation audit record is written.
- **External A2A endpoint returns a response that exceeds the platform's maximum A2A payload size**: Task fails with a "payload too large" error; partial content is discarded.
- **Outbound A2A call where the external endpoint is on the allowed-list but uses HTTP (not HTTPS)**: Call is denied; HTTPS is required for all outbound A2A interactions regardless of allowed-list membership.
- **Inbound A2A request with an authentication token that has been revoked since issuance**: Task is rejected with authentication error at the token-validation step; revocation status is checked on every request, not cached.
- **Two simultaneous A2A tasks submitted by the same external client for the same platform agent**: Both tasks are accepted and processed independently; tasks do NOT share state unless explicitly correlated via a shared conversation identifier.
- **Agent Card auto-generation encounters an agent whose registry metadata is incomplete (missing purpose or skills)**: The agent is excluded from the public Agent Card with a log warning; operators are alerted via the existing monitoring surface.
- **External A2A agent's Agent Card TTL expired mid-invocation**: The in-flight invocation continues with the previously-fetched card; a refresh is triggered for subsequent invocations.
- **A2A protocol version mismatch (external client sends a request for a version the gateway does not support)**: The gateway returns a protocol-error response listing the supported A2A protocol versions; the task is not created.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST expose a public Agent Card discovery endpoint at the A2A canonical well-known URL that returns a valid A2A Agent Card JSON document.
- **FR-002**: Agent Cards MUST be auto-generated from existing agent registry metadata (fully-qualified name as agent name, declared purpose, endpoint URL, version from the active revision, capabilities, authentication schemes, skills from tool bindings) — operators MUST NOT hand-author Agent Cards.
- **FR-003**: Agent Card generation MUST exclude agents that are archived, revoked, not publicly visible, or whose metadata is incomplete; excluded agents MUST NOT appear in the public Agent Card response.
- **FR-004**: The platform MUST accept inbound A2A task submissions targeting platform agents and map each task to an internal interaction record with a bidirectional identifier link.
- **FR-005**: Inbound A2A tasks MUST transition through the A2A canonical lifecycle states (submitted, working, input-required, completed, failed, cancelled) and expose the current state on the task status endpoint.
- **FR-006**: The platform MUST support outbound A2A calls from platform agents to external A2A-compliant endpoints, including fetching the external Agent Card, submitting the task, polling or streaming the result, and parsing the result into the platform's internal format.
- **FR-007**: All inbound A2A requests MUST be authenticated using one of the authentication schemes declared in the Agent Card; unauthenticated requests MUST be rejected with an A2A-compliant authentication error.
- **FR-008**: All inbound A2A requests, after authentication, MUST pass through an authorization check that verifies the authenticated principal has permission to invoke the targeted platform agent; unauthorized requests MUST be rejected without invoking the agent.
- **FR-009**: All outbound A2A calls MUST pass through the outbound policy check before any network request is made; denials MUST be recorded in the audit log with the reason.
- **FR-010**: A2A outputs — responses returned to external clients AND results from external agents returned to platform agents — MUST be processed through the platform's output sanitization rules to strip secret patterns and disallowed content.
- **FR-011**: The platform MUST expose an SSE streaming endpoint for in-flight A2A tasks that emits A2A-compliant lifecycle events and terminates the stream on task completion or failure.
- **FR-012**: The platform MUST support multi-turn A2A conversations: when a platform agent requests additional input mid-task, the task MUST transition to input-required state; external clients MUST be able to submit follow-up messages that resume the task.
- **FR-013**: External A2A endpoints MUST be registered via an operator-controlled surface; only registered endpoints MAY be invoked by platform agents in client mode (no ad-hoc destinations).
- **FR-014**: External Agent Cards MUST be cached with a configurable TTL; cached cards MUST be used on repeat invocations within the TTL; cache misses and expirations MUST trigger fresh fetches.
- **FR-015**: When an external Agent Card refresh fetch fails and a cached copy exists, the gateway MUST return the cached copy flagged as stale and schedule a retry.
- **FR-016**: Outbound A2A calls to non-HTTPS destinations MUST be denied regardless of allowed-list membership.
- **FR-017**: A2A task rate limits MUST be enforced per authenticated principal; over-limit requests MUST be rejected with an A2A-compliant rate-limit error and logged.
- **FR-018**: Every A2A interaction (inbound and outbound, success and failure) MUST produce an audit record capturing principal, agent, action, result, and timestamp.
- **FR-019**: Inbound A2A task failures MUST NOT disclose internal stack traces, internal agent names not present in the public Agent Card, or secret values in error messages.
- **FR-020**: A2A protocol version negotiation MUST reject requests for unsupported protocol versions with an A2A-compliant error listing the supported versions.
- **FR-021**: External A2A agents whose Agent Cards declare unsupported capabilities or unsupported authentication schemes MUST be refused invocation, with the incompatibility recorded in the audit log.
- **FR-022**: A2A task cancellation initiated by the external client MUST transition the task to cancellation-pending state; when the underlying internal interaction reaches a safe cancellation point, the task MUST terminate in cancelled state and the result MUST be discarded.
- **FR-023**: SSE streams MUST support reconnection with a last-event identifier so subscribers can resume without missing lifecycle transitions.
- **FR-024**: Multi-turn A2A conversations abandoned in input-required state MUST be auto-cancelled after a configurable idle timeout with an audit record.
- **FR-025**: A2A request and response payloads MUST be bounded by a configurable maximum size; over-limit payloads MUST be rejected with a protocol-compliant error.
- **FR-026**: The A2A gateway MUST NOT be used for communication between platform agents; internal agent-to-agent coordination MUST continue to use the existing internal event and service interfaces.
- **FR-027**: The public Agent Card MUST be refreshed automatically when a platform agent's registry metadata or active revision changes; external clients MUST NOT see stale metadata for longer than a defined propagation window.
- **FR-028**: A2A authentication token revocation MUST be checked on every request; revoked tokens MUST NOT be honored even if previously accepted within a session.
- **FR-029**: A2A task results returned to external clients MUST be in the A2A canonical response format regardless of the platform agent's internal output shape.

### Key Entities

- **Agent Card**: The public A2A discovery document describing one or more agents available through an A2A endpoint. Contains agent name, description, endpoint URL, version, capabilities, authentication schemes, and skills. For the platform, auto-generated from registry metadata.
- **A2A Task**: A single A2A invocation instance. Carries task identifier, targeted agent FQN, submitted message, lifecycle state, result (on completion or failure), correlation to an internal interaction record, and protocol-level metadata.
- **A2A Task Status**: The current lifecycle state of an A2A task (submitted, working, input-required, completed, failed, cancelled) along with the timestamp of the last transition and any intermediate progress details.
- **A2A Message**: A single message exchanged within an A2A task — either the initial request, a multi-turn follow-up, a progress update, or a final result. Structured per the A2A protocol message schema.
- **External A2A Endpoint Registration**: An operator-controlled record of an approved external A2A destination — endpoint URL, authentication configuration, outbound policy bindings, cached Agent Card reference, cache TTL.
- **A2A Audit Record**: A record of every A2A interaction capturing principal, agent, action, lifecycle transitions, result, timestamps, and policy-decision outcomes. Stored in the existing audit log.
- **Agent Card Cache Entry**: A cached external Agent Card with TTL, last-fetched timestamp, declared-version snapshot, and staleness flag.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of Agent Card responses reflect the live state of the agent registry — no stale entries persist longer than the propagation window (default 5 minutes).
- **SC-002**: 100% of inbound A2A tasks that target non-public, archived, or revoked agents are rejected with an A2A-compliant "agent not found" error; zero metadata about excluded agents leaks in error messages.
- **SC-003**: 100% of inbound A2A requests pass through authentication AND authorization before any internal agent invocation occurs; zero requests reach the internal invocation path without both checks succeeding.
- **SC-004**: 100% of outbound A2A calls pass through the outbound policy check before any network request is issued; zero outbound calls occur without a prior policy decision.
- **SC-005**: 100% of A2A responses (both directions) pass through output sanitization; zero secret-pattern matches appear in outbound responses when tested against a synthetic secret corpus.
- **SC-006**: 100% of A2A interactions produce an audit record; zero interactions are unaudited.
- **SC-007**: SSE streams deliver lifecycle events within 1 second (p95) of the underlying state transition.
- **SC-008**: External Agent Card cache achieves ≥ 90% hit rate on repeat invocations of the same external endpoint within TTL, as measured under normal operator usage.
- **SC-009**: A2A task lifecycle completeness: 100% of started tasks reach a terminal state (completed, failed, or cancelled); zero tasks are left in a non-terminal state indefinitely.
- **SC-010**: Protocol version mismatch, unsupported capability, and unsupported authentication scheme are each rejected within 100 milliseconds (p95) with the correct A2A error code.
- **SC-011**: A2A task submission to task acceptance latency: ≤ 500 milliseconds (p95) for server mode, excluding the time the internal agent actually spends executing.
- **SC-012**: Multi-turn conversations that reach input-required state and receive a follow-up within the idle timeout resume successfully ≥ 99% of the time on a controlled test suite.
- **SC-013**: External A2A calls to denied destinations (non-HTTPS, not on allowed-list, policy forbidden) fail-closed in 100% of attempts; zero calls bypass the deny decision.
- **SC-014**: No A2A-related regression to existing internal agent coordination: 100% of pre-existing internal tests continue to pass; internal event-and-service-interface communication remains the sole path for intra-platform agent coordination.

## Assumptions

- The A2A open protocol specification at the time of implementation defines the canonical task lifecycle states, Agent Card schema, streaming event format, and error code vocabulary — the platform adopts that specification faithfully without custom extensions.
- The platform agent registry already exposes the metadata fields needed for Agent Card generation (FQN, purpose, version, capabilities, tool bindings, authentication schemes); gaps in existing metadata are out of scope and surface as "excluded from public Agent Card" with operator alerts.
- The existing authentication layer supports the authentication schemes that A2A requires; no new authentication primitives are introduced as part of this feature.
- The existing policy enforcement layer supports the notions of inbound agent-invocation permission, outbound destination allowed-listing, and per-principal rate limiting — this feature wires into those existing surfaces rather than defining new policy primitives.
- The existing output sanitization surface applies uniformly to A2A responses without needing A2A-specific sanitization rules; secret patterns and disallowed content are covered by the shared sanitizer.
- The existing audit log accepts structured records from new bounded contexts; no new audit infrastructure is introduced as part of this feature.
- The existing interaction model is sufficient to back A2A tasks; A2A task state is a projection over the existing interaction record with A2A-specific metadata (task id, protocol version) persisted alongside.
- Server-Sent Events is an acceptable streaming transport for A2A; WebSocket-based streaming is out of scope for this release.
- The public Agent Card is world-readable (anonymous fetch is allowed); authentication is required only when submitting a task, not when discovering available agents.
- External A2A endpoint registration is a privileged operation performed by platform operators, not by arbitrary workspace members.
- Default Agent Card cache TTL is 1 hour; default A2A task input-required idle timeout is 30 minutes; default maximum A2A payload size is 10 MB — all configurable by operators.
- The A2A protocol version supported by this release is a single pinned version; simultaneous support for multiple A2A protocol versions is out of scope.
- Platform agents invoked via A2A see the A2A interaction as an ordinary workspace-scoped interaction — agents are NOT A2A-aware and do not need code changes to be invocable via A2A.
- The gateway is the sole ingress/egress point for A2A traffic; no other component in the platform speaks A2A directly.

## Dependencies

- Existing agent registry (FQN resolution, revisions, purpose, visibility rules, capabilities, tool bindings).
- Existing authentication system (token validation, revocation checking, principal resolution).
- Existing authorization system (per-agent invocation permissions, per-principal rate limits, outbound policy enforcement).
- Existing interaction model (for backing A2A tasks with internal interaction records).
- Existing output sanitization pipeline (for scrubbing responses before they leave the platform OR enter platform agent contexts).
- Existing audit log (for recording all A2A interactions).
- Existing policy engine (for inbound and outbound policy decisions on A2A calls).
- Existing caching infrastructure (for external Agent Card cache entries and TTL management).

## Out of Scope

- Communication between platform-internal agents via A2A (internal coordination stays on the existing event bus and service interfaces per the platform architecture).
- A2A protocol version multiplexing (this release supports a single pinned A2A protocol version).
- WebSocket streaming transport for A2A tasks (SSE is the sole streaming transport in this release).
- Custom A2A protocol extensions beyond the open A2A specification.
- A UI surface for browsing the public Agent Card or for human users to submit A2A tasks; the gateway's consumers are other programmatic agents, not interactive end users.
- Platform-initiated invitation of external A2A clients (no federation handshake, no "invite" flow); discovery remains pull-only via the public Agent Card URL.
- Cross-platform Agent Card federation (e.g., an index of Agent Cards across multiple platforms); each platform publishes its own Agent Card independently.
- Automated discovery of external A2A endpoints via scanning or registries; all external endpoints are explicitly registered by operators.
- Billing, metering, or quota management tied specifically to A2A usage beyond the existing per-principal rate limits.
- A2A-specific retry policies beyond the default transient-vs-permanent error classification; richer retry/backoff strategies are deferred.
- Platform-to-platform shared-state or distributed-transaction semantics over A2A; each A2A task is independent.
