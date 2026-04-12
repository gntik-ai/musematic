# Feature Specification: Fleet Management and Learning

**Feature Branch**: `033-fleet-management-learning`  
**Created**: 2026-04-12  
**Status**: Draft  
**Input**: User description: "Implement fleet domain model, topology management, orchestration rules, observer agents, degraded operation, fleet performance profiles, adaptation engine, cross-fleet knowledge transfer, and fleet personality profiles"

**Requirements Traceability**: FR-284-291, FR-362-366, TR-280-289, TR-351-354

## User Scenarios & Testing

### User Story 1 - Fleet Domain and Topology Management (Priority: P1)

A workspace administrator creates a fleet of agents, assigns members by their fully qualified name, selects a topology type (hierarchical, peer-to-peer, or hybrid), and binds policies to the fleet. The fleet is workspace-scoped and each fleet has a unique name within its workspace. Members can be added, removed, or reassigned roles (lead, worker, observer) within the fleet.

**Why this priority**: The fleet is the foundational domain object — all other fleet capabilities (orchestration, performance profiles, governance chains) attach to a fleet. Without fleet CRUD and topology, nothing else can function.

**Independent Test**: Can be fully tested by creating a fleet with 3 members in hierarchical topology, verifying member roles, changing topology to peer-to-peer, and confirming the fleet persists with correct structure.

**Acceptance Scenarios**:

1. **Given** a workspace, **When** an admin creates a fleet with a name, topology type "hierarchical", and 3 member agent FQNs, **Then** the fleet is created with those members, one designated as lead.
2. **Given** an existing fleet, **When** an admin changes the topology from "hierarchical" to "peer-to-peer", **Then** the topology updates and the lead designation is removed (all members are peers).
3. **Given** a fleet with 3 members, **When** an admin removes a member, **Then** the member is removed from the fleet and the fleet continues operating with 2 members.
4. **Given** a fleet, **When** an admin binds a policy to the fleet, **Then** the policy governs all members of the fleet.
5. **Given** a fleet with a name that already exists in the workspace, **When** an admin attempts to create another fleet with the same name, **Then** a validation error is returned.

---

### User Story 2 - Orchestration Rules (Priority: P1)

A fleet administrator defines orchestration rules that govern how work flows within the fleet. Rules cover: how tasks are delegated to members, how results are aggregated from multiple members, when and how escalation happens, how conflicts between member outputs are resolved, and what happens when a member fails (retry or reassign). Each fleet has a versioned set of orchestration rules.

**Why this priority**: Orchestration rules make a fleet more than a group — they define coordination behavior. Without them, the fleet has no operational semantics.

**Independent Test**: Can be fully tested by creating orchestration rules for a fleet, triggering a delegation, verifying escalation fires when conditions are met, and confirming retry/reassignment handles member failure.

**Acceptance Scenarios**:

1. **Given** a fleet with orchestration rules defining delegation by capability match, **When** a task is submitted to the fleet, **Then** the system delegates the task to the member whose capabilities best match.
2. **Given** a fleet with aggregation rules, **When** multiple members complete subtasks, **Then** the results are aggregated according to the rule (e.g., merge, vote, first-wins).
3. **Given** a fleet with escalation rules, **When** a member cannot complete a task within the configured timeout, **Then** the task is escalated to the fleet lead or to a human operator.
4. **Given** a fleet with conflict resolution rules, **When** two members produce contradictory outputs, **Then** the system applies the conflict strategy (e.g., majority vote, lead decision, human arbitration).
5. **Given** a fleet with retry/reassignment rules, **When** a member fails during task execution, **Then** the task is retried on the same member (if retry policy allows) or reassigned to another available member.

---

### User Story 3 - Observer Agents and Governance Chain (Priority: P2)

A fleet administrator assigns observer agents to a fleet. Observers subscribe to the fleet's execution streams and monitor activity without owning or executing tasks. Additionally, the administrator configures the fleet's governance chain: which observer agents detect anomalies, which judge agents evaluate them against policies, and which enforcer agents take action on verdicts. A default governance chain (platform-provided observer, judge, enforcer with workspace-level policies) is automatically assigned when a fleet is created.

**Why this priority**: Observers and the governance chain provide trust and safety oversight for fleet operations. They depend on the fleet domain (US1) existing.

