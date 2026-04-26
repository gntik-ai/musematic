# Feature Specification: Incident Response and Runbooks

**Feature Branch**: `080-incident-response-runbooks`
**Created**: 2026-04-26
**Status**: Draft
**Input**: User description: "Integrate with PagerDuty/OpsGenie/VictorOps, provide inline runbooks for common incidents, publish post-mortem templates with timeline reconstruction from audit log + execution journal + Kafka events."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Auto-Triage of Operator-Visible Incidents to On-Call (Priority: P1)

When the platform's existing alerting machinery determines that something operator-visible has gone wrong (sustained error-rate spike, SLA breach, certification failure, security event, chaos-induced unexpected behavior), an incident MUST be opened in the platform AND, when an external paging integration is configured, simultaneously raised in the configured on-call provider so the right humans are notified through the channel they already trust. The incident MUST carry enough context — severity, title, plain-language description, and the executions/events that triggered it — that the responder can begin diagnosing without first chasing context across dashboards.

**Why this priority**: Until alerts reach the people on call with the context they need, every other capability in this feature (runbooks, post-mortems) is reading material rather than incident response. Auto-triage is the smallest end-to-end slice that turns the platform from "produces alerts" into "responds to incidents," and is the prerequisite that everything else builds on.

**Independent Test**: Configure a single paging-provider integration on a non-production deployment. Trigger each of the supported alert rule classes (sustained error spike, SLA breach, certification failure, security event, chaos scenario). Verify that for each one (a) an incident record is opened in the platform with severity, title, description, and the related executions/events, (b) a corresponding alert is raised in the external provider with a stable correlation reference, and (c) the operator dashboard shows the new incident in an Incidents view with the related context already populated.

**Acceptance Scenarios**:

1. **Given** a configured PagerDuty/OpsGenie/VictorOps integration and an enabled alert rule for "sustained error rate spike", **When** the underlying condition fires, **Then** the platform opens an incident with severity, title, plain-language description, and the related executions/events, AND raises a corresponding alert in the configured provider, AND the two are correlatable by a stable external reference.
2. **Given** an integration that is configured but explicitly disabled, **When** an alert rule fires, **Then** the platform still opens an internal incident record but does NOT call the external provider, and the incident clearly indicates that no external page was attempted.
3. **Given** an alert rule that fires repeatedly while a related incident is already open and unresolved, **When** the same condition fires again, **Then** the platform does not open a duplicate incident or page on-call again for the same active condition; instead, the existing incident is updated with the new occurrence.
4. **Given** an external provider is unreachable at the moment an incident is created, **When** the integration call fails, **Then** the internal incident is still created with full context, the failure is recorded as part of the incident, and the platform retries delivery according to its standard delivery-guarantee policy without losing the alert.
5. **Given** an alert rule maps to a severity (e.g., critical, high, warning), **When** an incident is created, **Then** the platform applies the configured per-integration severity mapping so that the external provider receives the severity in its own taxonomy.
6. **Given** an incident has been resolved in the platform, **When** the resolution is recorded, **Then** the corresponding external alert (if any) is also closed/acknowledged via the integration so the on-call queue stays clean.

---

### User Story 2 - Inline Runbooks at the Point of Incident (Priority: P2)

A responder looking at an open incident — or an operator scanning the dashboard before an alert fires — MUST be able to find a curated, scenario-specific runbook (symptoms, diagnostic steps, remediation steps, escalation path) without leaving the platform. The platform MUST ship with at minimum the ten highest-frequency operational scenarios already authored, and the runbook library MUST be editable so that learnings from real incidents flow back into the same place a future responder will look.

**Why this priority**: Once an incident reaches the on-call responder, the next bottleneck is "what do I do?" Centralizing institutional knowledge as runbooks accessible from the incident itself shortens MTTR and reduces dependence on tribal knowledge. Lower priority than P1 because runbooks without incident triage have no entry point; higher priority than P3 because most incidents need triage + remediation, not post-mortems, to be closed.

