# Feature Specification: Workspace Goal Management and Agent Response Decision

**Feature Branch**: `059-workspace-goal-response`  
**Created**: 2026-04-18  
**Status**: Draft  
**Input**: Brownfield extension of the interactions bounded context. Adds a goal lifecycle state (READY → WORKING → COMPLETE) alongside the existing administrative status, binds posted messages to a specific goal, introduces per-agent-subscription response decision strategies so each agent independently decides whether to respond to a message, supports a best-match mode that guarantees exactly one responder per message, and enables automatic completion of idle goals.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Workspace member posts the first message and the goal activates (Priority: P1)

A workspace member opens a goal that has just been created (state READY, no messages yet) and posts the first message describing what they need help with. The system recognizes this is the first message for the goal and transitions the goal into WORKING state, signaling to subscribed agents that the goal is now live and that messages on this goal may require responses.

**Why this priority**: The READY → WORKING transition is the mechanism that distinguishes a newly-drafted goal (agents should not yet respond) from an active goal (agents should evaluate and respond). Without this, either every goal is active the moment it is created — causing spurious agent activity on still-being-drafted goals — or no goal is ever active — causing agents never to engage. This transition is the foundation of the lifecycle.

**Independent Test**: Create a goal via the existing workspace UI, verify its state is READY and no subscribed agent receives the goal as actionable. Post the first message. Verify the goal state becomes WORKING and that subscribed agents now see the message in their evaluation queue.

**Acceptance Scenarios**:

1. **Given** a newly-created goal in state READY with zero messages, **When** a workspace member posts the first message, **Then** the goal state transitions to WORKING, the message is stored with a reference to the goal, and subscribed agents become eligible to evaluate the message.
2. **Given** a goal already in state WORKING, **When** a second message is posted, **Then** the goal state remains WORKING (no re-transition event is emitted), the message is stored with a reference to the goal, and subscribed agents evaluate the new message.
3. **Given** a goal in state READY, **When** no message has been posted, **Then** no agent receives any evaluation task for that goal and no response is produced.

---

### User Story 2 — Each subscribed agent independently decides whether to respond using a configured strategy (Priority: P1)

When a message is posted to a WORKING goal, each agent subscribed to the workspace and in scope for the goal runs its configured response decision strategy against the message and the goal context. Only agents whose strategy returns "respond" actually produce a response. Agents whose strategy returns "skip" log their rationale and remain silent. Without this filtering, every subscribed agent would respond to every message, producing noise and cost.

**Why this priority**: The response decision is the core value delivery — tuning signal-to-noise without the workspace admin having to unsubscribe/resubscribe agents per conversation turn. P1 because without it the platform is either too noisy (every agent responds every time) or too silent (strategies must be manually invoked). This is the mechanism that makes multi-agent workspaces usable.

**Independent Test**: Configure one agent with a KeywordDecision strategy matching `"deploy"` and a second agent with an AllowBlocklistDecision strategy blocking `"meeting"`. Post a message containing `"deploy the service"` — only the first agent responds. Post a message containing `"meeting notes"` — the second agent explicitly skips and logs its rationale. Post a message containing `"deploy after the meeting"` — the first agent responds, the second skips.

**Acceptance Scenarios**:

1. **Given** an agent with LLM-relevance decision strategy configured (threshold 0.7), **When** a message with semantic relevance 0.82 to the goal is posted, **Then** the agent's decision returns "respond" and the agent produces a response.
2. **Given** an agent with LLM-relevance decision strategy configured (threshold 0.7), **When** a message with semantic relevance 0.34 to the goal is posted, **Then** the agent's decision returns "skip" with a logged rationale (low relevance score), and no response is produced.
3. **Given** an agent with AllowBlocklistDecision strategy with blocked keyword `"personal"`, **When** a message containing `"personal data export"` is posted, **Then** the agent's decision returns "skip" with a logged rationale referencing the matched blocked term.
4. **Given** an agent with KeywordDecision strategy requiring any of `["deploy", "release"]`, **When** a message containing `"ship the next release"` is posted, **Then** the agent's decision returns "respond" naming the matched keyword.
5. **Given** an agent with EmbeddingSimilarityDecision strategy with reference embeddings and similarity threshold 0.80, **When** a message produces cosine similarity 0.72 to all references, **Then** the agent's decision returns "skip" with similarity score in the rationale.
6. **Given** multiple agents with different decision strategies subscribed to the same workspace, **When** a single message is posted, **Then** each agent's decision runs independently and each agent either responds or skips according to its own strategy.

