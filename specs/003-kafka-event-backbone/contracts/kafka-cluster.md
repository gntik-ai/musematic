# Contract: Kafka Cluster Infrastructure

**Feature**: 003-kafka-event-backbone  
**Type**: Infrastructure Contract  
**Date**: 2026-04-09

---

## Cluster Contract

Any service that connects to the Kafka cluster must respect the following contract:

### Connection

| Property | Value |
|----------|-------|
| Bootstrap servers (production) | `musematic-kafka-kafka-bootstrap.platform-data:9092` |
| Bootstrap servers (development) | `musematic-kafka-kafka-bootstrap.platform-data:9092` |
| Protocol | PLAINTEXT (within cluster); TLS can be layered later |
| Namespace requirement | Caller must be in `platform-control` or `platform-execution` |

### Producer Requirements

- `acks=all` — required for durable commits (FR-011)
- `enable.idempotence=true` — required to avoid duplicates on retry
- `compression.type=lz4` — recommended for throughput
- Partition key: set per topic as documented in the Topic Registry (data-model.md)
- Message value: UTF-8 JSON bytes following the `EventEnvelope` schema

### Consumer Requirements

- Must join a named consumer group (not `group.id=<random>`)
- `auto.offset.reset=earliest` — new groups start from beginning
- `enable.auto.commit=false` — manual offset commit after processing
- After processing, commit offset only on success; delegate to `RetryHandler` on failure
- Consumer groups must not delete or modify topic configurations

### Broker SLA

| Metric | Value |
|--------|-------|
| Produce latency p99 | < 100ms same datacenter (SC-008) |
| Minimum throughput | 10,000 msg/s aggregate (SC-009) |
| Fault tolerance | Single-broker failure with no data loss (SC-002) |
| Retention guarantee | Per-topic policy (3d / 7d / 14d / 30d) |

---

## Topic Existence Contract

After Helm deployment, consumers may assume all 38 topics exist:
- 19 domain topics (as listed in data-model.md Topic Registry)
- 19 DLQ topics (`<topic>.dlq`)

Topics will not be auto-created by brokers (`auto.create.topics.enable=false` in cluster config). Missing topics indicate a deployment issue.

---

## Network Policy Contract

| Source Namespace | Can Connect? | Port |
|-----------------|--------------|------|
| `platform-control` | Yes | 9092 |
| `platform-execution` | Yes | 9092 |
| `platform-observability` | Yes (metrics only) | 9404 |
| `platform-data` | Yes (intra-cluster) | 9090, 9091 |
| Any other namespace | No | — |