**Independent Test**: Seed the platform with the initial runbook library on a clean deployment. From the operator dashboard, navigate to the runbook for "Kafka lag" without an active incident — confirm it loads with symptoms, diagnostic steps, remediation steps, and escalation path. Then trigger a synthetic incident whose alert rule maps to the "Kafka lag" scenario, open the incident in the dashboard, and verify the runbook is one click (or a direct deep link) away from the incident view.

**Acceptance Scenarios**:

1. **Given** a fresh deployment of the platform, **When** the operator opens the runbook library, **Then** at least the ten initial scenarios listed in the planning input are present (pod failure, database connection issue, Kafka lag, model provider outage, certificate expiry, S3 quota breach, governance verdict storm, auth service degradation, reasoning engine OOM, runtime pod crash loop), each with non-empty symptoms, diagnostic steps, remediation steps, and escalation path.
2. **Given** an open incident whose triggering alert rule maps to a known runbook scenario, **When** the responder views the incident, **Then** the relevant runbook is surfaced inline (or one click away) with no manual lookup required.
3. **Given** an authorized operator updates a runbook based on a recent learning, **When** they save the change, **Then** the next responder seeing the same scenario sees the updated content, and the change is auditable (who edited what, when).
4. **Given** an incident whose alert rule has no associated runbook, **When** the responder views the incident, **Then** the dashboard clearly indicates "no runbook for this scenario" and offers an authorized path to create one rather than silently showing nothing.
5. **Given** a runbook contains diagnostic commands, **When** the responder views it, **Then** the commands are presented in a copy-friendly form so the responder can execute them quickly without re-typing.
6. **Given** a runbook has an escalation path, **When** the runbook is rendered, **Then** the escalation path is visible alongside the remediation steps so the responder knows when and to whom to escalate without leaving the runbook.

---

### User Story 3 - Blameless Post-Mortems with Reconstructed Timelines (Priority: P3)

After an incident is resolved, an authorized operator MUST be able to start a blameless post-mortem from the incident itself and have the platform automatically reconstruct a timeline of what actually happened by stitching together the audit log, the execution journal, and the relevant Kafka events surrounding the incident window. The post-mortem MUST capture impact assessment, root cause, and action items, and MUST link back to the affected executions and certifications so the historical record is complete and discoverable.

**Why this priority**: Post-mortems compound over time — they are how the platform gets better. They are P3 because they happen after the incident is closed; an organization can survive a missing post-mortem on one incident, but it cannot survive missing alerts (P1) or missing runbooks (P2) on every incident.

**Independent Test**: Take a closed incident from User Story 1 (the simulated sustained-error-spike scenario), start a post-mortem, and verify that (a) a timeline is generated covering the relevant window pulling from audit, execution journal, and Kafka, (b) the post-mortem entity carries impact, root cause, and action items, (c) the post-mortem links the executions affected during the incident window, (d) the post-mortem can be marked blameless and exported for distribution, and (e) navigating from any of the linked executions or certifications surfaces the post-mortem.

**Acceptance Scenarios**:

1. **Given** a resolved incident, **When** an authorized user starts a post-mortem from the incident view, **Then** the platform generates a draft timeline covering the incident window using events from the audit log, the execution journal, and the relevant Kafka topics, presented in chronological order.
2. **Given** a draft post-mortem, **When** the author records impact assessment, root cause, and action items, **Then** the values are persisted, attributed to the author, and visible to anyone with access to the post-mortem.
3. **Given** a completed post-mortem, **When** the author marks it blameless, **Then** the artifact is recorded as blameless and the platform's UX presentation reflects the blameless-post-mortem norm (no individual is implicated as the cause).
4. **Given** a completed post-mortem, **When** the author distributes it, **Then** the configured distribution list receives the artifact, and the distribution event is itself recorded.
5. **Given** a post-mortem references one or more executions, **When** anyone views the linked execution, **Then** the post-mortem is discoverable from the execution detail view (and vice-versa).
6. **Given** a post-mortem references a certification, **When** anyone views the certification, **Then** the post-mortem is discoverable from the certification detail view (and vice-versa).
7. **Given** the timeline reconstruction sources data from multiple subsystems and one of them is temporarily unavailable, **When** the timeline is generated, **Then** the post-mortem clearly indicates which sources contributed and which were unavailable, rather than silently producing a partial timeline that looks complete.

