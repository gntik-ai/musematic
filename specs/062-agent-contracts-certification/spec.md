# Feature Specification: Agent Contracts and Certification Enhancements

**Feature Branch**: `062-agent-contracts-certification`
**Created**: 2026-04-19
**Status**: Draft  
**Input**: Brownfield extension. Adds machine-enforceable agent contracts (task scope, quality thresholds, cost/time limits, enforcement policy) attachable to interactions and executions. Adds third-party certifier entities and extends certifications with expiry, reassessment schedule, and status lifecycle to support ongoing surveillance programs. Runtime monitor evaluates executions against contract terms and triggers configured enforcement actions (warn / throttle / escalate / terminate). Surveillance service runs periodic compliance checks and transitions certifications through active → expiring → expired / suspended / revoked.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Author defines a contract and attaches it at runtime (Priority: P1)

An agent owner, platform operator, or workflow author defines a formal contract for an agent that specifies the task scope the agent is authorized to perform, the quality thresholds its outputs must meet (e.g., minimum accuracy, maximum latency), hard cost and time constraints, conditions under which the contract must escalate to a human, and the enforcement policy to apply on breach (warn, throttle, escalate, or terminate). The contract is attached to a specific interaction or execution at runtime. As the execution proceeds, a runtime monitor compares live telemetry against the contract's terms; when a term is breached, the monitor triggers the configured enforcement action and records the breach for audit.

**Why this priority**: Contracts are the machine-enforceable expression of what an agent is authorized to do and how it must behave. Without them, runtime behavior is governed only by policy (network-level) and observer signals (detection-level); the contract layer closes the gap by defining explicit performance guarantees per attachment. P1 because contract enforcement is the foundational capability upon which certification, surveillance, and compliance KPIs all build.

**Independent Test**: Create a contract for agent A with `time_constraint_seconds=10` and `enforcement_policy=terminate`. Attach it to an execution. Start an execution that takes 15 seconds. Verify the runtime monitor detects the time breach at the 10-second mark, triggers a termination action, and records a breach event with the contract reference, breach type, and enforcement outcome. Verify that attaching the same contract to a fast-running execution (5 seconds) completes normally with no breach recorded.

**Acceptance Scenarios**:

1. **Given** a contract specifying `cost_limit_tokens=1000` and `enforcement_policy=throttle`, attached to an execution, **When** the execution consumes 1000 tokens, **Then** the runtime monitor triggers the throttle action, records a cost-breach event referencing the contract, and subsequent token spend is blocked until the execution completes or escalates.
2. **Given** a contract specifying `quality_thresholds={accuracy_min: 0.95}` and `enforcement_policy=warn`, attached to an interaction, **When** the agent's output scores 0.90 accuracy, **Then** the monitor records a quality-breach warning event but allows the interaction to continue.
3. **Given** a contract specifying `escalation_conditions={human_required_on: ["pii_detected"]}`, **When** the execution encounters a PII-matching condition, **Then** the monitor triggers an escalation action and records the escalation with the matched condition name.
4. **Given** a contract with `enforcement_policy=terminate` and a `time_constraint_seconds=30` term, **When** the execution exceeds 30 seconds, **Then** the monitor terminates the execution, records a time-breach termination event, and the execution state transitions to a terminated-by-contract state distinguishable from user-initiated cancellation.
5. **Given** a contract without an `enforcement_policy` field set, **When** the contract is saved, **Then** the platform applies the default policy `warn` and the stored contract record reflects the default explicitly.
6. **Given** a contract attached to an in-flight execution and a subsequent contract update on the same agent, **When** the in-flight execution continues, **Then** it remains governed by the contract snapshot captured at attachment time; the update applies only to subsequent executions.

---

### User Story 2 — Third-party certifier issues a certification (Priority: P1)

A compliance officer or platform administrator registers an external certifier organization (e.g., an industry body, accredited lab, or trusted consulting firm) with the platform, recording its name, organization, credentials, and the scopes it is permitted to certify within. The external certifier then issues a certification to an agent; the certification record carries the certifier identity, scope of certification, any required evidence references, and an expiry date. The agent's trust surface shows the external certifier, its credentials, and the scope of the certification, giving platform consumers visibility into third-party attestations.