---

### User Story 3 — Completed goal preserves history and blocks new messages (Priority: P1)

A workspace admin (or the goal owner) marks a goal COMPLETE when the objective has been achieved. After the transition, the goal becomes read-only: attempts to post new messages are rejected with a clear explanation, but all prior messages and agent responses remain viewable. This keeps resolved work archived and prevents accidental re-opening.

**Why this priority**: Without terminal-state enforcement, completed goals silently accumulate new messages — agents keep responding to "settled" goals, cost accrues, and the completion signal loses meaning. This is P1 because it pairs with US1: if READY and WORKING exist without a real COMPLETE, the lifecycle is incomplete.

**Independent Test**: Create and transition a goal to COMPLETE. Attempt to post a message; verify rejection with a clear message. Verify existing messages are still readable. Verify agents receive no new evaluation tasks for messages attempted on the completed goal.

**Acceptance Scenarios**:

1. **Given** a goal in state WORKING with an ongoing conversation, **When** the workspace admin transitions the goal to COMPLETE, **Then** the transition succeeds, the goal is marked COMPLETE, and a completion event is emitted for audit.
2. **Given** a goal in state COMPLETE, **When** any user attempts to post a new message, **Then** the request is rejected with a clear explanation that the goal is complete and cannot accept new messages, and no message is stored.
3. **Given** a goal in state COMPLETE, **When** a user views the goal, **Then** all prior messages and agent responses remain readable.
4. **Given** a goal in state COMPLETE, **When** a subscribed agent is evaluated against historical messages, **Then** the agent does NOT produce new responses retroactively.

---

### User Story 4 — Best-match mode routes each message to a single agent (Priority: P2)

A workspace admin configures best-match mode on a subscription. When a message is posted and best-match mode applies, every eligible agent's decision strategy is run, each returning a score representing confidence or relevance. The single highest-scoring agent is selected to respond; all others skip. Ties break deterministically (earliest subscription wins). This prevents multiple agents from producing overlapping or duplicate answers when only one response is desired.

**Why this priority**: Best-match is important for efficiency and user experience but secondary to the fundamental decision mechanism. Multi-agent workspaces can run without best-match (all passing agents respond in parallel) — best-match is an optimization mode. P2 because it improves UX and cost but is not required for correctness.

**Independent Test**: Configure three agents with best-match mode. Post a message. Verify exactly one agent responds, that the rationale log shows all agents scored, and that the response came from the agent with the highest score. With a second post producing identical scores, verify the earliest-subscribed agent wins.

**Acceptance Scenarios**:

1. **Given** three agents configured with best-match mode and scoring strategies, **When** a message is posted and scores are (0.82, 0.71, 0.45), **Then** only the agent with score 0.82 produces a response; the other two skip with logged rationales citing "not selected in best-match".
2. **Given** three agents in best-match mode where two produce identical top scores, **When** a message is posted, **Then** the agent with the earliest subscription date is selected; the rationale log records the tie-break reason.
3. **Given** best-match mode enabled on a subscription, **When** every agent's strategy returns a "skip" decision (no eligible responders), **Then** no response is produced and the system logs that best-match found no candidates for that message.

---

### User Story 5 — Idle goals auto-complete after a configurable timeout (Priority: P2)

A workspace admin sets an auto-completion timeout on a goal (for example, 24 hours). If no new messages arrive within that window, the goal automatically transitions to COMPLETE. This reduces the operational burden of manually closing every goal and keeps the workspace view focused on currently-active goals.

