# Tasks: Apache Kafka Event Backbone

**Input**: Design documents from `specs/003-kafka-event-backbone/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US7)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory scaffolding and add dependencies before any story work begins.

- [X] T001 Create `deploy/helm/kafka/` directory and all subdirectories (`templates/`)
- [X] T002 [P] Create `apps/control-plane/src/platform/common/events/__init__.py` (empty package marker)
- [X] T003 [P] Add `aiokafka>=0.11` to `apps/control-plane/pyproject.toml` under `[project.dependencies]`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: EventEnvelope and Settings config — required by every user story's Python code.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Implement `CorrelationContext` and `EventEnvelope` Pydantic v2 models plus `make_envelope()` factory in `apps/control-plane/src/platform/common/events/envelope.py` — fields: `event_id` (UUID4), `event_type`, `schema_version`, `occurred_at` (UTC datetime), `actor`, `correlation` (CorrelationContext), `payload` (dict); `make_envelope()` auto-generates `event_id` and `occurred_at`
- [X] T005 Add Kafka config entries to `apps/control-plane/src/platform/common/config.py`: `KAFKA_BOOTSTRAP_SERVERS: str` (default `"localhost:9092"`), `KAFKA_CONSUMER_GROUP_ID: str` (default `"platform-control"`)

**Checkpoint**: Envelope + config ready — all user story phases can now begin.

---

## Phase 3: User Story 1 — Platform Operator Deploys Kafka Cluster (Priority: P1) 🎯 MVP

**Goal**: A production-ready Kafka cluster (3 brokers, KRaft) or development cluster (1 broker) deployable via a single Helm command.

**Independent Test**: `helm install musematic-kafka deploy/helm/kafka -n platform-data -f values.yaml -f values-prod.yaml` completes without error; `kubectl wait kafka/musematic-kafka --for=condition=Ready -n platform-data` succeeds; all broker pods report ready status.

- [X] T006 [US1] Create `deploy/helm/kafka/Chart.yaml` with `apiVersion: v2`, `name: musematic-kafka`, `version: 0.1.0`, `description: Strimzi Kafka cluster for Musematic platform` — **no `dependencies` block** (Strimzi operator is a cluster prerequisite, not a chart sub-dependency)
- [X] T007 [P] [US1] Create `deploy/helm/kafka/values.yaml` with shared defaults: `clusterName: musematic-kafka`, `namespace: platform-data`, `kafkaVersion: "3.7.0"`, `metadataVersion: "3.7-IV4"`, `replicationFactor: 3`, `minInsyncReplicas: 2`, `logRetentionMs: 604800000`, empty `topics: []` list (filled in US2), `dlqRetentionMs: 2592000000`, `dlqPartitions: 6`, `metricsPort: 9404`
- [X] T008 [P] [US1] Create `deploy/helm/kafka/values-prod.yaml` with production overrides: `brokerReplicas: 3`, `controllerReplicas: 3`, `storage.size: 100Gi`, `storage.class: standard`, `resources.requests.memory: 4Gi`, `resources.requests.cpu: "1"`, `networkPolicy.enabled: true`
- [X] T009 [P] [US1] Create `deploy/helm/kafka/values-dev.yaml` with development overrides: `combined: true` (single combined KRaft node), `combinedReplicas: 1`, `replicationFactor: 1`, `minInsyncReplicas: 1`, `storage.size: 5Gi`, `networkPolicy.enabled: false`
- [X] T010 [US1] Create `deploy/helm/kafka/templates/kafka.yaml` — `Kafka` CR (`kafka.strimzi.io/v1beta2`): `spec.kafka.version` from values, `spec.kafka.metadataVersion`, `spec.kafka.listeners` (plain on port 9092, internal on 9091), `spec.kafka.config` including `auto.create.topics.enable: "false"`, `offsets.topic.replication.factor`, `transaction.state.log.replication.factor`, `min.insync.replicas`; `spec.kafka.metricsConfig` enabling JMX Prometheus exporter on port 9404; omit `spec.zookeeper` entirely
- [X] T011 [P] [US1] Create `deploy/helm/kafka/templates/kafka-node-pool-broker.yaml` — `KafkaNodePool` CR with `roles: [broker]`, `replicas: {{ .Values.brokerReplicas }}`, persistent storage from values, wrapped in `{{- if not .Values.combined }}`
- [X] T012 [P] [US1] Create `deploy/helm/kafka/templates/kafka-node-pool-controller.yaml` — `KafkaNodePool` CR with `roles: [controller]`, `replicas: {{ .Values.controllerReplicas }}`, persistent storage, wrapped in `{{- if not .Values.combined }}`
- [X] T013 [P] [US1] Create `deploy/helm/kafka/templates/kafka-node-pool-combined.yaml` — `KafkaNodePool` CR with `roles: [broker, controller]`, `replicas: {{ .Values.combinedReplicas }}`, persistent storage, wrapped in `{{- if .Values.combined }}`

**Checkpoint**: `helm lint deploy/helm/kafka` passes; cluster CR and node pool CRs render correctly for both prod and dev values.

---

## Phase 4: User Story 2 — Platform Creates All Required Topics (Priority: P1)

**Goal**: All 19 domain topics + 19 DLQ topics (38 total) provisioned as `KafkaTopic` CRs after a single Helm deployment.

**Independent Test**: After deploying the chart, `kubectl get kafkatopic -n platform-data | wc -l` returns 38 (plus header = 39); `kubectl get kafkatopic workflow.runtime -n platform-data -o jsonpath='{.spec.partitions}'` returns 12.

- [X] T014 [US2] Add all 19 topics to the `topics` list in `deploy/helm/kafka/values.yaml` — each entry has `name`, `partitions`, and `retentionMs` per the data-model.md Topic Registry table (interaction.events/12/604800000, workflow.runtime/12/604800000, runtime.lifecycle/6/259200000, runtime.reasoning/12/604800000, runtime.selfcorrection/12/604800000, sandbox.events/6/259200000, workspace.goal/6/604800000, connector.ingress/12/259200000, connector.delivery/12/259200000, monitor.alerts/6/1209600000, trust.events/6/2592000000, evaluation.events/6/2592000000, context.quality/6/604800000, fleet.health/6/604800000, agentops.behavioral/6/2592000000, simulation.events/6/259200000, testing.results/6/2592000000, communication.broadcast/6/259200000, interaction.attention/6/604800000)
- [X] T015 [US2] Create `deploy/helm/kafka/templates/kafka-topics.yaml` — iterates `{{ range .Values.topics }}` to emit one `KafkaTopic` CR per topic: `apiVersion: kafka.strimzi.io/v1beta2`, `kind: KafkaTopic`, `metadata.labels` including `strimzi.io/cluster: {{ $.Values.clusterName }}`, `spec.partitions: {{ .partitions }}`, `spec.replicas: {{ $.Values.replicationFactor }}`, `spec.config.retention.ms: "{{ .retentionMs }}"`, `spec.config.min.insync.replicas: "{{ $.Values.minInsyncReplicas }}"`
- [X] T016 [US2] Create `deploy/helm/kafka/templates/kafka-dlq-topics.yaml` — iterates `{{ range .Values.topics }}` to emit one `.dlq` `KafkaTopic` CR per topic: name `{{ .name }}.dlq`, `spec.partitions: {{ $.Values.dlqPartitions }}`, `spec.replicas: {{ $.Values.replicationFactor }}`, `spec.config.retention.ms: "{{ $.Values.dlqRetentionMs }}"`

**Checkpoint**: `helm template deploy/helm/kafka -f values.yaml -f values-prod.yaml | grep "kind: KafkaTopic" | wc -l` outputs 38.

---

## Phase 5: User Story 3 — Services Produce and Consume Events Reliably (Priority: P1)

**Goal**: Python services can produce to and consume from any topic with durable commits, ordering guarantees, and consumer group offset tracking.

**Independent Test**: Port-forward bootstrap to localhost:9092; run the Python quickstart (section 5) — produce an envelope to `workflow.runtime` with `partition_key="exec-qs-001"`, consume it back, verify `event_id` and `event_type` match; restart consumer, verify it resumes from committed offset without re-reading the message.

- [X] T017 [US3] Implement `AsyncKafkaProducer` in `apps/control-plane/src/platform/common/events/producer.py` using `aiokafka.AIOKafkaProducer` — constructor accepts `Settings`; `start()` initializes producer with `acks="all"`, `enable_idempotence=True`, `compression_type="lz4"`; `produce(topic, envelope, partition_key)` serializes with `envelope.model_dump_json().encode()`, sets key as `partition_key.encode()` if provided; `stop()` calls `await producer.stop()`; implements `async with` via `__aenter__`/`__aexit__`; raises `KafkaProducerError` on delivery failure
- [X] T018 [US3] Implement `AsyncKafkaConsumer` in `apps/control-plane/src/platform/common/events/consumer.py` using `aiokafka.AIOKafkaConsumer` — constructor accepts `Settings`; `subscribe(topics)` stores topic list; `start()` initializes consumer with `group_id`, `enable_auto_commit=False`, `auto_offset_reset="earliest"`; `consume()` is an async generator yielding `(EventEnvelope, commit_callback)` pairs where `commit_callback` calls `await consumer.commit()`; `reset_offset_to_timestamp(topic, timestamp_ms)` calls `seek_to_end` after fetching offsets for the given timestamp via `consumer.offsets_for_times()`; implements `async with`; defines `CommitCallback = Callable[[], Awaitable[None]]` type alias
- [X] T019 [P] [US3] Add `KafkaProducerError` and `KafkaConsumerError` exception classes to `apps/control-plane/src/platform/common/exceptions.py`
- [X] T020 [US3] Write integration test `apps/control-plane/tests/integration/test_kafka_producer_consumer.py` — uses `testcontainers` Kafka container (or `KAFKA_TEST_MODE` env var pointing to running broker); tests: (1) produce 10 messages with same `partition_key`, consume all, assert ordering preserved; (2) consume 5, commit, restart consumer, assert it starts from offset 5 not 0; (3) verify `EventEnvelope` round-trips correctly (serialize → produce → consume → deserialize → fields match)

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_kafka_producer_consumer.py -v` passes all 3 test cases.

