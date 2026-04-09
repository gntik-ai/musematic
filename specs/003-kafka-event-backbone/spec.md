# Feature Specification: Apache Kafka Event Backbone Deployment

**Feature Branch**: `003-kafka-event-backbone`
**Created**: 2026-04-09
**Status**: Draft
**Input**: User description: Deploy Apache Kafka via Strimzi operator as the durable event backbone for all asynchronous coordination, replay, fan-out, backlog visibility, observer access, and recovery across the platform.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Platform Operator Deploys Kafka Cluster (Priority: P1)

A platform operator deploys a production-ready Kafka cluster with a single command. In production, the cluster runs 3 brokers using KRaft consensus (no ZooKeeper dependency), with replication factor 3 for durability. In development, a single broker runs for local testing. The operator can verify cluster health through built-in metrics exposed to the monitoring stack.

**Why this priority**: Without the running cluster, no other event-driven feature can function. This is the foundation for all async coordination across the platform.

**Independent Test**: Deploy the cluster, verify all brokers are running and healthy, confirm the cluster accepts connections on the designated port, and validate that metrics are being scraped by the monitoring system.

**Acceptance Scenarios**:

1. **Given** a configured environment, **When** the operator deploys with production settings, **Then** 3 broker pods start in the designated namespace, all report ready status, and the cluster forms with KRaft consensus.
2. **Given** a configured environment, **When** the operator deploys with development settings, **Then** a single broker pod starts and accepts connections.
3. **Given** a running production cluster, **When** one broker pod is terminated, **Then** the remaining brokers continue serving requests without data loss, and the terminated broker rejoins automatically.

---

### User Story 2 - Platform Creates All Required Topics (Priority: P1)

The platform provisions all 19 event topics (18 domain topics + 1 attention topic) with the correct partition counts, replication factors, and retention policies. Each topic also has a corresponding dead-letter queue (DLQ) topic for failed message handling.

**Why this priority**: Topics must exist before any service can produce or consume events. This is required immediately after the cluster is running.

**Independent Test**: After deployment, list all topics and verify each exists with the correct partition count and retention configuration. Produce a test message to each topic and consume it back to confirm end-to-end connectivity.

**Acceptance Scenarios**:

1. **Given** a running Kafka cluster, **When** topics are provisioned, **Then** all 19 topics exist with configured partition counts (6 or 12) and retention periods (3d, 7d, 14d, or 30d).
2. **Given** provisioned topics, **When** a message is produced to any topic, **Then** a consumer can read that message from the correct partition based on the partition key.
3. **Given** provisioned topics, **When** listing all topics, **Then** 19 corresponding `.dlq` topics also exist, each with 30-day retention.

---

### User Story 3 - Services Produce and Consume Events Reliably (Priority: P1)

Platform services produce events to topics and consumer groups read from them with guaranteed ordering within a partition key. Messages are durably committed (acks=all) so no data is lost even during broker failures. Consumer group offsets are tracked, enabling each service to resume from where it left off after restarts.

**Why this priority**: Reliable produce/consume is the core value proposition of the event backbone. Without it, all async coordination patterns fail.

**Independent Test**: Produce 1000 messages to a topic with a known partition key, consume them with a consumer group, verify ordering is preserved, then restart the consumer and verify it resumes from the correct offset.

**Acceptance Scenarios**:

1. **Given** a running topic, **When** a producer sends messages with `acks=all`, **Then** all messages are durably committed and survive a single-broker failure.
2. **Given** a consumer group reading from a topic, **When** the consumer is restarted, **Then** it resumes from the last committed offset without re-processing or skipping messages.
3. **Given** messages produced with the same partition key, **When** consumed, **Then** they arrive in the exact order they were produced.

---

### User Story 4 - Operator Replays Events from a Point in Time (Priority: P2)

An operator or automated system can reset a consumer group's offset to a specific timestamp, enabling replay of events from that point forward. This supports recovery scenarios, re-processing after bug fixes, and backfilling projections.

**Why this priority**: Replay capability is essential for operational recovery but not needed for initial deployment. It builds on top of working produce/consume.