**Why this priority**: Internal platform certifications are valuable but limited — external certifiers provide independent attestation required by regulated industries (finance, healthcare) and by customers who require an auditable third-party trust signal. Without this capability, the platform cannot support customers whose procurement policies require certifications from named external bodies. P1 because third-party certification is a prerequisite for enterprise adoption in regulated contexts.

**Independent Test**: Register certifier "ACME Labs" with permitted_scopes including "financial_calculations". Issue a certification for agent B with `external_certifier_id=ACME, scope=financial_calculations, expiry_date=2027-04-19`. Fetch agent B's trust profile. Verify the certification appears with certifier name "ACME Labs", its credentials, and the scope. Attempt to issue a certification from ACME for a scope outside its permitted_scopes — verify the issuance is rejected.

**Acceptance Scenarios**:

1. **Given** no registered certifiers, **When** an admin registers certifier "ACME Labs" with permitted_scopes `["financial_calculations", "hipaa_compliance"]`, **Then** the certifier record is persisted and retrievable for subsequent certification issuances.
2. **Given** registered certifier ACME Labs, **When** a certification is issued citing ACME as the external certifier with scope "financial_calculations", **Then** the certification record carries the `external_certifier_id` and the certifier's name appears on the agent's trust profile.
3. **Given** registered certifier ACME with permitted_scopes `["financial_calculations"]`, **When** a certification is attempted with scope "medical_diagnosis", **Then** issuance is rejected with a validation error identifying the out-of-scope certifier.
4. **Given** an agent with certifications from both an internal certifier and an external certifier, **When** the trust profile is rendered, **Then** both certifications are shown with their certifier source clearly distinguishable (internal vs external) and neither overrides the other.
5. **Given** an active external certification, **When** the source certifier is de-listed (removed from permitted_scopes), **Then** the existing certification remains valid until expiry but no new certifications from that certifier can be issued.

---

### User Story 3 — Certification expiry and ongoing surveillance (Priority: P2)

A certification is not a one-time attestation but a time-bound trust signal subject to ongoing surveillance. Every certification carries an expiry date and, optionally, a reassessment schedule (e.g., quarterly, monthly). A background surveillance process periodically evaluates each active certification: as the expiry date approaches, the certification transitions to status "expiring" and alerts are raised to the owning compliance team; when the expiry date passes without renewal, the certification transitions to "expired" and is no longer treated as active for trust surface purposes. Certifications bound to a reassessment schedule trigger periodic compliance jobs that produce a reassessment verdict (pass, fail, or action-required).

**Why this priority**: Trust signals that cannot expire or be revoked on schedule are fundamentally inadequate for regulated use. Customers and compliance auditors explicitly require proof of ongoing surveillance, not just point-in-time certifications. Without this lifecycle machinery, the platform's certifications are indistinguishable from a one-off stamp and lose credibility. P2 because the certification itself (US2) must exist before its lifecycle can be managed.

**Independent Test**: Issue a certification with `expiry_date=now+30_days, reassessment_schedule="0 0 * * 0"` (weekly Sunday). Fast-forward the system clock by 7 days. Verify the surveillance job has run a reassessment and produced a verdict. Fast-forward to day 29. Verify the certification status is now "expiring" and an operator alert has fired. Fast-forward to day 31. Verify the certification status is "expired" and it no longer appears in active-certification lookups.

**Acceptance Scenarios**:

1. **Given** a certification with `expiry_date=now+7d`, **When** the surveillance job runs and checks the certification, **Then** status remains "active" and no alert is raised.
2. **Given** a certification with `expiry_date=now+2d` and `status="active"`, **When** the surveillance job runs, **Then** the certification status transitions to "expiring" and an operator alert is emitted with the expiry date.
3. **Given** a certification whose `expiry_date` is in the past, **When** the surveillance job runs, **Then** the certification status transitions to "expired" and the certification no longer appears in active-certification lookups.
4. **Given** a certification with `reassessment_schedule="0 0 1 * *"` (monthly), **When** a month elapses since the last reassessment, **Then** a reassessment job runs, produces a verdict (pass/fail/action-required), and records the verdict in the certification's surveillance history.
5. **Given** a reassessment produces a "fail" verdict, **When** the verdict is recorded, **Then** the certification status transitions to "suspended" until a successful reassessment or human resolution; suspended certifications are not considered active for trust surface purposes.

---

