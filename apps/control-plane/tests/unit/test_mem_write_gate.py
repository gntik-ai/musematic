from __future__ import annotations

from platform.memory.exceptions import (
    MemoryError as MemoryDomainError,
)
from platform.memory.exceptions import (
    WriteGateAuthError,
    WriteGateRateLimitError,
    WriteGateRetentionError,
)
from platform.memory.models import MemoryScope, RetentionPolicy
from platform.memory.schemas import MemoryWriteRequest
from platform.memory.write_gate import MemoryWriteGate
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer
from tests.memory_support import (
    MemoryRepoStub,
    QdrantStub,
    RateLimitResult,
    RedisRateLimitStub,
    RegistryServiceStub,
    WorkspacesServiceStub,
    build_memory_entry,
    build_settings,
    install_qdrant_models_stub,
)


def _build_gate(
    *,
    repo: MemoryRepoStub | None = None,
    qdrant: QdrantStub | None = None,
    redis_client: RedisRateLimitStub | None = None,
    registry_service: RegistryServiceStub | None = None,
    workspaces_service: WorkspacesServiceStub | None = None,
    producer: RecordingProducer | None = None,
    settings_overrides: dict[str, object] | None = None,
) -> tuple[MemoryWriteGate, MemoryRepoStub, QdrantStub, RecordingProducer]:
    memory_repo = repo or MemoryRepoStub()
    qdrant_client = qdrant or QdrantStub()
    producer_client = producer or RecordingProducer()
    gate = MemoryWriteGate(
        repository=memory_repo,
        qdrant=qdrant_client,
        redis_client=redis_client or RedisRateLimitStub(),
        settings=build_settings(**(settings_overrides or {})),
        registry_service=registry_service or RegistryServiceStub(),
        workspaces_service=workspaces_service or WorkspacesServiceStub(),
        producer=producer_client,
    )
    return gate, memory_repo, qdrant_client, producer_client


@pytest.mark.asyncio
async def test_memory_write_gate_persists_entry_vector_and_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate, repo, qdrant, producer = _build_gate()
    workspace_id = uuid4()
    install_qdrant_models_stub(monkeypatch)

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model
        return [0.1, 0.2, float(len(content))]

    monkeypatch.setattr("platform.memory.write_gate.request_embedding", _fake_embedding)

    result = await gate.validate_and_write(
        request=MemoryWriteRequest(
            content="ACME prefers NET-30.",
            scope=MemoryScope.per_agent,
            namespace="finance",
            source_authority=0.9,
            retention_policy=RetentionPolicy.permanent,
            tags=["customer"],
        ),
        agent_fqn="finance:writer",
        workspace_id=workspace_id,
    )

    created = repo.memory_entries[result.memory_entry_id]
    assert created.workspace_id == workspace_id
    assert qdrant.upserts[0][0] == "platform_memory"
    assert producer.events[0]["event_type"] == "memory.written"
    assert result.contradiction_detected is False