**Why this priority**: Auto-completion reduces manual overhead but the platform works correctly without it (admins can close goals manually). P2 because it is a quality-of-life improvement with measurable cost/focus benefit.

**Independent Test**: Create a goal with `auto_complete_timeout_seconds` of 60. Post one message. Wait 65 seconds without posting. Verify the goal has transitioned to COMPLETE automatically and that an auto-completion event was emitted. Before the window elapses, post another message and confirm the goal remains WORKING and the timeout is reset.

**Acceptance Scenarios**:

1. **Given** a WORKING goal with `auto_complete_timeout_seconds` of 60 and a last-message time of T, **When** the current time exceeds T + 60 and no new message has arrived, **Then** the goal transitions to COMPLETE automatically and an auto-completion audit event is emitted.
2. **Given** a WORKING goal with a timeout configured, **When** a new message is posted before the window elapses, **Then** the timeout resets relative to the new message's timestamp and the goal remains WORKING.
3. **Given** a goal with `auto_complete_timeout_seconds` set to zero or null, **When** any amount of time elapses, **Then** the goal is NOT auto-completed and remains in its current state indefinitely.
4. **Given** a goal already in state COMPLETE, **When** the auto-completion scanner runs, **Then** the goal is not transitioned again and no duplicate event is emitted.

---

### User Story 6 — Decision rationale is persisted and queryable (Priority: P3)

An agent owner or workspace admin investigating why an agent did or did not respond to a particular message can retrieve the decision rationale: which strategy ran, the score or match details, and the resulting decision. This supports tuning of strategies and debugging of unexpected silence or noise.

**Why this priority**: Important for observability and long-term tuning but not blocking for core functionality. Admins can iterate on strategies without rationale logs in the short term.

**Independent Test**: Post several messages through different agent strategies. Query the decision log for one message. Verify that for each agent subscribed to the workspace, the log contains the strategy name, the inputs evaluated, the computed score or match details, and the final decision. Verify the log contains no raw secrets or model API keys.

**Acceptance Scenarios**:

1. **Given** a message that has been evaluated by multiple agents, **When** the admin queries the decision log for that message, **Then** the log returns one entry per subscribed agent with strategy name, decision (respond/skip), score (if applicable), matched keywords (if applicable), and timestamp.
2. **Given** a decision log entry, **When** any field is inspected, **Then** no client secrets, model API keys, or full raw-message text (beyond what is necessary to identify the match) appear in the record.

---

### Edge Cases

