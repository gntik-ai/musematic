from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.registry import event_registry
from platform.memory.events import (
    ConflictDetectedPayload,
    MemoryEventType,
    MemoryWrittenPayload,
    publish_conflict_detected,
    publish_memory_written,
    register_memory_event_types,
)
from platform.memory.exceptions import (
    ConflictDetectedError,
    GraphUnavailableError,
    MemoryEntryNotFoundError,
    WriteGateRateLimitError,
)
from platform.memory.models import (
    ConflictStatus,
    EmbeddingStatus,
    MemoryScope,
    PatternStatus,
    RetentionPolicy,
)
from platform.memory.schemas import (
    ConflictResolution,
    GraphTraversalQuery,
    KnowledgeEdgeCreate,
    MemoryEntryResponse,
    MemoryWriteRequest,
    PatternReview,
    RetrievalQuery,
)
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer
from tests.memory_support import build_conflict, build_memory_entry


def test_memory_request_schemas_validate_core_rules() -> None:
    request = MemoryWriteRequest(
        content="Remember ACME terms",
        scope=MemoryScope.per_agent,
        namespace="finance",
        retention_policy=RetentionPolicy.time_limited,
        ttl_seconds=60,
    )
    assert request.ttl_seconds == 60

    with pytest.raises(ValueError, match="execution_id is required"):
        MemoryWriteRequest(
            content="Remember ACME terms",
            scope=MemoryScope.per_agent,
            namespace="finance",
            retention_policy=RetentionPolicy.session_only,
        )

    with pytest.raises(ValueError, match="rejection_reason is required"):
        PatternReview(approved=False)

    resolution = ConflictResolution(action="dismiss", resolution_notes="Wrong source")
    graph_query = GraphTraversalQuery(start_node_id=uuid4(), max_hops=3)
    edge = KnowledgeEdgeCreate(
        source_node_id=uuid4(),
        target_node_id=uuid4(),
        relationship_type="supports",
        metadata={"source": "playbook"},
    )
    retrieval = RetrievalQuery(query_text="ACME payment terms", top_k=5)

    assert resolution.action == "dismiss"
    assert graph_query.max_hops == 3
    assert edge.metadata["source"] == "playbook"
    assert retrieval.top_k == 5


def test_memory_response_models_accept_domain_objects() -> None:
    entry = build_memory_entry()
    response = MemoryEntryResponse.model_validate(entry)

    assert response.id == entry.id
    assert response.embedding_status is EmbeddingStatus.pending
    assert response.retention_policy is RetentionPolicy.permanent


@pytest.mark.asyncio
async def test_memory_events_register_and_publish() -> None:
    register_memory_event_types()
    producer = RecordingProducer()
    correlation = CorrelationContext(correlation_id=uuid4(), workspace_id=uuid4())
    payload = MemoryWrittenPayload(
        memory_entry_id=uuid4(),
        workspace_id=uuid4(),
        agent_fqn="finance:writer",
        scope=MemoryScope.per_agent,
        namespace="finance",
        contradiction_detected=False,
    )
    conflict_payload = ConflictDetectedPayload(
        conflict_id=uuid4(),
        workspace_id=payload.workspace_id,
        memory_entry_id_a=uuid4(),
        memory_entry_id_b=uuid4(),
        similarity_score=0.99,
    )

    await publish_memory_written(producer, payload, correlation)
    await publish_conflict_detected(producer, conflict_payload, correlation)

    assert event_registry.is_registered(MemoryEventType.memory_written.value)
    assert producer.events[0]["event_type"] == MemoryEventType.memory_written.value
    assert producer.events[1]["event_type"] == MemoryEventType.conflict_detected.value


def test_memory_exceptions_expose_expected_status_and_details() -> None:
    conflict_id = uuid4()
    entry_id = uuid4()

    rate_limit = WriteGateRateLimitError(12)
    conflict = ConflictDetectedError(conflict_id)
    missing = MemoryEntryNotFoundError(entry_id)
    degraded = GraphUnavailableError()

    assert rate_limit.status_code == 429
    assert rate_limit.retry_after_seconds == 12
    assert conflict.details["conflict_id"] == str(conflict_id)
    assert missing.details["entry_id"] == str(entry_id)
    assert degraded.details["partial_sources"] == ["graph"]


def test_memory_conflict_response_enum_values_are_stable() -> None:
    conflict = build_conflict(status=ConflictStatus.dismissed)
    assert conflict.status is ConflictStatus.dismissed
    assert PatternStatus.pending.value == "pending"
    assert MemoryScope.shared_orchestrator.value == "shared_orchestrator"
    assert datetime.now(UTC).tzinfo is UTC