@pytest.mark.asyncio
async def test_memory_write_gate_rejects_unauthorized_agent() -> None:
    gate, _, _, _ = _build_gate(
        registry_service=RegistryServiceStub(profile_namespace="other"),
    )

    with pytest.raises(WriteGateAuthError):
        await gate.validate_and_write(
            request=MemoryWriteRequest(
                content="ACME prefers NET-30.",
                scope=MemoryScope.per_agent,
                namespace="finance",
                source_authority=0.9,
                retention_policy=RetentionPolicy.permanent,
            ),
            agent_fqn="finance:writer",
            workspace_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_memory_write_gate_enforces_rate_limit_and_retention() -> None:
    rate_limiter = RedisRateLimitStub(
        results=[
            RateLimitResult(allowed=False, remaining=0, retry_after_ms=5_000),
            RateLimitResult(allowed=True, remaining=100, retry_after_ms=0),
        ]
    )
    gate, _, _, _ = _build_gate(redis_client=rate_limiter)

    with pytest.raises(WriteGateRateLimitError):
        await gate.validate_and_write(
            request=MemoryWriteRequest(
                content="ACME prefers NET-30.",
                scope=MemoryScope.per_agent,
                namespace="finance",
                source_authority=0.9,
                retention_policy=RetentionPolicy.permanent,
            ),
            agent_fqn="finance:writer",
            workspace_id=uuid4(),
        )

    with pytest.raises(WriteGateRetentionError):
        gate._validate_retention(RetentionPolicy.session_only, MemoryScope.per_agent, None, None)


@pytest.mark.asyncio
async def test_memory_write_gate_flags_contradictions_and_applies_privacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = MemoryRepoStub()
    workspace_id = uuid4()
    install_qdrant_models_stub(monkeypatch)
    existing = build_memory_entry(
        workspace_id=workspace_id,
        content="Customer ACME prefers invoice terms NET-30.",
    )
    repo.memory_entries[existing.id] = existing
    qdrant = QdrantStub(
        search_results=[
            {
                "id": str(existing.id),
                "score": 0.99,
                "payload": {"memory_entry_id": str(existing.id)},
            }
        ]
    )
    gate, _, _, producer = _build_gate(
        repo=repo,
        qdrant=qdrant,
        settings_overrides={
            "MEMORY_DIFFERENTIAL_PRIVACY_ENABLED": True,
            "MEMORY_DIFFERENTIAL_PRIVACY_EPSILON": 0.5,
        },
    )
    monkeypatch.setattr(gate, "_laplace_noise", lambda scale: -30.0)

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model, content
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("platform.memory.write_gate.request_embedding", _fake_embedding)

    result = await gate.validate_and_write(
        request=MemoryWriteRequest(
            content="Customer ACME prefers invoice terms NET-60 and spends 100.",
            scope=MemoryScope.per_agent,
            namespace="finance",
            source_authority=0.7,
            retention_policy=RetentionPolicy.permanent,
            tags=["customer"],
        ),
        agent_fqn="finance:writer",
        workspace_id=workspace_id,
    )

    assert result.contradiction_detected is True
    assert result.conflict_id is not None
    assert result.privacy_applied is True
    assert any(event["event_type"] == "memory.conflict.detected" for event in producer.events)


@pytest.mark.asyncio
async def test_memory_write_gate_queues_embedding_job_or_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate, repo, _, _ = _build_gate()
    install_qdrant_models_stub(monkeypatch)

    async def _fail_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model, content
        raise RuntimeError("embedding unavailable")

    monkeypatch.setattr("platform.memory.write_gate.request_embedding", _fail_embedding)

    result = await gate.validate_and_write(
        request=MemoryWriteRequest(
            content="Remember this later.",
            scope=MemoryScope.per_agent,
            namespace="finance",
            source_authority=0.6,
            retention_policy=RetentionPolicy.permanent,
        ),
        agent_fqn="finance:writer",
        workspace_id=uuid4(),
    )

    assert repo.embedding_jobs
    assert repo.memory_entries[result.memory_entry_id].embedding_status.value == "pending"

    gate, repo, _, _ = _build_gate(qdrant=QdrantStub(fail_upsert=RuntimeError("qdrant down")))

    async def _ok_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model, content
        return [0.3, 0.2, 0.1]

    monkeypatch.setattr("platform.memory.write_gate.request_embedding", _ok_embedding)

    with pytest.raises(MemoryDomainError):
        await gate.validate_and_write(
            request=MemoryWriteRequest(
                content="Remember this later.",
                scope=MemoryScope.per_agent,
                namespace="finance",
                source_authority=0.6,
                retention_policy=RetentionPolicy.permanent,
            ),
            agent_fqn="finance:writer",
            workspace_id=uuid4(),
        )

    assert any(entry.deleted_at is not None for entry in repo.memory_entries.values())
