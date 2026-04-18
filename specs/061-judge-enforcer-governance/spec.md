# Feature Specification: Judge/Enforcer Agent Roles and Governance Pipeline

**Feature Branch**: `061-judge-enforcer-governance`  
**Created**: 2026-04-18  
**Status**: Draft  
**Input**: Brownfield extension. Introduces two formal agent roles (`judge` and `enforcer`) and a governance pipeline that connects observer signals to judge evaluations and enforcer actions. Each fleet and workspace can configure a governance chain (observer → judge → enforcer) that routes detected behavioral or policy signals through a structured evaluation and enforcement path. Verdicts and actions are persisted with full evidence and rationale so that every enforcement outcome can be audited, reviewed, and contested.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Observer signal triggers judge evaluation and verdict (Priority: P1)

A behavioral observer (e.g., an anomaly detector, an output-sanitization monitor, a trust-signal scorer) detects a concerning event about an agent or interaction and emits a signal onto the governance channel. The configured judge agent for that fleet/workspace receives the signal, evaluates it against the bound policy, and emits a structured verdict with a verdict type (compliant, warning, violation, or escalate-to-human), policy reference, evidence payload, rationale text, and a recommended action. The verdict is persisted and made available to downstream consumers.

**Why this priority**: This is the core of the Observer → Judge → Enforcer pattern. Without judge evaluation on observer signals, there is no governance loop — signals would be collected but never acted upon. Every downstream capability (enforcement, audit trail, contestation) depends on verdicts existing. P1 because the governance pipeline has no operational meaning without this step.

**Independent Test**: Configure a test fleet with a governance chain where an observer agent feeds a judge agent bound to a specific policy. Emit a test observer signal that clearly violates the policy. Verify the judge evaluates and emits a verdict within the latency SLA, that the verdict is persisted with policy id, evidence, and rationale, and that the `governance.verdict.issued` event appears for downstream consumers.

**Acceptance Scenarios**:

1. **Given** a fleet with an Observer→Judge chain configured and a policy bound, **When** an observer emits a signal that violates the policy, **Then** the judge evaluates the signal and emits a verdict with `verdict_type=VIOLATION`, the bound policy reference, and a rationale explaining why the signal violates the policy.
2. **Given** the same configuration, **When** an observer emits a signal that does not violate any bound policy, **Then** the judge emits a verdict with `verdict_type=COMPLIANT` and a rationale explaining why no violation was detected.
3. **Given** an observer signal with ambiguous policy implications, **When** the judge cannot reach a confident verdict, **Then** the judge emits `verdict_type=ESCALATE_TO_HUMAN` with a rationale and a recommended action for human review.
4. **Given** a fleet without any configured governance chain, **When** an observer emits a signal, **Then** no judge evaluation occurs and no verdict is persisted; the signal is simply ignored by the governance pipeline.
5. **Given** a fleet with a configured chain, **When** the bound policy has been deleted, **Then** the judge emits a verdict with `verdict_type=ESCALATE_TO_HUMAN`, rationale references the missing policy, and an incident log entry is created.

---

### User Story 2 — Enforcer executes configured action on verdict (Priority: P1)

When a judge emits a verdict, the configured enforcer agent for the same fleet/workspace receives the verdict and executes an action derived from the verdict type and the fleet/workspace enforcement configuration. Actions include blocking the target agent's next operation, quarantining the agent into a restricted state, notifying the operator or target user, revoking the agent's certification, or logging the event and continuing. Every enforcement action is persisted with a reference to the triggering verdict and an outcome payload describing what actually happened.

**Why this priority**: Verdicts without enforcement are inert — the platform would detect policy violations but take no action. Closing the loop is what makes the governance pipeline operationally meaningful. P1 because US1 (judge) alone delivers no behavioral change; US2 is required to actualize the governance posture.

**Independent Test**: Configure a fleet with an Observer→Judge→Enforcer chain, enforcement config mapping `VIOLATION` to `block`. Emit an observer signal that produces a VIOLATION verdict. Verify the enforcer executes the `block` action on the target agent within the latency SLA, that an `enforcement_actions` record is persisted with `action_type=block`, verdict id, target agent id, and outcome, and that a `governance.enforcement.executed` event is published.

