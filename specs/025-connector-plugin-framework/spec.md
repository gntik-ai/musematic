# Feature Specification: Connector Plugin Framework

**Feature Branch**: `025-connector-plugin-framework`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "Implement connector plugin contract, routing, Slack/Telegram/webhook/email connectors, credential isolation, retry/dead-letter handling, and Kafka integration."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Connector Registration and Configuration (Priority: P1)

A platform operator wants to connect an external communication channel (such as Slack, Telegram, a custom webhook, or email) to the platform so that agents can receive messages from and send messages to that channel. The operator creates a connector instance within a workspace, specifying the connector type, a human-readable name, and configuration parameters (e.g., webhook URL, bot token reference, email server settings). The system validates the configuration against the connector type's requirements — for example, a Slack connector requires a bot token and a signing secret. Credentials are stored as references (pointers to a secure vault), never as plaintext values. Once configured, the operator can enable or disable the connector instance, update its configuration, or remove it entirely. Each workspace manages its own connector instances independently — one workspace's connectors are invisible to another.

**Why this priority**: Without connector registration, no external channels can be connected. This is the foundation that all inbound/outbound message flows depend on.

**Independent Test**: Create a Slack connector instance in a workspace with a valid configuration. Verify the configuration is validated and the instance is created in "enabled" status. Attempt to create a connector with an invalid configuration (missing required field) — verify validation error. Update the connector configuration — verify the update is accepted. Disable the connector — verify it no longer processes messages. Delete the connector — verify it is removed. Attempt to access the connector from a different workspace — verify access denied.

**Acceptance Scenarios**:

1. **Given** a workspace, **When** an operator creates a connector instance with valid configuration, **Then** the instance is created, configuration is validated, and credentials are stored as vault references
2. **Given** a connector type with required fields, **When** configuration is missing a required field, **Then** creation fails with a validation error listing the missing fields
3. **Given** an existing connector instance, **When** the operator disables it, **Then** the connector stops processing inbound and outbound messages
4. **Given** a connector instance in workspace A, **When** a user in workspace B attempts to access it, **Then** access is denied
5. **Given** an enabled connector, **When** the operator runs a health check, **Then** the system reports the connector's reachability status (healthy, degraded, or unreachable)

---

### User Story 2 — Inbound Message Routing (Priority: P1)

An external message arrives from a connected channel — for example, a user sends a message in a Slack channel that the platform monitors, or a webhook receives a POST request from an external system. The connector normalizes the incoming payload into a standard format (sender identity, channel, content, timestamp, original payload reference). The normalized message is then routed according to the workspace's routing rules: each routing rule maps a connector instance and optional conditions (e.g., channel name, sender pattern) to a target agent or workflow. If a matching route is found, the message is published to the ingress event stream for the target to consume. If no route matches, the message is logged and optionally forwarded to a default handler. Webhook connectors verify the incoming request's signature before processing.

**Why this priority**: Inbound routing is the primary value proposition — it connects external channels to the agent platform. Without it, agents cannot receive messages from the outside world.

**Independent Test**: Configure a Slack connector with a route mapping channel "#support" to agent "support-ops:triage-agent." Send a simulated Slack event for channel "#support." Verify the event is normalized and published to the ingress stream with the correct target agent. Send a message for an unrouted channel — verify it is logged as unrouted. Send a webhook request with an invalid signature — verify it is rejected.

**Acceptance Scenarios**:

1. **Given** a configured connector and routing rule, **When** an inbound message arrives matching the route, **Then** the message is normalized to a standard format and published to the ingress stream targeting the configured agent
2. **Given** an inbound message with no matching route, **When** the message is processed, **Then** it is logged as unrouted and optionally forwarded to a default handler
3. **Given** a webhook connector, **When** an inbound request has an invalid signature, **Then** the request is rejected before any processing occurs
4. **Given** multiple routing rules for the same connector, **When** a message matches multiple rules, **Then** the first matching rule (by priority order) is applied
5. **Given** a disabled connector instance, **When** an inbound message arrives, **Then** the message is ignored and no processing occurs

---

### User Story 3 — Outbound Message Delivery (Priority: P1)

An agent or workflow produces a response that needs to be delivered to an external channel — for example, replying to a Slack message, sending a Telegram notification, or dispatching an email. The system receives a delivery request specifying the target connector instance, the destination (e.g., Slack channel ID, email address), and the message content. The connector formats the message according to the target channel's requirements and delivers it. If delivery fails, the system retries with exponential backoff (up to a configurable maximum attempts). If all retries are exhausted, the message is moved to a dead-letter queue for manual inspection and optional redelivery.

