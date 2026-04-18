# Feature Specification: Attention Pattern and Configurable User Alerts

**Feature Branch**: `060-attention-user-alerts`  
**Created**: 2026-04-18  
**Status**: Draft  
**Input**: Brownfield extension. Introduces a new `notifications` bounded context that consumes agent-initiated attention requests from the existing `interaction.attention` Kafka topic and consumes interaction state-change events, applies per-user alert preferences to decide whether to notify, persists the resulting alerts, and delivers them in real time (via the existing WebSocket gateway) or stores them for delivery on next login. Users control which state transitions alert them and through which channel (in-app, email, webhook).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Agent-initiated attention request reaches the target user (Priority: P1)

An agent working autonomously encounters a situation that requires urgent human input (an approval gate, an ambiguous instruction, a safety concern) and emits an attention request addressed to a specific user or role. The platform delivers this request to the target user in real time if they are online, and persists it for delivery on next login if they are offline. The request carries enough context (urgency level, brief summary, link to the originating interaction) for the user to decide whether to act now.

**Why this priority**: Agent-initiated urgency is the central pattern this feature enables — without it, agents have no out-of-band channel to reach a human when execution cannot proceed. The platform's value proposition of autonomous-but-supervisable agents depends on this loop closing. P1 because no other story has meaning if attention requests do not reach the target user.

**Independent Test**: Configure a test agent to emit an `AttentionRequest` with urgency `high`, target identity being a logged-in test user, and a short context summary. Verify that the user's active WebSocket session receives the alert within 2 seconds. Log the user out, emit another request, log back in, verify the alert appears in the unread list.

**Acceptance Scenarios**:

1. **Given** a user is online with an active WebSocket connection, **When** an agent emits an attention request addressed to that user, **Then** the user's client receives the alert on the dedicated attention channel within 2 seconds, carrying the urgency level, context summary, and a reference to the originating interaction.
2. **Given** a user is offline (no WebSocket sessions), **When** an agent emits an attention request addressed to that user, **Then** the alert is persisted as unread and delivered when the user next logs in and connects to the WebSocket gateway.
3. **Given** an attention request addressed to a user with multiple active WebSocket sessions (e.g., browser tab + mobile), **When** the request arrives, **Then** all active sessions for that user receive the alert simultaneously.
4. **Given** an attention request addressed to a role rather than a specific user, **When** any user holding that role is online, **Then** all online holders of that role receive the alert; those offline at the time of emission see the alert on next login.

---

### User Story 2 — User configures alert preferences (Priority: P1)

A user opens their alert settings and chooses which interaction state transitions should generate alerts (for example, "any transition to failed", "any transition to complete", "working → pending-approval"). The user also chooses the delivery method: in-app (WebSocket + persisted), email (for offline delivery), or webhook (for external integration). Changes take effect on the next event — in-flight events are unaffected.

**Why this priority**: Without preference configuration, every user receives every alert — volume grows to unmanageable levels and the alert signal is lost. Or conversely, no alerts are delivered because no sensible default matches every user. P1 because without it the rest of the feature is operationally unusable at scale.

**Independent Test**: Open the alert settings UI (or API). Set subscribed transitions to `["any_to_failed"]`. Save. Trigger an interaction transition running → failed — verify alert received. Trigger a different transition running → complete — verify no alert received. Change settings to include `any_to_complete`, save, re-trigger complete — verify alert now received.

**Acceptance Scenarios**:

1. **Given** a user with no alert settings record, **When** they first open the settings, **Then** the platform shows the default preferences (subscribed to `working_to_pending`, `any_to_complete`, `any_to_failed`, delivery method `in_app`) and persists them when explicitly saved.
2. **Given** a user with alert settings saved, **When** an interaction transitions through a state they are subscribed to, **Then** an alert is generated and delivered via their configured method.
3. **Given** a user with alert settings saved, **When** an interaction transitions through a state they are NOT subscribed to, **Then** no alert is generated for that user.
4. **Given** a user changes their delivery method from `in_app` to `email`, **When** a subsequent qualifying event occurs, **Then** the alert is delivered via email; in-flight events that began evaluation before the change are unaffected.
5. **Given** a user selects `webhook` as the delivery method, **When** they save without providing a webhook URL, **Then** the save is rejected with a clear validation error.