---

## Phase 6: User Story 4 — Operator Replays Events from a Point in Time (Priority: P2)

**Goal**: An operator can reset a consumer group's offset to a specific timestamp and re-consume events from that point forward.

**Independent Test**: Produce 20 messages over 10 seconds, consume all and commit. Reset offset to timestamp at message 10. Re-consume and verify exactly 10 messages are delivered (messages 11–20), in order, with no duplicates.

- [X] T021 [US4] Verify `reset_offset_to_timestamp(topic, timestamp_ms)` in `consumer.py` (implemented in T018) correctly handles the case where all partitions have been consumed past the target timestamp — it must seek each partition to the first offset at or after `timestamp_ms`, or to the beginning if the timestamp predates all retained messages; add a comment with the Kafka `offsets_for_times` API details
- [X] T022 [US4] Write integration test `apps/control-plane/tests/integration/test_kafka_replay.py` — produce 20 messages, record the timestamp after message 10, consume and commit all 20, call `reset_offset_to_timestamp(topic, mid_timestamp_ms)`, re-consume and assert: (1) exactly 10 messages received, (2) messages are in order, (3) no duplicates (all event_ids unique and match second half of produced set)

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_kafka_replay.py -v` passes.

---

## Phase 7: User Story 5 — Failed Events Route to Dead-Letter Queues (Priority: P2)

**Goal**: Messages that fail processing 3 times are routed to the corresponding `.dlq` topic with full error metadata within 30 seconds of the third failure.

**Independent Test**: Produce one message to `workflow.runtime`. Wire a consumer with a processor that always raises `ValueError("simulated failure")`. After `RetryHandler` exhausts 3 attempts, assert a message appears in `workflow.runtime.dlq` with `original_envelope`, `retry_attempts` list of length 3, and `error_class == "ValueError"`.

- [X] T023 [US5] Implement `RetryHandler` in `apps/control-plane/src/platform/common/events/retry.py` — constructor accepts `producer: AsyncKafkaProducer`, `max_attempts: int = 3`, `backoff_base_ms: int = 500`; `handle(envelope, source_topic, source_partition, source_offset, processor, commit_fn)` coroutine: tries `await processor(envelope)` up to `max_attempts` times with exponential backoff (`backoff_base_ms * 2^attempt` ms delay); on each failure appends `{attempt, timestamp, error}` to `retry_attempts` list; after exhausting retries, produces a DLQ `EventEnvelope` to `{source_topic}.dlq` with `event_type="dlq.FailedMessage"`, `payload` containing `original_envelope` (full envelope dict), `source_topic`, `source_partition`, `source_offset`, `error_class`, `error_message`, `retry_attempts`; always calls `commit_fn()` after DLQ produce (message is done)
- [X] T024 [US5] Write integration test `apps/control-plane/tests/integration/test_kafka_dlq.py` — (1) test that a processor raising an exception 3 times results in a DLQ message with all required payload fields; (2) test that a processor succeeding on the second attempt does NOT produce a DLQ message; (3) test that the DLQ message `payload.retry_attempts` has the correct length and error messages; (4) test that offset is committed after DLQ routing (consumer does not re-receive the message after restart)

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_kafka_dlq.py -v` passes all 4 test cases.

