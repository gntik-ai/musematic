# Data Model: Apache Kafka Event Backbone

**Feature**: 003-kafka-event-backbone  
**Date**: 2026-04-09

---

## Topic Registry

All 19 domain topics + 19 DLQ topics = 38 total topics.

### Domain Topics

| Topic | Partitions | Partition Key | Retention | `retention.ms` |
|-------|-----------|---------------|-----------|----------------|
| `interaction.events` | 12 | `interaction_id` | 7d | 604800000 |
| `workflow.runtime` | 12 | `execution_id` | 7d | 604800000 |
| `runtime.lifecycle` | 6 | `runtime_id` | 3d | 259200000 |
| `runtime.reasoning` | 12 | `execution_id` | 7d | 604800000 |
| `runtime.selfcorrection` | 12 | `execution_id` | 7d | 604800000 |
| `sandbox.events` | 6 | `sandbox_id` | 3d | 259200000 |
| `workspace.goal` | 6 | `workspace_id` | 7d | 604800000 |
| `connector.ingress` | 12 | `workspace_id` | 3d | 259200000 |
| `connector.delivery` | 12 | `workspace_id` | 3d | 259200000 |
| `monitor.alerts` | 6 | — (none) | 14d | 1209600000 |
| `trust.events` | 6 | — (none) | 30d | 2592000000 |
| `evaluation.events` | 6 | — (none) | 30d | 2592000000 |
| `context.quality` | 6 | `execution_id` | 7d | 604800000 |
| `fleet.health` | 6 | `fleet_id` | 7d | 604800000 |
| `agentops.behavioral` | 6 | `agent_id` | 30d | 2592000000 |
| `simulation.events` | 6 | `simulation_id` | 3d | 259200000 |
| `testing.results` | 6 | — (none) | 30d | 2592000000 |
| `communication.broadcast` | 6 | `fleet_id` | 3d | 259200000 |
| `interaction.attention` | 6 | `target_id` | 7d | 604800000 |

**Total domain topics**: 19

### Dead-Letter Topics

Each domain topic has a corresponding DLQ topic with `.dlq` suffix, 6 partitions (fixed), replication factor 3, and 30-day retention (`retention.ms: 2592000000`).

| DLQ Topic | Source Topic |
|-----------|-------------|
| `interaction.events.dlq` | `interaction.events` |
| `workflow.runtime.dlq` | `workflow.runtime` |
| `runtime.lifecycle.dlq` | `runtime.lifecycle` |
| `runtime.reasoning.dlq` | `runtime.reasoning` |
| `runtime.selfcorrection.dlq` | `runtime.selfcorrection` |
| `sandbox.events.dlq` | `sandbox.events` |
| `workspace.goal.dlq` | `workspace.goal` |
| `connector.ingress.dlq` | `connector.ingress` |
| `connector.delivery.dlq` | `connector.delivery` |
| `monitor.alerts.dlq` | `monitor.alerts` |
| `trust.events.dlq` | `trust.events` |
| `evaluation.events.dlq` | `evaluation.events` |
| `context.quality.dlq` | `context.quality` |
| `fleet.health.dlq` | `fleet.health` |
| `agentops.behavioral.dlq` | `agentops.behavioral` |
| `simulation.events.dlq` | `simulation.events` |
| `testing.results.dlq` | `testing.results` |
| `communication.broadcast.dlq` | `communication.broadcast` |
| `interaction.attention.dlq` | `interaction.attention` |

**Total DLQ topics**: 19  
**Grand total**: 38 topics

---

## Event Envelope

The canonical envelope wraps every message on every topic.

```
EventEnvelope
├── event_id: UUID                  # Unique per message (UUID4)
├── event_type: str                 # "<domain>.<topic>.<EventName>" (e.g., "workflow.runtime.StepStarted")
├── schema_version: str             # Semantic version (e.g., "1.0.0")
├── occurred_at: datetime           # UTC timestamp, set by producer
├── actor: str                      # FQN of emitting agent/service (e.g., "reasoning-engine:main")
├── correlation: CorrelationContext
│   ├── workspace_id: str | None
│   ├── execution_id: str | None
│   ├── interaction_id: str | None
│   ├── fleet_id: str | None
│   ├── goal_id: str | None         # GID — first-class per constitution AD-3.10
│   └── trace_id: str | None       # OpenTelemetry trace ID
└── payload: dict[str, Any]        # Opaque; validated by each consumer
```

**Constraints**:
- `event_id` must be unique globally (UUID4 guarantees this)
- `occurred_at` is producer-set UTC; consumers must not reject events with timestamps in the past
- `payload` is opaque to the backbone; domain-specific schema validation is the consumer's responsibility
- Serialization: UTF-8 JSON bytes via Pydantic `model_dump_json()`

---

## DLQ Message Structure

When a message fails after `max_attempts` retries, a DLQ message is produced with this payload:

```
DLQ EventEnvelope
├── event_id: UUID                  # New UUID for the DLQ message itself
├── event_type: "dlq.FailedMessage"
├── schema_version: "1.0.0"
├── occurred_at: datetime           # When the DLQ message was produced
├── actor: str                      # The consumer group that failed (e.g., "consumer-group:workflow-processor")
├── correlation: CorrelationContext # Copied from original message
└── payload:
    ├── original_envelope: dict     # Full original EventEnvelope as JSON object
    ├── source_topic: str           # e.g., "workflow.runtime"
    ├── source_partition: int       # Partition number of the failed message
    ├── source_offset: int          # Offset of the failed message
    ├── error_class: str            # Exception class name
    ├── error_message: str          # Exception message
    └── retry_attempts: list[RetryAttempt]
        └── RetryAttempt:
            ├── attempt: int        # 1-indexed
            ├── timestamp: datetime # When this attempt occurred
            └── error: str          # Error message for this attempt
```

---

## Helm Values Topic Schema

In `deploy/helm/kafka/values.yaml`, topics are defined as a list to drive Helm range loops:

```yaml
topics:
  - name: interaction.events
    partitions: 12
    retentionMs: 604800000
  - name: workflow.runtime
    partitions: 12
    retentionMs: 604800000
  # ... (19 entries total)

replicationFactor: 3   # overridden to 1 in values-dev.yaml
dlqRetentionMs: 2592000000
dlqPartitions: 6
```

---

## Kubernetes Resources

### Cluster Resources (per environment)

| Resource | Production | Development |
|---------|-----------|-------------|
| `Kafka` CR | 1 | 1 |
| `KafkaNodePool` (controller) | 1 (3 nodes) | — |
| `KafkaNodePool` (broker) | 1 (3 nodes) | — |
| `KafkaNodePool` (combined) | — | 1 (1 node) |
| `KafkaTopic` domain | 19 | 19 |
| `KafkaTopic` DLQ | 19 | 19 |
| `NetworkPolicy` | 3 | 0 (dev skips) |

### Namespace: `platform-data`

All Kafka infrastructure (cluster, topics, node pools) lives in `platform-data`.

### Port Reference

| Port | Protocol | Purpose |
|------|----------|---------|
| 9090 | TCP | KRaft controller quorum (internal) |
| 9091 | TCP | Inter-broker replication (internal) |
| 9092 | TCP | Client connections (producer/consumer) |
| 9404 | TCP | Prometheus JMX metrics scraping |