---

### User Story 3 — Users read, dismiss, and review alert history (Priority: P1)

A user sees unread alerts on their dashboard and in a dedicated alerts view. They can mark individual alerts as read, filter by read/unread, and browse historical alerts. Unread count is visible in the UI header and stays in sync across all open sessions.

**Why this priority**: Persistent, readable alert history is what makes alerts useful beyond the moment of delivery — users need a place to review what happened when they were away. P1 because offline delivery (US1 scenario 2) is meaningless if there is no persistent surface on which to view the alerts.

**Independent Test**: Trigger three alerts for the test user. Log in. Verify all three appear as unread and the header shows "3 unread". Mark one as read. Verify header updates to "2 unread" and the read alert is distinguishable in the list. Open a second browser tab — verify the same "2 unread" count without refreshing.

**Acceptance Scenarios**:

1. **Given** a user has received several alerts, **When** they open their alerts view, **Then** they see a list of all alerts ordered by recency with read/unread state distinguished and filterable.
2. **Given** an unread alert, **When** the user marks it as read, **Then** the alert is persisted as read, the unread count decrements across all of the user's sessions in real time, and the alert is no longer highlighted in the list.
3. **Given** a user with no alerts, **When** they open the alerts view, **Then** the view displays an empty-state message.
4. **Given** historical alerts older than the retention window, **When** the retention policy runs, **Then** alerts past the retention date are removed from the user's view.

---

### User Story 4 — Offline alerts deliver on next login (Priority: P2)

When an alert is generated for a user who has no active WebSocket sessions, the alert is stored in the persistent alert log. On the user's next login, all unread alerts accumulated while offline are delivered to their client so the client can render them. The user is not spammed with pop-ups for old alerts — they appear in the alerts view with their original timestamps and unread state.

**Why this priority**: Offline delivery ensures that important alerts are not lost, but the basic in-app delivery (US1) plus the alerts view (US3) covers the most common case. P2 because users who are actually offline when an alert fires will typically see it when they log in anyway — they just need the alert to be preserved.

**Independent Test**: Log the test user out. Generate three alerts addressed to that user. Log in. Verify all three alerts appear in the unread list with correct timestamps. Verify no pop-up / modal spam — alerts are just visible in the alerts view and unread count.

**Acceptance Scenarios**:

1. **Given** a user is offline, **When** an alert is generated for them, **Then** the alert is persisted with read=false and no delivery attempt is made over WebSocket.
2. **Given** a user logs in and establishes a WebSocket connection, **When** the notifications service detects the connection, **Then** all unread alerts for that user are delivered on the attention channel in chronological order along with a single summary message indicating how many were delivered.
3. **Given** a user has been offline long enough that some unread alerts have aged past the retention window, **When** they log in, **Then** the expired alerts are not delivered (they have been garbage-collected by the retention policy).

---

### User Story 5 — Webhook delivery for external integrations (Priority: P3)

A power user or admin configures their delivery method to `webhook` and provides a URL. When a qualifying alert is generated, the platform POSTs the alert payload to the URL. If the endpoint is unreachable, the platform retries with exponential backoff and logs failures. Users can review webhook delivery outcomes per alert.

**Why this priority**: Webhook delivery enables external integrations (PagerDuty, Slack via custom middleware, ops dashboards) but is not required for core platform usability. P3 because in-app delivery plus email cover the mainstream needs.

**Independent Test**: Configure the test user's delivery method to `webhook` with a test URL that records POST bodies. Trigger a qualifying alert. Verify a POST arrives within 5 seconds with the expected payload (alert id, type, title, body, urgency, timestamp). Take the endpoint down; trigger another alert. Verify the platform retries and eventually marks the delivery as failed after the configured retry budget is exhausted.

