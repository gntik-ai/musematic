# Feature Specification: Multi-Channel Notifications

**Feature Branch**: `077-multi-channel-notifications`
**Created**: 2026-04-25
**Status**: Draft
**Input**: User description: "Extend notifications BC from 3 channels to 6: in-app WebSocket (existing), email, webhook (new — HMAC-signed with delivery guarantees), Slack, Microsoft Teams, SMS. Includes per-user channel configuration with quiet hours, workspace-level outbound webhooks with HMAC + at-least-once + idempotency, exponential backoff, dead-letter queue. FRs: FR-494, FR-495, FR-496."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Per-user multi-channel notification routing with quiet hours (Priority: P1)

A platform user configures **how** they want to be reached for different categories of alerts (execution failures, attention requests, governance verdicts, weekly digests, etc.). They can register one or more channels (email, Slack DM, Teams, SMS, in-app) and apply a per-channel filter (e.g., "only critical alerts to SMS") and quiet hours window in their local timezone (e.g., suppress non-critical alerts between 22:00 and 08:00 Europe/Madrid). At delivery time, the platform consults the user's channel configuration, evaluates the alert against each channel's filter and quiet hours, and dispatches only through eligible channels.

**Why this priority**: This is the headline value of the feature. Today users only get in-app notifications and a limited email path; they cannot be reached when away from the UI. Without this capability, alerts about failures and attention requests are routinely missed, defeating the purpose of the notifications system. Email is the baseline missing channel needed by every persona and unlocks immediate operational value even before Slack/Teams/SMS land.

**Independent Test**: Provision a user with one email channel and one in-app channel, configure quiet hours 22:00–08:00 in their timezone, and trigger two alerts of different criticality — one inside quiet hours and one outside. Verify only the outside-window alert is dispatched to email while in-app keeps both. Quiet-hours suppression for critical alerts is bypassed (see Edge Cases). MVP demonstrable on email + in-app alone, before Slack/Teams/SMS adapters are written.

**Acceptance Scenarios**:

1. **Given** a user has an email channel enabled with no filters and no quiet hours, **When** an alert fires for that user, **Then** the alert is delivered to the email channel within the platform delivery SLA and the in-app channel keeps receiving it.
2. **Given** a user has quiet hours 22:00–08:00 (Europe/Madrid) configured for their email channel, **When** a non-critical alert fires at 23:00 local time, **Then** no email is sent and the alert is buffered or surfaced only via in-app, while the same alert outside quiet hours is delivered immediately.
3. **Given** a user has an alert-type filter set to `["governance.verdict"]` on their Slack channel, **When** an alert of a different type fires, **Then** the alert is not routed to that Slack channel but is still delivered via other eligible channels.
4. **Given** a user disables a channel via self-service, **When** any alert fires, **Then** that channel receives nothing until it is re-enabled, and the user receives confirmation that disablement took effect.
5. **Given** a user adds a new email address as a channel, **When** they save the channel, **Then** the platform sends a verification message to that address and only enables routing once verification is confirmed.

---

### User Story 2 — Workspace outbound webhooks with HMAC signing and at-least-once delivery (Priority: P1)

A workspace administrator integrates the platform with an external system (their own incident-response tool, ticketing system, or SOC platform) by registering an outbound webhook URL, selecting which event types to forward (e.g., `execution.failed`, `governance.verdict.issued`, `interaction.attention`), and receiving a HMAC signing secret. The platform delivers each subscribed event to the URL with a HMAC-SHA-256 signature header and a unique idempotency key, retries with exponential backoff if the receiver returns a non-2xx, and surfaces undeliverable events in a dead-letter queue the admin can inspect and replay.

**Why this priority**: The webhook channel is what makes the platform interoperable with the rest of the customer's stack. Without delivery guarantees and signing, no production integration is safe — receivers cannot trust the source, cannot deduplicate retries, and cannot tell when a delivery has been silently dropped. P1 alongside US1 because both unblock different but equally critical user populations (end users vs. workspace integrations) and share the same channel-router infrastructure.

**Independent Test**: Register a webhook against a local HTTPS receiver, subscribe it to one event type, trigger 5 events of that type with one event repeated twice, and verify: (1) every event arrives at least once, (2) each delivery carries a valid HMAC-SHA-256 signature verifiable with the shared secret, (3) the duplicated event carries the same idempotency key on both deliveries, and (4) when the receiver returns 503 for the first 2 attempts of a given event, the platform retries on the configured backoff schedule and stops emitting after success.