**Acceptance Scenarios**:

1. **Given** a fleet with enforcement config mapping `VIOLATION` → `block`, **When** a judge emits a `VIOLATION` verdict for target agent A, **Then** the enforcer blocks A's next operation and persists an enforcement action with `action_type=block`, reference to the verdict, and an outcome indicating the block took effect.
2. **Given** enforcement config mapping `WARNING` → `notify`, **When** a judge emits a `WARNING` verdict, **Then** the enforcer notifies the configured recipient (fleet operator or target user per config) and persists the enforcement action with outcome capturing the delivery receipt.
3. **Given** enforcement config mapping `ESCALATE_TO_HUMAN` → `quarantine`, **When** a judge emits an escalation verdict, **Then** the enforcer moves the target agent into a quarantine state, persists the enforcement action, and the agent cannot perform further operations until a human resolves the escalation.
4. **Given** enforcement config mapping `VIOLATION` → `revoke_cert`, **When** a judge emits a `VIOLATION` verdict, **Then** the enforcer revokes the target agent's active certification through the certification subsystem and persists the enforcement action with the revocation outcome.
5. **Given** enforcement config mapping a verdict type → `log_and_continue`, **When** that verdict arrives, **Then** the enforcer persists the enforcement action with `action_type=log_and_continue` and an outcome indicating no behavioral change was applied; the target agent continues operating normally.
6. **Given** a verdict arrives for which the fleet has no matching enforcement config, **When** the enforcer processes it, **Then** it defaults to `log_and_continue`, records the unmapped verdict type in the outcome, and emits an incident log entry for operator review.

---

### User Story 3 — Admin configures governance chain per fleet and workspace (Priority: P2)

An administrator opens the governance configuration surface for a fleet or workspace and selects which agents serve as observer, judge, and enforcer within the chain. The admin can also configure the verdict-to-action mapping used by the enforcer (e.g., `VIOLATION → block`, `WARNING → notify`). The platform validates that the referenced agents exist and have the correct role (judges must have the `judge` role, enforcers must have the `enforcer` role). Fleets can layer multiple judges in the chain; chains can be different per fleet and per workspace. A fleet/workspace without a configured chain has no governance enforcement.

**Why this priority**: Configurability is what makes governance fit diverse compliance postures — a finance fleet and a research fleet have different enforcement needs. Without per-fleet/workspace configuration, the platform would need a single global governance chain, which does not fit multi-tenant reality. P2 because a minimal operational governance loop (US1 + US2) can run with a default chain; configurability is what turns this into a reusable platform capability.

**Independent Test**: Create two fleets, configure different governance chains (one with judge A + enforcer X mapping `VIOLATION→block`; the other with judge B + enforcer Y mapping `VIOLATION→quarantine`). Emit matching observer signals to both. Verify each fleet produces verdicts from its own judge and enforcement actions from its own enforcer with its own action type. Attempt to configure a chain referencing a non-existent judge agent — verify the configuration is rejected with a clear error.

**Acceptance Scenarios**:

1. **Given** an admin with permission to manage a fleet, **When** they configure the governance chain with valid observer/judge/enforcer agent references and a verdict-to-action mapping, **Then** the chain is persisted on the fleet record, becomes effective for subsequent signals, and is retrievable for review.
2. **Given** an admin configuring a chain, **When** they reference an agent whose role is not `judge` as a judge, **Then** the configuration is rejected with a validation error identifying the role mismatch.
3. **Given** an admin configuring a chain, **When** they reference an agent that does not exist, **Then** the configuration is rejected with a validation error identifying the unknown agent reference.
4. **Given** an existing chain is in use, **When** the admin replaces the judge agent, **Then** subsequent signals route to the new judge; verdicts in flight complete against whichever judge received the signal, and the change is recorded in the governance audit trail.
5. **Given** a workspace without a configured chain and a containing fleet with a chain, **When** an observer signal fires for a workspace-scoped target, **Then** the fleet-level chain applies; workspace-level chains override fleet-level chains when both are configured.

---

### User Story 4 — Audit trail query for verdicts and enforcement actions (Priority: P2)

