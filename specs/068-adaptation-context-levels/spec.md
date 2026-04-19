# Feature Specification: Agent Adaptation Pipeline and Context Engineering Levels

**Feature Branch**: `068-adaptation-context-levels`  
**Created**: 2026-04-19  
**Status**: Draft  
**Input**: Brownfield additions to two existing bounded contexts. The **Agent Adaptation Pipeline** formalizes a five-stage workflow (evaluate → identify → propose → approve → apply) for improving agents that have been observed to under-perform against their goals. Each stage produces an auditable artifact; the fourth stage (approve) is a hard human-review gate; the fifth stage (apply) mutates agent configuration only after explicit approval. The **Context Engineering Proficiency Levels** introduces a comparable, per-agent capability measurement derived from observed context-quality signals (retrieval accuracy, instruction adherence, context coherence) and correlates that measurement against the agent's observed performance. Adaptation signals flow from the existing evaluation framework (self-correction convergence data, scorer verdicts) into the pipeline as inputs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Operator Receives an Adaptation Proposal with Rationale and Expected Improvement (Priority: P1)

An agent operator notices that an agent has degraded on a recurring task. They invoke the adaptation pipeline, which analyzes recent performance signals, identifies a concrete weakness (e.g., "retrieval irrelevance on domain X", "tool selection drift on step Y"), and produces a structured proposal that states what should change, why it should change, and what improvement is expected. The operator can review the proposal artifact without any change being applied to the live agent.

**Why this priority**: This is the entire differentiator of the feature. Without a structured proposal, operators must manually investigate degradation, hypothesize causes, and hand-craft fixes. A proposal with rationale and expected improvement transforms that workflow into a reviewable artifact. P1 because every other story in the feature (approval, apply, rollback, outcome measurement) builds on the proposal artifact existing and being well-formed.

**Independent Test**: Create an agent with synthetic under-performance signals (e.g., low scorer verdicts on recent runs). Invoke the adaptation pipeline for the agent. Verify a proposal is produced that includes: agent reference, concrete proposed changes, a rationale citing specific signals, an expected improvement statement, and the signal source(s) used. Verify nothing about the live agent has changed.

**Acceptance Scenarios**:

1. **Given** an agent with recent underperformance signals, **When** the adaptation pipeline is invoked, **Then** it produces a proposal containing proposed changes, rationale, expected improvement, and references to the source signals.
2. **Given** a pipeline invocation for an agent with no underperformance signals, **When** the pipeline completes, **Then** it records a "no change needed" outcome rather than producing an empty proposal.
3. **Given** a proposal produced by the pipeline, **When** it is inspected, **Then** its rationale cites at least one specific observed signal (e.g., a scorer verdict, a convergence measurement) and its expected improvement is expressed as a measurable target.
4. **Given** a proposal is produced, **When** it is inspected, **Then** the live agent configuration is unchanged and no behavior modification has taken effect.
5. **Given** multiple invocations for the same agent within the signal-refresh window, **When** the pipeline runs again, **Then** it reuses cached signals rather than re-computing and produces a proposal consistent with the prior invocation.

---

### User Story 2 — Reviewer Approves or Rejects a Proposal Before Anything Applies (Priority: P1)

A quality reviewer inspects an open proposal. They can see the proposed changes, the rationale, the expected improvement, and the source signals. They can approve with an optional comment, reject with a required reason, or request changes (returning the proposal to the originator). Only an approved proposal becomes eligible for application; rejected and pending proposals cannot be applied by any path. Every decision is audited with reviewer identity, timestamp, and decision reason.

**Why this priority**: Human approval is the load-bearing gate that makes automatic pipeline-driven adaptation safe in production. Without it, a faulty signal or an over-fitting pipeline could degrade agents invisibly. P1 because the ability to propose changes (US1) is valueless without the ability to stop bad proposals from landing.

**Independent Test**: Given an open proposal, attempt application before any review — expect refusal. Approve the proposal; verify it is now eligible for application, a reviewer audit entry exists, and the agent is still unchanged (approval ≠ apply). Create a second proposal; reject it with a reason; verify the rejection is recorded and the proposal cannot be applied.

**Acceptance Scenarios**:

1. **Given** a proposal in "proposed" state, **When** application is attempted, **Then** it is refused with an "approval required" error and no agent mutation occurs.
2. **Given** a proposal in "proposed" state, **When** a reviewer approves it, **Then** its state transitions to "approved", a reviewer audit record is created with timestamp and identity, and the agent is still unchanged.
3. **Given** a proposal in "proposed" state, **When** a reviewer rejects it with a reason, **Then** its state transitions to "rejected", a rejection audit record is created with the reason, and the proposal is no longer applicable.
4. **Given** a proposal in "rejected" state, **When** application is attempted, **Then** it is refused and no mutation occurs.
5. **Given** an "approved" proposal, **When** the reviewer revokes approval prior to application, **Then** the proposal returns to "proposed" state with a revocation audit record; any subsequent application attempt is refused.
6. **Given** a proposal in "proposed" state for more than the configured TTL, **When** the TTL expires, **Then** the proposal transitions to "expired" and can no longer be approved or applied.

---

### User Story 3 — Applied Adaptation Is Audited and Post-Apply Outcome Is Measured (Priority: P1)

An operator digo que el oprimer docudigo que el primer documento sedigo que el priddt pre-apply configuration snapshot. After a configurable observation window, the pipeline measures the post-apply outcome against the proposal's expected improvement: did performance improve as predicted, stay flat, or regress? The outcome is attached to the proposal record. If the applied adaptation regressed the agent, the operator can trigger a rollback that restores the exact pre-apply configuration.

**Why this priority**: Apply-and-forget would make the pipeline untrustworthy. Measuring outcome turns every application into a learning signal: which kinds of proposals deliver predicted improvements and which don't. Rollback is the safety net when a proposal's prediction is wrong in production. P1 because apply without audit is unsafe, and apply without outcome measurement cannot be improved over time.

**Independent Test**: Apply an approved proposal. Verify the application is audited (who, when, pre-apply snapshot hash, new configuration hash). After the observation window, verify a post-apply outcome record exists comparing measured performance against the predicted improvement. Trigger a rollback; verify the agent configuration matches the pre-apply snapshot byte-for-byte and the rollback is audited.

**Acceptance Scenarios**:

1. **Given** an approved proposal, **When** it is applied, **Then** the agent configuration updates, an apply-audit record captures operator identity/timestamp/pre-apply snapshot, and the proposal state transitions to "applied".
2. **Given** an applied adaptation, **When** the post-apply observation window elapses, **Then** an outcome record is produced containing the observed performance delta vs. the predicted improvement and an outcome classification (improved, no change, regressed).
3. **Given** an applied adaptation classified "regressed", **When** the operator triggers rollback, **Then** the agent configuration reverts to the pre-apply snapshot byte-identically, a rollback audit record is created, and the proposal state transitions to "rolled_back".
4. **Given** an applied adaptation, **When** the pre-apply snapshot is older than the configured retention window, **Then** rollback is refused with a clear "rollback window expired" error.
5. **Given** an apply operation that fails mid-execution (partial mutation), **When** the failure is detected, **Then** the pipeline automatically rolls forward or rolls back to a consistent state and records the recovery path on the proposal.

---

### User Story 4 — Operator Sees a Per-Agent Context Engineering Proficiency Level (Priority: P2)

An operator looks at an agent's profile and sees a proficiency level — one of an ordered scale (e.g., novice, competent, advanced, expert) — derived from observed context-quality signals. The level is presented alongside the dimensions that contributed (retrieval accuracy, instruction adherence, context coherence) so the operator can see which dimension is weakest. Agents with insufficient data are shown as "undetermined" rather than defaulted to the lowest tier.

**Why this priority**: Proficiency is a fleet-wide lens that lets operators compare agents and target adaptation effort where it is most needed. P2 because the adaptation pipeline (US1–US3) is usable without the proficiency lens — proficiency is a prioritization and observability layer, not a gating primitive.

**Independent Test**: Compute proficiency for an agent with synthetic context-quality signals spanning all dimensions. Verify the agent receives a non-"undetermined" level. Zero the signals; verify the level drops appropriately. Remove signals entirely; verify "undetermined" is reported rather than "novice".

**Acceptance Scenarios**:

1. **Given** an agent with recent context-quality signals across all dimensions, **When** proficiency is computed, **Then** an ordered-scale level is assigned and the contributing dimension values are visible.
2. **Given** an agent with fewer signals than the configured minimum, **When** proficiency is computed, **Then** the result is "undetermined" and the missing dimensions are listed.
3. **Given** two agents with different proficiency levels, **When** the operator compares them, **Then** the levels are ordered consistently and the dimension values are comparable across agents.
4. **Given** an agent whose proficiency changes over time, **When** its history is inspected, **Then** a trajectory of proficiency-level transitions is available with timestamps and the trigger (signal change, significant context update).

---

### User Story 5 — Quality Engineer Sees Correlation Between Context Quality and Performance (Priority: P2)

A quality engineer needs to confirm that investing in context quality improvements actually improves agent performance. They query the correlation view: for a configurable window, the system surfaces the per-agent correlation coefficient between context-quality dimensions and a performance metric (e.g., scorer overall_score, task success rate). High-correlation outliers (strong positive correlation and high context quality) become model agents; low-correlation outliers (weak or negative correlation) are flagged for investigation.

**Why this priority**: Correlation grounds the feature's investment thesis — "context engineering matters" — in observed data. P2 because the adaptation pipeline is functional without correlation tracking, but fleet-wide optimization benefits strongly from it.

**Independent Test**: Populate synthetic context-quality and performance signals for 10 agents, with known correlation structure (e.g., 5 strongly positive, 3 weak, 2 negative). Compute correlation over the configured window. Verify each agent's coefficient is reported and classification (high/medium/low/inconclusive) matches the synthetic design. Verify agents with insufficient data are reported as "inconclusive" rather than a default coefficient.

**Acceptance Scenarios**:

1. **Given** agents with context-quality and performance signals over the configured window, **When** the correlation is queried, **Then** each agent receives a correlation coefficient with a classification and the underlying data-point count.
2. **Given** an agent with fewer than the minimum data-point threshold, **When** correlation is computed, **Then** the result is "inconclusive" with the reason recorded.
3. **Given** an agent whose correlation is strongly negative, **When** the flag is raised, **Then** the quality engineer receives an observable signal and the agent becomes an adaptation-pipeline candidate.
4. **Given** a time-window change, **When** the correlation is re-queried with a new window, **Then** the coefficient and classification reflect the new window.

---

### User Story 6 — Evaluation Convergence Data Feeds the Adaptation Pipeline Automatically (Priority: P3)

When evaluation scorers detect that an agent's self-correction convergence has worsened (e.g., the agent now requires more iterations to stabilize on its outputs, or consistently disagrees with judges after multiple attempts), the pipeline ingests the convergence signal automatically and queues a proposal for review. The operator does not need to invoke the pipeline manually for convergence regressions — the signal-to-proposal chain runs on its own, subject to the same human-approval gate before any application.

**Why this priority**: Automatic signal ingestion closes the loop between evaluation and adaptation. P3 because manual pipeline invocation (US1) already covers the core use case; automatic ingestion is an operational-maturity layer that reduces the time between regression detection and proposal review.

**Independent Test**: Deploy an agent with a baseline convergence measurement. Simulate a convergence regression (e.g., doubling of iterations to stabilize). Verify a proposal is automatically produced within the configured signal-poll window, the proposal's rationale cites the convergence signal, and the proposal enters the review queue requiring the same approval as a manually-produced proposal.

**Acceptance Scenarios**:

1. **Given** an agent with a convergence regression detected by evaluation scorers, **When** the signal-ingestion process runs, **Then** a proposal is produced automatically with rationale citing the convergence signal.
2. **Given** an automatic proposal queued for review, **When** a reviewer inspects it, **Then** the approval gate is identical to manually-produced proposals (FR-004) and no auto-apply occurs.
3. **Given** an agent whose convergence stabilizes before review, **When** the reviewer inspects the proposal, **Then** the proposal surfaces the stabilization and allows the reviewer to reject it with reason "signal self-resolved".

---

### Edge Cases

