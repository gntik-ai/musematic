# Feature Specification: Multi-Region High-Availability Deployment

**Feature Branch**: `081-multi-region-ha`
**Created**: 2026-04-26
**Status**: Draft
**Input**: User description: "Add multi-region active-passive deployment support with documented replication for all data stores, active-active considerations documentation, zero-downtime upgrade procedures, maintenance mode, and capacity planning."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Active-Passive Disaster-Recovery Posture (Priority: P1)

A platform operator running production in a single region MUST be able to declare a second region as a continuously-replicated passive standby — and at any moment know, with confidence, whether that standby is fresh enough to be useful in a disaster. The platform's data stores (relational system-of-record, event backbone, object storage, OLAP, vector, graph, full-text) MUST replicate to the secondary region within an operator-stated **Recovery Point Objective (RPO)**, and the operator MUST be able to declare a target **Recovery Time Objective (RTO)** that the failover procedure (User Story 2) is designed to meet. Without a trustworthy passive standby, no other multi-region capability has value.

**Why this priority**: Disaster recovery without measurable replication is theatre. An operator who cannot answer "is the secondary fresh enough to fail over to right now?" within seconds cannot make the cutover decision under pressure. P1 is "the secondary exists, is replicating every store, and the freshness is observable" — the floor below which everything else (User Stories 2–5) is meaningless.

**Independent Test**: Stand up a secondary region against a non-production primary using the platform's existing deployment surface. Confirm that for each data store category — relational, event backbone, object storage, OLAP, vector, graph, full-text — there is a configured replication path with a measurable lag in seconds, that the operator dashboard surfaces those lags in one place, that a synthetic disturbance (e.g., pause replication for one component) produces an alert against the operator-declared RPO threshold, and that resuming replication clears the alert.

**Acceptance Scenarios**:

1. **Given** a primary region is running production and a secondary region is configured as passive, **When** an authorised operator opens the operator dashboard's regions view, **Then** the per-component replication lag (one row per (source, target, component) tuple) is visible with a clear "healthy / degraded / unhealthy" indicator and a measured-at timestamp.
2. **Given** an operator-declared RPO target of 15 minutes for the secondary, **When** any component's replication lag crosses that threshold for a sustained interval, **Then** the platform raises an alert through the existing operational alerting path with the component, source, target, observed lag, and threshold included in the payload.
3. **Given** a secondary region was previously degraded and replication has caught up, **When** the lag returns below the threshold for a sustained interval, **Then** the alert is auto-cleared and the dashboard returns to "healthy" without operator intervention.
4. **Given** a passive secondary with replication intentionally paused for maintenance, **When** the operator queries the dashboard, **Then** the paused state is distinguishable from an unintended outage and the operator-declared reason is visible.
5. **Given** a secondary region with no replication path configured for one of the required data stores, **When** the operator views the regions configuration, **Then** that gap is surfaced explicitly (not silently hidden) so the operator knows the DR posture is incomplete for that store.

---

### User Story 2 - Documented and Auditable Failover Procedure (Priority: P2)

When the primary region degrades to the point of needing a cutover, an authorised operator MUST be able to execute a **named failover plan** from the platform that captures the steps, who initiated it, when, why, and the per-step outcome. The same plan MUST be exercisable as a quarterly rehearsal against a non-production target so the team's muscle memory and the plan's correctness are kept fresh — failovers that are never tested fail unpredictably under real pressure.

**Why this priority**: Replication without a tested failover plan is a half-built bridge. The failover step is where most disaster-recovery exercises actually fail — a plan that worked on a whiteboard breaks on the day because the secondary's DNS, the application's region pointer, or a runbook command is wrong. P2 is "the cutover is rehearsable, auditable, and produces a clear pass/fail outcome at every step" — without it, the P1 standby has theoretical value only.

**Independent Test**: Author a failover plan from primary→secondary on a non-production deployment; execute it as a rehearsal; verify that each step's outcome (succeeded, failed-with-reason, skipped) is recorded; verify the plan's `tested_at` timestamp updates; intentionally break one step (e.g., a step references a hostname that does not resolve) and re-run the rehearsal — confirm the failure is surfaced clearly and stops execution at the broken step rather than silently continuing.

**Acceptance Scenarios**:

1. **Given** a configured primary and secondary region, **When** an authorised operator authors a failover plan with named steps, **Then** the plan is persisted, named, scoped to a specific (from_region, to_region) pair, and visible alongside other plans in the regions view.
2. **Given** an existing failover plan, **When** an authorised operator executes it as a rehearsal against a non-production target, **Then** each step records succeeded / failed / skipped with a per-step duration and any error detail, the plan's `tested_at` timestamp updates, and the rehearsal does NOT alter production routing.
3. **Given** a failover plan rehearsal where a step fails, **When** the failure occurs, **Then** execution halts at the failing step (does not silently proceed), the failure reason is recorded against the run, and an alert reaches the operator.
4. **Given** a real production failover, **When** an authorised operator executes the plan, **Then** the platform records `last_executed_at`, emits an event indicating failover initiated and (subsequently) completed, and every action taken during the plan is auditable end-to-end via the platform's existing audit chain.
5. **Given** a failover plan that has not been rehearsed within the operator-declared rehearsal interval, **When** the operator views the regions dashboard, **Then** the staleness is visibly flagged (without hiding the plan) so the team knows to schedule a rehearsal.
6. **Given** a failover-in-progress, **When** any concurrent operator attempts to start the same or a conflicting plan, **Then** the platform refuses with a clear, actionable error rather than allowing two simultaneous cutovers.

---

### User Story 3 - Maintenance Mode that Drains Cleanly and Speaks Plainly (Priority: P3)

For planned upgrades and unplanned but controlled disturbances, an authorised operator MUST be able to schedule a **maintenance window**, enable maintenance mode at the start, and have the platform: (a) refuse new writes (executions, conversations, mutating API calls) with a clear, user-visible message, (b) allow already-in-flight work to complete rather than killing it, (c) keep read-only operations (marketplace browsing, audit log access, dashboards) available, (d) communicate the window through the platform's existing user-facing status surface so users see context not silence, and (e) cleanly resume on disable.

**Why this priority**: Maintenance mode is the everyday tool that makes upgrades and disturbances safe; failovers (P2) are rare. Without a maintenance gate, every scheduled disturbance either silently corrupts in-flight work or produces a flood of confused user reports. P3 is "the platform can take itself partially offline gracefully and tell users why" — and is the prerequisite for the zero-downtime upgrade procedure (User Story 4).

**Independent Test**: Schedule a maintenance window on a non-production deployment; arrange an in-flight execution to be running at the window start; enable maintenance mode at the scheduled start; verify that (a) new mutating API calls return a clear maintenance message, (b) the in-flight execution runs to completion (is not killed), (c) read-only endpoints continue to return data, (d) the user-facing platform status surface shows the configured announcement, (e) disable the mode and confirm new writes resume.

**Acceptance Scenarios**:

1. **Given** maintenance mode is disabled, **When** an authorised operator schedules a maintenance window with a future `starts_at`, an `ends_at`, a reason, and an announcement text, **Then** the window is persisted in `scheduled` state and visible to operators; the user-facing status surface shows an upcoming-maintenance banner sufficiently in advance.
2. **Given** a scheduled window's `starts_at` arrives, **When** the platform transitions into maintenance mode (automatically or by operator action), **Then** the configured announcement is presented to UI and API callers, and writes are refused with a clear error that names the window, reason, and `ends_at`.
3. **Given** an execution is already running when maintenance mode is enabled, **When** the mode is enabled, **Then** that execution is allowed to continue to completion (in-flight work is not aborted by the mode itself).
4. **Given** maintenance mode is enabled with `blocks_writes=true`, **When** a caller attempts a read-only operation (browsing the marketplace, viewing audit history, querying a dashboard), **Then** the operation succeeds — read-only access is preserved.
5. **Given** maintenance mode is enabled, **When** the configured `ends_at` arrives or the operator disables the mode, **Then** writes resume immediately, the user-facing announcement is removed, and the window's status transitions to `completed`.
6. **Given** a failed maintenance disable (e.g., a downstream resume step errored), **When** the failure occurs, **Then** the operator dashboard surfaces a clear "maintenance disable failed" alert with the underlying reason, and the platform does NOT silently leave writes blocked.
7. **Given** a non-operator caller, **When** they attempt to schedule, enable, or disable maintenance, **Then** the action is refused with a 403 and the attempt is auditable.

---

### User Story 4 - Zero-Downtime Platform Upgrades Through Documented Patterns (Priority: P4)