A compliance officer or operator reviewing governance activity opens a query surface and filters verdicts and enforcement actions by time range, target agent, policy, verdict type, action type, or fleet/workspace. The results show every verdict with its full evidence, rationale, policy reference, and the enforcement action that followed (if any), in chronological order. Individual verdict records can be opened to inspect the complete evidence payload. Every record includes timestamps, actor (judge or enforcer) identifiers, and trace correlation so the full causal chain from observer signal to enforcement outcome can be reconstructed.

**Why this priority**: Audit trail is how governance becomes defensible in the face of compliance review, user contestation, or post-incident analysis. Without it, verdicts and actions exist only as runtime events — not a recoverable record. P2 because the runtime enforcement (US1 + US2) can operate without the audit surface, but governance is hollow without auditability.

**Independent Test**: Generate a sequence of governance events: one COMPLIANT verdict, one WARNING with notify action, one VIOLATION with block action, and one ESCALATE_TO_HUMAN with quarantine action, each spaced across time for agent X. Open the audit query, filter by agent X and the time range. Verify all four verdicts appear with their verdict types, policy references, rationales, and corresponding enforcement actions. Verify the VIOLATION→block record shows action_type=block and the target_agent_id matching X.

**Acceptance Scenarios**:

1. **Given** a compliance user querying verdicts by agent, **When** they filter for a specific agent over a 7-day window, **Then** they receive every verdict issued for that agent within the window, with rationale, evidence reference, policy id, and verdict type visible.
2. **Given** a compliance user querying enforcement actions, **When** they filter by action_type=revoke_cert, **Then** they see every certification revocation with the triggering verdict id and the target agent identity.
3. **Given** a compliance user opening a single verdict record, **When** they request detail, **Then** they see the complete evidence payload, rationale text, the source observer event identifier, the judge agent identity and role, and (if an enforcement action exists) the follow-up action record with outcome detail.
4. **Given** verdicts older than the governance retention window, **When** the retention job runs, **Then** expired verdicts and their enforcement actions are removed according to the retention policy and no longer appear in queries.
5. **Given** a user without the compliance viewing role, **When** they attempt to query verdicts, **Then** the request is denied with an authorization error.

---

### User Story 5 — Governance pipeline supports multiple layered judges (Priority: P3)

A fleet can configure a governance chain with more than one judge (e.g., a fast rule-based judge followed by a slower LLM-based judge). The platform routes observer signals through judges in configured order; if the first judge emits a non-terminal verdict (e.g., COMPLIANT or WARNING with no enforcement configured), the signal continues to the next judge. If a judge emits a terminal verdict (VIOLATION or ESCALATE_TO_HUMAN), the chain stops and the enforcer receives the terminal verdict. All intermediate verdicts are persisted for audit.

**Why this priority**: Layered evaluation is valuable for production governance where cheap-fast filters reduce load on expensive-slow judges. Not required for the initial operational loop. P3 because a single-judge chain covers most cases; layered judges are an optimization/expressiveness feature that can be added after the core works.

**Independent Test**: Configure a chain with two judges: judge A (rule-based, fast) and judge B (LLM-based, thorough) in order. Emit an observer signal. Verify judge A runs first and emits its verdict. If COMPLIANT, verify judge B also runs and emits its verdict. If judge A emits VIOLATION, verify judge B does NOT run and the enforcer receives judge A's verdict. All intermediate verdicts are persisted.

**Acceptance Scenarios**:

1. **Given** a two-judge chain and an observer signal, **When** the first judge emits COMPLIANT, **Then** the second judge receives the signal, emits its own verdict, and both verdicts are persisted.
2. **Given** a two-judge chain and an observer signal, **When** the first judge emits VIOLATION, **Then** the second judge does not run, the enforcer receives only the first judge's verdict, and only that verdict is persisted.
3. **Given** a two-judge chain and an observer signal, **When** the first judge emits ESCALATE_TO_HUMAN, **Then** the second judge does not run and the enforcer receives the escalation verdict.

---

### Edge Cases