**Independent Test**: Can be fully tested by assigning an observer to a fleet, triggering an execution event, verifying the observer receives the event stream, and confirming the governance chain fires a verdict when an anomaly is detected.

**Acceptance Scenarios**:

1. **Given** a fleet, **When** an admin assigns an observer agent by FQN, **Then** the observer is linked to the fleet and receives execution stream events for that fleet.
2. **Given** a fleet with an observer, **When** a fleet member completes a task, **Then** the observer receives the execution event without being assigned as a task executor.
3. **Given** a new fleet, **When** it is created, **Then** a default governance chain is automatically assigned with platform-provided observer, judge, and enforcer agents.
4. **Given** a fleet, **When** an admin customizes the governance chain with specific observer, judge, and enforcer FQNs, **Then** the custom chain replaces the default for that fleet.
5. **Given** a governance chain configured for a fleet, **When** an observer detects an anomaly, **Then** the judge evaluates it against the bound policies and the enforcer executes the verdict.
6. **Given** a governance chain, **When** the chain configuration is updated, **Then** the change is versioned alongside the fleet topology.

---

### User Story 4 - Degraded Operation (Priority: P2)

When one or more fleet members become unavailable (crashed, timed out, or unreachable), the fleet continues operating if the fleet's degradation policy allows it. The system maintains a health projection for each fleet, tracking member availability. A minimum quorum can be configured — if the available member count drops below the quorum, the fleet pauses and notifies the administrator.

**Why this priority**: Resilience is critical for production fleets. Degraded operation depends on the fleet domain (US1) and orchestration rules (US2) for retry/reassignment.

**Independent Test**: Can be fully tested by simulating a member failure in a 3-member fleet, verifying the fleet continues with 2 members, then simulating a second failure to trigger quorum violation and fleet pause.

**Acceptance Scenarios**:

1. **Given** a fleet with 3 members and a quorum of 2, **When** 1 member becomes unavailable, **Then** the fleet continues operating with the remaining 2 members.
2. **Given** a fleet in degraded mode (1 member down), **When** a task is delegated, **Then** the system skips the unavailable member and delegates to an available one.
3. **Given** a fleet with quorum of 2, **When** a second member becomes unavailable (only 1 remaining), **Then** the fleet pauses operation and a notification is sent to the administrator.
4. **Given** a paused fleet, **When** a previously unavailable member recovers, **Then** the fleet resumes operation automatically if the quorum is met again.
5. **Given** a fleet, **When** the health projection is queried, **Then** it returns the current availability status of each member, the overall fleet health percentage, and whether the fleet is in degraded mode.

---

### User Story 5 - Fleet Performance Profiles (Priority: P2)

The system aggregates individual member performance metrics into fleet-wide performance indicators. Metrics include: average task completion time, success rate, cost per task, quality scores, and throughput. Fleet performance profiles are computed periodically and are queryable by time range. The profile serves as the input data for the adaptation engine (US6).

**Why this priority**: Performance visibility is needed before adaptation can be automated (US6). It also provides fleet administrators with operational intelligence.

**Independent Test**: Can be fully tested by populating member execution metrics, triggering profile aggregation, and verifying the fleet-level performance profile contains correct averages, rates, and trends.

**Acceptance Scenarios**:

1. **Given** a fleet with 3 members who have completed tasks, **When** performance profile aggregation runs, **Then** the fleet profile contains average task completion time, success rate, cost per task, and throughput across all members.
2. **Given** a fleet performance profile, **When** queried for a specific time range (e.g., last 7 days), **Then** the profile returns metrics aggregated over that range.
3. **Given** a fleet, **When** an admin views the performance profile, **Then** individual member contribution to fleet metrics is visible alongside the fleet-wide aggregate.
4. **Given** a fleet member with consistently low quality scores, **When** the performance profile is computed, **Then** the member's metrics are flagged in the profile for administrator review.

---

### User Story 6 - Adaptation Engine (Priority: P3)

The fleet adaptation engine observes fleet performance profiles over time and automatically adjusts orchestration rules to improve performance. Adaptation rules define conditions (e.g., "if average task completion time exceeds threshold") and actions (e.g., "increase parallelism", "reassign tasks from slowest member", "switch delegation strategy"). Adaptations are logged and can be reviewed or reverted by administrators.

**Why this priority**: Adaptation is a higher-order capability that requires both orchestration rules (US2) and performance profiles (US5) to be operational.