### User Story 4 — Material change triggers recertification (Priority: P2)

A certification attests that an agent in a specific configuration meets specific criteria. When a material change occurs to that agent (e.g., a new revision deploying a different model, a policy change altering its allowed tools, or a training-data change affecting its responses), the certification's validity is automatically placed in question: the certification transitions to "suspended" pending recertification. The compliance team or the original certifier must then re-evaluate the agent against the certification criteria; upon successful reassessment the certification transitions back to "active"; if the reassessment does not occur within a configurable grace period, the certification transitions to "revoked".

**Why this priority**: A certification that survives a material configuration change silently is a false trust signal. Customers relying on the certification may be misled into trusting behavior that no longer matches what was originally certified. This capability is the bridge between certification issuance (US2) and ongoing trust (US3). P2 because the base certification lifecycle (US3) must exist first, and material-change detection depends on existing upstream change-notification infrastructure.

**Independent Test**: Issue a certification for agent C revision R1. Deploy a new revision R2 for agent C (material change). Verify the certification status transitions to "suspended" and a recertification request is recorded. Perform a reassessment that produces a "pass" verdict. Verify the certification status transitions back to "active" and is reference-updated to revision R2. Skip reassessment and advance past the grace period. Verify the certification transitions to "revoked".

**Acceptance Scenarios**:

1. **Given** an active certification for agent C at revision R1, **When** agent C deploys a new revision R2, **Then** the certification status transitions to "suspended" and a recertification request is created referencing both R1 and R2.
2. **Given** a suspended certification pending recertification, **When** a reassessment is performed and produces a "pass" verdict, **Then** the certification status returns to "active" and the certified-revision reference updates to R2.
3. **Given** a suspended certification, **When** the configured grace period elapses without reassessment, **Then** the certification status transitions to "revoked" with the revocation reason "recertification timeout".
4. **Given** an active certification when an attached policy change occurs on agent C, **When** the policy change notification is received, **Then** the certification status transitions to "suspended" and the change reference is recorded in the recertification request.
5. **Given** a material-change suspension, **When** an operator manually dismisses the suspension (with justification), **Then** the certification returns to "active" with an audit note recording the dismissal and justification.

---

### User Story 5 — Contract compliance rate as a compliance KPI (Priority: P3)

A compliance officer or platform administrator queries the contract compliance surface to see, per agent, per fleet, or per workspace over a time range, the rate of contract-attached executions that completed without breach, the rate that completed with warnings, the rate that were throttled or terminated by contract, and the trend over time. The query returns both aggregate metrics and a breach breakdown by term (time / cost / quality / escalation), so that owners can identify which contract terms are driving breaches and adjust thresholds or agent behavior.

**Why this priority**: Compliance rate is the leadership-level indicator of whether contracts are working: too many breaches signal either too-strict contracts, misconfigured agents, or real performance regression. Without the KPI surface, the raw breach data in the audit trail is inaccessible for decision-making. P3 because the runtime data (from US1) must exist before it can be aggregated, and the KPI surface is an observability layer rather than a functional prerequisite.

**Independent Test**: Run 100 contract-attached executions against agent D, where 85 complete compliantly, 10 produce warnings, 3 are throttled, and 2 are terminated. Query the compliance rate surface for agent D over the time window. Verify the response reports 85% compliance rate, 10% warning rate, 5% enforcement rate, and a breakdown showing the dominant breach term. Verify querying the same surface for a different agent with no breaches shows 100% compliance and zero enforcement actions.

**Acceptance Scenarios**:

1. **Given** a fleet F with multiple agents under contract, **When** a compliance officer queries compliance rate for fleet F over 30 days, **Then** the response shows fleet-aggregate compliance rate, per-agent breakdown, and a breach-by-term breakdown (time/cost/quality/escalation).
2. **Given** a request to view the trend for agent D over 90 days, **When** the query is executed, **Then** the response includes a time-bucketed series (e.g., daily compliance rate) suitable for trend visualization.
3. **Given** a query by a user without the compliance-viewing role, **When** the request is made, **Then** access is denied with an authorization error and no compliance data is returned.

---

### Edge Cases