**Acceptance Scenarios**:

1. **Given** a workspace admin registers a webhook URL with event type `execution.failed`, **When** an execution fails in their workspace, **Then** the webhook is invoked with a HMAC-SHA-256 signature header and an idempotency key unique to that delivery attempt sequence.
2. **Given** a webhook receiver returns HTTP 500, **When** the platform attempts redelivery, **Then** the same idempotency key is reused so the receiver can deduplicate, and retries follow the configured exponential backoff until either success or the retry budget is exhausted.
3. **Given** retries are exhausted without a 2xx response, **When** the delivery transitions to dead-letter, **Then** the workspace admin can see the dead-lettered event in an admin view and trigger a manual replay from there.
4. **Given** a webhook is set to inactive, **When** new events occur, **Then** no delivery attempts are made and pending retries for that webhook are abandoned (status set to dead-letter with a reason of "webhook deactivated").
5. **Given** an admin rotates the signing secret, **When** the next event is delivered, **Then** the new signature is produced from the new secret and the rotation is auditable by timestamp without exposing the previous secret material.
6. **Given** a webhook URL is restricted to HTTPS, **When** an admin attempts to register an HTTP URL, **Then** registration is rejected with a clear validation message.

---

### User Story 3 — Slack channel for personal and workspace notifications (Priority: P2)

A user (or workspace admin acting for a workspace channel) connects Slack so that platform alerts can land in a designated Slack channel or DM. They configure the connection once (incoming webhook URL or app credentials) and select which alert types should be forwarded. Messages render with the alert title, severity, brief context, and a deep link back to the platform UI for full detail.

**Why this priority**: Slack is the most-requested chat destination but is not blocking for first delivery — email + in-app already cover the core "tell me when something happens" need. P2 because it materially improves operator and team experience but the platform remains usable without it.

**Independent Test**: Connect a Slack incoming webhook to one user's account, fire an alert, and verify the message appears in the target Slack channel with the correct severity rendering, the correct deep link, and that quiet-hours and alert-type filters from US1 are honored.

**Acceptance Scenarios**:

1. **Given** a user has a working Slack channel configured for `attention.requested`, **When** an attention request fires, **Then** the Slack message appears with the alert title, severity badge, and a working deep link to the platform UI.
2. **Given** a user's Slack target has been revoked or rate-limited externally, **When** the platform attempts delivery, **Then** the failure is recorded and the user is notified through their other configured channels of the Slack outage.

---

### User Story 4 — Microsoft Teams channel (Priority: P2)

Identical user story to Slack but for Microsoft Teams: a user or admin connects an Office 365 / Teams connector URL, selects alert types, and messages render as Teams adaptive cards (or a simple message format) with severity and a deep link back to the platform.

**Why this priority**: Many customer organizations standardize on Teams rather than Slack; coverage parity between the two is required for go-to-market completeness. Same priority logic as Slack — additive, not blocking.

**Independent Test**: Configure a Teams connector for a user, fire an alert, and verify the card renders correctly in the Teams channel and that quiet-hours and alert-type filters are honored.

**Acceptance Scenarios**:

1. **Given** a user has a working Teams channel configured, **When** any subscribed alert fires, **Then** a Teams card appears in the target channel with title, severity, and deep link.
2. **Given** the Teams connector URL is invalid or returns a non-2xx, **When** the platform attempts delivery, **Then** the failure follows the same retry-and-dead-letter path as webhooks (US2).

---

### User Story 5 — Operator dead-letter inspection and replay (Priority: P2)

An operator (or workspace admin for workspace-scoped webhooks) opens a dead-letter view that lists every delivery that exhausted its retry budget across email, webhook, Slack, Teams, and SMS. For each entry the operator sees the original event, the destination, the failure reason and last response status, the count of attempts, and timestamps. They can manually replay a single entry or a filtered batch (e.g., everything that failed during a transient outage), and they can mark entries as resolved without replay.

**Why this priority**: Operability of the system depends on visibility into and recovery from delivery failures. Without dead-letter UX, the at-least-once guarantee in US2 is hollow — operators cannot tell what was lost and cannot make it right. P2 because the underlying dead-letter persistence already produces value as an audit trail in US2 even before the inspection UI lands; the UI/CLI replay path is the next increment.