---

### Edge Cases

- **Repeated firing of the same condition**: Duplicate alerts for an unresolved incident MUST update, not multiply. On-call must not be re-paged for the same open condition.
- **Provider unreachable at trigger time**: External provider failures MUST NOT lose the internal incident. The platform retries delivery to the external provider while keeping the local record canonical.
- **Severity-mapping mismatch**: An alert rule with a severity that has no mapping in the configured integration MUST fail safe — either fall back to a documented default severity or refuse to deliver and surface the misconfiguration loudly. Silent severity dropping is unacceptable.
- **Disabled integration**: An integration explicitly toggled off MUST NOT be called, but the internal incident MUST still be created so internal investigation is not blocked by an external silence.
- **No paging integration configured at all**: The platform MUST still produce internal incidents and surface them in the dashboard. External paging is an enhancement, not a precondition.
- **Alert resolved before page acknowledged**: When the underlying condition clears before on-call acknowledges, the platform MUST close the external alert (when the provider supports it) and clearly mark the internal incident as auto-resolved.
- **Runbook drift**: A runbook that has not been updated for a long time MUST be visibly flagged as stale to the responder so they can apply judgment, but the runbook MUST NOT be hidden — outdated guidance is better than no guidance at the moment of an incident.
- **Concurrent runbook edits**: Two operators editing the same runbook simultaneously MUST surface the conflict; silently overwriting one author's changes is not acceptable.
- **Post-mortem on a years-old incident**: Timeline reconstruction MUST gracefully handle the case where source data has aged out of one or more retention windows, indicating which segments are missing rather than fabricating continuity.
- **Post-mortem started on an unresolved incident**: The platform MUST either prevent this (preferred) or clearly mark the post-mortem as "draft over an open incident" so it is not mistaken for the canonical record.
- **Distribution list contains an inactive recipient**: Distribution MUST not silently swallow undeliverable recipients; the failed delivery MUST be surfaced so the operator can fix the list.
- **Cross-incident correlation**: When multiple alert rules fire simultaneously due to a single underlying root cause, the platform's behavior (one umbrella incident vs. multiple linked incidents) MUST be consistent and documented; arbitrary merging or splitting depending on the order alerts arrive is unacceptable.
- **Authorized-edit boundary**: Runbook editing and post-mortem authoring are administrative operations. The platform's existing RBAC layer governs both — a viewer-role responder MUST be able to read but not edit; an unauthorized user MUST NOT see incident detail pages they cannot otherwise access.
- **External alert acknowledged in the provider**: When an on-call user acknowledges/resolves the alert in PagerDuty/OpsGenie/VictorOps directly, the platform's incident state SHOULD reflect that acknowledgement so dashboards do not lie. If two-way sync is out of scope for v1, the limitation MUST be documented in the integration UI rather than silently divergent.

## Requirements *(mandatory)*

### Functional Requirements

**Integrations and Triage (FR-505)**