**Independent Test**: Can be fully tested by creating adaptation rules, populating performance data that triggers a condition, and verifying the engine adjusts the orchestration rules accordingly with a logged change.

**Acceptance Scenarios**:

1. **Given** a fleet with an adaptation rule "if avg_completion_time > 30s, increase parallelism to 3", **When** the fleet's average completion time exceeds 30 seconds, **Then** the orchestration rules are updated to allow 3 parallel task assignments.
2. **Given** an adaptation rule that fires, **When** the orchestration rules change, **Then** the change is logged with the adaptation rule reference, the performance data that triggered it, and the before/after values.
3. **Given** an administrator reviewing adaptation logs, **When** they choose to revert an adaptation, **Then** the orchestration rules return to their pre-adaptation state.
4. **Given** a fleet with multiple adaptation rules, **When** two rules conflict (e.g., one increases parallelism, one decreases it), **Then** the rule with higher priority takes precedence.

---

### User Story 7 - Cross-Fleet Knowledge Transfer (Priority: P3)

When a fleet develops effective orchestration patterns, performance optimizations, or learned strategies, an administrator can propose transferring these patterns to another fleet. The receiving fleet's administrator must approve the transfer. Transferred patterns are adapted to the receiving fleet's topology and member capabilities. Transfer requests track status (proposed, approved, applied, rejected).

**Why this priority**: Knowledge transfer enables organizational learning but requires mature fleet operations (US1, US2, US5) to produce patterns worth sharing.

**Independent Test**: Can be fully tested by creating a transfer request from Fleet A to Fleet B, verifying Fleet B's admin can approve it, and confirming the pattern is applied to Fleet B with appropriate adjustments.

**Acceptance Scenarios**:

1. **Given** Fleet A with a successful orchestration pattern, **When** Fleet A's admin proposes a transfer to Fleet B, **Then** a transfer request is created with status "proposed" containing the pattern definition.
2. **Given** a transfer request in "proposed" status, **When** Fleet B's admin approves it, **Then** the status changes to "approved" and the pattern is queued for application.
3. **Given** an approved transfer, **When** the pattern is applied to Fleet B, **Then** the system adapts the pattern to Fleet B's topology and member capabilities; the request status becomes "applied".
4. **Given** a transfer request, **When** Fleet B's admin rejects it, **Then** the status changes to "rejected" with an optional reason.
5. **Given** an applied transfer, **When** Fleet B's performance degrades after the transfer, **Then** the administrator can revert the applied pattern.

---

### User Story 8 - Fleet Personality Profiles (Priority: P3)

Each fleet has a personality profile that influences how the fleet operates as a collective. The personality profile includes: communication style (verbose/concise/structured), decision speed (fast/deliberate/consensus-seeking), risk tolerance (conservative/moderate/aggressive), and autonomy level (supervised/semi-autonomous/fully-autonomous). The personality profile influences orchestration behavior — for example, a "consensus-seeking" fleet routes decisions to all members, while a "fast" fleet delegates to the first available member.

**Why this priority**: Personality profiles add behavioral nuance to fleet operations but are only meaningful when the core fleet mechanics (US1, US2) are established.

**Independent Test**: Can be fully tested by setting a fleet's personality to "fast decision + aggressive risk tolerance" and verifying that delegation prefers speed over consensus, compared to a "deliberate + conservative" personality where delegation waits for quorum.

**Acceptance Scenarios**:

1. **Given** a fleet with decision speed "fast", **When** a task arrives, **Then** it is delegated to the first available member without waiting for group consensus.
2. **Given** a fleet with decision speed "consensus-seeking", **When** a task arrives, **Then** the system polls all members for input before delegation.
3. **Given** a fleet with risk tolerance "conservative", **When** a task involves an unverified action, **Then** the system escalates to human approval before proceeding.
4. **Given** a fleet with autonomy level "fully-autonomous", **When** a task completes, **Then** the result is committed without waiting for human review.
5. **Given** a fleet, **When** an admin updates the personality profile, **Then** the change takes effect on the next task and is versioned with the fleet configuration.

---

### Edge Cases