**Acceptance Scenarios**:

1. **Given** a user with delivery method `webhook` and a valid URL, **When** an alert is generated, **Then** the platform POSTs a JSON payload to the URL within 5 seconds and records the delivery outcome (success/failure) per alert.
2. **Given** a webhook URL that returns 5xx or times out, **When** the platform attempts delivery, **Then** it retries with exponential backoff up to a configured maximum retry count, then marks the delivery as failed and surfaces the error in the user's alerts view.
3. **Given** a user with `webhook` delivery method but no valid URL (deleted or invalidated), **When** an alert would be generated, **Then** the alert is still persisted (with in-app fallback) and the webhook failure is logged, not silently dropped.

---

### Edge Cases

- **User has multiple active WebSocket sessions**: Alerts are delivered to all sessions concurrently. Marking as read in one session propagates to the others in real time.
- **Attention request addressed to a nonexistent user identity**: Request is logged and discarded; no alert record is created.
- **Attention request with an unknown or invalid urgency**: Urgency defaults to `medium` and a warning is logged; the request is still delivered.
- **State-change event for an interaction that no longer exists (e.g., deleted mid-flight)**: The event is logged and discarded; no alert is generated.
- **User changes delivery method while an alert is in the delivery pipeline**: The in-flight alert delivers via the method that was active when the alert was generated; subsequent alerts use the new method.
- **Concurrent read/mark-read operations from multiple sessions**: Last-writer-wins is acceptable; the alert ends up read either way. Unread count re-derived on each read operation.
- **Webhook endpoint returns 2xx but with a large body**: Platform treats 2xx as success regardless of response body; body is not persisted.
- **Email delivery when the user has no verified email on file**: Alert falls back to `in_app` delivery; failure reason is recorded.
- **Subscription list contains an unknown state transition name**: Unknown entries are ignored at evaluation time; other valid entries in the list still apply.
- **User deleted while they have unread alerts**: Unread alerts are also deleted in cascade with the user record; no orphaned alerts persist.
- **Attention request volume spike from a misbehaving agent**: The notifications service applies per-source rate limiting so a single agent cannot flood a user with more than a configured number of alerts per minute; excess alerts are dropped with an incident log.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST provide a new notifications bounded context that subscribes to the existing `interaction.attention` Kafka topic and to interaction state-change events, and generates user alerts according to each user's configured preferences.
- **FR-002**: The platform MUST persist every generated alert in a durable alert record carrying: alert identifier, target user identifier, optional originating interaction identifier, alert type, title, body, read state (default false), and creation timestamp.
- **FR-003**: The platform MUST support per-user alert settings that include: subscribed state transitions (list of transition patterns, defaulting to a platform-standard set of high-signal transitions), delivery method (in-app, email, or webhook), and a webhook URL when the delivery method is webhook.
- **FR-004**: A user MUST be able to read their own alert settings and update them through a dedicated interface; updates MUST take effect on the next event evaluation (in-flight evaluations unaffected).
- **FR-005**: When an attention request arrives on the `interaction.attention` topic addressed to a specific user or role, the platform MUST generate alert records for all resolved target users and dispatch them according to each user's configured delivery method.
- **FR-006**: When an interaction state transition event arrives and a user's alert settings subscribe to that transition, the platform MUST generate an alert for that user and dispatch it via the user's configured delivery method.
- **FR-007**: If a user has no alert settings record, the platform MUST treat them as having the default preferences (subscribed to `working_to_pending`, `any_to_complete`, `any_to_failed`, delivery method `in_app`).
- **FR-008**: For users with delivery method `in_app` who have at least one active WebSocket session, the platform MUST push the alert to every active session over the existing attention/alerts channel within 2 seconds of alert generation.
- **FR-009**: For users with delivery method `in_app` who have no active WebSocket session, the platform MUST persist the alert as unread and deliver all unread alerts when the user next connects to the WebSocket gateway.
- **FR-010**: For users with delivery method `email`, the platform MUST dispatch alert emails through the existing platform email infrastructure within 60 seconds of alert generation; failures MUST be retried according to the existing email delivery policy.
- **FR-011**: For users with delivery method `webhook`, the platform MUST POST a JSON payload of the alert to the configured URL, retry on 5xx and timeout responses with exponential backoff up to a configured maximum, and record the final delivery outcome (success, failed, timed_out) per alert.
- **FR-012**: If a user's delivery method is `email` and they have no verified email on file, or `webhook` and they have no valid URL, the platform MUST fall back to `in_app` delivery so the alert is not lost, and MUST record the fallback reason.
- **FR-013**: A user MUST be able to list their own alerts with filters for read state (all, unread, read), ordered by most recent first, with pagination.
- **FR-014**: A user MUST be able to mark individual alerts as read; the read state change MUST be propagated to all of the user's active WebSocket sessions in real time so unread counts stay in sync.
- **FR-015**: A user MUST be able to see their unread alert count at all times through a lightweight query interface; the count MUST update in real time as alerts arrive or are read.
- **FR-016**: A user MUST NOT be able to read, mark-read, or otherwise access alerts belonging to another user. All alert access MUST be scoped to the authenticated identity.
- **FR-017**: The platform MUST rate-limit alert generation per attention-request source; a single agent MUST NOT cause more than a configured threshold of alerts per minute to reach a single user; excess alerts MUST be dropped with an incident log entry.
- **FR-018**: Alert records MUST carry a reference to the originating event (interaction identifier when applicable, attention request identifier when applicable) so administrators can trace an alert back to its source.
- **FR-019**: The platform MUST enforce a configurable retention window for alert records; records older than the retention window MUST be removed by a scheduled garbage-collection process and MUST NOT be delivered to users on login.
- **FR-020**: Attention requests with unknown urgency values MUST default to a configured standard urgency (e.g., `medium`) and the unknown urgency MUST be logged; the request MUST still be delivered.
- **FR-021**: Attention requests addressed to nonexistent or invalid user identities MUST be logged and discarded; no alert record MUST be created.
- **FR-022**: State-change events for interactions that are not in an addressable state (deleted, archived, belonging to a suspended workspace) MUST be discarded without generating alerts.
- **FR-023**: The platform MUST NOT deliver the same alert more than once per delivery channel; delivery attempts MUST be idempotent against the alert identifier.
- **FR-024**: Subscription patterns that do not match any registered state transition name MUST be ignored at evaluation time; valid entries in the same subscription list MUST still apply.
- **FR-025**: Alert payloads delivered via webhook MUST NOT contain any credential, token, or secret; body and title are user-safe text only. (Consistency with the platform's secret-handling posture.)

### Key Entities

- **User Alert Settings**: A per-user record capturing which interaction state transitions generate alerts for that user, the preferred delivery method, and (when applicable) a webhook URL. Exactly one record per user; default values apply when no record exists.
- **User Alert**: An immutable-by-default record produced when a qualifying event occurs. Carries the target user, optional originating interaction reference, alert type, title, body, read/unread state, and creation timestamp. Read state is the only field that mutates over time.
- **Attention Request (existing)**: The agent-initiated signal consumed from the `interaction.attention` topic. Already defined in the interactions bounded context; this feature consumes rather than redefines it.
- **State-Change Event (existing)**: Emitted by the interactions bounded context when an interaction transitions between states. Already exists; this feature adds a new consumer on top.
- **Delivery Outcome**: Per-alert metadata capturing the delivery method used, timestamp of delivery attempt, outcome (success/failed/timed_out/fallback), and any error detail. Especially relevant for webhook delivery where retry and failure tracking are needed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: When an attention request is emitted for an online user, the alert reaches the user's client within 2 seconds in 95% of cases (p95 delivery latency SLA).
- **SC-002**: When an attention request is emitted for an offline user, the alert is persisted and is among the alerts delivered on the user's next login in 100% of cases (no loss).
- **SC-003**: Users with configured preferences receive alerts only for state transitions in their subscribed list in 100% of cases (zero false-positive alerts for unsubscribed transitions).
- **SC-004**: Alert read-state changes propagate across all of a user's active sessions within 2 seconds of the read action in 95% of cases.
- **SC-005**: Email delivery completes within 60 seconds of alert generation in 95% of cases.
- **SC-006**: Webhook delivery succeeds within 5 seconds of alert generation in 95% of cases where the endpoint is reachable; failed deliveries are retried until success or the retry budget is exhausted.
- **SC-007**: Per-source alert rate limiting prevents any single agent from generating more than the configured per-minute threshold of alerts for any single user in 100% of attempts.
- **SC-008**: 100% of alert records can be traced to an originating attention request or interaction state-change event via the persisted reference identifier.
- **SC-009**: After the retention window elapses, alerts older than that window are no longer visible in user-facing lists in 100% of cases and do not appear on user login.
- **SC-010**: No user is able to access the alerts, settings, or unread count belonging to another user through any interface (verifiable via authorization tests), in 100% of cases.
- **SC-011**: The proportion of alerts successfully delivered (sum of in-app, email, webhook) divided by alerts generated is observable as a metric per tenant; target SLO is tenant-configurable.

## Assumptions

- The `interaction.attention` Kafka topic and the `AttentionRequest` model already exist in the platform and are emitted by agents through existing mechanisms; this feature consumes from, not redefines, that topic.
- Interaction state-change events are already published by the interactions bounded context on the existing `interaction.events` topic or an equivalent; this feature adds a new consumer without altering the producer.
- The WebSocket gateway already supports channel-based subscription; this feature reuses the existing attention/alerts channel mechanism rather than introducing a new transport.
- The platform's existing email infrastructure (connectors bounded context or equivalent) handles the actual sending of email; this feature hands off to that infrastructure and does not implement its own SMTP.
- The user authentication/identity subsystem resolves "target identity" (user id or role) to a concrete set of users; this feature consumes that resolution rather than re-implementing it.
- Role resolution for role-addressed attention requests is performed against the existing RBAC tables.
- Alert retention policy follows the platform-wide audit retention defaults unless an operator overrides; this feature does not introduce new retention policy semantics.
- Default state transitions in the user alert settings (`working_to_pending`, `any_to_complete`, `any_to_failed`) are standard patterns already emitted by the interactions bounded context; adding new transition patterns is straightforward and does not require a new subsystem.

## Dependencies

- Existing `interaction.attention` Kafka topic and `AttentionRequest` record structure (produced by agents; consumed by this feature).
- Existing interaction state-change events (produced by the interactions bounded context; consumed by this feature).
- Existing WebSocket gateway with channel-based subscription and per-user session registry.
- Existing email/connector infrastructure for email delivery.
- Existing authentication/identity subsystem for resolving target identities and enforcing per-user access.
- Existing audit/event infrastructure and retention policy.
- Existing outbound HTTP client capability for webhook delivery (including retry policy).

## Out of Scope

- Creating new attention request types or new attention emission APIs; this feature only consumes the existing topic. Agents continue to emit attention requests through their existing mechanisms.
- New transport channels beyond in-app, email, and webhook (e.g., SMS, push notifications). Future features may add transports.
- Bulk mark-all-read or cross-user bulk operations.
- Alert templating or localization per recipient; alerts carry the title/body as produced by the source event.
- Priority inboxes, alert snoozing, or digest-mode aggregation. All alerts are delivered individually per the user's preferences.
- Administrative override to force-deliver alerts to users who have unsubscribed from a transition. A user's preferences are authoritative for that user.
- Machine-learning-driven alert filtering or relevance scoring. Subscription rules are the only filter.
- Changes to how attention requests are emitted by agents (urgency semantics, targeting rules). The emission side is unchanged.
