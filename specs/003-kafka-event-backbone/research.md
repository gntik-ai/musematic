# Research: Apache Kafka Event Backbone

**Feature**: 003-kafka-event-backbone  
**Date**: 2026-04-09  
**Phase**: 0 — Pre-design research

---

## Decision 1: Strimzi KRaft Mode Configuration

**Decision**: Use `Kafka` CR with `spec.kafka.version ≥ 3.7.0`, `spec.kafka.metadataVersion` set, and `spec.zookeeper` omitted entirely. The `KafkaNodePool` CRD is the current Strimzi approach for KRaft — each pool defines roles (`broker`, `controller`, or combined). For production: one pool with `controller` role (3 nodes) + one pool with `broker` role (3 nodes). For development: single combined pool (1 node, all roles).

**Rationale**: Strimzi 0.39+ fully supports KRaft GA (Kafka 3.6+). ZooKeeper mode is deprecated and removed in Kafka 3.8+. KRaft eliminates the ZooKeeper dependency, reducing infrastructure complexity by 3 pods per cluster. `KafkaNodePool` is the recommended abstraction — it replaces inline `spec.kafka.replicas` and allows mixed topology.

**Alternatives considered**:
- ZooKeeper mode: deprecated, requires 3 additional ZK pods, removed in Kafka 3.8+. Rejected.
- Inline `spec.kafka.replicas` (old Strimzi style): still works but discouraged; `KafkaNodePool` is forward-compatible. Rejected.

---

## Decision 2: KafkaTopic CR Schema

**Decision**: Use `KafkaTopic` CRD (`kafka.strimzi.io/v1beta2`). Each CR defines `spec.partitions`, `spec.replicas`, and `spec.config` (map of topic-level configs). Retention is set via `retention.ms` in `spec.config`. DLQ topics are separate `KafkaTopic` CRs with suffix `.dlq` and `retention.ms` = 2592000000 (30 days).

**Rationale**: The `KafkaTopic` operator watches CRs and reconciles topic state. This is idempotent — re-applying the chart is safe. Topic config is versionable in Git. No separate admin job needed.

**Alternatives considered**:
- Init container running `kafka-topics.sh`: brittle, requires broker access at chart install time, not idempotent. Rejected.
- Strimzi `KafkaTopicList`: not a real CRD; topics must be individual CRs. Rejected.

**Retention config mapping**:
| Retention | `retention.ms` value |
|-----------|---------------------|
| 3d        | 259200000           |
| 7d        | 604800000           |
| 14d       | 1209600000          |
| 30d       | 2592000000          |

---

## Decision 3: Network Policy for Strimzi

**Decision**: Three network policies are needed:
1. **Intra-cluster**: Allow broker ↔ broker communication (port 9090 for KRaft quorum, port 9091 for inter-broker replication) within `platform-data` namespace.
2. **Client access**: Allow ingress to brokers on port 9092 from namespaces `platform-control` and `platform-execution` only (via `namespaceSelector` on namespace labels).
3. **Monitoring**: Allow ingress on port 9404 (JMX/Prometheus exporter) from namespace `platform-observability`.

**Rationale**: Strimzi creates internal listeners on port 9091 and external (within-cluster) listeners on 9092 by default. KRaft controller quorum uses port 9090. Prometheus scraping comes from `platform-observability` namespace where the Prometheus stack runs (per constitution).

**Alternatives considered**:
- Single broad `allow-all-within-namespace` policy: violates constitution network isolation (section 3.7). Rejected.
- Istio mTLS for service mesh: out of scope for this feature; infrastructure concern. Rejected.

---

## Decision 4: Helm Chart Structure

**Decision**: Single Helm chart at `deploy/helm/kafka/` with the following resource types as templates:
- `Kafka` CR (cluster definition)
- `KafkaNodePool` CRs (broker/controller pools)
- `KafkaTopic` CRs (19 domain topics + 19 DLQ topics = 38 CRs, generated via Helm range loop from `values.yaml`)
- `NetworkPolicy` resources (3 policies)
- No `dependencies` in Chart.yaml — Strimzi operator is a cluster prerequisite, not a chart sub-dependency.