---

## Phase 8: User Story 6 — Network Access Is Restricted to Authorized Namespaces (Priority: P2)

**Goal**: Only services in `platform-control` and `platform-execution` can connect to Kafka brokers. All other namespaces are blocked.

**Independent Test**: Deploy with `networkPolicy.enabled: true`; `kubectl run` a test pod in `platform-control` namespace and confirm `kafka-topics.sh --list` succeeds; `kubectl run` a test pod in `default` namespace and confirm the connection times out.

- [X] T025 [US6] Create `deploy/helm/kafka/templates/network-policy.yaml` — three `NetworkPolicy` resources wrapped in `{{- if .Values.networkPolicy.enabled }}`:
  (1) **intra-cluster**: `podSelector: {matchLabels: {strimzi.io/cluster: musematic-kafka}}` allows ingress from same selector on ports 9090 (KRaft quorum) and 9091 (inter-broker replication);
  (2) **client-access**: same `podSelector` allows ingress on port 9092 from `namespaceSelector` matching `kubernetes.io/metadata.name: platform-control` OR `platform-execution` (two separate `from` entries with `namespaceSelector`);
  (3) **metrics**: same `podSelector` allows ingress on port 9404 from `namespaceSelector` matching `kubernetes.io/metadata.name: platform-observability`

