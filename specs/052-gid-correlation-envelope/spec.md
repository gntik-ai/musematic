# Feature Specification: GID Correlation and Event Envelope Extension

**Feature Branch**: `052-gid-correlation-envelope`
**Created**: 2026-04-18
**Status**: Draft
**Input**: User description: "GID Correlation and Event Envelope Extension — Add goal_id (GID) as a first-class field in the event correlation envelope. Propagate through middleware, Kafka, logs, and analytics."

**Scope note**: The `goal_id` field is **already present** on `CorrelationContext` (shipped with features 018 Workspaces and 024 Interactions), and `goal_id` already appears in existing goal-related Kafka event payloads (`GoalMessagePostedPayload`, `GoalStatusChangedPayload`, `InteractionStartedPayload`). This update pass closes the three genuine gaps that remain:

1. HTTP request middleware does not extract or propagate the `X-Goal-Id` header.
2. Analytics event storage does not carry `goal_id` as a queryable dimension.
3. Log indexing does not expose `goal_id` as a first-class filter field.

In addition, at least one internal producer (the workspace goal message path) does not set `goal_id` on the outgoing correlation context when emitting downstream events, so a correlation chain started inside the process loses the GID.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Goal-scoped request tracing across services (Priority: P1)

Operators investigating issues with a specific workspace goal need every event, log entry, and metric triggered by that goal's activity to carry the `goal_id`, so they can pull a complete end-to-end trace using only the goal identifier. Today, a user action inside a goal is recorded as part of the conversation/workflow, but when operators try to pivot a debugging session on the goal itself they must reconstruct the association from indirect joins instead of directly filtering by goal.

**Why this priority**: Without reliable goal propagation an operator cannot answer the question "what happened on this goal?" in one query. This is the core value of the feature — every other story derives from having GID-tagged signals downstream.

**Independent Test**: A client sends an HTTP request with the header `X-Goal-Id: <uuid>`. Any Kafka event, log line, or analytics row produced as a downstream effect of that request carries the same `goal_id`. Delivered value: a single identifier threads through all observability surfaces.

**Acceptance Scenarios**:

1. **Given** a caller includes `X-Goal-Id` on an HTTP request that triggers one or more asynchronous events, **When** the downstream event envelopes are inspected, **Then** every event's correlation context contains the same `goal_id` value as the inbound header.
2. **Given** a service internally posts a goal message (no inbound HTTP request), **When** the resulting event is published, **Then** the event's correlation context contains the `goal_id` derived from the goal being addressed.
3. **Given** a request arrives without an `X-Goal-Id` header and does not involve a goal, **When** events are produced, **Then** the correlation context's `goal_id` is empty and no errors are raised in any consumer.

---

### User Story 2 — Goal-dimensioned analytics and cost attribution (Priority: P1)

Workspace owners and finance stakeholders need to see token usage, cost, and execution metrics broken down **per goal**, not only per workspace or per agent. Today, analytics records a usage event per execution but has no way to aggregate spend or throughput by the business-level goal that motivated the work. Without goal-level aggregation, it is impossible to answer "how much has this specific initiative cost so far?" or "which goals deliver the most value per token spent?".

**Why this priority**: Goal-level cost attribution is the business lens for agentic work. Without it, finance and product owners cannot decide which initiatives to scale or cut.

**Independent Test**: Run two executions against the same workspace and agent, one tagged with goal A and one with goal B. Query the analytics system grouped by `goal_id`. Delivered value: costs and volumes split correctly by goal, even when workspace and agent are identical.

**Acceptance Scenarios**:

1. **Given** usage events arrive with populated `goal_id` values, **When** the analytics aggregation pipeline ingests them, **Then** the stored analytics rows retain `goal_id` as a queryable dimension.
2. **Given** a query groups usage by `goal_id` for a workspace, **When** the aggregation runs, **Then** per-goal totals for tokens, cost, and event count are returned and reconcile to the per-workspace total.
3. **Given** legacy rows that pre-date this change (no `goal_id`), **When** a goal-filtered query runs, **Then** those rows are excluded cleanly without breaking the response.

---