- **Agent deleted mid-proposal lifecycle**: A proposal for an archived or deleted agent cannot be approved or applied; the proposal transitions to "orphaned" with a clear annotation and any subsequent approval attempt is refused.
- **Concurrent proposals for the same agent**: Only one proposal per agent may be in the "proposed" or "approved" state at a time; a new pipeline invocation while one is open returns the existing proposal rather than creating a duplicate (or is rejected with "open proposal exists" — system chooses one consistent policy).
- **Proposal expires before approval**: A "proposed" proposal older than the configured TTL automatically transitions to "expired"; it cannot be approved or applied, and a new pipeline invocation is required to re-examine the agent.
- **Apply fails mid-operation (partial mutation)**: The pipeline detects the partial state, rolls back or rolls forward to a consistent configuration, and records the recovery path on the proposal; the agent never remains in a mixed state.
- **Rollback attempted outside retention window**: If the pre-apply snapshot is older than the configured retention window, rollback is refused with a "rollback window expired" error; the operator is informed that manual reconfiguration is required.
- **Context quality undefined for early-lifecycle agent**: Agents with fewer than the minimum number of observations show proficiency as "undetermined" rather than defaulting to the lowest tier; the minimum-data rationale is surfaced.
- **Correlation cannot be computed (insufficient data)**: Agents with fewer than the minimum data-point threshold are classified "inconclusive" rather than given a spurious coefficient; the threshold is documented.
- **Multiple reviewers with conflicting verdicts**: First decision wins; any subsequent reviewer action on a decided proposal is refused with "already decided"; review history retains all attempted decisions with timestamps.
- **Self-approval attempt**: A reviewer who is also the originator of a proposal may approve it only if their role explicitly permits self-approval; otherwise approval by a different reviewer is required; the role-check outcome is audited.
- **Signal source unavailable**: When the evaluation framework is unreachable, the signal-ingestion process retries with bounded back-off; after exhausting retries, it records an "ingestion-degraded" health signal and the automatic-proposal feature is flagged unhealthy in monitoring.
- **Proposed change targets a field that no longer exists**: At approve-time, the system validates the proposal's changes against the current agent configuration; if a targeted field has been removed or renamed, the proposal is marked "stale" and cannot be applied; a reason is recorded.
- **Outcome measurement cannot distinguish improvement from noise**: If observed post-apply variance exceeds the expected-improvement magnitude, the outcome is classified "inconclusive" rather than "improved" or "regressed"; the variance envelope is surfaced.
- **Proficiency level boundary flapping**: An agent whose signal values hover near a level boundary must not flap rapidly between levels; hysteresis or a dwell-time requirement suppresses boundary noise; the dwell time is documented.
- **Backward compatibility**: Pre-existing agentops and context_engineering endpoints return identical responses before and after this feature ships; new fields (proficiency level, open-proposal count) are added only to response payloads where they are additive, never replacing existing fields.

## Requirements *(mandatory)*

### Functional Requirements

**Adaptation Pipeline — Proposal Production**

- **FR-001**: The platform MUST provide an adaptation pipeline that, given an agent reference and optional signal snapshot, produces a structured proposal or an explicit "no change needed" outcome.
- **FR-002**: Each proposal MUST include: the target agent reference, a set of proposed changes described as structured data, a free-text rationale, a measurable expected-improvement statement, and references to the source signals that motivated the proposal.
- **FR-003**: A proposal's rationale MUST cite at least one specific observed signal (e.g., a scorer verdict, a convergence measurement, a context-quality regression); proposals without a cited signal MUST NOT be creatable.
- **FR-004**: The pipeline MUST produce the proposal artifact without any mutation to the live agent configuration; creation of a proposal MUST NOT itself apply it.
- **FR-005**: The pipeline MUST be invokable manually (operator trigger), automatically on signal ingestion, or on a configured schedule.

**Adaptation Pipeline — Review and Approval Gate**