- **Contract attached to an interaction that completes before monitoring can evaluate any term**: The interaction completes successfully with a compliance record marked "not evaluated" (no terms observed) rather than an implicit pass.
- **Contract with conflicting terms (e.g., cost_limit_tokens=0 and quality_thresholds requiring large context)**: The contract is rejected at save time with a validation error identifying the conflict.
- **Multiple contracts attempted on the same interaction or execution**: One-contract-per-interaction and one-contract-per-execution constraints are enforced; a second attachment attempt is rejected.
- **Contract reference deleted while attached to in-flight executions**: In-flight executions retain their contract-snapshot terms and continue evaluating against the captured snapshot; the deleted contract cannot be referenced for new attachments.
- **Quality threshold breach but within a declared tolerance band**: If the contract declares a tolerance band around a threshold, breaches within the band are recorded but do not trigger enforcement; only true breaches outside the band do.
- **Enforcement policy is `terminate` but termination fails**: A termination failure is recorded with a follow-up enforcement action; the execution is quarantined rather than allowed to continue unchecked.
- **Certifier de-listed while its certifications are still active**: Active certifications remain valid until expiry; no new certifications can be issued by a de-listed certifier.
- **Overlapping internal and external certifications for the same scope**: Both are displayed on the trust surface; neither overrides the other; scoring combines both when relevant.
- **Reassessment schedule set to a cron expression that is invalid**: Configuration is rejected at save time with a parsing error.
- **Reassessment job fails to run (infrastructure outage)**: A missed-run alert is emitted; the certification status remains at its prior state and is not silently transitioned.
- **Material change occurs during an active reassessment**: The active reassessment is marked stale; a fresh recertification request is created referencing the new change.
- **Certification with no expiry_date set**: The certification is treated as having an indefinite validity period; surveillance only triggers on material change; an operational warning is logged on save recommending an explicit expiry.
- **Contract compliance query requested for a period with no attached executions**: The response returns zero counts rather than an error; the compliance rate is reported as "not applicable" rather than 0% or 100%.
- **Execution terminates due to contract breach mid-way through a multi-step workflow**: The enclosing workflow transitions to a recoverable failure state referencing the contract breach; compensating actions configured on the workflow still run.
- **Certificate revocation cascades to contract attachments**: Revoked certifications do not automatically revoke attached contracts; contracts are independent of certification status.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST support creation, retrieval, update, and archival of agent contracts that define task scope, expected outputs, quality thresholds, time constraints, cost limits, escalation conditions, success criteria, and enforcement policy.
- **FR-002**: The platform MUST validate agent contracts at save time: required fields present, enforcement policy within the allowed set (warn/throttle/escalate/terminate), numeric limits non-negative, and any cron or schedule expressions syntactically valid.
- **FR-003**: The platform MUST allow attaching exactly one contract to an interaction and exactly one contract to an execution; attempts to attach a second contract MUST be rejected.
- **FR-004**: When a contract is attached, the platform MUST capture a snapshot of the contract terms effective at attachment time so that in-flight work is governed by the snapshot even if the underlying contract is later modified or deleted.
- **FR-005**: A runtime monitor MUST evaluate live execution and interaction telemetry against the attached contract's terms and emit a breach event whenever a term is violated; each breach event MUST reference the contract, the breached term, the observed value, and the threshold.
- **FR-006**: On breach, the runtime monitor MUST trigger the action specified by the contract's `enforcement_policy` (warn / throttle / escalate / terminate); default enforcement is `warn` when no policy is set.
- **FR-007**: When enforcement policy is `terminate`, the execution MUST transition to a distinguishable contract-terminated state, separate from user-initiated cancellation, so downstream systems can report correctly.
- **FR-008**: The platform MUST record every enforcement action taken by the runtime monitor in the audit trail, including contract reference, breach reference, action type, and outcome.
- **FR-009**: The platform MUST support registration of third-party certifier organizations with name, organization, credentials, and permitted scopes; certifier records MUST be retrievable for subsequent certification issuance.
- **FR-010**: The platform MUST allow issuing a certification that references an external certifier; issuance MUST validate that the scope of the certification falls within the certifier's `permitted_scopes`, rejecting out-of-scope issuances.
- **FR-011**: Certifications MUST carry a status lifecycle covering active, expiring, expired, suspended, and revoked, and MUST expose the current status to consumers of the trust surface.
- **FR-012**: Certifications MUST support an expiry date and an optional reassessment schedule; expiry date is mandatory unless explicitly marked indefinite, in which case a warning MUST be logged at save time.
- **FR-013**: A surveillance process MUST periodically evaluate active certifications: as expiry approaches within a configurable window, status MUST transition to "expiring"; once expiry elapses without renewal, status MUST transition to "expired".
- **FR-014**: Certifications with a reassessment schedule MUST trigger reassessment jobs at the scheduled cadence; each reassessment MUST produce a verdict (pass / fail / action-required) and MUST be persisted in the certification's surveillance history.
- **FR-015**: A "fail" reassessment verdict MUST transition the certification to "suspended"; a subsequent "pass" reassessment MUST transition it back to "active".
- **FR-016**: When a material change occurs on a certified agent (new revision, policy change, or configured change signal), the certification MUST transition to "suspended" and a recertification request MUST be created referencing the change.
- **FR-017**: A suspended certification that is not successfully recertified within a configurable grace period MUST transition to "revoked" with revocation reason "recertification timeout".
- **FR-018**: Third-party certifications and internal certifications MUST be distinguishable on the agent's trust surface; neither source MUST override the other.
- **FR-019**: When a certifier is de-listed (removed from eligible certifiers), existing certifications MUST remain valid until expiry but no new certifications from that certifier MUST be issuable.
- **FR-020**: The platform MUST expose a compliance-rate query surface that, for a given agent, fleet, or workspace over a time range, returns the proportion of contract-attached executions that completed compliantly, with warnings, or with enforcement actions (throttle/terminate/escalate), plus a breach breakdown by term (time / cost / quality / escalation).
- **FR-021**: Compliance-rate queries MUST require the compliance-viewing role; unauthorized users MUST be denied with an authorization error.
- **FR-022**: The platform MUST retain contract breach events and enforcement actions for a configurable retention window; records older than the window MUST be removed by a scheduled garbage-collection process.
- **FR-023**: Operator alerts MUST fire when a certification transitions to "expiring", "expired", "suspended", or "revoked", and when a reassessment job fails to run at its scheduled time.
- **FR-024**: Operators with appropriate permission MUST be able to manually dismiss a material-change suspension with a written justification; dismissals MUST be recorded in the audit trail.
- **FR-025**: The platform MUST reject contract definitions that contain internally conflicting terms (e.g., `cost_limit_tokens=0` paired with a nonzero expected output volume) with a clear validation error at save time.
- **FR-026**: Contract attachment to an interaction or execution MUST be idempotent: re-attaching the same contract to the same target MUST be a no-op and MUST NOT create duplicate records.
- **FR-027**: The platform MUST preserve backward compatibility: existing interactions and executions without a contract MUST continue to behave exactly as before; attachment is opt-in per target.