- **Message posted to a goal that is mid-transition**: If a transition (e.g., to COMPLETE) is happening concurrently with a message post, exactly one of the following MUST occur atomically: the message is accepted (goal still WORKING) and the transition is blocked from moving to COMPLETE for this instant, OR the transition succeeds and the message is rejected. No inconsistent state where a message is stored against a COMPLETE goal.
- **Goal transition attempt from terminal state**: Any attempt to transition a COMPLETE goal back to WORKING or READY MUST be rejected. The lifecycle is one-directional.
- **Unknown strategy name in configuration**: If a subscription's configured strategy name does not match any registered strategy, the system MUST fail safely (default to "skip" with a clear error logged), not crash or default to "respond".
- **Invalid strategy configuration parameters**: If the configuration parameters are missing or malformed (e.g., a KeywordDecision with no keywords), the system MUST fail safely and log the configuration error, not respond to every message or every-few.
- **Strategy evaluation failure (e.g., embedding service timeout)**: If a strategy's evaluation errors out, the agent defaults to "skip" and the error is logged in the decision rationale. The platform does not retry indefinitely and does not silently respond.
- **Best-match mode with only one subscribed agent**: If best-match mode is enabled and only one agent is subscribed, that agent participates in best-match selection of one — its decision is applied normally (respond or skip) with no tie-break.
- **Best-match tie-break stability**: When two or more agents produce the same top score, the tie-break MUST be deterministic so repeated evaluations of the same message against the same subscriptions yield the same winner. Earliest-subscription is the tie-break rule.
- **Auto-completion race with user activity**: If the auto-completion scanner begins transitioning a goal at the same moment a user posts a new message, the post MUST win (goal remains WORKING) if the scanner has not yet committed the transition; otherwise the user's post MUST be rejected with a COMPLETE-state message.
- **Concurrent decision rationale writes**: Multiple agents writing decision rationales for the same message MUST each produce independent records; partial writes MUST NOT overwrite other agents' rationales.
- **Subscription revoked mid-evaluation**: If an agent's subscription is removed between message post and decision evaluation, the decision is skipped (no response) and the rationale log records the reason.
- **Goal transitions to COMPLETE while decision is evaluating**: Decisions that began evaluating before the transition MAY complete and, if they decide to "respond", MAY produce a response that is delivered before the goal is marked COMPLETE; no new decision begins once COMPLETE.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A workspace goal MUST carry a lifecycle state with three values: READY (newly created, not yet active), WORKING (accepting messages, agents evaluate), COMPLETE (terminal, read-only). This state is independent of any existing administrative status field on the goal.
- **FR-002**: A new goal MUST start in state READY by default.
- **FR-003**: The goal MUST transition from READY to WORKING exactly once, automatically, when the first message is posted to the goal.
- **FR-004**: The goal MAY transition from WORKING to COMPLETE at any time via an explicit workspace admin action, or automatically via the auto-completion timeout mechanism.
- **FR-005**: The goal MUST NOT transition from COMPLETE back to WORKING or READY under any circumstances. The terminal state is one-directional.
- **FR-006**: The goal MUST NOT transition directly from READY to COMPLETE without passing through WORKING (except as a workspace admin archival action, if supported, which is out of scope for this feature).
- **FR-007**: The platform MUST reject any attempt to post a new message to a goal in state COMPLETE with a clear explanation and MUST NOT store the rejected message.
- **FR-008**: The platform MUST reject any attempt to post a message to a goal in state READY that is NOT the first message (i.e., if some condition produces such a case) — however in practice the first message itself triggers the READY→WORKING transition atomically, so this edge should not normally be observable.
- **FR-009**: Every stored message MUST carry a reference to the goal it belongs to; messages without a goal reference MUST NOT be accepted.
- **FR-010**: The platform MUST support configurable per-agent-subscription response decision strategies from a defined catalog: LLM-relevance, allow/blocklist, keyword matching, embedding similarity, and best-match (composite).
- **FR-011**: The LLM-relevance strategy MUST evaluate a message against the goal context and return a "respond" decision when the computed relevance score meets or exceeds a configurable threshold; otherwise "skip".
- **FR-012**: The allow/blocklist strategy MUST return "skip" when a message contains any term from the configured blocklist, "respond" when it matches any term from the configured allowlist and no blocklist term, and fall through to a configured default otherwise.
- **FR-013**: The keyword strategy MUST return "respond" when a message contains configured keywords according to a configurable match mode (any-of or all-of); otherwise "skip".
- **FR-014**: The embedding-similarity strategy MUST compute semantic similarity between the message and configured reference embeddings, returning "respond" when similarity meets or exceeds a configurable threshold; otherwise "skip".
- **FR-015**: The best-match strategy MUST run all other participating agents' strategies, score the candidates, and return "respond" only for the single highest-scoring agent. All other agents in best-match scope MUST skip.
- **FR-016**: Best-match ties MUST be broken deterministically by earliest subscription date; the tie-break reason MUST be recorded in the decision rationale.
- **FR-017**: Each agent's decision for each message MUST be computed independently (except when best-match explicitly requires cross-agent comparison); agents MUST NOT share or influence each other's decisions outside of the best-match mechanism.
- **FR-018**: Every decision (respond or skip) MUST persist a rationale record containing: agent identifier, message identifier, strategy name, decision, score (when applicable), matched keywords or terms (when applicable), and timestamp.
- **FR-019**: Decision rationale records MUST NOT contain secrets, API keys, or any credentials required to invoke the strategy's backing services.
- **FR-020**: Rationale records MUST NOT contain the full raw text of messages beyond what is necessary to identify the match (e.g., a matched keyword span); the authoritative message text stays in the messages store.
- **FR-021**: A configuration error (unknown strategy name, missing required strategy parameters, invalid thresholds) MUST cause the affected subscription to fail safely to "skip" decisions, NOT default to "respond", and MUST log the configuration error.
- **FR-022**: A strategy evaluation runtime error (timeout, downstream service failure) MUST cause that single evaluation to return "skip" with the error noted in the rationale, NOT retry indefinitely and NOT produce a response.
- **FR-023**: A goal MAY have a configurable auto-completion timeout measured in seconds; when set, the platform MUST automatically transition the goal to COMPLETE if no message has been posted within the timeout window measured from the most-recent message's timestamp.
- **FR-024**: A null or zero auto-completion timeout MUST mean "never auto-complete"; the goal remains in its current state indefinitely.
- **FR-025**: An auto-completion transition MUST emit the same terminal-state audit event as a manually triggered transition, with an indicator that the transition was automatic.
- **FR-026**: Goal lifecycle transitions (READY→WORKING, WORKING→COMPLETE, auto-completion) MUST be atomic with respect to concurrent message posts: either the post succeeds (goal remains WORKING or just transitioned to WORKING) or the post is rejected (goal is COMPLETE), never a partial or inconsistent outcome.
- **FR-027**: The response-decision configuration MUST be attached to the agent's subscription to the workspace (one configuration per subscription per agent), NOT to the goal or the message, so that an agent's behavior across a workspace is consistent by default with the subscription-level choice.
- **FR-028**: Workspace admins MUST be able to change a subscription's response-decision strategy and configuration at any time; new decisions use the updated configuration; in-flight decisions are unaffected.
- **FR-029**: The platform MUST emit a domain event for each terminal-state transition (manual COMPLETE, auto-completion) so downstream consumers (audit, notifications, analytics) can react.