- What happens when a fleet has zero members? Fleet enters "empty" state; all tasks are rejected until at least one member is added.
- What happens when the fleet lead in a hierarchical topology becomes unavailable? The orchestration rules should have a lead succession policy; if none defined, the fleet enters degraded mode and notifies the administrator.
- What happens when all observers in a governance chain are unavailable? The fleet continues operating (governance chain is non-blocking) but a warning is logged and the administrator is notified.
- What happens when a cross-fleet transfer pattern references members that don't exist in the receiving fleet? The pattern adaptation step adjusts for the receiving fleet's actual member capabilities; if no suitable members exist, the transfer fails with reason "incompatible_topology".
- What happens when an adaptation rule fires during an active task execution? The adaptation applies to the next task, not the currently executing one.
- What happens when a fleet's personality profile conflicts with its orchestration rules? Orchestration rules take precedence over personality profiles; personality is advisory.
- What happens when a fleet is archived or deleted? Members are unlinked (not deleted), orchestration rules are deactivated, performance profiles are retained for historical queries, and governance chains are deactivated.

## Requirements

### Functional Requirements

**Fleet Domain and Topology**

- **FR-001**: System MUST allow creating fleets with a unique name within a workspace, topology type, and initial member list
- **FR-002**: System MUST support three topology types: hierarchical (with lead designation), peer-to-peer (all equal), and hybrid (multiple sub-groups with leads)
- **FR-003**: System MUST allow adding and removing fleet members by their agent FQN
- **FR-004**: System MUST support member roles within a fleet: lead, worker, observer
- **FR-005**: System MUST allow binding one or more policies to a fleet
- **FR-006**: System MUST maintain fleet lifecycle states: active, paused, degraded, archived
- **FR-007**: System MUST version fleet topology changes so previous configurations can be inspected

**Orchestration Rules**

- **FR-008**: System MUST support delegation rules: assign tasks to members based on capability match, round-robin, or priority
- **FR-009**: System MUST support aggregation rules: merge, vote, or first-wins strategies for combining member outputs
- **FR-010**: System MUST support escalation rules: escalate after timeout, failure count, or quality threshold
- **FR-011**: System MUST support conflict resolution rules: majority vote, lead decision, or human arbitration
- **FR-012**: System MUST support retry/reassignment rules: configurable retry count per member, then reassign to next available
- **FR-013**: System MUST version orchestration rules so changes can be audited and reverted

**Observer Agents and Governance Chain**

- **FR-014**: System MUST allow assigning observer agents to a fleet by FQN; observers receive execution events without task ownership
- **FR-015**: System MUST automatically assign a default governance chain (platform-provided observer, judge, enforcer) when a fleet is created
- **FR-016**: System MUST allow customizing the governance chain with specific observer, judge, and enforcer agent FQNs
- **FR-017**: System MUST store governance chain configurations versioned alongside the fleet topology
- **FR-018**: System MUST route observer anomaly signals through the judge and enforcer per the configured chain

**Degraded Operation**

- **FR-019**: System MUST continue fleet operation when members fail, provided the remaining count meets the configured quorum
- **FR-020**: System MUST pause fleet operation and notify administrators when the quorum is no longer met
- **FR-021**: System MUST automatically resume fleet operation when sufficient members recover to meet the quorum
- **FR-022**: System MUST maintain a health projection per fleet tracking each member's availability status

**Performance Profiles**

- **FR-023**: System MUST aggregate member execution metrics into fleet-wide performance indicators: average completion time, success rate, cost per task, quality score, throughput
- **FR-024**: System MUST compute performance profiles periodically (configurable interval, default daily)
- **FR-025**: System MUST support querying fleet performance profiles by time range
- **FR-026**: System MUST flag individual members whose metrics deviate significantly from fleet averages

**Adaptation Engine**

- **FR-027**: System MUST support defining adaptation rules with a condition (metric threshold) and action (orchestration rule change)
- **FR-028**: System MUST evaluate adaptation rules against the latest performance profile at each computation interval
- **FR-029**: System MUST log all adaptation actions with the triggering rule, performance data, and before/after orchestration state
- **FR-030**: System MUST support reverting adaptations to restore previous orchestration rules
- **FR-031**: System MUST support adaptation rule priorities to resolve conflicts between competing rules

**Cross-Fleet Knowledge Transfer**