**Why this priority**: Outbound delivery completes the communication loop. Agents need to respond through the same channels they receive messages from. Retry and dead-letter handling ensures reliability.

**Independent Test**: Create an outbound delivery request targeting a Slack connector. Verify the message is formatted and delivered to the Slack API. Simulate a delivery failure — verify the system retries with increasing intervals. Simulate persistent failures beyond the maximum retry count — verify the message is moved to the dead-letter queue. Inspect the dead-letter queue — verify the failed message is retrievable with error details.

**Acceptance Scenarios**:

1. **Given** a delivery request targeting an enabled connector, **When** delivery succeeds, **Then** the message is delivered to the external channel and a success event is emitted
2. **Given** a delivery failure (transient error), **When** the first attempt fails, **Then** the system retries with exponential backoff up to the maximum retry count
3. **Given** all retry attempts exhausted, **When** the final attempt fails, **Then** the message is moved to a dead-letter queue with error details and a dead-letter event is emitted
4. **Given** a dead-letter message, **When** an operator inspects the queue, **Then** they can see the original message, target, error history, and optionally trigger a manual redeliver
5. **Given** a delivery request targeting a disabled connector, **When** the delivery is attempted, **Then** it is rejected with a connector-disabled error

---

### User Story 4 — Credential Isolation and Security (Priority: P1)