### Key Entities

- **Workspace Goal (extended)**: Existing record representing an objective within a workspace. Extended in this feature to carry a new lifecycle state (READY, WORKING, COMPLETE) and an auto-completion timeout. The new state is independent of any existing administrative status attribute on the goal; both coexist until a future feature reconciles them.
- **Goal-Bound Message**: A message posted within a workspace, always associated with exactly one goal. Messages without a goal reference are not accepted.
- **Agent Subscription (extended)**: Existing record representing an agent's subscription to receive messages in a workspace. Extended in this feature to carry a response-decision strategy name and a strategy-specific configuration object.
- **Response Decision Strategy**: A named strategy that, given a message and a goal context, produces a "respond" or "skip" decision. Registered strategies include LLM-relevance, allow/blocklist, keyword, embedding-similarity, and best-match. Each has a strategy-specific configuration schema.
- **Decision Rationale**: An immutable audit record, one per (agent, message) evaluation pair, containing the strategy used, the decision, the score or match details, and the timestamp. Queryable by message, by agent, or by decision outcome.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A newly created goal is in state READY in 100% of cases and never receives agent evaluations while in READY.
- **SC-002**: The READY → WORKING transition occurs within 1 second of the first message being posted, in 100% of cases.
- **SC-003**: A goal in state COMPLETE rejects 100% of new message posts with a clear, actionable error message.
- **SC-004**: A goal in state COMPLETE never causes a new agent response to be produced (verified by zero agent-response events occurring against any message that arrives after the COMPLETE transition).
- **SC-005**: When a message is posted to a WORKING goal, every subscribed agent's decision runs within 2 seconds, in 95% of cases (the 95th-percentile decision latency SLA).
- **SC-006**: Each decision strategy correctly filters at least 98% of test cases against a representative labelled dataset of (message, expected-decision) pairs (e.g., keyword strategy matches known keyword sets with ≥98% precision and recall).
- **SC-007**: In best-match mode, exactly one agent responds per message in 100% of cases where at least one agent's strategy would have returned "respond" individually.
- **SC-008**: Best-match tie-breaking produces the same winner across repeated evaluations of the same (subscriptions, message) input in 100% of cases.
- **SC-009**: A goal with an auto-completion timeout of T seconds and no new messages transitions to COMPLETE within T + 60 seconds of the last message, in 100% of cases.
- **SC-010**: Decision rationale records exist for 100% of (agent, message) evaluation pairs that reached strategy execution, and no rationale record contains any credential or secret material (verifiable by automated scan).
- **SC-011**: Workspace admins can change a subscription's strategy and see the new strategy take effect on the next message within 5 seconds.
- **SC-012**: The proportion of messages that receive exactly one response versus zero versus multiple is observable via a workspace dashboard metric after rollout; the specific targets (e.g., at most 15% of messages receive zero responses) are tenant-dependent.