**Independent Test**: Force-fail a webhook receiver, generate 10 events that exhaust their retry budget, then in the dead-letter view verify all 10 entries appear, restore the receiver, replay the batch, and verify all 10 are delivered exactly once-more and transition out of dead-letter.

**Acceptance Scenarios**:

1. **Given** 5 webhook deliveries dead-lettered to the same URL, **When** the operator triggers a batch replay, **Then** each entry reuses its original idempotency key, redelivery is attempted, and successful entries leave the queue.
2. **Given** a dead-lettered entry references a workspace the operator does not have access to, **When** they attempt to inspect or replay it, **Then** the operation is denied with an authorization error.
3. **Given** the dead-letter queue grows beyond a configurable capacity threshold, **When** the threshold is crossed, **Then** an alert fires to platform operators so the underlying delivery failure can be investigated.

---

### User Story 6 — SMS for critical-only alerts (Priority: P3)

A user (typically an oncall operator or workspace admin) registers a verified phone number as an SMS channel and pins it to critical-severity alerts only (e.g., "platform health critical", "governance enforcer blocked an action"). The platform sends an SMS via a third-party SMS provider on those events. Because SMS is the most disruptive and most expensive channel, it is opt-in, requires phone-number verification, and respects a hard severity floor.

**Why this priority**: SMS is the last-resort channel and is the most expensive and intrusive of the six. It is highly valued by oncall personas but is not a baseline requirement. P3 because email + Slack/Teams already cover urgent reachability for most users and SMS delivery requires per-deployment SMS-provider credentials and a cost-control story that is incremental to the channel router itself.

**Independent Test**: Register a phone number, complete verification, configure SMS for critical alerts only, fire a critical alert and a non-critical alert, and verify exactly one SMS is sent for the critical alert and zero SMS for the non-critical one.

**Acceptance Scenarios**:

1. **Given** a user registers a phone number, **When** they save the channel, **Then** an SMS verification code is sent and the channel is only enabled once verified.
2. **Given** an SMS channel restricted to critical severity, **When** a non-critical alert fires, **Then** no SMS is sent and the user is reached through their other configured channels.
3. **Given** the SMS provider is unavailable or the cost cap for the workspace is exhausted, **When** an SMS would otherwise be sent, **Then** the delivery transitions to dead-letter with a reason and the user is reached through fallback channels (email/in-app).

---

### Edge Cases

- **Quiet hours and critical alerts**: Quiet hours suppress non-critical alerts only. Alerts marked critical bypass quiet hours on every channel that the user has subscribed to that severity, so safety/governance signals are never silenced.
- **Timezone drift**: A user's configured timezone is the authority for quiet-hours evaluation, not the platform's UTC clock. Daylight-saving transitions and travel are handled by re-evaluating against the user's configured timezone every time.
- **Channel target verification**: Email addresses, phone numbers, and Slack/Teams targets must be verified or owned (in the case of incoming webhooks) before they receive any alert. Unverified channels are stored as `pending_verification` and emit nothing.
- **Webhook receiver returns 4xx**: Permanent client errors (`400`, `401`, `403`, `404`, `410`) skip retries and go straight to dead-letter — retrying makes no sense if the receiver explicitly refuses or doesn't exist.
- **Webhook receiver returns 429**: The platform respects `Retry-After` headers when present and falls back to the configured exponential schedule otherwise.
- **Receiver is slow but eventually returns 2xx after the first retry**: The receiver may still process the original delivery later; the idempotency key on every retry lets the receiver dedupe safely and avoids double-applying side effects.
- **Out-of-order delivery**: Retries can cause an older event to arrive after a newer one. Each delivery payload includes the event timestamp and a monotonic sequence within its event type so receivers can choose to discard stale events.
- **Per-user configuration limits**: A user may register at most a configurable number of channels per type (e.g., 3 email addresses, 1 SMS) to prevent abuse and runaway fan-out.
- **Per-workspace webhook limits**: A workspace may register at most a configurable number of active outbound webhooks to keep dead-letter and audit volumes bounded.
- **Dead-letter retention**: Dead-letter entries are retained for a configurable window (default 30 days) before being archived or purged, preserving audit visibility while bounding storage.
- **Provider rotation**: An admin can rotate a webhook signing secret without breaking in-flight retries — the next attempt uses the new secret and the rotation event is auditable.
- **PII in payloads**: Outbound payloads MUST honor the platform's data-loss-prevention rules (feature 076) and the workspace residency rules; webhook URLs in disallowed regions are rejected at registration.
- **Channel disabled mid-retry**: If a channel/webhook is disabled while retries are pending for it, all pending retries are abandoned and the entries dead-letter with a reason of "destination disabled" so the operator sees them and can re-enable + replay.