**Independent Test**: Produce messages over a time range, consume them, reset the consumer group offset to a mid-point timestamp, then re-consume and verify only messages from that timestamp forward are delivered.

**Acceptance Scenarios**:

1. **Given** a consumer group that has fully consumed a topic, **When** the operator resets the offset to a past timestamp, **Then** the consumer re-reads all messages from that timestamp forward.
2. **Given** a topic with 7 days of retained events, **When** replaying from 3 days ago, **Then** approximately 3 days of events are re-delivered.

---

### User Story 5 - Failed Events Route to Dead-Letter Queues (Priority: P2)

When a consumer fails to process a message after a configured number of retries (default: 3 attempts), the message is routed to the corresponding dead-letter topic (`.dlq` suffix). DLQ messages retain the original payload, error details, and source topic metadata for later inspection and re-processing.

**Why this priority**: DLQ handling prevents poison messages from blocking consumers. Important for production resilience but can be added after basic produce/consume works.

**Independent Test**: Produce a message that triggers processing failure, verify it appears in the DLQ topic after 3 failed attempts, and confirm the DLQ message includes original payload and error metadata.

**Acceptance Scenarios**:

1. **Given** a consumer processing messages, **When** a message fails processing 3 times, **Then** it is published to the corresponding `.dlq` topic with original payload and error details.
2. **Given** a DLQ message, **When** an operator inspects it, **Then** the message includes the source topic, partition, offset, error reason, and all retry timestamps.

---

### User Story 6 - Network Access Is Restricted to Authorized Namespaces (Priority: P2)

Only services in authorized namespaces (`platform-control` and `platform-execution`) can connect to Kafka brokers. All other namespaces are blocked by network policy. This enforces the platform's security boundary.

**Why this priority**: Security hardening is critical for production but does not block development or basic testing.

**Independent Test**: Attempt to connect to Kafka from an authorized namespace (succeeds) and from an unauthorized namespace (connection refused or times out).

**Acceptance Scenarios**:

1. **Given** a running Kafka cluster, **When** a service in `platform-control` connects, **Then** the connection succeeds and the service can produce/consume.
2. **Given** a running Kafka cluster, **When** a service in an unauthorized namespace (e.g., `default`) attempts to connect, **Then** the connection is blocked.

---

### User Story 7 - Attention Signals Are Routed Separately from System Alerts (Priority: P2)

Agent-initiated urgency signals (attention requests) are published to the `interaction.attention` topic, which is distinct from system-health alerts on `monitor.alerts`. This ensures that agent-initiated urgent communications do not get mixed with infrastructure alerts and can be consumed by a dedicated attention handler.

**Why this priority**: The attention pattern is a core platform pattern that requires its own routing to avoid conflation with operational alerts.

**Independent Test**: Publish an attention event and a monitor alert simultaneously; verify each arrives on its respective topic and can be consumed independently by separate consumer groups.

**Acceptance Scenarios**:

1. **Given** the attention topic exists, **When** an agent publishes an `AttentionRequest` event, **Then** it arrives on `interaction.attention` with the correct partition key (`target_id`).
2. **Given** both `interaction.attention` and `monitor.alerts` topics, **When** events are published to each, **Then** a consumer subscribed only to attention events does not receive system alerts, and vice versa.

---

### Edge Cases