- **FR-505.1**: System MUST support configurable integrations with at least PagerDuty, OpsGenie, and VictorOps; each integration MUST be independently enabled/disabled by an authorized operator.
- **FR-505.2**: System MUST allow each integration to declare a severity mapping that translates platform incident severity into the provider's severity taxonomy.
- **FR-505.3**: System MUST be able to translate a matching alert rule firing into a platform incident record carrying severity, title, description, the executions and events that contextualize it, and a triggered-at timestamp.
- **FR-505.4**: System MUST raise an external alert in every enabled integration whose configuration applies to the incident, and MUST persist the external reference (or the failure to obtain one) on the internal incident.
- **FR-505.5**: System MUST suppress duplicate incidents for the same active underlying condition; recurrence updates the existing open incident rather than creating a new one.
- **FR-505.6**: System MUST gracefully handle external provider unavailability — internal incident creation MUST succeed, and external delivery MUST be retried per the platform's standard delivery-guarantee policy.
- **FR-505.7**: System MUST close or acknowledge external alerts when the corresponding internal incident is resolved, when the provider supports such an action.
- **FR-505.8**: System MUST allow the alert rule classes called out in FR-505 (sustained error rate spike, SLA breach, certification failure, security event, chaos-triggered unexpected behavior) to be configured as incident triggers.
- **FR-505.9**: Provider integration credentials MUST be stored via the platform's existing secret-resolution mechanism — never in the database, code, or logs.

**Runbooks (FR-506)**

- **FR-506.1**: System MUST provide a runbook library accessible from the operator dashboard that contains, at minimum, the ten initial scenarios enumerated in the planning input (pod failure, database connection issue, Kafka lag, model provider outage, certificate expiry, S3 quota breach, governance verdict storm, auth service degradation, reasoning engine OOM, runtime pod crash loop).
- **FR-506.2**: Each runbook MUST capture symptoms, diagnostic steps, remediation steps, and an escalation path; none of these fields may be empty in the seeded set.
- **FR-506.3**: An incident whose triggering alert rule maps to a known runbook scenario MUST surface that runbook inline (or via a one-click deep link) from the incident view.
- **FR-506.4**: Authorized operators MUST be able to create, update, and retire runbooks; updates MUST be auditable (who, when, what changed).
- **FR-506.5**: Diagnostic commands within a runbook MUST be presented in a form that supports quick copy-and-execute by the responder; long unwieldy command transcriptions are not acceptable.
- **FR-506.6**: Stale runbooks (not updated within a documented freshness window) MUST be visibly flagged to the responder; staleness MUST NOT hide the runbook.
- **FR-506.7**: When an incident has no matching runbook, the dashboard MUST surface that absence as an actionable signal — not a silent gap — so the operator can author one.

**Post-Mortems (FR-507)**

- **FR-507.1**: Authorized users MUST be able to create a post-mortem for any resolved incident from the incident view.
- **FR-507.2**: System MUST automatically generate a draft timeline for the post-mortem by stitching the audit log, the execution journal, and the relevant Kafka events covering the incident window, presented in chronological order.
- **FR-507.3**: The post-mortem MUST capture impact assessment, root cause, action items, and a distribution list, with author attribution and timestamps.
- **FR-507.4**: Post-mortems MUST be markable as blameless and the platform's UX presentation MUST reflect that disposition.
- **FR-507.5**: Post-mortems MUST be linkable to (and discoverable from) the executions affected during the incident window and the certifications associated with the affected agents.
- **FR-507.6**: When timeline reconstruction encounters a source that is unavailable or has aged past its retention window, the post-mortem MUST clearly indicate which sources contributed and which were missing — never produce a partial timeline that looks complete.
- **FR-507.7**: Distribution of a post-mortem MUST be recorded as an event; failed deliveries to recipients MUST surface as feedback to the operator rather than being silently dropped.

**Cross-Cutting**

- **FR-CC-1**: All incident, runbook, and post-mortem operations MUST be governed by the platform's existing RBAC and admin-endpoint segregation rules — administrative actions live behind admin role gates and do not mingle with user-facing endpoints.
- **FR-CC-2**: All administrative actions on integrations, runbooks, and post-mortems (creation, modification, retirement, distribution) MUST emit audit chain entries via the platform's existing audit-chain service — never written directly.
- **FR-CC-3**: System MUST emit incident lifecycle events (`incident.triggered`, `incident.resolved`) on the platform's event backbone so other subsystems (notifications, post-mortem service, downstream analytics) can react without polling.
- **FR-CC-4**: Incident, runbook, and post-mortem records MUST survive workspace archival and platform upgrades; the historical record is durable.
- **FR-CC-5**: The visibility and interoperability path MUST integrate with the platform's existing notifications subsystem rather than introduce a parallel notification channel; external paging providers are the only new outbound integration path this feature owns.
- **FR-CC-6**: All operator-facing surfaces (incident detail, runbook viewer, post-mortem composer) MUST be reachable from the existing operator dashboard rather than living in a separate application.