The platform MUST publish a documented, repeatable procedure for upgrading any service or schema **without taking the platform fully offline**. The procedure MUST cover: (a) rolling upgrades of stateless services so callers always reach a healthy instance, (b) the **expand-migrate-contract** pattern for database schema changes (additive columns and tables before any writes; rename via dual-write; drop only after the read side has been verified on the new shape), (c) **agent runtime versioning** so a new and an old runtime can coexist during the upgrade window, and (d) explicit rollback steps that are themselves zero-downtime. The procedure MUST be linked from the operator dashboard so it is reachable at the moment of an upgrade, not buried.

**Why this priority**: Zero-downtime upgrades are how the platform avoids needing User Story 3 for every weekly change. P4 is the codified institutional knowledge that turns "we sometimes upgrade without downtime" into "we always upgrade without downtime, by following this procedure." Without it, every upgrade defaults to maintenance mode, which is operationally expensive and customer-visible.

**Independent Test**: Take an additive schema change (e.g., adding a column with a default), execute it against a non-production deployment using the documented procedure; verify the platform stays available throughout, the new column is populated for new writes, and old code paths that do not reference the new column continue to function. Then take a rename change executed via dual-write and confirm the procedure reaches a state where the platform can read either the old or new column safely. Finally, exercise a rollback step from the published procedure and confirm it returns the platform to the prior state without downtime.

**Acceptance Scenarios**:

1. **Given** the platform's published upgrade procedure, **When** an additive schema change is performed against a non-production deployment, **Then** at no point during the change is the platform unavailable for either reads or writes, and the change is reversible per the published rollback step.
2. **Given** the published upgrade procedure, **When** a stateless service is upgraded as a rolling deployment, **Then** at every moment of the rollout there exists at least one healthy instance handling traffic, and no caller observes a downtime gap.
3. **Given** an upgrade that requires a column rename, **When** executed via the dual-write pattern in the published procedure, **Then** there exists a defined intermediate state where both column names are valid for reads, and the procedure documents how to verify the new shape before dropping the old.
4. **Given** an upgrade that introduces a new agent runtime, **When** the new runtime is deployed alongside the existing one, **Then** both are simultaneously serviceable for a documented coexistence window so existing executions complete on their original runtime version.
5. **Given** an upgrade that fails at any step, **When** the operator follows the published rollback step, **Then** the platform returns to the prior state without downtime, and the rollback itself is auditable.
6. **Given** an operator viewing the operator dashboard during an upgrade, **When** the upgrade procedure is referenced, **Then** the procedure is reachable from the dashboard (not only from external documentation) so it is in-context at the moment of need.

---

### User Story 5 - Capacity Planning Signals That Reach the Operator Before Saturation (Priority: P5)

The operator dashboard MUST surface forward-looking capacity signals: **historical usage trends**, **projected usage based on growth curves**, **resource utilization alerts ahead of saturation**, and **cost forecasts**, with **recommended actions** (scale up, throttle, restrict new workspace creation) when a saturation horizon is approached. The intent is to avoid the case where the platform learns about its own scaling problem from user complaints.

**Why this priority**: Capacity planning is "look ahead so the operator does not learn about saturation from a user complaint." It is P5 because it depends on the rest of the platform being operationally functional first (P1–P4), and because its value is preventive rather than acute. But it pays back consistently — every dashboard signal that fires before saturation prevents a different incident.

**Independent Test**: On a deployment with at least one full historical window of usage data, open the operator dashboard's capacity view; confirm a historical usage chart, a projected-usage curve, a saturation horizon for the most-loaded resource, and at least one recommended action when the projection crosses an operator-declared threshold. Drive synthetic load to push utilization toward saturation and confirm that an alert is raised ahead of saturation, not at it.

**Acceptance Scenarios**:

1. **Given** at least one operator-declared minimum window of historical usage, **When** the operator opens the dashboard's capacity view, **Then** historical trends and a forward projection are visible per major resource class with a clearly indicated freshness timestamp.
2. **Given** a projected utilization curve that crosses an operator-configured saturation horizon (e.g., projected usage > 80% of capacity in N days), **When** the projection updates, **Then** an alert is raised that names the resource, the projected horizon, and at least one recommended action.
3. **Given** insufficient historical data to project confidently, **When** the dashboard renders, **Then** the projection is flagged as low-confidence rather than silently displaying a misleading number.
4. **Given** a recommended action surfaced on the dashboard (e.g., "scale up component X"), **When** the operator clicks through, **Then** the dashboard provides the operator a path to act (linking to the relevant control surface or runbook) rather than leaving them to translate the recommendation into a procedure on their own.
5. **Given** historical capacity data exists but actual recent observations diverge sharply from the projection, **When** the dashboard renders, **Then** the divergence is surfaced (the projection's accuracy is itself observable).

---

### Edge Cases

- **Replication paused intentionally vs. unintentionally**: The dashboard MUST distinguish operator-paused replication (with a stated reason) from an unintended outage. Both surface the same lag, but the implications are different.
- **Replication catch-up after a long disruption**: When a previously-disconnected secondary catches up over hours, the dashboard MUST show the catching-up trajectory rather than oscillating between "alerting" and "clearing".
- **Partial replication coverage**: A secondary with replication for only some data stores is a real and legitimate intermediate state; the dashboard MUST mark uncovered stores explicitly rather than implying full coverage.
- **Failover plan with an unresolvable hostname**: A plan whose steps reference resources that do not currently resolve MUST surface the issue at rehearsal (preferably at authoring) — never silently succeed and produce a real-cutover surprise.
- **Failover during ongoing maintenance**: If maintenance mode is active when a failover is initiated, the platform MUST behave consistently — either complete maintenance first, or override with a clearly-documented and audited "emergency failover" path.
- **Two operators initiating overlapping plans**: Concurrent failover initiation MUST be refused with an actionable error; never two simultaneous cutovers.
- **Maintenance mode disabling fails partway**: If disable encounters an error mid-procedure, the platform MUST NOT silently leave writes blocked; the operator dashboard MUST raise an actionable alert.
- **Maintenance window scheduled in the past**: A retroactive window MUST be rejected at scheduling time (or scheduled as `completed` immediately, with a clear note) — never silently bring the platform offline.
- **Maintenance window overlaps with another**: The system MUST decide deterministically (e.g., extend or refuse) and document the rule rather than letting overlapping windows produce an ambiguous state.
- **In-flight execution that exceeds the maintenance window**: The procedure MUST document the policy when an in-flight execution outlives the configured `ends_at` (e.g., extend the window automatically, or end the window and let the execution finish without re-blocking writes — but not both inconsistently).
- **Read-only operations during maintenance**: Browsing the marketplace, viewing audit history, and querying dashboards MUST remain available; the maintenance gate MUST distinguish read from write rather than blanket-blocking.
- **Active-active misconfiguration attempt**: An operator attempting to enable both regions as primary simultaneously MUST be refused with a clear pointer to the active-active documentation, not allowed to silently produce a split-brain.
- **Secondary promoted during a partial-replication state**: Failover MUST surface what data is and is not present at the promoted region, rather than silently presenting a hole as completeness.
- **Capacity projection during onboarding**: A brand-new deployment with no history MUST show "insufficient history" rather than a misleading flat projection.
- **Capacity recommendation that is no longer applicable**: A previously-surfaced recommendation that has been resolved (e.g., the operator already scaled the resource) MUST clear automatically — recommendations that linger after resolution are noise.
- **Zero-downtime upgrade rollback that fails**: The published procedure MUST include the case where a rollback step itself fails, so the operator does not have to invent a recovery path under pressure.
- **Operator dashboard reachable during a partial outage**: The capacity, regions, maintenance, and failover-plan views MUST remain reachable during partial outages — they are precisely the surfaces an operator needs in that moment.

## Requirements *(mandatory)*

### Functional Requirements

**Active-Passive Replication (FR-478)**

- **FR-478.1**: System MUST support declaring one or more secondary regions configured as passive standbys to a single primary region.
- **FR-478.2**: System MUST replicate every data-store category that holds production state — the relational system-of-record, the event backbone, object storage, OLAP analytics, vector search, graph, and full-text search — from the primary to each declared secondary.
- **FR-478.3**: System MUST surface, per (source region, target region, component) tuple, an observed replication lag in seconds and a categorical health state (e.g., healthy / degraded / unhealthy) with a measured-at timestamp.
- **FR-478.4**: System MUST allow an operator to declare an RPO target per region; replication lag exceeding that target for a sustained interval MUST produce an alert through the platform's existing operational alerting path; the alert MUST auto-clear once lag returns below the threshold for a sustained interval.
- **FR-478.5**: System MUST allow an operator to declare an RTO target per region; the failover plans declared for that region MUST be evaluated against the RTO target as part of plan authoring or rehearsal, surfacing any plan whose measured rehearsal duration exceeds the RTO.
- **FR-478.6**: System MUST distinguish operator-paused replication (with a stated reason) from an unintended outage in dashboard presentation and alert behaviour.
- **FR-478.7**: System MUST surface a missing replication path for a configured secondary as an explicit gap rather than silently treating uncovered stores as healthy.

**Failover (FR-478 cont.)**

- **FR-478.8**: Authorised operators MUST be able to author named failover plans scoped to a specific (from_region, to_region) pair, with ordered steps capturing the operations to perform.
- **FR-478.9**: Authorised operators MUST be able to execute a plan as a non-production rehearsal whose outcomes are recorded per step (succeeded / failed / skipped, duration, error detail) and whose execution does NOT alter production routing.
- **FR-478.10**: Authorised operators MUST be able to execute a plan as a real production failover; execution MUST emit a `region.failover.initiated` event at the start and a `region.failover.completed` event at the end (constitutionally-declared topics, lines 769–770), and every action MUST be auditable end-to-end via the platform's existing audit chain.
- **FR-478.11**: A failed step in a plan execution MUST halt execution at that step and surface the failure; the platform MUST NOT silently continue past a failed step.
- **FR-478.12**: Concurrent attempts to start the same or a conflicting plan MUST be refused with an actionable error; the platform MUST NOT permit two simultaneous cutovers.
- **FR-478.13**: A plan that has not been rehearsed within the operator-declared rehearsal interval MUST be visibly flagged as stale; the plan MUST NOT be hidden — staleness is a signal, not a quarantine.
- **FR-478.14**: Plans MUST be linkable to the runbooks (feature 080) that document their human-procedural counterparts, so the operator's dashboard view of a plan reaches the relevant runbook in one hop.

**Active-Active Considerations (FR-479)**

- **FR-479.1**: System MUST publish documentation that explicitly identifies which subsystems can run active-active without additional conflict resolution (stateless services — the API surface, workflow engine, runtime controller) and which cannot (the relational system-of-record as primary, the global agent-namespace registry).
- **FR-479.2**: System MUST refuse, with a clear actionable error, an operator configuration that attempts to enable two regions as primary simultaneously without a documented and explicitly-acknowledged conflict resolution strategy in place. A silent split-brain is unacceptable.
- **FR-479.3**: Active-active deployments MUST NOT be the default; the default deployment posture is active-passive per FR-478.

**Zero-Downtime Upgrades (FR-480)**

- **FR-480.1**: System MUST publish a documented, repeatable upgrade procedure that supports rolling upgrades of stateless services such that no caller observes a downtime gap during a rollout.
- **FR-480.2**: Schema changes MUST follow the **expand-migrate-contract** pattern as documented: additive (new columns, new tables) before any writes against them; renames via dual-write; drops only after the read side has been verified on the new shape.
- **FR-480.3**: System MUST support **agent runtime versioning** so that a new and an old runtime can coexist for a documented window, allowing in-flight executions to complete on their original runtime version while new executions are routed to the new version.
- **FR-480.4**: The upgrade procedure MUST include explicit, themselves-zero-downtime, rollback steps for each phase; rollback steps MUST themselves be auditable.
- **FR-480.5**: The procedure MUST be reachable from the operator dashboard at the moment of an upgrade — not only from external documentation.
- **FR-480.6**: The procedure MUST address the rollback-fails-too case so the operator is not left to invent a recovery path under pressure.

**Maintenance Mode (FR-481)**

- **FR-481.1**: Authorised operators MUST be able to schedule a maintenance window with `starts_at`, `ends_at`, a reason, an announcement text visible to users, and a `blocks_writes` flag.
- **FR-481.2**: When maintenance mode is enabled, the platform MUST refuse new mutating API calls (executions, conversations, write endpoints) with a clear error that names the window, the reason, and the `ends_at`.
- **FR-481.3**: When maintenance mode is enabled, in-flight executions MUST be allowed to continue to completion; the mode itself MUST NOT abort in-flight work.
- **FR-481.4**: When maintenance mode is enabled, read-only operations (marketplace browsing, audit log access, dashboards) MUST remain available.
- **FR-481.5**: The configured announcement text MUST be visible to users through the platform's existing user-facing status surface during the window — silence is not acceptable.
- **FR-481.6**: When the configured `ends_at` arrives or the operator explicitly disables the mode, writes MUST resume immediately and the announcement MUST be removed.
- **FR-481.7**: A failed disable MUST surface as an actionable alert; the platform MUST NOT silently leave writes blocked.
- **FR-481.8**: Maintenance mode operations (schedule, enable, disable, modify, cancel) MUST be authorised at the platform-administrator scope and MUST be audited via the platform's existing audit chain.
- **FR-481.9**: System MUST emit `maintenance.mode.enabled` on enable and `maintenance.mode.disabled` on disable (constitutionally-declared topics, lines 771–772) so other services can drain or resume accordingly.
- **FR-481.10**: Retroactive windows (whose `starts_at` is in the past at scheduling time) MUST be rejected or scheduled as `completed`; the platform MUST NOT silently bring itself offline due to a backdated schedule.
- **FR-481.11**: Overlapping windows MUST be resolved deterministically per a documented rule; ambiguous overlapping state is unacceptable.

**Capacity Planning (FR-482)**

- **FR-482.1**: Operator dashboard MUST surface historical usage trends per major resource class (e.g., compute / memory / storage / events / model-tokens) over an operator-configurable retrospective window.
- **FR-482.2**: Operator dashboard MUST surface a forward-looking projection per major resource class with a confidence indicator; insufficient history MUST be marked as low-confidence rather than silently displayed as a confident number.
- **FR-482.3**: System MUST raise an alert when the projected utilization crosses an operator-configured saturation horizon (e.g., projected > 80% of capacity in N days) ahead of actual saturation.
- **FR-482.4**: Each capacity alert MUST carry at least one recommended action (scale up, throttle, restrict new workspace creation) and MUST link to the appropriate control surface or runbook so the operator can act without translating the recommendation into a procedure on their own.
- **FR-482.5**: Recommendations that have been resolved (e.g., the operator already scaled the resource) MUST clear automatically; lingering resolved recommendations are noise.
- **FR-482.6**: Cost forecasts produced by feature 079 (`cost_governance/`) MUST be referenced from the capacity view rather than re-implemented here, so the two surfaces remain consistent.

**Cross-Cutting**

- **FR-CC-1**: All region, replication, failover-plan, and maintenance-window operations MUST be governed by the platform's existing RBAC and admin-endpoint segregation (constitution rule 29) — administrative actions live behind admin role gates and do not mingle with user-facing endpoints.
- **FR-CC-2**: All administrative actions on regions, plans, and maintenance windows MUST emit audit chain entries via the platform's existing audit-chain service — never written directly (constitution rule 9, 32).
- **FR-CC-3**: Region-related events (`region.replication.lag`, `region.failover.initiated`, `region.failover.completed`, `maintenance.mode.enabled`, `maintenance.mode.disabled`) are constitutionally declared (lines 768–772); this feature implements them under that registry without renaming.
- **FR-CC-4**: System MUST integrate with the platform's existing notifications subsystem (feature 077) for alert delivery rather than introducing a parallel notification path.
- **FR-CC-5**: System MUST integrate with the platform's existing incident-response subsystem (feature 080) so that RPO/RTO threshold breaches and failover failures produce incidents through the established `IncidentTriggerInterface` rather than a parallel alert pipeline.
- **FR-CC-6**: Region, replication, failover-plan, maintenance-window, and capacity records MUST survive workspace archival and platform upgrades; the historical record is durable.
- **FR-CC-7**: All operator-facing surfaces (regions view, replication status, failover-plan composer, maintenance-mode console, capacity dashboard) MUST be reachable from the existing operator dashboard rather than living in a separate application (constitution rule 45).
- **FR-CC-8**: Feature flags `FEATURE_MAINTENANCE_MODE` and `FEATURE_MULTI_REGION` (constitutionally declared, lines 888–889) MUST gate the operator-visible enforcement paths so a deployment can opt out or gradually roll out without code changes.

### Key Entities

- **Region Configuration**: A declared region with a stable code, a role (primary | secondary), a set of endpoint URLs (for the per-store replication targets and the user-facing surfaces), an operator-declared RPO and RTO target, and an enable flag. The set of regions for a deployment is small (typically 1 + N secondaries).
- **Replication Status**: A per-(source region, target region, component) measurement of lag in seconds and a categorical health state, with a measured-at timestamp. Components include the relational store, event backbone, object storage, OLAP, vector, graph, and full-text — i.e., every data store category that holds production state.
- **Failover Plan**: A named, ordered set of steps that, executed against a given (from, to) region pair, performs the cutover. Carries `tested_at` (when the plan was last successfully rehearsed) and `last_executed_at` (when it was last actually executed). Linkable to runbooks (feature 080).
- **Failover Plan Run**: The audit-relevant record of a specific execution (rehearsal or production) of a plan. Captures who, when, why, per-step outcome, and the overall result. The `failover_plans` table itself is the plan; runs are the execution history.
- **Maintenance Window**: A scheduled interval with a `starts_at`, `ends_at`, reason, announcement text, `blocks_writes` flag, and a status (`scheduled`, `active`, `completed`, `cancelled`). The platform's runtime maintenance-mode behaviour is driven by the active window.
- **Capacity Signal**: A forward-looking projection per major resource class with a confidence indicator and, when applicable, a recommended action and a resolution state. Sourced from existing telemetry — this feature surfaces and routes the signal rather than computing the underlying usage.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A deployment with one configured secondary region surfaces, on the operator dashboard, replication lag for every data store category that holds production state, with no category silently absent.
- **SC-002**: With an operator-declared RPO target, a deliberate replication disturbance produces an alert within the platform's stated alert-delivery latency budget; resuming replication clears the alert without operator intervention.
- **SC-003**: A failover plan rehearsal records a per-step outcome for every step in the plan; a deliberately broken step halts the rehearsal and surfaces a clear failure rather than silently continuing.
- **SC-004**: A failover plan that has not been rehearsed within the operator-declared rehearsal interval is visibly flagged as stale on the operator dashboard — verified by automated assertion.
- **SC-005**: Concurrent attempts to initiate failover plans on the same (from_region, to_region) pair produce exactly one running plan; the second initiator receives an actionable error.
- **SC-006**: With maintenance mode enabled and `blocks_writes=true`, every mutating API endpoint returns the maintenance error within the platform's stated p95 latency budget; every read-only endpoint returns its normal response — verified by automated coverage across the API surface.
- **SC-007**: An execution started before maintenance mode is enabled runs to completion after the mode is enabled — no in-flight work is killed by the mode.
- **SC-008**: The configured maintenance announcement is visible on the user-facing status surface during the active window and is removed within the platform's stated p95 latency budget after disable.
- **SC-009**: The published zero-downtime upgrade procedure is reachable from the operator dashboard in one click and includes explicit rollback and rollback-failed branches — verified by automated content presence assertion.
- **SC-010**: An additive schema change executed against a non-production deployment using the published procedure produces no caller-observable downtime gap — verified by continuous synthetic readiness probing during the change window.
- **SC-011**: The capacity dashboard shows a historical trend, a forward projection, and a saturation horizon for at least the resource classes the operator has declared, on every supported deployment topology — verified by post-install assertion.
- **SC-012**: A controlled load injection that pushes utilization toward the configured saturation horizon produces a capacity alert ahead of saturation, not at it; the alert carries at least one recommended action with a working link to a control surface or runbook.
- **SC-013**: No region, plan, maintenance, or capacity action observable in audit review occurs without a corresponding audit chain entry — verified by automated audit-coverage check.
- **SC-014**: Quarterly failover rehearsal outcomes are persisted and reviewable as a historical record at least one fiscal year back — verified by retention assertion.

## Assumptions

- The platform's existing data stores already support replication at the technology level (PostgreSQL streaming replication, Kafka MirrorMaker 2, S3-compatible cross-region replication, ClickHouse replicated tables, and analogous replication paths for Qdrant / Neo4j / OpenSearch). This feature integrates the operational surface around those technology paths; it does not invent new replication mechanisms.
- The platform's existing notifications, audit chain, and RBAC subsystems are reused; this feature does not introduce a parallel notification, audit, or authorization path.
- The platform's existing operator dashboard is the home for region, replication, failover, maintenance, and capacity UIs; no new application is created.
- The platform's existing user-facing status surface (per the constitution's `<PlatformStatusBanner>` rule 48) is the channel for maintenance-window announcements; this feature does not duplicate that surface.
- The platform's existing incident-response subsystem (feature 080) is the route by which RPO/RTO threshold breaches and failover failures become incidents; this feature triggers incidents rather than reinventing alert routing.
- The platform's existing cost-governance subsystem (feature 079) provides cost forecasts; the capacity view references those forecasts rather than re-computing them.
- The set of data store categories whose replication this feature integrates is fixed at v1 to the seven listed in the planning input (PostgreSQL, Kafka, S3, ClickHouse, Qdrant, Neo4j, OpenSearch); adding new categories is a future change.
- Active-active deployments are documented but not enabled by default; the v1 default is active-passive.
- Quarterly rehearsal cadence (constitution Critical Reminder 33) is the operator's responsibility to schedule; the platform surfaces staleness and supports the rehearsal but does not auto-initiate cutovers.
- Per-region time zones are out of scope for v1; maintenance-window timestamps are evaluated in the platform-default time zone declared at deployment.
- Backward-compatibility shims and dual-write windows for schema changes are scoped to the duration of the upgrade per the published procedure; this feature does not maintain dual-shape state indefinitely.