- **FR-006**: A proposal MUST progress through a defined state machine: proposed → approved | rejected | expired | orphaned; approved → applied | revoked; applied → rolled_back; rolled_back is terminal.
- **FR-007**: Application MUST NOT occur without an explicit human-approval audit entry for the proposal; any code path that mutates an agent based on a proposal MUST check the approval record.
- **FR-008**: Every state transition (approve, reject, apply, revoke, roll back, expire, orphan) MUST be audited with actor identity, timestamp, and transition reason.
- **FR-009**: A reviewer MAY revoke their own approval prior to application; a revoked proposal returns to "proposed" state and requires fresh approval.
- **FR-010**: A proposal not decided within a configurable TTL MUST automatically transition to "expired"; expired proposals MUST NOT be approvable or applicable.
- **FR-011**: A proposal whose target agent has been archived or deleted MUST transition to "orphaned" on next evaluation; orphaned proposals MUST NOT be approvable or applicable.
- **FR-012**: At most one proposal per agent may be in the "proposed" or "approved" state at any time; pipeline invocations for an agent with an open proposal MUST return the existing proposal rather than creating a duplicate.

**Adaptation Pipeline — Apply, Outcome, and Rollback**

- **FR-013**: When an approved proposal is applied, the platform MUST capture a byte-identical snapshot of the pre-apply agent configuration and persist it for the configured rollback-retention window.
- **FR-014**: Application MUST validate the proposal's proposed changes against the current agent configuration; if any target field no longer exists or has been renamed, the proposal MUST transition to "stale" and apply MUST be refused.
- **FR-015**: After a configurable post-apply observation window elapses, the platform MUST produce an outcome record comparing observed performance against the expected-improvement target; the record MUST classify the outcome as improved, no_change, regressed, or inconclusive.
- **FR-016**: An outcome classified "inconclusive" MUST surface the observed variance relative to the expected-improvement magnitude so the reviewer can judge signal quality.
- **FR-017**: Rollback MUST restore the pre-apply snapshot byte-identically; rollback MUST be refused if the snapshot is outside the retention window.
- **FR-018**: Apply failures mid-operation MUST be auto-recovered to a consistent configuration state (forward or backward); the agent MUST NOT remain in a partial-change state; the recovery path MUST be recorded on the proposal.

**Context Engineering Proficiency Levels**

- **FR-019**: The platform MUST compute a per-agent proficiency level drawn from a defined ordered scale (at least four named levels plus an "undetermined" state).
- **FR-020**: Proficiency MUST be derived from observed context-quality dimensions: retrieval accuracy, instruction adherence, context coherence; the derivation function MUST be documented and reproducible.
- **FR-021**: Agents with fewer observations than the configured minimum MUST be reported as "undetermined" rather than receiving the lowest-tier level by default.
- **FR-022**: Proficiency levels MUST be comparable across agents, enabling fleet-wide queries of the form "list agents at level X or below".
- **FR-023**: Proficiency-level transitions over time MUST be recorded as a trajectory with timestamps and trigger annotations.
- **FR-024**: Boundary flapping between proficiency levels MUST be suppressed via hysteresis or a dwell-time threshold; the threshold MUST be documented.

**Context-Performance Correlation**

- **FR-025**: The platform MUST compute, on demand and for a configurable time window, a per-agent correlation coefficient between each context-quality dimension and a configured performance metric.
- **FR-026**: The correlation result MUST be reported with its underlying data-point count and a classification (strong_positive, moderate_positive, weak, moderate_negative, strong_negative, inconclusive).
- **FR-027**: Agents with fewer than the minimum data-point threshold MUST be classified "inconclusive" rather than receiving a numeric coefficient.
- **FR-028**: Strongly-negative correlations MUST be surfacable via an observable signal (e.g., an event or a monitoring flag) so quality engineers can triage them.

**Signal Ingestion**

- **FR-029**: The platform MUST accept adaptation signals from the existing evaluation framework (self-correction convergence metrics, scorer verdict aggregates, post-apply outcome records) as pipeline inputs.
- **FR-030**: Signal ingestion MUST tolerate transient unavailability of the source with bounded retries; after retries are exhausted, an "ingestion-degraded" health signal MUST be emitted and the automatic-proposal feature MUST be marked unhealthy until the source recovers.
- **FR-031**: Signals referenced by a proposal MUST be immutable snapshots captured at proposal-creation time so the rationale remains accurate even if the underlying signal evolves.

**Observability and Auditability**

- **FR-032**: Every pipeline state transition, signal ingestion event, proficiency-level change, and correlation computation MUST emit an observable event with the correlation context (agent reference, actor if any, timestamp).
- **FR-033**: The complete life-cycle chain for any applied adaptation (signal → proposal → approval → apply → outcome → rollback if any) MUST be traceable end-to-end from a single proposal identifier.

