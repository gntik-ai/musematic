# Quickstart: Apache Kafka Event Backbone

**Feature**: 003-kafka-event-backbone  
**Date**: 2026-04-09

---

## Prerequisites

- Kubernetes cluster with `kubectl` configured
- `helm` 3.x
- Strimzi operator pre-installed in the target cluster:
  ```bash
  kubectl create namespace platform-data
  kubectl apply -f "https://strimzi.io/install/latest?namespace=platform-data" -n platform-data
  kubectl wait --for=condition=Ready pod -l name=strimzi-cluster-operator -n platform-data --timeout=120s
  ```
- Python 3.12+ with `aiokafka 0.11+` installed:
  ```bash
  pip install aiokafka
  ```
- Install the control-plane package before running Python tests:
  ```bash
  pip install -e ./apps/control-plane
  ```

---

## 1. Deploy Kafka Cluster (Production)

```bash
helm install musematic-kafka deploy/helm/kafka \
  -n platform-data \
  -f deploy/helm/kafka/values.yaml \
  -f deploy/helm/kafka/values-prod.yaml

# Wait for cluster ready (3 brokers + 3 controllers)
kubectl wait kafka/musematic-kafka \
  --for=condition=Ready \
  --timeout=300s \
  -n platform-data

# Verify pods
kubectl get pods -n platform-data -l strimzi.io/cluster=musematic-kafka
# Expected: 3 broker pods + 3 controller pods (or 3 combined KRaft pods depending on config)
```

---

## 2. Deploy Kafka Cluster (Development)

```bash
helm install musematic-kafka deploy/helm/kafka \
  -n platform-data \
  -f deploy/helm/kafka/values.yaml \
  -f deploy/helm/kafka/values-dev.yaml

# Wait for single broker
kubectl wait kafka/musematic-kafka \
  --for=condition=Ready \
  --timeout=120s \
  -n platform-data
```

---

## 3. Verify All Topics Exist

```bash
# Port-forward bootstrap service
kubectl port-forward svc/musematic-kafka-kafka-bootstrap 9092:9092 -n platform-data &

# List all topics (expect 38: 19 domain + 19 DLQ)
kubectl exec -n platform-data \
  $(kubectl get pod -n platform-data -l strimzi.io/name=musematic-kafka-kafka -o jsonpath='{.items[0].metadata.name}') \
  -- bin/kafka-topics.sh --bootstrap-server localhost:9092 --list | wc -l
# Expected: 38

# Verify a specific topic
kubectl exec -n platform-data \
  $(kubectl get pod -n platform-data -l strimzi.io/name=musematic-kafka-kafka -o jsonpath='{.items[0].metadata.name}') \
  -- bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic workflow.runtime
# Expected: PartitionCount: 12, ReplicationFactor: 3, retention.ms: 604800000
```

---

## 4. Test Basic Produce and Consume

```bash
# Produce a test message
kubectl exec -n platform-data \
  $(kubectl get pod -n platform-data -l strimzi.io/name=musematic-kafka-kafka -o jsonpath='{.items[0].metadata.name}') \
  -- bin/kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic interaction.events \
  --property "parse.key=true" \
  --property "key.separator=:" <<EOF
interaction-123:{"event_id":"00000000-0000-0000-0000-000000000001","event_type":"interaction.events.Test","schema_version":"1.0.0","occurred_at":"2026-04-09T00:00:00Z","actor":"test","correlation":{},"payload":{}}
EOF

# Consume and verify
kubectl exec -n platform-data \
  $(kubectl get pod -n platform-data -l strimzi.io/name=musematic-kafka-kafka -o jsonpath='{.items[0].metadata.name}') \
  -- bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic interaction.events \
  --from-beginning \
  --max-messages 1
```

---

## 5. Test Produce/Consume with Python Client

```python
import asyncio
from platform.common.events.envelope import make_envelope, CorrelationContext
from platform.common.events.producer import AsyncKafkaProducer
from platform.common.events.consumer import AsyncKafkaConsumer
from platform.common.config import Settings

settings = Settings(
    KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
    KAFKA_CONSUMER_GROUP_ID="test-group",
)

async def main():
    async with AsyncKafkaProducer(settings) as producer:
        envelope = make_envelope(
            event_type="workflow.runtime.StepStarted",
            actor="test-script",
            payload={"step": "quickstart"},
            correlation=CorrelationContext(execution_id="exec-qs-001"),
        )
        await producer.produce("workflow.runtime", envelope, partition_key="exec-qs-001")
        print(f"Produced: {envelope.event_id}")

    async with AsyncKafkaConsumer(settings) as consumer:
        consumer.subscribe(["workflow.runtime"])
        async for received_envelope, commit_fn in consumer.consume():
            print(f"Consumed: {received_envelope.event_id} ({received_envelope.event_type})")
            await commit_fn()
            break  # read one message

asyncio.run(main())
```