## Out of Scope (v1)

- Active-active production deployment as a supported default; v1 supports it via documentation and explicit operator configuration only.
- Automated triggering of a real production failover by the platform without operator initiation; v1 surfaces signals and supports rehearsal/execution, but the cutover decision remains human.
- Cross-region traffic shaping or geo-routing at the user-traffic level (e.g., latency-based DNS, anycast); v1 supports failover, not steady-state geo-distribution.
- Per-workspace region pinning (workspace data lives in a specific region) beyond the existing residency rules from the platform's privacy compliance subsystem; that is a separate feature scope.
- Automated self-healing of replication (e.g., the platform reseeding a degraded secondary autonomously). v1 surfaces lag and lets the operator act.
- Replication of derived analytics views beyond the source-of-truth tables they're built on; v1 replicates the underlying state; secondary-side view rebuild is part of failover.
- Capacity recommendations that auto-apply changes (e.g., auto-scaling actions taken by the platform). v1 surfaces recommendations and links to control surfaces; the operator acts.
- Multi-currency cost-forecast handling within the capacity view (single canonical currency per cost-governance v1).
- Public-facing region status pages distinct from the existing public status surface (constitution rule 49).
- Backup-restore lifecycle is owned by the existing backup-restore feature (feature 048) and is referenced but not re-scoped here.