**Backward Compatibility**

- **FR-034**: Pre-existing agentops and context_engineering endpoints MUST return identical response shapes for all fields that existed before this feature ships; new fields MAY be added additively to response payloads.
- **FR-035**: New database schema changes MUST be additive; no renaming, removal, or type changes of pre-existing columns.
- **FR-036**: The pipeline MUST NOT introduce any code path that mutates an agent outside the approved-proposal gate; direct-mutation endpoints in agentops remain unchanged in behavior.

### Key Entities

- **Adaptation Proposal**: A structured record of a proposed agent change, including target agent, proposed changes, rationale, expected improvement, source signals, state (in the state machine), and timestamps. Immutable fields: source signals snapshot. Mutable fields: state, decided_at, decided_by, apply_at, applied_by, outcome_at.
- **Adaptation Signal**: A point-in-time observation from the evaluation framework or other source that motivates a proposal. Includes signal type, value, measured_at, source system, and a reference to the agent.
- **Adaptation Decision**: A record of a reviewer's decision on a proposal — approve, reject, revoke — with reviewer identity, timestamp, and reason.
- **Adaptation Application**: A record of an applied change, including operator identity, apply timestamp, pre-apply snapshot reference, post-apply snapshot reference, and recovery path if applicable.
- **Adaptation Outcome**: A record of post-apply performance measurement, including observation window, observed delta, expected delta, classification, and variance annotation.
- **Adaptation Rollback**: A record of a rollback operation, including operator identity, timestamp, snapshot reference, and resulting configuration hash.
- **Proficiency Assessment**: A per-agent, point-in-time proficiency level plus contributing dimension values, observation count, and trigger annotation.
- **Context Quality Measurement**: An observation of a context-quality dimension (retrieval_accuracy, instruction_adherence, context_coherence) at a point in time, attached to an agent reference.
- **Context-Performance Correlation**: A computed correlation coefficient between a context-quality dimension and a performance metric over a time window, with classification and data-point count.
- **Proposal State Machine**: The defined transitions between proposal states (proposed, approved, rejected, expired, orphaned, applied, rolled_back, stale, revoked).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of produced proposals include all of: target agent reference, proposed changes, rationale, expected improvement, source signals (no empty or null required fields).
- **SC-002**: Zero proposals are applied without a corresponding approval audit record; auditors can verify this with a single query.
- **SC-003**: 100% of applied adaptations produce a post-apply outcome record within the configured observation window plus a grace period.
- **SC-004**: 100% of rollback operations within the retention window restore the agent to a byte-identical pre-apply configuration.
- **SC-005**: 100% of proposals not decided within TTL transition to "expired" automatically; no stale "proposed" records remain past TTL.
- **SC-006**: 100% of proposal state transitions emit an observable event containing actor identity, timestamp, and transition reason.
- **SC-007**: Every agent in the system receives either a proficiency level or the "undetermined" state; no agent is reported without a proficiency field.
- **SC-008**: Proficiency levels are strictly orderable and queryable with a deterministic comparator; fleet-wide queries of the form "agents at level X or below" return consistent results.
- **SC-009**: Agents with insufficient data for proficiency or correlation are classified "undetermined" or "inconclusive" in 100% of cases rather than receiving a default value.
- **SC-010**: Proficiency-level changes honor the configured dwell-time or hysteresis threshold; agents whose signals hover within the noise band do not transition more than once per threshold window.
- **SC-011**: Correlation coefficients are reported with underlying data-point counts and classifications for 100% of agents with sufficient data; the coefficient is reproducible given the same window and signals.
- **SC-012**: Automatic signal-driven proposals are produced within the configured poll window after a qualifying regression is detected; the detection-to-proposal latency is measurable and bounded.
- **SC-013**: When the signal source is unavailable, the platform emits an "ingestion-degraded" health event within one poll cycle of the outage and recovers within one poll cycle of source restoration.
- **SC-014**: Pre-existing agentops and context_engineering endpoints produce byte-identical responses before and after this feature ships for all fields that existed pre-feature.
- **SC-015**: The end-to-end life-cycle chain (signal → proposal → approval → apply → outcome → rollback if any) is traceable from any single proposal identifier and returns all linked records.
- **SC-016**: Concurrent pipeline invocations for the same agent with an open proposal return the existing proposal rather than creating a duplicate; zero duplicate "proposed" records for the same agent exist at any time.