### Key Entities

- **Incident Integration**: A configured connection to an external on-call provider (PagerDuty, OpsGenie, VictorOps). Carries an enable flag, a reference to the credential held in the platform's secret store (never the credential itself), and a severity mapping into the provider's taxonomy. Additional providers may be added in the future without re-architecting this entity.
- **Incident**: A platform-recognized operational event with a severity, a title, a plain-language description, a triggered-at timestamp, an optional resolved-at timestamp, an optional external reference back to the originating provider, and pointers to the executions and events that contextualize it. The internal canonical record of "something operator-visible happened."
- **Runbook**: A scenario-keyed knowledge artifact: symptoms, diagnostic steps, remediation steps, and escalation path. Editable, audited, freshness-tracked. The library ships seeded with the ten initial scenarios.
- **Post-Mortem**: A blameless artifact attached to a resolved incident. Carries an automatically-reconstructed timeline (sourced from audit, journal, events), impact assessment, root cause, action items, and a distribution list. Linkable to affected executions and certifications.
- **Alert Rule Mapping**: The relationship between an alert rule class (e.g., "sustained error spike") and (a) the severity to apply, (b) the runbook scenario to surface on the resulting incident. This is a configuration concern, not a stored data structure in this spec — exact representation is left to planning, but the relationship MUST be expressible.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With at least one paging integration configured, every supported alert rule class produces both an internal incident and an external alert within the platform's stated alert-delivery latency budget; loss rate of external alerts under normal operating conditions is zero.
- **SC-002**: Repeated firings of the same active condition produce zero duplicate incidents and zero duplicate external pages — verified by driving a sustained synthetic alert-storm and inspecting the resulting incident and external-alert counts.
- **SC-003**: When the configured external provider is intermittently unreachable, no internal incidents are lost; all eventually deliver to the provider once it recovers, within the platform's standard delivery-retry envelope.
- **SC-004**: The runbook library on a fresh deployment contains exactly the ten initial scenarios with all four required fields populated for each, verified by an automated post-install assertion.
- **SC-005**: For every incident whose alert rule maps to a known runbook scenario, the responder can reach the runbook from the incident view in one click — verified by automated UI tests across the supported alert rule classes.
- **SC-006**: Mean responder time-to-first-action on a P1-severity incident decreases (compared to a pre-feature baseline) by a target percentage agreed during planning, attributable to inline runbook surfacing.
- **SC-007**: A post-mortem started on a closed incident produces a draft timeline in chronological order combining audit, journal, and event sources, with explicit indication of any source that was unavailable.
- **SC-008**: Every post-mortem is reachable from the incident, every linked execution, and every linked certification — bidirectional discoverability is verified by automated tests across all three entry points.
- **SC-009**: No audit-relevant action (integration create/edit/disable, runbook edit, post-mortem create/distribute) occurs without a corresponding audit chain entry — verified by an automated audit-coverage check.
- **SC-010**: Severity mapping correctness: for every supported (provider, platform-severity) pair, the external alert carries the configured provider-severity — verified by an automated integration test against provider sandboxes (or platform-supplied mocks where sandbox access is impractical).

## Assumptions

