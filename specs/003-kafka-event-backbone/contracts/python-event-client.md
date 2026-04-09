# Contract: Python Event Client

**Feature**: 003-kafka-event-backbone  
**Type**: Python Internal Interface Contract  
**Date**: 2026-04-09  
**Location**: `apps/control-plane/src/platform/common/events/`

---

## AsyncKafkaProducer

```python
class AsyncKafkaProducer:
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def produce(
        self,
        topic: str,
        envelope: EventEnvelope,
        *,
        partition_key: str | None = None,
    ) -> None:
        """
        Serialize envelope to JSON and produce to `topic`.

        Args:
            topic: Target topic name (must exist in registry).
            envelope: Fully constructed EventEnvelope (caller sets event_id, occurred_at).
            partition_key: String key for partition routing. None → round-robin.

        Raises:
            KafkaProducerError: On delivery failure after internal retries.
        """

    async def __aenter__(self) -> "AsyncKafkaProducer": ...
    async def __aexit__(self, *args: Any) -> None: ...
```

**Configuration** (from `platform.common.config.Settings`):
- `KAFKA_BOOTSTRAP_SERVERS`: comma-separated broker list
- Producer is initialized with `acks=all`, `enable.idempotence=true`, `compression_type=lz4`

---

## AsyncKafkaConsumer

```python
class AsyncKafkaConsumer:
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    def subscribe(self, topics: list[str]) -> None:
        """Subscribe to one or more topics. Must be called before start()."""

    async def consume(self) -> AsyncIterator[tuple[EventEnvelope, CommitCallback]]:
        """
        Yield (envelope, commit_fn) pairs.

        The caller MUST call commit_fn() after successful processing.
        Do NOT call commit_fn() on failure — let RetryHandler manage it.

        Raises:
            KafkaConsumerError: On unrecoverable consumer errors.
        """

    async def reset_offset_to_timestamp(self, topic: str, timestamp_ms: int) -> None:
        """
        Reset all partitions of `topic` for this consumer group to the
        first offset at or after `timestamp_ms` (Unix ms). Enables replay (FR-008).
        """

    async def __aenter__(self) -> "AsyncKafkaConsumer": ...
    async def __aexit__(self, *args: Any) -> None: ...
```

**Configuration**:
- `KAFKA_BOOTSTRAP_SERVERS`
- `KAFKA_CONSUMER_GROUP_ID`: consumer group name (must be set per service)
- Consumer uses `enable.auto.commit=false`, `auto.offset.reset=earliest`

---

## RetryHandler

```python
class RetryHandler:
    def __init__(
        self,
        producer: AsyncKafkaProducer,
        max_attempts: int = 3,
        backoff_base_ms: int = 500,
    ) -> None: ...

    async def handle(
        self,
        envelope: EventEnvelope,
        source_topic: str,
        source_partition: int,
        source_offset: int,
        processor: Callable[[EventEnvelope], Awaitable[None]],
        commit_fn: Callable[[], Awaitable[None]],
    ) -> None:
        """
        Call processor(envelope). On exception, retry up to max_attempts times
        with exponential backoff. After exhausting retries, produce to
        `{source_topic}.dlq` and commit offset (message is "done").

        DLQ message payload includes: original_envelope, source_topic,
        source_partition, source_offset, error_class, error_message, retry_attempts.
        """
```

---

## EventEnvelope

```python
class CorrelationContext(BaseModel):
    model_config = ConfigDict(frozen=True)
    workspace_id: str | None = None
    execution_id: str | None = None
    interaction_id: str | None = None
    fleet_id: str | None = None
    goal_id: str | None = None
    trace_id: str | None = None

class EventEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: UUID
    event_type: str
    schema_version: str
    occurred_at: datetime
    actor: str
    correlation: CorrelationContext
    payload: dict[str, Any]
```

**Factory helper** (in `envelope.py`):

```python
def make_envelope(
    event_type: str,
    actor: str,
    payload: dict[str, Any],
    correlation: CorrelationContext | None = None,
    schema_version: str = "1.0.0",
) -> EventEnvelope:
    """Create an EventEnvelope with auto-generated event_id and occurred_at."""
```

---

## Exceptions

```python
class KafkaProducerError(Exception): ...
class KafkaConsumerError(Exception): ...
```

---

## Usage Pattern

```python
async with AsyncKafkaProducer(settings) as producer:
    envelope = make_envelope(
        event_type="workflow.runtime.StepStarted",
        actor="control-plane:scheduler",
        payload={"execution_id": "exec-123", "step": "load-data"},
        correlation=CorrelationContext(execution_id="exec-123"),
    )
    await producer.produce("workflow.runtime", envelope, partition_key="exec-123")
```

```python
async with AsyncKafkaConsumer(settings) as consumer:
    consumer.subscribe(["workflow.runtime"])
    retry = RetryHandler(producer, max_attempts=3)
    async for envelope, commit_fn in consumer.consume():
        await retry.handle(
            envelope, "workflow.runtime", partition, offset,
            processor=my_handler,
            commit_fn=commit_fn,
        )
```