## Assumptions

- The workspace, goals, agents, subscriptions, and messages bounded contexts already exist (from prior features). This feature extends them additively.
- Agents subscribed to a workspace see messages posted in that workspace, subject to existing visibility rules. The response-decision mechanism is applied on top of existing visibility — a decision never grants an agent access it would not otherwise have.
- The existing goal administrative status (e.g., open/in_progress/completed/cancelled) is orthogonal to the new lifecycle state in this feature. The two coexist; a future feature may reconcile or migrate one into the other. For this feature, only the new lifecycle state governs response-decision behavior and message acceptance.
- The embedding service used by the embedding-similarity strategy is the platform's existing vector/embedding infrastructure; this feature does not introduce new embedding providers or new indexes.
- The LLM used by the LLM-relevance strategy is the platform's existing configured model provider; this feature does not introduce new model providers.
- Auto-completion runs as a periodic background scan (frequency chosen so that SC-009's T+60 upper bound is met); the scan is idempotent — running it on an already-COMPLETE goal is a no-op.
- Clock drift between any auto-completion scanner instance and the database is within ±30 seconds, acceptable for the SC-009 ±60-second upper bound.
- Decision rationale retention follows the platform's existing audit-retention policy; this feature does not introduce new retention rules.

## Dependencies

- The existing interactions bounded context (conversations, interactions, workspace goals, workspace goal messages) — this feature extends the goal record, the message record, and the subscription record.
- The existing policy/visibility engine — decision strategies operate within the bounds of what the agent is already authorized to see; this feature does not bypass or override visibility.
- The existing workspace administration UI — the response-decision configuration surface is a new panel within the existing per-subscription configuration screen.
- The existing audit/event infrastructure — terminal-state events and decision rationale records publish through existing channels.
- The existing embedding/vector infrastructure (used by the embedding-similarity strategy).
- The existing model-provider infrastructure (used by the LLM-relevance strategy).

## Out of Scope

- Reconciliation of the new lifecycle state with the existing administrative status column on the goal — a later feature may merge them, but they coexist as independent attributes for now.
- Adding new decision strategies beyond the five defined in this feature (LLM-relevance, allow/blocklist, keyword, embedding-similarity, best-match). Additional strategies (e.g., ML-classifier, rule-engine) may be added later within the same strategy-registry contract.
- Multi-tier best-match (e.g., top-K instead of top-1). Best-match selects exactly one responder.
- Per-message overrides of the subscription's strategy (forcing a specific strategy for a specific message). Strategy is chosen at the subscription level.
- Cross-workspace decision strategies (e.g., a single agent having different strategies in different workspaces via a single configuration). Strategies are per-subscription, which is inherently per-workspace.
- Bidirectional goal state changes (reopening a COMPLETE goal). The lifecycle is one-directional.
- Retroactive decision rationale generation for messages that predate this feature; rationale records begin accumulating from this feature's rollout forward.
- Machine learning-driven strategy optimization (automatic threshold tuning). All thresholds are admin-configured.