A platform operator configures credentials for a connector — for example, a Slack bot token, a webhook signing secret, or SMTP credentials. The credentials must be isolated per workspace (one workspace cannot access another's credentials), encrypted at rest, and never included in logs, error messages, or event payloads. When a connector needs credentials at runtime, the system retrieves them from the secure vault using the credential reference — the actual secret value is injected directly into the connector's outbound call, bypassing any context that could leak to agents or logs.

**Why this priority**: Credential security is a non-negotiable requirement (constitution §XI — secrets never in LLM context). A credential leak could compromise external systems. This must be enforced from day one alongside connector registration.

**Independent Test**: Create a connector with a credential reference. Verify the credential is stored as a reference (not plaintext). Retrieve the connector configuration — verify the credential value is masked. Trigger an outbound delivery — verify the actual credential is used in the API call but never appears in logs or event payloads. Attempt to access a credential from a different workspace — verify access denied.

**Acceptance Scenarios**:

1. **Given** a connector with credential references, **When** the configuration is retrieved, **Then** credential values are masked and the actual secrets are not returned
2. **Given** an outbound delivery, **When** the connector authenticates with the external service, **Then** the credential is retrieved from the vault and injected at the point of use, never passing through the agent or logs
3. **Given** a workspace with credentials, **When** a user from a different workspace queries connector configurations, **Then** no credential information from the first workspace is visible
4. **Given** a connector execution that fails, **When** the error is logged, **Then** no credential values appear in the error message or event payload
5. **Given** a credential update, **When** an operator rotates a credential, **Then** the new credential takes effect on subsequent deliveries without restarting the connector

---

### User Story 5 — Multi-Channel Connector Types (Priority: P2)

The platform ships with built-in connectors for the most common communication channels: Slack (receiving messages via Events API, sending via Web API), Telegram (receiving via Bot API webhooks, sending via Bot API), generic webhooks (receiving with signature verification, sending via HTTP POST), and email (receiving via periodic inbox polling, sending via standard email delivery). Each connector type implements the same plugin contract — validating configuration, normalizing inbound messages to a standard format, formatting and delivering outbound messages, and reporting health status. Additional connector types can be added by implementing the same contract.

**Why this priority**: The four built-in connector types cover the most common enterprise communication channels. Without them, the connector framework is an empty abstraction. However, the framework contract (US1-US4) must work first — specific connectors plug into it.

**Independent Test**: For each connector type (Slack, Telegram, Webhook, Email): create an instance with valid configuration → verify health check passes → send a simulated inbound message → verify normalization produces the standard format → send an outbound delivery → verify formatting matches the channel's requirements. Verify that all four types produce the same normalized inbound format despite different source payloads.

**Acceptance Scenarios**:

1. **Given** a Slack connector, **When** a Slack event arrives, **Then** it is normalized into the standard inbound format with sender, channel, content, and timestamp
2. **Given** a Telegram connector, **When** a Telegram update arrives, **Then** it is normalized into the same standard inbound format
3. **Given** a webhook connector, **When** a POST request arrives with a valid signature, **Then** the payload is normalized into the standard inbound format
4. **Given** an email connector, **When** new emails are detected in the monitored inbox, **Then** each email is normalized into the standard inbound format
5. **Given** any connector type, **When** an outbound delivery is requested, **Then** the message is formatted according to the channel's specific requirements (rich text for Slack, Markdown for Telegram, raw body for webhooks, MIME for email)

---

### User Story 6 — Monitoring and Dead-Letter Management (Priority: P3)

An operator wants visibility into the health and activity of their workspace's connectors. They can view the status of each connector instance (enabled/disabled, last health check result, message counts), inspect the dead-letter queue for failed deliveries, and manually redeliver or discard dead-letter messages. The system tracks delivery metrics per connector (messages sent, failed, retried, dead-lettered) for operational awareness.

**Why this priority**: Monitoring and dead-letter management are operational necessities but not blocking for the core message flow. Connectors can operate (send and receive) without a monitoring UI — metrics and dead-letter inspection improve operations but are not part of the critical path.

**Independent Test**: Send 10 outbound messages through a connector — verify delivery counts are tracked. Force 2 failures beyond retry limit — verify dead-letter queue shows 2 entries. Manually redeliver one dead-letter message — verify it is retried. Discard the other — verify it is removed from the queue. Check connector status — verify health status and message counts are accurate.

**Acceptance Scenarios**:

1. **Given** a connector processing messages, **When** the operator queries its status, **Then** they see the connector's health status and message counts (sent, failed, retried, dead-lettered)
2. **Given** messages in the dead-letter queue, **When** the operator lists dead-letter entries, **Then** they see the original message, target, error details, and failure timestamp for each entry
3. **Given** a dead-letter entry, **When** the operator triggers a manual redeliver, **Then** the message is retried through the normal delivery pipeline
4. **Given** a dead-letter entry, **When** the operator discards it, **Then** the entry is removed from the queue and archived
5. **Given** multiple connector instances, **When** the operator lists all connectors, **Then** each shows its current status and aggregate delivery metrics

---

### Edge Cases

- What happens when a connector's external service is down during an inbound message? The inbound message is queued in the ingress stream. If normalization cannot complete (e.g., payload format unrecognizable), the raw payload is stored with an "unparseable" flag for manual review.
- What happens when an outbound delivery target does not exist (e.g., deleted Slack channel)? The delivery fails with a "target not found" error. After retries are exhausted, the message is dead-lettered with the specific error, and the operator is notified.
- What happens when a credential reference points to a deleted vault entry? The connector fails its health check with a "credential unavailable" error. Outbound deliveries are rejected until the credential is restored or updated.
- What happens when two routing rules have the same priority for a message? The system uses creation order as the tiebreaker — the older rule takes precedence. This is documented in the routing rule configuration.
- What happens when an inbound message exceeds the maximum payload size? The message is rejected at the connector level with a "payload too large" error. The rejection is logged with the source and size.
- What happens when the dead-letter queue is full? The dead-letter queue has no fixed size limit. Old entries can be archived or discarded by operators to manage storage. A workspace-level alert is triggered when the dead-letter count exceeds a configurable threshold.
- What happens when a connector type is deprecated or removed? Existing connector instances of that type continue to function but cannot be newly created. The type is marked as "deprecated" in the connector registry. Operators are advised to migrate to an alternative type.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support connector instance registration within a workspace, including type, name, configuration, and credential references
- **FR-002**: The system MUST validate connector configuration against the connector type's schema before accepting registration or updates
- **FR-003**: The system MUST support enabling, disabling, updating, and deleting connector instances per workspace
- **FR-004**: The system MUST normalize all inbound messages from any connector type into a standard format containing sender identity, channel, content, timestamp, and original payload reference
- **FR-005**: The system MUST route inbound messages to target agents or workflows based on configurable routing rules per workspace
- **FR-006**: The system MUST support routing rule conditions including connector instance, channel/source pattern, and sender pattern, with priority-based matching
- **FR-007**: The system MUST verify inbound webhook signatures before processing any webhook payload
- **FR-008**: The system MUST deliver outbound messages through the appropriate connector, formatting content according to the target channel's requirements
- **FR-009**: The system MUST retry failed outbound deliveries with exponential backoff up to a configurable maximum attempts (default: 3)
- **FR-010**: The system MUST move permanently failed deliveries to a dead-letter queue with full error history
- **FR-011**: The system MUST store connector credentials as vault references, never as plaintext, and never include them in logs, events, or API responses
- **FR-012**: The system MUST enforce workspace isolation on all connector operations — no cross-workspace visibility or access
- **FR-013**: The system MUST support a health check mechanism for each connector instance to verify external service reachability
- **FR-014**: The system MUST publish inbound messages to an ingress event stream for consumption by routing targets
- **FR-015**: The system MUST publish outbound delivery requests to a delivery event stream for consumption by connector workers
- **FR-016**: The system MUST support built-in connector types for Slack, Telegram, generic webhooks, and email
- **FR-017**: The system MUST support dead-letter queue inspection, manual redelivery, and message discard
- **FR-018**: The system MUST track per-connector delivery metrics (messages sent, failed, retried, dead-lettered)
- **FR-019**: The system MUST enforce a configurable maximum payload size for inbound messages (default: 1 MB)
- **FR-020**: The system MUST support credential rotation without connector restart — new credentials take effect on the next operation

### Key Entities

- **Connector**: A registered connector type (e.g., Slack, Telegram, Webhook, Email). Defines the configuration schema, validation rules, and normalization/delivery logic. The platform ships with 4 built-in types and supports extensibility.
- **ConnectorInstance**: A workspace-scoped instance of a connector type. Contains the connector type, name, configuration (validated against the type's schema), credential references, enabled/disabled status, and health check results.
- **ConnectorCredentialRef**: A reference to a secret stored in the platform's secure vault. Contains the credential key, vault path, and workspace scope. Never contains the actual secret value.
- **ConnectorRoute**: A routing rule that maps inbound messages from a connector instance to a target agent or workflow. Contains the connector instance reference, matching conditions (channel, sender patterns), target agent FQN or workflow ID, priority, and enabled status.
- **InboundMessage**: A normalized inbound message produced by a connector. Contains the source connector instance, sender identity, channel/source, content (text and/or structured data), timestamp, original payload reference, and workspace ID.
- **OutboundDelivery**: A delivery request for an outbound message. Contains the target connector instance, destination (channel, address, etc.), content, priority, retry count, status, and error history.
- **DeadLetterEntry**: A record of a permanently failed outbound delivery. Contains the original delivery request, full error history, dead-letter timestamp, and resolution status (pending, redelivered, discarded).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Inbound message normalization and routing completes within 500 milliseconds from message receipt
- **SC-002**: Outbound message delivery (excluding external API latency) initiates within 300 milliseconds of the delivery request
- **SC-003**: Failed delivery retries follow exponential backoff (1s, 4s, 16s default intervals) with 100% adherence to the configured schedule
- **SC-004**: Credential isolation is enforced on 100% of operations — zero cross-workspace credential leakage
- **SC-005**: Dead-letter queue captures 100% of permanently failed deliveries — zero silent message loss
- **SC-006**: All four built-in connector types (Slack, Telegram, Webhook, Email) produce the same normalized inbound format — zero format inconsistencies
- **SC-007**: Connector health checks detect external service unavailability within 30 seconds
- **SC-008**: The system sustains 500 inbound messages per minute per workspace without degradation
- **SC-009**: Credential values never appear in logs, events, or API responses — verified by log audit
- **SC-010**: Test coverage of the connector plugin framework is at least 95%

## Assumptions

- The platform provides a secure vault service for credential storage and retrieval. The connector framework references credentials by vault path, not by managing encryption directly.
- Workspace membership and access control are provided by the workspaces bounded context (feature 018) via in-process service interface.
- The interactions bounded context (feature 024) consumes inbound messages from the ingress event stream and creates interactions from them.
- Outbound delivery requests are produced by agents or workflows via the execution bounded context and published to the delivery event stream.
- Slack integration uses the Slack Events API for inbound and the Slack Web API for outbound. The platform does not implement a Slack socket mode adapter.
- Telegram integration uses the Bot API with webhook mode for inbound. Long polling mode is not supported.
- Email inbound uses periodic inbox polling (configurable interval, default: 60 seconds) rather than IMAP IDLE push notifications.
- The exponential backoff for retries uses base 4 (1s, 4s, 16s) by default, configurable per connector type.
- Webhook signature verification supports HMAC-SHA256 by default, with configurable algorithm per connector instance.
- The dead-letter queue is stored persistently — entries survive restarts. Operators can redeliver or discard entries via the management interface.
- Connector workers run as a separate runtime profile (`worker`) that consumes from the delivery event stream and processes outbound messages.