### User Story 3 — Goal-scoped log search for incident response (Priority: P2)

On-call engineers responding to an incident use log search to triage. When the incident is tied to a specific goal, they need to enter the `goal_id` as a filter and see every log line that was produced in the context of that goal across all services, without having to pre-join by correlation ID or interaction ID.

**Why this priority**: Log-level filterability improves MTTR during incidents. It builds on US1 (field propagation) and US2 (analytics dimension) but is not itself blocking for the primary observability use case — operators can still pivot via correlation ID as a fallback.

**Independent Test**: Search the log index for a specific `goal_id`. Delivered value: all log records produced during activity for that goal are returned, regardless of which service emitted them.

**Acceptance Scenarios**:

1. **Given** services produce log records while handling goal-related activity, **When** those records are written to the log index, **Then** each record carries `goal_id` as a top-level, indexed field.
2. **Given** a search is executed with a `goal_id` filter, **When** results are returned, **Then** only log records matching that goal are included, with sub-second response for workspace-typical volumes.
3. **Given** a log record was produced for non-goal activity, **When** the `goal_id` filter is applied, **Then** the record is correctly excluded.

---

### User Story 4 — Internal producers preserve goal context (Priority: P2)

Services that act on behalf of a goal (for example, posting a message to a workspace goal thread) currently may publish downstream events without carrying the goal identifier on the outgoing correlation context, even though the payload itself records the goal. Operators chasing a trace through the event bus therefore lose the GID boundary the moment an internal service re-publishes. This story closes that gap so the GID travels on the envelope, not just in the payload.

**Why this priority**: This is the "last mile" for US1. Without it, external callers that correctly set `X-Goal-Id` can still see the chain fragment at the first internal re-publish. It is P2 because US1 already delivers most of the value on ingress.

**Independent Test**: Post a message on a workspace goal via the service interface. Inspect the published event envelope. Delivered value: the envelope's correlation context `goal_id` matches the goal the message was posted to.

**Acceptance Scenarios**:

1. **Given** an internal service writes or updates goal-bound data, **When** it publishes downstream events, **Then** the correlation context on each event includes the `goal_id` derived from the goal being acted upon.
2. **Given** an internal action is not bound to a goal, **When** events are published, **Then** the correlation context's `goal_id` is empty and no default or placeholder is substituted.

---

### Edge Cases

- An `X-Goal-Id` header is present but malformed (not a valid identifier) → the request is rejected with a clear validation error and no envelope is produced with an invalid value.
- An `X-Goal-Id` header references a goal the caller has no visibility into → handled by existing authorization rules on goal access; the GID itself is still propagated to observability so an operator can later see the blocked attempt.
- A single request cascades into dozens of events across services → every resulting event carries the same `goal_id`; there is no fan-out divergence.
- Analytics rollup queries run against a period that spans the rollout boundary → rows written before the change carry an empty `goal_id`; queries must not error and must not silently misattribute legacy rows.
- A log record is produced before `goal_id` propagation has been wired into the calling code path → the record appears without the field; search by `goal_id` simply excludes it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept an `X-Goal-Id` HTTP header on inbound requests and bind the value to the request's correlation context for the duration of the request.
- **FR-002**: System MUST echo the resolved `X-Goal-Id` value back on outbound HTTP responses so callers can confirm which goal the request was associated with.
- **FR-003**: System MUST reject inbound requests whose `X-Goal-Id` header is present but malformed, returning a validation error without performing the requested action.
- **FR-004**: System MUST carry `goal_id` on every Kafka event envelope produced by a request that was bound to a goal, including events produced by background tasks spawned from that request.
- **FR-005**: System MUST allow internal producers that act on behalf of a specific goal to set `goal_id` on the outgoing event envelope's correlation context, even when no inbound HTTP request is involved.
- **FR-006**: Workspace goal message creation MUST populate `goal_id` on the correlation context of all events it emits, so the GID is not only in the payload but also on the envelope.
- **FR-007**: Consumers that deserialize event envelopes written before this change MUST continue to process them without error; missing `goal_id` is acceptable and interpreted as "no goal associated".
- **FR-008**: The analytics usage event store MUST persist `goal_id` as a queryable column on the usage event record.
- **FR-009**: The analytics aggregation pipeline (hourly, daily, monthly rollups) MUST include `goal_id` as a grouping dimension so per-goal totals can be queried alongside per-workspace totals.
- **FR-010**: Analytics queries MUST be able to return usage, cost, and execution counts grouped or filtered by `goal_id`, with empty `goal_id` handled as a distinct bucket rather than causing an error.
- **FR-011**: The log index MUST carry `goal_id` as an indexed top-level field so log search can filter by goal identifier directly.
- **FR-012**: Log search responses MUST return only records matching the supplied `goal_id` when that filter is applied, without requiring a join against another store.
- **FR-013**: All changes MUST be backward-compatible: events, analytics rows, and log records produced before this feature rolls out MUST remain readable and queryable; missing `goal_id` values MUST not surface as errors to consumers or operators.
- **FR-014**: Introduction of the new storage column and log field MUST be applied via the standard migration mechanism (versioned database migration for analytics; index template update for logs); no out-of-band schema edits.
- **FR-015**: The system MUST NOT introduce `goal_id` to HTTP endpoints, event schemas, or analytics interfaces as a required field; it MUST remain optional everywhere to preserve existing callers and stored data.