**Checkpoint**: `helm template deploy/helm/kafka -f values.yaml -f values-prod.yaml | grep "kind: NetworkPolicy" | wc -l` outputs 3; `helm template ... -f values-dev.yaml | grep "kind: NetworkPolicy"` outputs nothing.

---

## Phase 9: User Story 7 — Attention Signals Are Routed Separately from System Alerts (Priority: P2)

**Goal**: `interaction.attention` topic exists as a distinct channel from `monitor.alerts`; attention events and system alerts cannot be cross-consumed.

**Independent Test**: Publish one message to `interaction.attention` and one to `monitor.alerts`; confirm a consumer subscribed only to `interaction.attention` receives exactly 1 message and 0 messages appear from `monitor.alerts`; confirm the reverse.

- [X] T026 [US7] Verify `interaction.attention` is present in `deploy/helm/kafka/values.yaml` topic list (added in T014) with `partitions: 6` and `retentionMs: 604800000`; add a comment in values.yaml above this entry: `# Attention pattern — agent-initiated urgency signals (see constitution AD-3.13); distinct from monitor.alerts`
- [X] T027 [US7] Write integration test `apps/control-plane/tests/integration/test_kafka_attention.py` — (1) produce an `AttentionRequest`-shaped envelope to `interaction.attention` (partition_key=`target_id`), verify consumer subscribed to `interaction.attention` receives it; (2) produce a system alert envelope to `monitor.alerts`, verify consumer subscribed to `interaction.attention` does NOT receive it (timeout after 2s); (3) verify the reverse — `monitor.alerts` consumer does not receive attention events

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_kafka_attention.py -v` passes all 3 scenarios.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Go producer, quality gates, health check, CI integration.

- [X] T028 [P] Create `services/reasoning-engine/internal/events/producer.go` — Go `KafkaProducer` struct using `confluent-kafka-go/v2`; `NewKafkaProducer(bootstrapServers string) (*KafkaProducer, error)` constructor; `Produce(ctx context.Context, topic string, key string, valueJSON []byte) error` method that wraps `confluent-kafka-go` `Producer.Produce()` with delivery channel; `Close()` flushes and closes the producer; configured with `acks=all`, `enable.idempotence=true`
- [X] T029 [P] Create `services/reasoning-engine/internal/events/producer_test.go` — unit tests using `confluent-kafka-go` mock producer; tests: (1) `NewKafkaProducer` returns error on invalid bootstrap servers; (2) `Produce` encodes key and value correctly; (3) `Close` flushes pending messages
- [ ] T030 [P] Run `helm lint deploy/helm/kafka` and fix any linting errors — confirm no wildcard versions, no missing required fields, no stale template placeholders
- [X] T031 [P] Run `ruff check apps/control-plane/src/platform/common/events/` and fix any linting violations in envelope.py, producer.py, consumer.py, retry.py
- [X] T032 [P] Run `mypy apps/control-plane/src/platform/common/events/` in strict mode and fix any type errors
- [X] T033 Add Kafka broker connectivity + topic existence check to platform-cli health diagnostics — in `apps/control-plane/src/platform/common/events/producer.py`, add `async def health_check(settings: Settings) -> dict` that connects, lists topics (expecting ≥ 38), and returns `{"status": "ok", "topic_count": N}` or `{"status": "error", "error": msg}`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **blocks all user stories**
- **US1 (Phase 3)**: Depends on Foundational — Helm only, no Python dependency
- **US2 (Phase 4)**: Depends on US1 (topics need a cluster to deploy to)
- **US3 (Phase 5)**: Depends on Foundational (envelope + config) and US2 (topics must exist)
- **US4 (Phase 6)**: Depends on US3 (replay requires working consumer)
- **US5 (Phase 7)**: Depends on US3 (DLQ routing requires working producer + consumer)
- **US6 (Phase 8)**: Depends on US1 (network policy is part of the cluster Helm chart)
- **US7 (Phase 9)**: Depends on US2 (attention topic is in the topic list) and US3 (produce/consume needed to verify)
- **Polish (Phase 10)**: Depends on all phases complete

### User Story Dependencies

```
Phase 1 (Setup)
    └── Phase 2 (Foundational: Envelope + Config)
            ├── Phase 3 (US1: Cluster)
            │       ├── Phase 4 (US2: Topics)
            │       │       ├── Phase 5 (US3: Produce/Consume)
            │       │       │       ├── Phase 6 (US4: Replay)
            │       │       │       ├── Phase 7 (US5: DLQ)
            │       │       │       └── Phase 9 (US7: Attention)
            │       └── Phase 8 (US6: Network Policy)
            └── Phase 10 (Polish)