---

## 6. Test Consumer Group Offset Replay

```bash
# Produce several messages with timestamps
# ... (produce 10 messages over a few seconds)

# Reset consumer group to a timestamp (Unix ms)
TIMESTAMP_MS=$(date -d "1 minute ago" +%s%3N)

kubectl exec -n platform-data \
  $(kubectl get pod -n platform-data -l strimzi.io/name=musematic-kafka-kafka -o jsonpath='{.items[0].metadata.name}') \
  -- bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group test-group \
  --topic workflow.runtime \
  --reset-offsets \
  --to-datetime $(date -u -d "@$((TIMESTAMP_MS/1000))" +%Y-%m-%dT%H:%M:%S.000Z) \
  --execute

# Re-consume from that point
```

Via Python client:
```python
async with AsyncKafkaConsumer(settings) as consumer:
    consumer.subscribe(["workflow.runtime"])
    timestamp_ms = int(time.time() * 1000) - 60_000  # 1 minute ago
    await consumer.reset_offset_to_timestamp("workflow.runtime", timestamp_ms)
    # now consume messages from that point forward
```

---

## 7. Test DLQ Routing

```python
async def always_fails(envelope):
    raise ValueError("Simulated processing failure")

async with AsyncKafkaProducer(settings) as producer:
    async with AsyncKafkaConsumer(settings) as consumer:
        consumer.subscribe(["workflow.runtime"])
        retry = RetryHandler(producer, max_attempts=3)
        async for envelope, commit_fn in consumer.consume():
            await retry.handle(
                envelope, "workflow.runtime", 0, 0,
                processor=always_fails,
                commit_fn=commit_fn,
            )
            break

# Verify DLQ received the message
```

```bash
kubectl exec -n platform-data \
  $(kubectl get pod -n platform-data -l strimzi.io/name=musematic-kafka-kafka -o jsonpath='{.items[0].metadata.name}') \
  -- bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic workflow.runtime.dlq \
  --from-beginning \
  --max-messages 1
# Expected: DLQ message with original_envelope, error_class, retry_attempts (3 entries)
```

---

## 8. Verify Broker Failure Tolerance (Production Only)

```bash
# Identify one broker pod
BROKER_POD=$(kubectl get pod -n platform-data -l strimzi.io/name=musematic-kafka-kafka -o jsonpath='{.items[0].metadata.name}')

# Delete it
kubectl delete pod $BROKER_POD -n platform-data

# While deleted, continue producing/consuming in another terminal

# Watch broker rejoin
kubectl get pods -n platform-data -l strimzi.io/cluster=musematic-kafka -w
# Expected: pod recreated, joins cluster, partitions rebalanced automatically
```

---

## 9. Verify Network Policy (Production Only)

```bash
# From authorized namespace (should succeed)
kubectl run -n platform-control --rm -it test-kafka --image=bitnami/kafka:latest --restart=Never -- \
  kafka-topics.sh --bootstrap-server musematic-kafka-kafka-bootstrap.platform-data:9092 --list

# From unauthorized namespace (should timeout/refuse)
kubectl run -n default --rm -it test-kafka --image=bitnami/kafka:latest --restart=Never -- \
  kafka-topics.sh --bootstrap-server musematic-kafka-kafka-bootstrap.platform-data:9092 --list
# Expected: connection refused or timeout
```

---

## 10. Verify Prometheus Metrics

```bash
kubectl port-forward svc/musematic-kafka-kafka-prometheus 9404:9404 -n platform-data &

# Check broker health metric
curl -s http://localhost:9404/metrics | grep kafka_server_replicamanager_leadercount
# Expected: non-zero values per broker

# Check consumer group lag (after some consume activity)
curl -s http://localhost:9404/metrics | grep kafka_consumergroup_lag
```

---

## 11. Run Kafka Integration Tests Locally

```bash
# Requires Docker (testcontainers spins up Kafka)
export KAFKA_TEST_MODE=testcontainers
python -m pytest apps/control-plane/tests/integration/test_kafka_*.py -v
```
