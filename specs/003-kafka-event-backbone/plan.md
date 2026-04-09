# Implementation Plan: Apache Kafka Event Backbone

**Branch**: `003-kafka-event-backbone` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/003-kafka-event-backbone/spec.md`

## Summary

Deploy Apache Kafka via Strimzi operator as the durable event backbone for all asynchronous coordination. The implementation delivers: a Helm chart for Strimzi Kafka cluster (KRaft mode, no ZooKeeper), 38 KafkaTopic CRs (19 domain + 19 DLQ), network policies for namespace isolation, and a Python async producer/consumer framework (`aiokafka`) with canonical EventEnvelope, RetryHandler, and DLQ routing. The Go reasoning engine gains a Kafka producer for event emission via `confluent-kafka-go/v2`.

## Technical Context

**Language/Version**: Python 3.12+ (control plane), Go 1.22+ (reasoning engine)  
**Primary Dependencies**: aiokafka 0.11+ (Python producer/consumer), confluent-kafka-go v2 (Go producer), Strimzi operator (Kubernetes Kafka), Helm 3.x  
**Storage**: Apache Kafka 3.7+ with KRaft consensus (no ZooKeeper)  
**Testing**: pytest + pytest-asyncio 8.x + testcontainers (Kafka) for integration tests  
**Target Platform**: Kubernetes 1.28+ (`platform-data` namespace)  
**Project Type**: Infrastructure (Helm chart) + library (Python event client)  
**Performance Goals**: < 100ms p99 produce-to-consume latency, 10,000 msg/s aggregate throughput  
**Constraints**: Single-broker failure must not cause data loss; network access restricted to `platform-control` and `platform-execution`  
**Scale/Scope**: 38 topics, 19 consumer groups (one per domain), production cluster = 3 brokers

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Check | Status |
|------|-------|--------|
| Python version | Python 3.12+ per constitution §2.1 | PASS — plan uses Python 3.12+ |
| Go version | Go 1.22+ per constitution §2.2 | PASS — plan uses Go 1.22+ |
| Kafka client (Python) | `aiokafka 0.11+` per constitution §2.1 | PASS |
| Kafka client (Go) | `confluent-kafka-go/v2` per constitution §2.2 | PASS |
| Kafka operator | Strimzi per constitution §2.5 | PASS |
| Namespace: data store | `platform-data` per constitution | PASS — Kafka lives in `platform-data` |
| Namespace: clients | `platform-control`, `platform-execution` per constitution | PASS — network policy allows both |
| Namespace: observability | `platform-observability` per constitution | PASS — metrics port open to `platform-observability` |
| Go service path | `services/reasoning-engine/` per constitution §3.2 | PASS — Go Kafka producer in `services/reasoning-engine/` |
| Helm chart conventions | No operator sub-dependencies; exact versions | PASS — Strimzi is pre-installed; chart deploys CRs only |
| Async everywhere | aiokafka async API used throughout | PASS |
| No ZooKeeper | KRaft mode only | PASS — `spec.zookeeper` omitted from Kafka CR |
| Append-only journal | Kafka topics are append-only by nature | PASS |
| Secrets not in LLM context | Kafka credentials managed via Kubernetes Secrets | PASS |
| Observability | Strimzi JMX exporter → Prometheus | PASS |

All gates pass. Proceeding to Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/003-kafka-event-backbone/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (topic registry, envelope, DLQ structure)
├── quickstart.md        # Phase 1 output (deployment and testing guide)
├── contracts/
│   ├── kafka-cluster.md         # Cluster infrastructure contract
│   └── python-event-client.md   # Python producer/consumer/retry interface
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
deploy/helm/kafka/
├── Chart.yaml                    # Chart metadata (no dependencies — Strimzi is pre-installed)
├── values.yaml                   # Shared defaults (topic list, replication factor 3, etc.)
├── values-prod.yaml              # Production overrides (3 brokers, PVC size, resource limits)
├── values-dev.yaml               # Development overrides (1 broker, replication factor 1)
└── templates/
    ├── kafka.yaml                # Kafka CR (KRaft, listeners, JMX metrics)
    ├── kafka-node-pool-broker.yaml      # KafkaNodePool — broker role (prod only)
    ├── kafka-node-pool-controller.yaml  # KafkaNodePool — controller role (prod only)
    ├── kafka-node-pool-combined.yaml    # KafkaNodePool — combined role (dev only)
    ├── kafka-topics.yaml         # KafkaTopic CRs (range loop over values.topics)
    ├── kafka-dlq-topics.yaml     # KafkaTopic CRs for DLQ (range loop, .dlq suffix)
    └── network-policy.yaml       # NetworkPolicy (intra-cluster, client access, metrics)

apps/control-plane/src/platform/common/events/
├── __init__.py
├── envelope.py          # EventEnvelope + CorrelationContext Pydantic models + make_envelope()
├── producer.py          # AsyncKafkaProducer (aiokafka)
├── consumer.py          # AsyncKafkaConsumer + CommitCallback type
└── retry.py             # RetryHandler with exponential backoff + DLQ routing

services/reasoning-engine/
└── internal/
    └── events/
        ├── producer.go       # confluent-kafka-go/v2 Kafka producer
        └── producer_test.go  # Unit tests with mock producer

apps/control-plane/tests/integration/
├── test_kafka_producer.py    # Produce → consume round-trip (testcontainers)
├── test_kafka_consumer.py    # Consumer group offset tracking, replay
├── test_kafka_dlq.py         # DLQ routing after 3 failed attempts
└── test_kafka_topics.py      # Topic existence, partition count, retention
```