## Requirements *(mandatory)*

### Functional Requirements

#### Channel configuration (per-user)

- **FR-001**: The platform MUST allow each user to register, list, update, and remove channel configurations across at least the six channel types: in-app, email, webhook (personal), Slack, Microsoft Teams, and SMS.
- **FR-002**: The platform MUST require verification of new email addresses, phone numbers, and (where applicable) chat-platform targets before any alert is dispatched to them.
- **FR-003**: Each channel configuration MUST support an optional alert-type filter so the user receives only the alert categories they care about on that channel.
- **FR-004**: Each channel configuration MUST support optional quiet hours expressed as a start time, end time, and IANA timezone, and quiet-hours evaluation MUST use the user's configured timezone (not server UTC).
- **FR-005**: Quiet hours MUST suppress only non-critical alerts; alerts marked critical (severity floor configurable per deployment) MUST always bypass quiet hours.
- **FR-006**: A user MUST be able to enable or disable a channel without deleting it, and disablement MUST take effect for all subsequent deliveries.
- **FR-007**: The platform MUST enforce a per-user maximum number of channels per type to prevent runaway fan-out, with the cap configurable per deployment.

#### Channel router and delivery

- **FR-008**: When an alert is generated, the platform MUST consult every enabled channel configuration of the recipient user and route a delivery to each eligible channel (passing alert-type filter and quiet-hours rules).
- **FR-009**: The platform MUST evaluate quiet hours and filters atomically per delivery so a configuration change concurrent with delivery does not produce inconsistent routing.
- **FR-010**: Each channel adapter MUST report success, transient failure, or permanent failure back to the router so retry policy and dead-letter behavior can be applied uniformly.
- **FR-011**: The in-app (WebSocket) channel MUST continue to operate exactly as before for backward compatibility, even for users who have not yet configured any other channels.

#### Outbound webhooks (workspace-scoped)

- **FR-012**: Workspace administrators MUST be able to register, list, update, and deactivate outbound webhooks for their workspace, each carrying a destination URL, a list of subscribed event types, and a HMAC signing secret.
- **FR-013**: The platform MUST refuse to register webhook URLs that are not HTTPS in production deployments and MUST refuse URLs whose origin region is disallowed by the workspace's residency configuration.
- **FR-014**: Each outbound webhook delivery MUST carry a HMAC-SHA-256 signature header computed over the canonicalized payload using the webhook's signing secret, plus the timestamp of signing.
- **FR-015**: Each outbound webhook delivery MUST carry an idempotency key that uniquely identifies the (webhook, event) pair so all retries of the same event share the same key for receiver-side deduplication.
- **FR-016**: The platform MUST guarantee at-least-once delivery: an event subscribed by an active webhook MUST be attempted until either a 2xx is received from the receiver or the retry budget is exhausted.
- **FR-017**: Retries MUST follow a configurable exponential-backoff schedule (default 60 s, 5 min, 30 min) and the maximum total retry window MUST be configurable up to 24 hours per webhook.
- **FR-018**: Permanent client errors (HTTP 4xx other than 408 and 429) MUST short-circuit retries and route the delivery directly to dead-letter.
- **FR-019**: HTTP 429 responses MUST honor the `Retry-After` header when present and otherwise fall back to the configured exponential schedule.
- **FR-020**: Webhook signing-secret rotation MUST be supported without service interruption: the next delivery MUST sign with the new secret and the rotation MUST be auditable by timestamp and actor.

#### Dead-letter queue and replay

- **FR-021**: When a delivery exhausts its retry budget or hits a permanent failure, the platform MUST persist a dead-letter entry that includes the original event, destination, signature input, attempt count, last response status, failure reason, and timestamps.
- **FR-022**: The platform MUST provide a way for operators (and workspace admins for workspace-scoped destinations) to list, filter, and inspect dead-letter entries scoped to their authorization boundary.
- **FR-023**: Operators and workspace admins MUST be able to manually replay a dead-letter entry; replay MUST reuse the original idempotency key so receivers can deduplicate.
- **FR-024**: Operators and workspace admins MUST be able to mark a dead-letter entry as resolved without replay, with the resolution reason recorded.
- **FR-025**: Dead-letter entries MUST be retained for at least the configured retention window (default 30 days) before being archived or purged.
- **FR-026**: When the dead-letter queue depth crosses a configurable warning threshold, the platform MUST emit an operator alert so underlying delivery problems are surfaced proactively.

