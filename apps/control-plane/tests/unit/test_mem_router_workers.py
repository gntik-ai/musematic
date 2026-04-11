from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.auth_middleware import AuthMiddleware
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.memory.consolidation_worker import ConsolidationWorker, SessionMemoryCleaner
from platform.memory.dependencies import build_memory_service, get_memory_service
from platform.memory.embedding_worker import EmbeddingWorker
from platform.memory.memory_setup import setup_memory_collections
from platform.memory.models import EmbeddingJobStatus, RetentionPolicy
from platform.memory.router import router
from platform.memory.write_gate import MemoryWriteGate
from platform.workspaces.models import WorkspaceRole
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from tests.auth_support import RecordingProducer, role_claim
from tests.memory_support import (
    MemoryRepoStub,
    Neo4jStub,
    QdrantStub,
    RedisRateLimitStub,
    RegistryServiceStub,
    RouterMemoryServiceStub,
    WorkspacesServiceStub,
    build_embedding_job,
    build_memory_entry,
    build_settings,
    install_qdrant_models_stub,
)


def _test_settings() -> PlatformSettings:
    return PlatformSettings(AUTH_JWT_SECRET_KEY="memory-router-secret", AUTH_JWT_ALGORITHM="HS256")


def _build_app(service: RouterMemoryServiceStub) -> FastAPI:
    app = FastAPI()
    app.state.settings = _test_settings()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_memory_router_requires_auth_for_real_app() -> None:
    app = FastAPI()
    app.state.settings = _test_settings()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.add_middleware(AuthMiddleware)
    app.dependency_overrides[get_memory_service] = lambda: RouterMemoryServiceStub()
    app.include_router(router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/memory/entries")

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "payload", "expected_status"),
    [
        (
            "post",
            "/api/v1/memory/entries",
            {
                "content": "remember",
                "scope": "per_agent",
                "namespace": "finance",
            },
            201,
        ),
        ("get", f"/api/v1/memory/entries/{uuid4()}", None, 200),
        ("get", "/api/v1/memory/entries", None, 200),
        ("delete", f"/api/v1/memory/entries/{uuid4()}", None, 204),
        (
            "post",
            f"/api/v1/memory/entries/{uuid4()}/transfer",
            {
                "target_scope": "per_workspace",
                "target_namespace": "finance",
            },
            201,
        ),
        ("post", "/api/v1/memory/retrieve", {"query_text": "acme"}, 200),
        ("get", "/api/v1/memory/conflicts", None, 200),
        ("post", f"/api/v1/memory/conflicts/{uuid4()}/resolve", {"action": "dismiss"}, 200),
        (
            "post",
            "/api/v1/memory/trajectories",
            {
                "execution_id": str(uuid4()),
                "agent_fqn": "finance:writer",
                "actions": [],
                "tool_invocations": [],
                "reasoning_snapshots": [],
                "verdicts": [],
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:00:01Z",
            },
            201,
        ),
        ("get", f"/api/v1/memory/trajectories/{uuid4()}", None, 200),
        (
            "post",
            "/api/v1/memory/patterns",
            {"content": "remember", "description": "desc", "tags": []},
            201,
        ),
        ("post", f"/api/v1/memory/patterns/{uuid4()}/review", {"approved": True}, 200),
        ("get", "/api/v1/memory/patterns", None, 200),
        (
            "post",
            "/api/v1/memory/graph/nodes",
            {
                "node_type": "Concept",
                "external_name": "ACME",
                "attributes": {},
            },
            201,
        ),
        (
            "post",
            "/api/v1/memory/graph/edges",
            {
                "source_node_id": str(uuid4()),
                "target_node_id": str(uuid4()),
                "relationship_type": "uses",
                "metadata": {},
            },
            201,
        ),
        (
            "post",
            "/api/v1/memory/graph/traverse",
            {"start_node_id": str(uuid4()), "max_hops": 2},
            200,
        ),
        ("get", f"/api/v1/memory/graph/nodes/{uuid4()}/provenance", None, 200),
    ],
)
@pytest.mark.asyncio
async def test_memory_router_endpoints_delegate(
    method: str,
    path: str,
    payload: dict[str, object] | None,
    expected_status: int,
) -> None:
    service = RouterMemoryServiceStub()
    app = _build_app(service)

    async def _current_user_override() -> dict[str, object]:
        return {
            "sub": str(uuid4()),
            "agent_fqn": "finance:writer",
            "workspace_id": str(uuid4()),
            "roles": [role_claim("workspace_admin", uuid4())],
        }

    async def _service_override() -> RouterMemoryServiceStub:
        return service

    app.dependency_overrides[get_current_user] = _current_user_override
    app.dependency_overrides[get_memory_service] = _service_override

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.request(method.upper(), path, json=payload)

    assert response.status_code == expected_status