- **Judge agent unavailable at evaluation time**: Signal is logged as pending; an incident log entry is created; if the judge does not recover within a configurable timeout, the signal is treated as ESCALATE_TO_HUMAN and routed to the enforcer.
- **Enforcer agent unavailable when verdict arrives**: Verdict is persisted and queued; the enforcer retries delivery up to a configured maximum; an operator alert fires if the queue grows beyond a threshold.
- **Multiple observer signals about the same target within a short window**: Each signal produces an independent verdict; no deduplication at the verdict layer; enforcement actions are idempotent per-verdict (a second block action for an already-blocked agent is a no-op with outcome noting the existing state).
- **Judge emits a verdict but with missing required fields (evidence or rationale)**: Verdict is rejected at persistence, an incident log entry is created, and the signal is re-routed as ESCALATE_TO_HUMAN so it is not silently dropped.
- **Target agent is deleted between verdict issuance and enforcement execution**: The enforcement action is persisted with outcome noting the target no longer exists; no behavioral action is attempted; the record remains for audit.
- **Governance chain changed while a signal is being evaluated**: The in-flight evaluation completes against the chain that was active when the signal was routed; subsequent signals use the updated chain.
- **Circular governance chain (judge under evaluation is itself the target)**: Platform rejects the configuration at save time; cannot configure an agent to judge itself.
- **Fleet belongs to multiple hierarchical contexts (workspace, organization)**: Workspace-level chain wins when present; fleet-level chain is the default; no deeper hierarchy is consulted in this feature.
- **Enforcement action references a target in a different workspace than the verdict's fleet/workspace**: The enforcement action is still persisted but marked cross-workspace; the enforcer's cross-workspace permission is checked before the action is actually executed.
- **Retention removes a verdict while its enforcement action is still visible**: Both are removed together via cascade; enforcement actions cannot outlive their parent verdicts in the audit trail.
- **Bulk signal spike from a misbehaving observer**: Governance pipeline applies per-source rate limiting so a single observer cannot overwhelm the judge; excess signals are dropped with an incident log entry.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST support `judge` and `enforcer` as formal agent role types so that agents can be registered with these roles and governance logic can check role eligibility.
- **FR-002**: The platform MUST support configuring a governance chain on a fleet and on a workspace; each chain MUST identify the observer source(s), the ordered sequence of judge agents, and the enforcer agent, plus the verdict-to-action mapping used by the enforcer.
- **FR-003**: When an observer emits a signal on the governance channel and the fleet (or containing workspace) has a configured chain, the platform MUST route the signal to the first judge in the chain.
- **FR-004**: A judge receiving a signal MUST evaluate it against the bound policy and emit a verdict carrying: verdict type (COMPLIANT, WARNING, VIOLATION, or ESCALATE_TO_HUMAN), policy reference, evidence payload, rationale text, recommended action (optional), source event identifier, and the judge agent identity.
- **FR-005**: Every verdict MUST be persisted so that it can be retrieved for audit, regardless of whether an enforcement action is configured.
- **FR-006**: When a judge emits a verdict, the platform MUST publish it to the `governance.verdict.issued` channel so downstream consumers (enforcer, audit log, operator dashboard) can react.
- **FR-007**: The enforcer MUST consume verdicts on the `governance.verdict.issued` channel and, for each verdict, look up the verdict-to-action mapping on the relevant fleet/workspace chain.
- **FR-008**: For each matched mapping, the enforcer MUST execute the configured action (block, quarantine, notify, revoke_cert, or log_and_continue) and persist an enforcement action record with: enforcer agent identity, verdict reference, action type, target agent (if applicable), and outcome payload.
- **FR-009**: When an enforcement action completes, the platform MUST publish it to the `governance.enforcement.executed` channel for audit and dashboard consumers.
- **FR-010**: When a verdict has no matching enforcement mapping for its verdict type, the enforcer MUST default to `log_and_continue` and record the unmapped verdict type in the outcome.
- **FR-011**: The platform MUST validate that agents referenced as judge in a chain have the `judge` role, and agents referenced as enforcer have the `enforcer` role; configurations with role mismatches MUST be rejected with a clear error.
- **FR-012**: The platform MUST reject governance chain configurations that reference non-existent agents, with a clear error identifying the unknown agent reference.
- **FR-013**: Workspace-level governance chains MUST take precedence over fleet-level chains when both are configured for a target.
- **FR-014**: When a governance chain change occurs, in-flight signals MUST complete against the chain active at routing time; subsequent signals MUST use the updated chain.
- **FR-015**: Every verdict record MUST carry an identifier that links it to its source observer signal so the full causal chain can be reconstructed for audit.
- **FR-016**: Every enforcement action record MUST carry an identifier linking it to the verdict that triggered it; orphan enforcement actions (no referenced verdict) MUST NOT exist.
- **FR-017**: The platform MUST expose a governance audit query surface allowing filtering verdicts by target agent, policy, verdict type, time range, and fleet/workspace, and enforcement actions by action type and time range.
- **FR-018**: Audit queries MUST require the compliance-viewing role; unauthorized users MUST be denied with an authorization error.
- **FR-019**: Verdicts and enforcement actions MUST be retained for a configurable retention window; records older than the window MUST be removed by a scheduled garbage-collection process and cascaded so enforcement actions do not outlive their parent verdicts.
- **FR-020**: When a bound policy referenced in a chain has been deleted, the judge MUST emit an ESCALATE_TO_HUMAN verdict with the missing-policy detail in the rationale, and an incident log entry MUST be created.
- **FR-021**: When the configured judge agent is unavailable beyond a configurable timeout, the platform MUST route the signal as ESCALATE_TO_HUMAN to the enforcer so that the signal is not silently dropped.
- **FR-022**: Enforcement actions MUST be idempotent per-verdict so retrying the enforcer's execution after a partial failure does not duplicate side effects (e.g., two block actions for the same verdict result in a single effective block with outcome noting prior state).
- **FR-023**: When a verdict fails validation at persistence (missing required fields), the platform MUST log the incident and re-route the originating signal as ESCALATE_TO_HUMAN rather than silently discarding.
- **FR-024**: The platform MUST enforce per-observer rate limiting on governance signals so a single observer cannot flood the judge with more than a configured threshold of signals per minute; excess signals MUST be dropped with an incident log entry.
- **FR-025**: The platform MUST reject governance chain configurations that create self-referential loops (e.g., configuring an agent as its own judge); detection MUST occur at save time with a clear error.
- **FR-026**: When an enforcement action's target agent has been deleted between verdict issuance and action execution, the platform MUST persist the action with an outcome noting the missing target and MUST NOT attempt to mutate non-existent state.