### Key Entities

- **Correlation Context**: The shared metadata block attached to every Kafka event. Already includes `goal_id`; this feature ensures the field is populated consistently by all producers and propagated through HTTP middleware.
- **Usage Event (analytics)**: A record of token consumption, cost, or execution volume. Extended with a `goal_id` column so it can be aggregated by goal.
- **Log Record**: A structured log entry produced by any platform service. Extended with a `goal_id` indexed field so it can be searched by goal.
- **Workspace Goal**: The existing goal entity (from feature 018 Workspaces). Acts as the referent of `goal_id`; unchanged by this feature, but its surrounding producers are updated to ensure its identifier travels on the envelope.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator given only a `goal_id` can retrieve the complete list of events, log records, and analytics rows associated with that goal in a single query per store, with 100% recall against events produced after the feature rolls out.
- **SC-002**: For requests that arrive with an `X-Goal-Id` header, the proportion of downstream event envelopes that carry the matching `goal_id` is 100%, measured over a sample of synthetic and production traffic.
- **SC-003**: Analytics queries grouped by goal for a typical workspace return results in under 2 seconds at current workspace volumes.
- **SC-004**: Log search filtered by `goal_id` returns matching records in under 1 second for typical investigations (single-workspace, 24-hour window).
- **SC-005**: Zero regressions are observed in existing event consumers, analytics queries not using `goal_id`, or log searches not using `goal_id` after the feature is deployed.
- **SC-006**: A rollout on a database holding pre-change rows completes without data loss; rows produced before the change continue to be queryable and are returned cleanly (with empty `goal_id`) by goal-aware queries.
- **SC-007**: Finance and product stakeholders can answer "what did goal X cost this month?" directly from the analytics surface without manual correlation work.

## Assumptions

- The `goal_id` field is already defined on the shared correlation context (confirmed in `apps/control-plane/src/platform/common/events/envelope.py`); this feature does not add or rename the field on the envelope itself.
- Goal-related event payloads that already carry a `goal_id` body field (e.g., goal message posted, goal status changed) remain unchanged; this feature ensures the envelope also carries the identifier.
- Log indexing and analytics storage currently group primarily by workspace, agent, and execution identifiers; adding `goal_id` as an additional dimension does not require changing partitioning or retention policies.
- Existing log producers that do not have a `goal_id` in scope continue to emit log records without the field; they are not required to be modified unless they already have access to the identifier.
- The `X-Goal-Id` header convention aligns with the existing `X-Correlation-ID` header pattern used by the correlation middleware; the same lifecycle rules apply (set on ingress, echoed on response, propagated via context variable for the request duration).
- Authorization of goal access (ensuring callers may only act on goals they can see) is enforced by the existing workspace/goal authorization layer and is not part of this feature.
- Analytics pre-change rows will remain in the store; a separate backfill effort, if required, is out of scope here — this feature is purely additive and backward-compatible.