#### Channel adapters

- **FR-027**: The email channel MUST deliver via the platform's existing email transport configuration and MUST honor the platform's existing email branding/templating conventions.
- **FR-028**: The Slack channel MUST deliver to a configured Slack incoming-webhook target (or app installation) and MUST render with title, severity badge, brief context, and a deep link back to the platform UI.
- **FR-029**: The Microsoft Teams channel MUST deliver to a configured Teams connector (or app installation) and MUST render an equivalent card with title, severity, context, and deep link.
- **FR-030**: The SMS channel MUST deliver via a configured third-party SMS provider, MUST require phone-number verification before activation, MUST be restricted to alerts at or above a configurable severity floor (default critical-only), and MUST respect a per-workspace cost cap.

#### Security, audit, and observability

- **FR-031**: All channel signing secrets and SMS provider credentials MUST be stored via the platform secrets-management mechanism (vault refs), never in plaintext at rest.
- **FR-032**: Every channel configuration change (create, update, enable/disable, delete, secret rotation) MUST emit an audit-chain entry for compliance traceability.
- **FR-033**: Every delivery (success and failure) MUST emit a structured event consumable by the platform analytics pipeline so per-channel success rates and latencies are observable.
- **FR-034**: Outbound payloads MUST be evaluated by the platform's data-loss-prevention rules before transmission; payloads that would leak governed categories MUST be redacted or blocked according to policy.
- **FR-035**: Cross-user access to channel configurations MUST be denied: users MUST only be able to read or modify their own channels, except for platform/workspace admins acting within their explicit authorization scope.

### Key Entities *(include if feature involves data)*

- **Channel configuration**: A per-user record binding a channel type, a destination target, an optional signing-secret reference, an enabled flag, optional quiet-hours, and an optional alert-type filter. Uniquely identified by (user, channel type, target).
- **Outbound webhook**: A workspace-scoped record binding a destination URL, a set of subscribed event types, a HMAC signing secret reference, an active flag, and a retry policy (attempt count, backoff schedule, total window).
- **Webhook delivery**: A per-event delivery attempt sequence carrying the original event reference, the canonical payload, an idempotency key, the current status (`pending`, `delivered`, `failed`, `dead_letter`), the attempt count, the last response status, and timestamps.
- **Dead-letter entry**: The persisted final state of a delivery (across any channel) that exhausted retries or hit a permanent failure, including the failure reason, last response status, all retry timestamps, and an authorization-scope reference (workspace or user) so it can be surfaced to the right operator.
- **Quiet-hours window**: Per-channel start time, end time, and IANA timezone evaluated at delivery time against the user's configured timezone.
- **Alert-type filter**: Per-channel allow-list of alert categories (e.g., `execution.failed`, `governance.verdict.issued`, `interaction.attention`, `digest.weekly`).
- **Severity floor**: Per-channel minimum severity at which the channel will receive a delivery (used heavily by SMS to enforce critical-only).
- **Audit record**: An audit-chain entry recording every channel-configuration change and every webhook secret rotation, for compliance traceability.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can complete configuration of a new channel (including verification) and receive their first alert through it in under 3 minutes from start of configuration to first delivery.
- **SC-002**: At least 99% of webhook deliveries to a healthy receiver succeed on the first attempt within 5 seconds of the underlying event, measured over a rolling 24-hour window per workspace.
- **SC-003**: At-least-once delivery is observed at 100% in fault-injection tests: across 10 000 events with the receiver intermittently returning 5xx, every event is observed at least once at the receiver and idempotency keys are stable across retries.
- **SC-004**: When the receiver returns a permanent 4xx, the platform stops attempting redelivery within 1 retry cycle (≤ 60 s default), preventing wasted retry budget and runaway alerting.
- **SC-005**: Dead-letter operators can replay a batch of 100 dead-lettered events and complete redelivery within 5 minutes of pressing replay, with the receiver observing 100 successful deliveries each carrying the original idempotency keys.
- **SC-006**: Quiet-hours suppression is correct in 100% of cases when validated against a representative user's IANA timezone across two daylight-saving transitions, and critical alerts always bypass quiet hours.
- **SC-007**: 95% of users who enable a non-default channel (Slack, Teams, SMS) report (in qualitative feedback or via "stop reaching me here" toggles) that the channel is reaching them at the desired times — proxy: under 5% of users disable a channel within 7 days of activating it.
- **SC-008**: SMS volume per workspace stays under the configured cost cap in 100% of measurement intervals; the platform does not silently exceed cost limits.
- **SC-009**: When the dead-letter queue depth crosses the warning threshold, the operator alert fires within 1 minute, before the queue grows by another 10%.
- **SC-010**: All six channel types (in-app, email, webhook, Slack, Teams, SMS) are demonstrably deliverable end-to-end in the platform's E2E suite, with each suite run exercising at least one delivery per channel.
- **SC-011**: Backward compatibility: 100% of existing in-app subscribers continue to receive alerts unchanged after this feature ships, with zero migration steps required of end users for the in-app path.
- **SC-012**: Webhook signature verification by an external receiver succeeds in 100% of deliveries (no key drift, no canonicalization mismatch), validated by a verification client running against the platform's test deployment.