@pytest.mark.asyncio
async def test_memory_dependencies_and_setup_wire_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings()
    # memory setup imports qdrant_client.models dynamically
    install_qdrant_models_stub(monkeypatch)
    qdrant = QdrantStub()
    neo4j = Neo4jStub()
    redis_client = RedisRateLimitStub()
    workspaces_service = WorkspacesServiceStub(membership_role=WorkspaceRole.owner)
    registry_service = RegistryServiceStub(role_types=["executor", "orchestrator"])
    service = build_memory_service(
        session=MemoryRepoStub().session,  # type: ignore[arg-type]
        settings=settings,
        qdrant=qdrant,  # type: ignore[arg-type]
        neo4j=neo4j,  # type: ignore[arg-type]
        redis_client=redis_client,  # type: ignore[arg-type]
        producer=RecordingProducer(),  # type: ignore[arg-type]
        workspaces_service=workspaces_service,  # type: ignore[arg-type]
        registry_service=registry_service,  # type: ignore[arg-type]
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={
                    "qdrant": qdrant,
                    "neo4j": neo4j,
                    "redis": redis_client,
                    "kafka": RecordingProducer(),
                },
            )
        )
    )

    resolved = await get_memory_service(
        request,
        session=MemoryRepoStub().session,  # type: ignore[arg-type]
        workspaces_service=workspaces_service,  # type: ignore[arg-type]
        registry_service=registry_service,  # type: ignore[arg-type]
    )
    await setup_memory_collections(qdrant, neo4j, settings)  # type: ignore[arg-type]

    assert service.settings.memory.embedding_dimensions == 1536
    assert resolved.settings.memory.embedding_model == "text-embedding-3-small"
    assert qdrant.collection_calls
    assert len(qdrant.payload_indexes) == 3
    assert neo4j.cypher_calls


@pytest.mark.asyncio
async def test_memory_workers_process_embeddings_consolidation_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    install_qdrant_models_stub(monkeypatch)
    repo = MemoryRepoStub()
    producer = RecordingProducer()
    qdrant = QdrantStub()
    entry = build_memory_entry(workspace_id=workspace_id, content="Cluster memory one")
    repo.memory_entries[entry.id] = entry
    job = build_embedding_job(memory_entry_id=entry.id)
    repo.embedding_jobs[job.id] = job

    async def _fake_embedding(*, api_url: str, model: str, content: str) -> list[float]:
        del api_url, model
        return [0.1, 0.2, float(len(content))]

    monkeypatch.setattr("platform.memory.embedding_worker.request_embedding", _fake_embedding)
    await EmbeddingWorker(repository=repo, qdrant=qdrant, settings=build_settings()).run()

    assert qdrant.upserts
    assert repo.embedding_jobs[job.id].status is not EmbeddingJobStatus.pending

    gate = MemoryWriteGate(
        repository=repo,
        qdrant=qdrant,
        redis_client=RedisRateLimitStub(),
        settings=build_settings(),
        registry_service=RegistryServiceStub(role_types=["executor", "orchestrator"]),
        workspaces_service=WorkspacesServiceStub(membership_role=WorkspaceRole.owner),
        producer=producer,  # type: ignore[arg-type]
    )
    monkeypatch.setattr("platform.memory.write_gate.request_embedding", _fake_embedding)

    for content in ("Cluster memory one", "Cluster memory one!", "Cluster memory one?"):
        seeded = build_memory_entry(workspace_id=workspace_id, content=content)
        repo.memory_entries[seeded.id] = seeded

    await ConsolidationWorker(
        repository=repo,
        write_gate=gate,
        settings=build_settings(),
        producer=producer,  # type: ignore[arg-type]
    ).run()

    expired = build_memory_entry(
        workspace_id=workspace_id,
        retention_policy=RetentionPolicy.session_only,
        ttl_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        qdrant_point_id=uuid4(),
    )
    repo.memory_entries[expired.id] = expired
    await SessionMemoryCleaner(repository=repo, qdrant=qdrant).run()

    assert any(event["event_type"] == "memory.consolidation.completed" for event in producer.events)
    assert any(item.provenance_consolidated_by is not None for item in repo.memory_entries.values())
    assert qdrant.deletes