- What happens when a broker runs out of disk space? Log segments are deleted according to retention policy; if disk fills before retention expires, the oldest segments are force-deleted and an alert is raised.
- What happens when a producer cannot reach the cluster? The producer retries with exponential backoff; after exhausting retries, the send fails with an error that the calling service must handle (circuit breaker pattern).
- What happens when a consumer group has more members than partitions? Excess consumers remain idle until a partition becomes available (standard Kafka rebalancing behavior).
- What happens when a topic's partition count needs to increase? Partition count can be increased but never decreased; existing messages retain their partition assignment; new messages are routed by the updated partition count.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST deploy a Kafka cluster that operates without ZooKeeper (KRaft mode).
- **FR-002**: System MUST support configurable cluster sizes: 3 brokers for production, 1 broker for development.
- **FR-003**: System MUST create all 19 event topics with the partition counts, partition keys, and retention periods defined in the topic registry.
- **FR-004**: System MUST create a dead-letter topic (`.dlq` suffix) for each of the 19 event topics, with 30-day retention.
- **FR-005**: System MUST replicate all topic data with replication factor 3 in production to survive single-broker failures.
- **FR-006**: System MUST expose cluster and topic metrics for monitoring (broker health, consumer group lag, throughput, disk usage).
- **FR-007**: System MUST enforce network access restrictions so only authorized namespaces can connect to brokers.
- **FR-008**: System MUST support consumer group offset reset to a specific timestamp for event replay.
- **FR-009**: System MUST route failed messages to the corresponding DLQ after a configurable number of retry attempts (default: 3).
- **FR-010**: System MUST preserve message ordering within a partition key across produce and consume operations.
- **FR-011**: System MUST durably commit messages when producers use `acks=all` configuration.
- **FR-012**: System MUST support the `interaction.attention` topic as a distinct channel from `monitor.alerts`, keyed by `target_id`.
- **FR-013**: System MUST retain events according to per-topic retention policies (3d, 7d, 14d, or 30d).
- **FR-014**: System MUST automatically recover from single-broker failures without manual intervention.
- **FR-015**: System MUST support graceful rolling restarts of brokers without message loss or consumer disruption.

### Key Entities

- **Kafka Cluster**: The broker ensemble that stores and serves event data. Defined by broker count, storage configuration, and consensus mode (KRaft).
- **Topic**: A named, partitioned, replicated log. Each topic has a partition count, partition key scheme, replication factor, and retention period.
- **Dead-Letter Topic**: A companion topic (`.dlq` suffix) that receives messages that failed processing after exhausting retries. Includes original payload, error metadata, and retry history.
- **Consumer Group**: A named group of consumers that collectively process a topic's partitions. Tracks committed offsets for resume-after-restart.
- **Attention Event**: An agent-initiated urgency signal carrying source agent FQN, target identifier, urgency level, context summary, and correlation IDs. Routed via `interaction.attention`, distinct from system alerts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 19 event topics and 19 DLQ topics (38 total) are created and operational after a single deployment command.
- **SC-002**: The cluster survives termination of any single broker without message loss or service interruption for producers/consumers.
- **SC-003**: Consumer group lag is visible in the monitoring system within 60 seconds of lag occurring.
- **SC-004**: Event replay from a specified timestamp delivers all retained events from that point forward, with zero duplicates and correct ordering per partition key.
- **SC-005**: Messages that fail processing 3 times arrive in the corresponding DLQ within 30 seconds of the third failure.
- **SC-006**: Unauthorized namespace connections are blocked 100% of the time by the network policy.
- **SC-007**: Attention events and system alerts are fully independent: consuming one channel never delivers events from the other.
- **SC-008**: End-to-end latency from produce to consume is under 100ms at p99 for messages within the same data center.
- **SC-009**: The cluster handles at least 10,000 messages per second aggregate throughput across all topics.

## Assumptions

- The cluster operator (Strimzi) is pre-installed in the target environment before this feature is deployed. This feature deploys cluster and topic resources, not the operator itself.
- All services that produce or consume events implement their own serialization/deserialization logic; the cluster stores opaque byte payloads.
- Consumer retry logic (3 attempts before DLQ routing) is implemented by the consuming services using the platform's event consumer framework, not by the cluster itself.
- Topic partition keys are chosen by the producing services based on the documented key scheme; the cluster does not enforce key formats.
- The `interaction.attention` topic follows the same infrastructure patterns as all other topics; the distinction between attention events and alerts is semantic (different topics), not structural.
- Development mode uses a single broker with replication factor 1, which means no fault tolerance in development.
- Disk-based persistent storage is available in the deployment environment for broker log segments.
- The platform's Python async Kafka client (`aiokafka`) and Go Kafka client (`confluent-kafka-go`) are used by consuming/producing services but are not part of this feature's scope — this feature covers cluster and topic infrastructure only.