- The platform's existing alerting machinery (`analytics/services/alert_rules.py` and the rules surface above it) is the upstream of this feature; this feature is downstream of "an alert rule has fired" and does not redesign rule evaluation.
- The platform's existing audit chain, notifications, and RBAC subsystems are reused; this feature does not introduce a parallel audit, notification, or authorization path.
- The platform's existing operator dashboard is the home for incident, runbook, and post-mortem UIs; no new application is created.
- The platform's existing secret-resolution mechanism is used for paging-provider credentials; database, code, and logs do not contain the credentials.
- The execution journal, audit log, and the relevant Kafka topics retain at least enough history to make post-mortem timeline reconstruction useful for incidents within the platform's stated incident-investigation horizon. The exact retention requirements are determined during planning.
- The platform-default time zone (already declared at deployment) is used to render incident, runbook, and post-mortem timestamps in operator-facing surfaces; per-user time-zone rendering is out of scope for v1.
- The set of supported paging providers is fixed at v1 to PagerDuty, OpsGenie, and VictorOps; the entity model permits adding more later without redesign.
- The set of seeded runbook scenarios is the ten enumerated in the planning input; further scenarios are operator-authored over time.
- Two-way state sync with the external paging provider (e.g., reflecting provider-side acknowledgement back into the platform incident) is desirable but not a strict v1 requirement; if not delivered in v1, the limitation MUST be documented in the integration UI.

## Out of Scope (v1)

- A full case-management system (assignment, shifts, rotations, paging escalation policies) inside the platform — those concerns belong to the external paging provider.
- A bidirectional state-sync engine that fully reflects provider-side state changes back into the platform incident, beyond best-effort acknowledgement-on-resolution.
- Auto-generation of action items via root-cause analysis or LLM reasoning over the timeline — drafting remains a human task in v1.
- Incident-to-incident correlation engines that infer common root causes across simultaneous unrelated alerts — the v1 behavior is "one alert per incident with deduplication of the same active condition" and any cross-incident correlation is left to operators.
- Public, customer-facing incident communication. The platform's public status page already addresses that surface; this feature is internal to platform operators.
- Provider-specific advanced features (PagerDuty Event Orchestration, OpsGenie Heartbeat-style health checks, VictorOps custom routing rules) are not generalized in v1; only the standard alert-create / alert-resolve actions are exercised.

## Dependencies and Brownfield Touchpoints

This feature is additive to the existing platform. The relevant existing capabilities the new bounded context relies on or extends:

- **Analytics alert rules** (`analytics/services/alert_rules.py`): the upstream signal that drives incident creation. This feature subscribes to that rule-firing path; it does not replace it.
- **Operator dashboard**: the existing surface for operator workflows. This feature adds an Incidents tab with runbook links, an inline runbook viewer, and a post-mortem composer rather than introducing a new application.
- **Audit chain** (`security_compliance/services/audit_chain_service.py`): the canonical write path for all administrative actions on integrations, runbooks, and post-mortems. This feature does not write audit entries directly.
- **Notifications**: the platform's existing notification subsystem is the delivery channel for any internal-to-platform notifications (e.g., post-mortem distribution receipts). External paging providers are the only new outbound channel this feature owns.
- **Execution journal**, **audit log**, and **Kafka topics**: the data sources for post-mortem timeline reconstruction. This feature reads from these sources via well-defined query interfaces; it does not mutate them.
- **Trust and certification**: post-mortems can reference affected agents' certifications. The cross-link is integration-level, not a schema change to the certification entity.
- **Secret store**: paging-provider credentials live in the platform's existing secret store and are referenced by ID, never inlined.
- **Existing `incident_response/` bounded context** (declared in the constitution under "New Bounded Contexts" and owning the `/api/v1/incidents/*` and `/api/v1/runbooks/*` REST prefixes, the `incident.triggered` and `incident.resolved` Kafka topics, and feature UPD-031): this is the home for the implementation. The Kafka topics and REST prefixes are reserved at the constitutional level and MUST be used.

The implementation strategy (specific tables, services, schemas, and code-level integration points) is intentionally deferred to the planning phase. The brownfield input that motivated this spec is preserved in the feature folder as `planning-input.md`.