**Structure Decision**: Python event client lives in `apps/control-plane/src/platform/common/events/` (existing common/ package pattern from constitution §4 repo structure). Go producer lives in `services/reasoning-engine/internal/events/` (satellite service pattern). Helm chart at `deploy/helm/kafka/` (consistent with 001 and 002 chart locations).

## Implementation Phases

### Phase 0: Research (Complete)

All technical decisions resolved in [research.md](research.md):
- Strimzi KRaft configuration via `KafkaNodePool` CRDs
- KafkaTopic CR schema with `retention.ms` values
- Network policy ports (9090, 9091, 9092, 9404)
- EventEnvelope Pydantic v2 schema
- DLQ routing pattern via `RetryHandler`
- Go `confluent-kafka-go/v2` for reasoning engine

### Phase 1: Design & Contracts (Complete)

Artifacts generated:
- [data-model.md](data-model.md) — Topic registry (38 topics), EventEnvelope, DLQ structure, Helm values schema
- [contracts/kafka-cluster.md](contracts/kafka-cluster.md) — Cluster infrastructure contract
- [contracts/python-event-client.md](contracts/python-event-client.md) — Python producer/consumer/retry interfaces
- [quickstart.md](quickstart.md) — Deployment and testing guide

### Phase 2: Implementation (tasks.md — generated by /speckit.tasks)

Implementation order follows spec priorities:

**P1 — User Story 1**: Kafka cluster deployment (Helm chart, Kafka CR, KafkaNodePool CRs)  
**P1 — User Story 2**: Topic provisioning (KafkaTopic CRs, DLQ CRs)  
**P1 — User Story 3**: Produce/consume (EventEnvelope, AsyncKafkaProducer, AsyncKafkaConsumer, integration tests)  
**P2 — User Story 4**: Event replay (offset reset by timestamp in consumer)  
**P2 — User Story 5**: DLQ routing (RetryHandler with exponential backoff)  
**P2 — User Story 6**: Network policy (NetworkPolicy templates for namespace isolation)  
**P2 — User Story 7**: Attention topic (already in topic list; verify distinct from monitor.alerts)  

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Kafka mode | KRaft (no ZooKeeper) | Constitution mandates Strimzi; ZooKeeper deprecated in Kafka 3.8+ |
| Topic provisioning | KafkaTopic CRs via Helm range | Idempotent, Git-versionable, no admin job needed |
| Python client | aiokafka 0.11+ | Constitution-mandated async Kafka client |
| Go client | confluent-kafka-go/v2 | Constitution-mandated Go Kafka client |
| DLQ strategy | RetryHandler in consumer framework | Per spec assumption: cluster stores bytes, consumer framework handles retry |
| Serialization | UTF-8 JSON (Pydantic model_dump_json) | No Avro/Schema Registry dependency; opaque bytes per constitution |
| Network isolation | Kubernetes NetworkPolicy | Enforces namespace boundary without service mesh |
| Helm operator dep | None (Strimzi is pre-installed) | Same pattern as CloudNativePG (feature 001) |

## Dependencies

- **Upstream**: Strimzi operator must be installed before Helm chart deployment (cluster prerequisite, not chart dependency)
- **Downstream**: All features using async event coordination depend on this feature
- **Parallel with**: Redis cache (002) — no dependency relationship
- **Blocks**: Any bounded context that produces or consumes Kafka events

## Complexity Tracking

No constitution violations. Standard complexity for this feature.