### Key Entities

- **Governance Verdict**: Record emitted by a judge agent after evaluating an observer signal against a policy. Carries verdict type, policy reference, evidence payload, rationale text, recommended action, source event identifier, judge agent identity, and timestamp. Immutable after issuance.
- **Enforcement Action**: Record persisted when an enforcer executes a verdict-driven action. Carries enforcer agent identity, verdict reference, action type, target agent (optional), outcome payload, and timestamp. Immutable after execution.
- **Governance Chain (per fleet or workspace)**: Configuration record on the fleet or workspace identifying the observer source(s), ordered judge agent(s), enforcer agent, and verdict-to-action mapping. Mutable by admins; changes audited.
- **Observer Signal (existing; produced elsewhere)**: Input to the judge. This feature consumes these signals rather than defining or producing them. Observer agents are defined in the existing behavioral-monitoring subsystems and continue to emit signals through their current mechanisms.
- **Agent Role (existing, extended)**: Agent registry role type, extended with `judge` and `enforcer` values so that role-eligibility checks can be enforced when configuring chains.
- **Policy Reference (existing)**: Every verdict references a policy in the existing policy subsystem; this feature consumes policy records and does not modify them.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When an observer signal arrives for a fleet with a configured governance chain, the judge emits a verdict within 5 seconds in 95% of cases (p95 end-to-end evaluation latency).
- **SC-002**: When a judge emits a terminal verdict (VIOLATION or ESCALATE_TO_HUMAN) with an enforcer configured, the enforcer executes the mapped action within 10 seconds in 95% of cases (p95 verdict-to-action latency).
- **SC-003**: 100% of judge verdicts are persisted with all required fields (verdict type, policy reference, evidence, rationale, source event id) — verdicts missing required fields are rejected and re-routed as ESCALATE_TO_HUMAN.
- **SC-004**: 100% of enforcement actions can be traced back to a persisted verdict record (no orphan enforcement actions exist).
- **SC-005**: 100% of governance chain configurations that reference non-existent agents or role-mismatched agents are rejected at save time; no runtime errors occur from invalid chain configurations.
- **SC-006**: Enforcement actions are idempotent per-verdict — retrying an enforcement on the same verdict produces zero additional side effects in 100% of retry attempts.
- **SC-007**: Per-observer rate limiting prevents any single observer from generating more than the configured per-minute threshold of signals to a single judge in 100% of attempts.
- **SC-008**: Audit queries filtering by agent, policy, verdict type, or time range return results consistent with the underlying verdict/action records in 100% of queries (no stale or missing records within the retention window).
- **SC-009**: No user can query verdicts or enforcement actions without the compliance-viewing role (verifiable via authorization tests) in 100% of access attempts.
- **SC-010**: After the retention window elapses, verdicts and their enforcement actions are removed in cascade in 100% of cases, with no enforcement actions orphaned by deletion of their parent verdicts.
- **SC-011**: The proportion of verdicts that successfully trigger their mapped enforcement action (excluding `log_and_continue` mappings which require no execution) is observable as a metric per fleet and workspace; target SLO is tenant-configurable.
- **SC-012**: When a judge is unavailable beyond the configured timeout, the platform re-routes the signal as ESCALATE_TO_HUMAN within 100% of cases rather than silently dropping the signal.