## Dependencies and Brownfield Touchpoints

This feature is additive to the existing platform. The relevant existing capabilities the new bounded context relies on or extends:

- **Existing `multi_region_ops/` bounded context slot** (Constitution § "New Bounded Contexts" line 492 — owns UPD-025 — and the constitutionally-declared REST prefixes `/api/v1/regions/*` and `/api/v1/maintenance/*` at lines 798–799, the Kafka topics `region.replication.lag` / `region.failover.initiated` / `region.failover.completed` / `maintenance.mode.enabled` / `maintenance.mode.disabled` at lines 768–772, and the feature flags `FEATURE_MAINTENANCE_MODE` / `FEATURE_MULTI_REGION` at lines 888–889): this is the home for the implementation; the topics, prefixes, and flags are reserved at the constitutional level and MUST be used.
- **Helm chart at `deploy/helm/platform/`**: the existing chart is extended, not forked. A region-overlay values file and a replication-jobs templates subtree integrate with the chart's existing pattern.
- **Operator dashboard**: the existing surface is the home for the regions view, replication status, failover-plan composer, maintenance-mode console, and capacity dashboard.
- **Audit chain** (`security_compliance/services/audit_chain_service.py` per the established pattern): the canonical write path for all administrative actions on regions, plans, and maintenance windows.
- **Notifications** (feature 077): the platform's existing notification subsystem is the delivery channel for RPO/RTO and capacity alerts.
- **Incident response** (feature 080): RPO/RTO breaches and failover failures produce incidents through the established `IncidentTriggerInterface` rather than a parallel alert pipeline.
- **Cost governance** (feature 079): cost forecasts are referenced by the capacity view; the capacity dashboard composes existing signals rather than re-computing them.
- **Privacy compliance / data residency**: the residency rules from the platform's privacy compliance subsystem (constitution rule 18, AD-21) remain authoritative for cross-region transfer enforcement; this feature observes them and does not override them.
- **Backup-restore** (feature 048): backup lifecycle is referenced by failover plans where appropriate; this feature does not re-scope backups.
- **Public status surface** (`<PlatformStatusBanner>` per constitution rule 48): the channel for user-visible maintenance announcements; this feature emits the announcement, the surface displays it.
- **User-facing platform status** (constitution rule 48): the platform's commitment that users always see explanatory context during disturbances; this feature is one of the producers.

The implementation strategy (specific tables, services, schemas, Helm chart layout, and code-level integration points) is intentionally deferred to the planning phase. The brownfield input that motivated this spec is preserved in the feature folder as `planning-input.md`.