## Assumptions

- **Existing notifications context**: The notifications bounded context already exists with in-app and a baseline email path. This feature extends rather than replaces — existing in-app subscribers must keep working unchanged.
- **Existing email transport**: An email transport (SMTP or equivalent) is already configurable at the deployment level; this feature does not introduce a new email infrastructure choice.
- **Existing secrets-management**: A vault / secret-reference mechanism is already in place (the platform's standard for connectors and rotated secrets) and channel secrets reuse it directly.
- **Existing audit chain**: The audit chain (UPD-024) is available for recording configuration changes and secret rotations; this feature consumes it rather than defining new audit infrastructure.
- **Existing data-loss-prevention rules**: Feature 076's DLP pipeline is available and is consulted before outbound delivery; this feature relies on those rules rather than re-implementing them.
- **Existing residency configuration**: Feature 076's residency rules are available and are consulted before webhook URL acceptance and at delivery time; webhooks pointing at disallowed regions are rejected at registration.
- **Existing severity model**: Alerts already carry a severity classification (e.g., `info`, `warn`, `critical`) used by quiet-hours bypass and SMS severity floor. This feature relies on that taxonomy rather than redefining it.
- **External provider credentials**: Slack incoming-webhook URLs (or app credentials), Microsoft Teams connector URLs, and SMS-provider credentials are configured per deployment by an administrator and are not provisioned by the platform itself.
- **At-least-once is the contract**: The platform commits to at-least-once delivery and explicitly does not commit to exactly-once; receivers MUST deduplicate using the supplied idempotency key.
- **Backoff schedule defaults**: Default backoff is 60 s / 300 s / 1800 s for the first three attempts, with the total retry window configurable up to 24 hours per webhook. Operators can tune both per deployment without code changes.
- **Retention defaults**: Dead-letter retention default is 30 days; alert-event retention follows existing notification BC retention rules.
- **Verification mechanics**: Email verification uses a tokenized link valid for 24 hours; SMS verification uses a 6-digit code valid for 10 minutes. These match existing platform conventions.
- **Caps and limits**: Per-user channel caps and per-workspace webhook caps are configurable per deployment and default to values consistent with the platform's existing rate-limit posture.
- **Timezone source**: User timezone is taken from their existing user profile; quiet-hours evaluation is centralized in the channel router and uses IANA timezone identifiers.
- **Backward-compatibility flag**: The new channel router replaces the direct in-app push at the call site for `alert_service`. Existing in-app subscribers continue to receive alerts because the in-app channel remains a first-class channel within the new router.

## Dependencies

- **UPD-009 / existing notifications context**: This feature extends the notifications bounded context that UPD-009 established — it must not regress in-app delivery or break existing event consumers.
- **Audit chain (UPD-024)**: Required for FR-032 audit emissions on configuration changes and secret rotations.
- **DLP pipeline (feature 076)**: Required for FR-034 outbound payload evaluation.
- **Residency configuration (feature 076)**: Required for FR-013 webhook origin-region rejection.
- **Vault / secrets management**: Required for FR-031 storage of HMAC signing secrets and SMS provider credentials.
- **Workspace administration**: Workspace-admin RBAC scope must already exist for outbound-webhook CRUD to be authorized correctly.