### Key Entities

- **Agent Contract**: Machine-enforceable definition of what an agent may do and how it must behave. Carries task scope, expected outputs, quality thresholds, time constraints, cost limits, escalation conditions, success criteria, and enforcement policy. Immutable after attachment to a specific interaction or execution (via snapshot); mutable independently as a reusable definition.
- **Contract Attachment (existing interaction/execution extended)**: A link between a contract and a single interaction or execution. Includes a captured contract-term snapshot so that runtime evaluation is stable against later contract edits.
- **Breach Event**: Record emitted by the runtime monitor when a contract term is violated. Carries the contract reference, breached term, observed value, threshold, timestamp, and the enforcement action triggered.
- **Certifier**: External organization registered with the platform to issue certifications. Carries name, organization, credentials, permitted scopes, and registration timestamp.
- **Certification (existing, extended)**: Time-bound attestation that an agent meets specific criteria, issued by internal or external certifier. Extended with expiry date, reassessment schedule, status lifecycle (active/expiring/expired/suspended/revoked), and optional external-certifier reference.
- **Reassessment Record**: Result of a periodic surveillance job against a certification. Carries reassessment verdict (pass / fail / action-required), timestamp, reassessor identity, and notes.
- **Recertification Request**: Record created when a material change suspends a certification. Carries the triggering change reference (revision / policy / signal), the certification reference, the deadline for reassessment, and resolution status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When a contract is attached to an execution with a hard time constraint, the runtime monitor detects the time-constraint breach within 1 second of the breach occurring in 95% of cases.
- **SC-002**: 100% of contract-terminated executions are distinguishable from user-initiated cancellations in execution state queries (no ambiguous termination reason).
- **SC-003**: 100% of attempts to issue a third-party certification outside the certifier's permitted scopes are rejected at save time.
- **SC-004**: 100% of certifications with an expiry date in the past are transitioned to "expired" within 24 hours of expiry (surveillance cadence).
- **SC-005**: 100% of active certifications whose expiry date falls within the configurable warning window transition to "expiring" and emit an operator alert within one surveillance cycle.
- **SC-006**: 100% of material-change signals for a certified agent cause the certification to transition to "suspended" within 1 hour of the signal being received.
- **SC-007**: After a successful reassessment, 100% of suspended certifications transition back to "active" with the certified-revision reference updated.
- **SC-008**: 100% of contract breach events are recorded in the audit trail with the contract reference, breached term, observed value, and triggered enforcement action.
- **SC-009**: Compliance-rate queries for a single agent return aggregate and per-term breakdowns in under 3 seconds in 95% of cases.
- **SC-010**: No user can access the compliance-rate query surface without the compliance-viewing role, verifiable in 100% of access attempts.
- **SC-011**: 100% of enforcement actions taken on contract breach are idempotent — re-triggering the same action on the same breach produces zero additional side effects.
- **SC-012**: 100% of certifications that expire without renewal transition through "expiring" before "expired" (no direct active → expired transitions).
- **SC-013**: 100% of interactions and executions without a contract continue to behave identically to their pre-feature behavior (backward compatibility verifiable in regression test suite).