```

### Parallel Opportunities

Within each phase, tasks marked [P] can run simultaneously:
- **Phase 3 (US1)**: T007, T008, T009 (values files) run in parallel; T011, T012, T013 (node pool CRs) run in parallel after T010 is drafted
- **Phase 10 (Polish)**: T028, T029, T030, T031, T032 all run in parallel

---

## Parallel Example: Phase 3 (US1 — Cluster)

```
# Parallel group 1 — values files:
Task T007: Create values.yaml (shared defaults)
Task T008: Create values-prod.yaml (production overrides)
Task T009: Create values-dev.yaml (development overrides)

# Sequential: T010 (Kafka CR) must come before node pools (references CR name)

# Parallel group 2 — node pool CRs (after T010):
Task T011: kafka-node-pool-broker.yaml
Task T012: kafka-node-pool-controller.yaml
Task T013: kafka-node-pool-combined.yaml
```

---

## Implementation Strategy

### MVP (User Stories 1–3 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T005)
3. Complete Phase 3: US1 — Kafka cluster (T006–T013)
4. Complete Phase 4: US2 — Topic provisioning (T014–T016)
5. Complete Phase 5: US3 — Produce/Consume (T017–T020)
6. **STOP and VALIDATE**: All 3 P1 user stories independently testable and deployable

### Incremental Delivery

After MVP:
1. Add US4 (Replay) → 2 tasks → test independently
2. Add US5 (DLQ) → 2 tasks → test independently
3. Add US6 (Network Policy) → 1 task → test independently
4. Add US7 (Attention) → 2 tasks → test independently
5. Polish phase → Go producer, quality gates, health check

---

## Notes

- [P] tasks use different files with no dependencies on incomplete tasks
- [Story] label maps each task to its user story for traceability
- `helm lint` must pass before any cluster deployment attempt
- Integration tests require either a running Kafka cluster or `testcontainers` Kafka image
- Topic names in Helm values must exactly match the topic registry in data-model.md
- `auto.create.topics.enable: "false"` is required — topics must be created as KafkaTopic CRs
- Strimzi operator must be pre-installed before `helm install` (see quickstart.md section Prerequisites)
- Go producer (T028) lives in `services/reasoning-engine/` not `apps/` (constitution §3.2)