**Rationale**: Same pattern established in feature 001 (CloudNativePG) and 002 (Bitnami Redis). Operator is pre-installed; chart deploys CRDs only. Helm range over topic list keeps the chart DRY without 38 separate template files.

**Alternatives considered**:
- Separate Helm charts for cluster vs. topics: unnecessary split for a single feature boundary. Rejected.
- Kustomize overlays: project uses Helm exclusively (constitution). Rejected.

---

## Decision 5: EventEnvelope Schema

**Decision**: Define a canonical Pydantic v2 model in `apps/control-plane/src/platform/common/events/envelope.py`:

```python
class CorrelationContext(BaseModel):
    workspace_id: str | None
    execution_id: str | None
    interaction_id: str | None
    fleet_id: str | None
    goal_id: str | None
    trace_id: str | None

class EventEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: UUID          # unique per message
    event_type: str         # e.g., "workflow.runtime.StepStarted"
    schema_version: str     # e.g., "1.0.0"
    occurred_at: datetime   # UTC, producer-set
    actor: str              # FQN of emitting agent or service
    correlation: CorrelationContext
    payload: dict[str, Any] # opaque; validated by consumer
```

Serialization: JSON bytes via `model.model_dump_json()`. Producer sets `event_id`, `occurred_at`, `schema_version`. Consumers deserialize with `EventEnvelope.model_validate_json(raw)`.

**Rationale**: All Kafka messages share this envelope (per FR-010, SC-007). Frozen Pydantic model prevents mutation. `payload` is opaque so the backbone is payload-agnostic (per constitution §3.3 — cluster stores opaque byte payloads). `CorrelationContext` embeds the GID, execution_id, interaction_id for tracing (constitution AD-3.10).

**Alternatives considered**:
- Avro/Schema Registry: adds infrastructure dependency; out of scope for this feature. May be added later.
- Dataclass: no JSON serialization built-in, no validation. Rejected.

---

## Decision 6: DLQ Routing Pattern

**Decision**: DLQ routing is handled by the consumer framework in `retry.py`. The `RetryHandler` wraps a processing coroutine: on exception, it retries up to `max_attempts` (default 3) with exponential backoff. After exhausting retries, it produces a DLQ message to `{original_topic}.dlq` with envelope fields:
- `event_type`: `"dlq.FailedMessage"`
- `payload.original_envelope`: the original message JSON
- `payload.error`: exception class + message
- `payload.retry_attempts`: list of `{attempt, timestamp, error}` dicts
- `payload.source_topic`, `payload.source_partition`, `payload.source_offset`

**Rationale**: Per spec assumption: "Consumer retry logic is implemented by the consuming services using the platform's event consumer framework, not by the cluster itself." The `retry.py` module is that framework. DLQ messages contain all required metadata for FR-009, FR-010, SC-005, and User Story 5 acceptance scenarios.

**Alternatives considered**:
- Kafka Streams for DLQ: Go dependency, out of Python control-plane scope. Rejected.
- Manual DLQ in each consumer: code duplication; centralized retry framework is cleaner. Rejected.

---

## Decision 7: Go Kafka Client Integration

**Decision**: The Go reasoning engine (`services/reasoning-engine/`) uses `confluent-kafka-go/v2` for event emission only (produce-side). It does not consume Kafka topics — it emits events like `runtime.reasoning.ChainStarted`, `runtime.selfcorrection.ConvergenceDetected`. The producer is initialized at service startup and closed on graceful shutdown.

**Rationale**: Constitution specifies `confluent-kafka-go v2` for Go services. The reasoning engine is primarily a gRPC server — Kafka emission is a side-effect of reasoning operations, not a control path. Consumer logic stays in the Python control plane.

**Alternatives considered**:
- `segmentio/kafka-go`: good library but not the constitution-mandated choice. Rejected.
- sarama: complex API, not constitutionally mandated. Rejected.

---

## Resolution Summary

All technical unknowns resolved. No NEEDS CLARIFICATION markers remain. Plan can proceed to Phase 1.