- **FR-032**: System MUST support creating transfer requests from one fleet to another with a pattern definition
- **FR-033**: System MUST require approval from the receiving fleet's administrator before applying a transfer
- **FR-034**: System MUST adapt transferred patterns to the receiving fleet's topology and member capabilities
- **FR-035**: System MUST track transfer request status: proposed, approved, applied, rejected
- **FR-036**: System MUST support reverting applied transfers

**Fleet Personality Profiles**

- **FR-037**: System MUST support configuring fleet personality attributes: communication style, decision speed, risk tolerance, autonomy level
- **FR-038**: System MUST influence orchestration behavior based on personality profile (e.g., consensus-seeking decision speed triggers member polling)
- **FR-039**: System MUST version personality profile changes with the fleet configuration
- **FR-040**: System MUST give orchestration rules precedence over personality profile when they conflict

### Key Entities

- **Fleet**: A named, workspace-scoped group of agents with a topology, lifecycle state, and versioned configuration
- **FleetMember**: A link between a fleet and an agent (by FQN), with a role (lead, worker, observer) and availability status
- **FleetTopology**: The structure of a fleet — hierarchical, peer-to-peer, or hybrid — with version tracking
- **FleetPolicyBinding**: A link between a fleet and a policy that governs member behavior
- **FleetHealthProjection**: Real-time health status of a fleet, tracking each member's availability and overall fleet health percentage
- **ObserverAssignment**: A link between an observer agent (by FQN) and a fleet, granting execution stream access without task ownership
- **FleetGovernanceChain**: Configuration of observer, judge, and enforcer agent FQNs for a fleet, versioned with the topology
- **FleetOrchestrationRules**: Versioned set of delegation, aggregation, escalation, conflict resolution, and retry/reassignment rules for a fleet
- **FleetPerformanceProfile**: Aggregated performance metrics for a fleet over a time period (completion time, success rate, cost, quality, throughput)
- **FleetAdaptationRule**: A condition-action pair that automatically adjusts orchestration rules based on performance metrics, with priority
- **CrossFleetTransferRequest**: A request to share a pattern from one fleet to another, with status (proposed, approved, applied, rejected) and pattern definition
- **FleetPersonalityProfile**: Fleet-level behavioral attributes (communication style, decision speed, risk tolerance, autonomy level)

## Success Criteria

### Measurable Outcomes

- **SC-001**: Fleets with 3+ members can execute coordinated tasks with correct delegation within 5 seconds of task submission
- **SC-002**: When a fleet member fails, the fleet continues operating within 10 seconds (no manual intervention required)
- **SC-003**: Fleet performance profiles aggregate correctly (within 1% of manually computed values) and are queryable within 2 seconds
- **SC-004**: Adaptation rules fire within one computation interval of the triggering condition and adjust orchestration rules without manual intervention
- **SC-005**: Cross-fleet knowledge transfers complete end-to-end (propose, approve, apply) within 30 seconds of all human approvals
- **SC-006**: Observer agents receive execution stream events within 2 seconds of the event occurring, without delaying task execution
- **SC-007**: Governance chain processes anomaly signals from detection to enforcement action within 15 seconds
- **SC-008**: Fleet health projection updates within 30 seconds of a member availability change
- **SC-009**: Personality profile changes take effect on the next task without requiring fleet restart
- **SC-010**: Test coverage is at least 95% across all fleet management and learning components

## Assumptions

- The agent registry (feature 021) provides agent FQN resolution and capability metadata for member selection
- The execution engine (feature 029) provides execution stream events consumed by observers
- The trust service (feature 032) provides the Observer-Judge-Enforcer pipeline mechanics; the fleet governance chain configuration feeds into the trust service's OJE pipeline
- The policy governance engine (feature 028) provides policies that can be bound to fleets
- Performance metrics are sourced from the analytics service (feature 020) which stores execution data in ClickHouse
- The runtime controller (feature 009) provides member availability status (heartbeats)
- The WebSocket gateway (feature 019) provides the `fleet.health` channel for real-time health projection delivery
- A "default" governance chain uses platform-provided agent FQNs that are pre-registered in every workspace (e.g., `platform:default-observer`, `platform:default-judge`, `platform:default-enforcer`)
- Personality profile is advisory — orchestration rules always take precedence over personality-driven behavior
- Cross-fleet knowledge transfer is restricted to fleets within the same workspace (cross-workspace transfer is out of scope for v1)
- Performance profile aggregation runs as a scheduled job; real-time streaming aggregation is out of scope for v1