## Assumptions

- Observer agents and the signal emission mechanism already exist; this feature consumes observer signals rather than defining or producing them.
- The agent registry already enforces role validation and supports enum extension for new role types; this feature adds `judge` and `enforcer` as new role enum values.
- Policies are already defined and persisted in the policy subsystem; this feature only references policies by identifier and reads their current state at verdict time.
- The certification subsystem exposes a revocation interface that the enforcer can invoke for the `revoke_cert` action.
- The fleet and workspace records support adding a JSON configuration field for the governance chain without requiring structural changes to their primary schema.
- The existing operator alerting/notification subsystem handles the notify enforcement action; this feature hands off to that infrastructure rather than implementing notifications itself.
- Default governance posture is "no chain configured" (no enforcement) to preserve backward compatibility with fleets and workspaces deployed before this feature.
- The audit retention policy for verdicts and enforcement actions follows the platform-wide audit retention defaults unless an operator overrides.
- Judges may be rule-based, LLM-based, or hybrid — the feature treats judge agents as opaque evaluators whose internal reasoning is not the subject of this feature.

## Dependencies

- Existing agent registry with role-based validation, extended to include `judge` and `enforcer`.
- Existing policy subsystem (policies are referenced by verdicts; deletion semantics matter for FR-020).
- Existing observer/monitoring subsystems that emit governance signals (producers; this feature is consumer-side).
- Existing fleet and workspace records that accept new configuration fields.
- Existing certification subsystem for the `revoke_cert` enforcement action.
- Existing notification/alerting subsystem for the `notify` enforcement action.
- Existing audit/event infrastructure and retention policy.
- Existing RBAC and compliance-viewing role enforcement.

## Out of Scope

- Defining or producing observer signals; this feature only consumes them. Observer agents continue to emit signals through existing mechanisms.
- Adding new policy types or changing how policies are authored, bound, or resolved.
- Modifying the certification subsystem beyond invoking its existing revocation interface from the enforcer.
- Building new notification transports; the notify action hands off to existing notification infrastructure.
- User-facing contestation or appeal flows for enforcement actions. Contestation is a future capability.
- Machine-learning-driven judge auto-selection or dynamic chain reconfiguration. Chains are declaratively configured.
- Cross-organization governance (chains that span multiple tenants). Scope is single-tenant per chain.
- Real-time verdict streaming to end users. The audit surface is query-based, not push-based (operator dashboards subscribe to the existing `governance.enforcement.executed` channel for real-time views, but this feature does not itself render dashboards).