## Assumptions

- The existing certification subsystem supports adding status lifecycle columns and an external-certifier reference without a schema rewrite.
- The existing interactions and executions subsystems support adding an optional contract foreign key without breaking current consumers.
- Quality metric computations (accuracy, latency, etc.) already exist in the evaluation or runtime telemetry subsystems; this feature consumes those metrics rather than computing them.
- Material-change signals (agent revision deploys, policy attachments/detachments, training data changes) are already emitted by upstream systems on existing event channels; this feature consumes those signals rather than detecting changes itself.
- The existing operator alerting subsystem handles surveillance alerts (expiring / expired / suspended / revoked / missed-reassessment); this feature hands off to that infrastructure rather than implementing notifications.
- The default enforcement policy is `warn` when not explicitly set, consistent with "first do no harm" for brownfield rollout.
- Contracts are attachable independently of certifications — a contract does not require a certification to function, and a certification does not imply contract attachment.
- The reassessment schedule is expressed as a cron-style expression with minute resolution; schedules finer than one minute are out of scope.
- The grace period for material-change recertification is operator-configurable (default 14 days) and applies uniformly across all certifications unless per-certification override is specified.
- Compliance-rate query time buckets follow platform-standard granularity (daily by default, configurable to hourly for short windows).

## Dependencies

- Existing trust / certification subsystem, extended with external certifier reference, status lifecycle, expiry, and reassessment schedule.
- Existing agent registry (for contract agent reference and material-change revision signals).
- Existing interactions and workflow-execution subsystems (for contract attachment).
- Existing runtime telemetry (token usage, latency, quality metrics) consumed by the runtime monitor.
- Existing policy subsystem (for policy-change material-change signals).
- Existing operator alerting / notification subsystem (for certification lifecycle alerts).
- Existing audit trail and retention infrastructure.
- Existing RBAC and compliance-viewing role enforcement.
- Existing scheduled-job infrastructure (for surveillance and reassessment jobs).

## Out of Scope

- Computing the actual quality metrics (accuracy scoring, latency calibration, etc.); this feature assumes metrics are produced elsewhere and consumed here.
- Integrating with specific third-party certifier APIs (REST/protocol bridges to external certifier systems); only modeling the certifier entity and scoped issuance is in scope.
- Automated material-change detection; change signals come from upstream change-publishing subsystems.
- Defining or extending the set of quality-metric types themselves (e.g., adding new scorer categories).
- Building new UI surfaces for contract authoring or compliance dashboards; this feature defines the data and query surface that future UI features can consume.
- Automated arbitration or dispute resolution for contract breaches; breaches are recorded and escalated, but human dispute workflows are separate.
- Cross-tenant certification recognition (a certification issued in tenant A applying to agents in tenant B); scope is within a single tenant.
- Real-time streaming of compliance metrics; compliance queries are pull-based aggregations.