## Assumptions

- Existing agentops captures per-agent performance metrics (scorer verdicts, task success, latency) in a consumable form; if any dimension is missing, adding it is considered prerequisite work outside this feature's scope.
- Existing context_engineering/quality_service captures per-agent context-quality observations (retrieval accuracy, instruction adherence, context coherence); dimensions not yet captured are considered prerequisite.
- Existing evaluation scorers emit self-correction convergence metrics; these are ingestable without changes to the scorers themselves.
- Existing auth/RBAC surface supports the approval-gate enforcement with the identity and role-check semantics required; no new authentication primitives are introduced.
- Proficiency scale default: four named levels (novice, competent, advanced, expert) plus "undetermined"; operators may rename or extend the scale via configuration.
- Proposal TTL default: 7 days; operator-configurable.
- Post-apply observation window default: 3 days; operator-configurable.
- Rollback retention window default: 30 days; operator-configurable.
- Signal poll interval default: 1 hour; operator-configurable.
- Correlation window default: 30 days rolling; operator-configurable.
- Minimum data-points for correlation default: 30; operator-configurable.
- Minimum observations for proficiency: per-dimension threshold default 10; operator-configurable.
- Proficiency boundary dwell-time default: 24 hours; operator-configurable.
- Self-approval policy default: disallowed unless the reviewer holds an explicit self-approval role; auditable either way.
- Conflict resolution for concurrent proposals: at most one open proposal per agent; new invocations return the existing record until it is decided or expires.
- Snapshot persistence: pre-apply and post-apply configuration snapshots stored additively in existing persistence surface; no new store introduced.
- Signal-source unavailability handling: bounded retry with exponential back-off, then "ingestion-degraded" health event; no silent feature disable.
- Pipeline results are ingestable by monitoring and audit surfaces via the existing event bus; no new bus introduced.
- The feature reuses existing agent-configuration-mutation endpoints; the pipeline does NOT introduce new mutation endpoints for fields already mutable via agentops.

## Dependencies

- Existing agentops bounded context (for agent references, performance metrics, and configuration mutation).
- Existing context_engineering bounded context (for context-quality observations and quality-service surface).
- Existing evaluation framework (for scorer verdicts, self-correction convergence data).
- Existing auth/RBAC surface (for approval-gate enforcement and reviewer identity).
- Existing audit surface (for state-transition audit records).
- Existing event bus (for lifecycle events, signal-ingestion health events, and proficiency-change events).
- Existing persistence surface (for proposal, decision, application, outcome, rollback, proficiency assessment, and correlation records — additive schema changes only).
- Existing monitoring surface (for "ingestion-degraded" and correlation-flagged signals).

## Out of Scope

- Fully automatic adaptation without human approval — approval is a hard gate per FR-007.
- Fine-tuning, retraining, or weight-level modifications of agent models — proposals change configuration/context, not model weights.
- Cross-agent adaptation inheritance (applying one agent's approved adaptation automatically to peers) — each agent requires its own pipeline run and approval.
- Multi-tenant proposal sharing or an external marketplace exchange of adaptations.
- Reinforcement-learning loops where outcome records automatically trigger further proposals without review — each proposal requires independent human approval.
- UI tooling for proposal authoring, review dashboards, or proficiency visualization — this release delivers API/backend capabilities; UI is a separate initiative.
- New authentication or authorization primitives — reuses existing auth surface.
- Alternative correlation methods (non-Pearson, rank-based, multivariate) beyond the single documented method — extensions are deferred.
- Root-cause analysis of why a correlation is weak or negative — the feature reports correlation; diagnosis is a separate workflow.
- Proficiency levels for non-agent entities (fleets, workflows, humans) — agent-only in this release.
- Historical recomputation of proficiency or correlation across the full agent history — initial release computes going forward from feature launch.
- Direct mutation of agents outside the approved-proposal path — pre-existing agentops mutation endpoints remain unchanged; the pipeline does not replace them.
