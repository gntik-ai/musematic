from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from platform.accounts.models import SignupSource, User, UserStatus
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.config import PlatformSettings, Settings
from platform.common.models.user import User as PlatformUser
from uuid import UUID, uuid4

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.accounts_support import NoopClient, issue_access_token
from tests.auth_support import RecordingProducer, role_claim


@dataclass(slots=True)
class RegistryBackends:
    producer: RecordingProducer
    object_storage: AsyncObjectStorageClient
    opensearch: AsyncOpenSearchClient
    qdrant: AsyncQdrantClient


def redis_url(redis_client: object) -> str:
    return getattr(redis_client, "_url", None) or "redis://localhost:6379"


def build_registry_settings(
    auth_settings: PlatformSettings,
    *,
    database_url: str,
    redis_client: object,
    object_storage_settings: Settings,
    opensearch_settings: Settings,
    qdrant_settings: Settings,
    package_size_limit_mb: int = 50,
) -> PlatformSettings:
    return auth_settings.model_copy(
        update={
            "db": auth_settings.db.model_copy(update={"dsn": database_url}),
            "redis": auth_settings.redis.model_copy(
                update={"url": redis_url(redis_client), "test_mode": "standalone"}
            ),
            "minio": object_storage_settings.minio,
            "opensearch": opensearch_settings.opensearch,
            "qdrant": qdrant_settings.qdrant,
            "registry": auth_settings.registry.model_copy(
                update={
                    "package_size_limit_mb": package_size_limit_mb,
                    "embedding_api_url": "http://127.0.0.1:9/v1/embeddings",
                }
            ),
        }
    )


def build_registry_backends(
    *,
    object_storage_settings: Settings,
    opensearch_settings: Settings,
    qdrant_settings: Settings,
    producer: RecordingProducer | None = None,
) -> RegistryBackends:
    return RegistryBackends(
        producer=producer or RecordingProducer(),
        object_storage=AsyncObjectStorageClient(object_storage_settings),
        opensearch=AsyncOpenSearchClient.from_settings(opensearch_settings),
        qdrant=AsyncQdrantClient(qdrant_settings),
    )


def build_registry_clients(
    *,
    redis_client: object,
    backends: RegistryBackends,
) -> dict[str, object]:
    noop = NoopClient()
    return {
        "redis": redis_client,
        "kafka": backends.producer,
        "kafka_consumer": noop,
        "qdrant": backends.qdrant,
        "neo4j": noop,
        "clickhouse": noop,
        "opensearch": backends.opensearch,
        "minio": backends.object_storage,
        "runtime_controller": noop,
        "reasoning_engine": noop,
        "sandbox_manager": noop,
        "simulation_controller": noop,
    }


async def seed_registry_user(
    session_factory: async_sessionmaker,
    *,
    user_id: UUID,
    email: str,
    display_name: str,
    max_workspaces: int = 0,
) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add(
            User(
                id=user_id,
                email=email,
                display_name=display_name,
                status=UserStatus.active,
                signup_source=SignupSource.self_registration,
                email_verified_at=now,
                activated_at=now,
                created_at=now,
                updated_at=now,
                max_workspaces=max_workspaces,
            )
        )
        session.add(
            PlatformUser(
                id=user_id,
                email=email,
                display_name=display_name,
                status="active",
            )
        )
        await session.commit()


def human_token(settings: PlatformSettings, user_id: UUID, role: str = "workspace_admin") -> str:
    return issue_access_token(settings, user_id, [role_claim(role)])


def agent_token(settings: PlatformSettings, agent_profile_id: UUID) -> str:
    return issue_access_token(
        settings,
        uuid4(),
        [],
        extra_claims={"agent_profile_id": str(agent_profile_id)},
    )


def auth_headers(token: str, workspace_id: UUID | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if workspace_id is not None:
        headers["X-Workspace-ID"] = str(workspace_id)
    return headers


async def create_workspace(
    client: httpx.AsyncClient,
    token: str,
    *,
    name: str,
    description: str | None = None,
) -> UUID:
    response = await client.post(
        "/api/v1/workspaces",
        headers=auth_headers(token),
        json={"name": name, "description": description},
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def create_namespace(
    client: httpx.AsyncClient,
    token: str,
    workspace_id: UUID,
    *,
    name: str,
    description: str | None = None,
) -> httpx.Response:
    return await client.post(
        "/api/v1/namespaces",
        headers=auth_headers(token, workspace_id),
        json={"name": name, "description": description},
    )


async def upload_package(
    client: httpx.AsyncClient,
    token: str,
    workspace_id: UUID,
    *,
    namespace_name: str,
    package_bytes: bytes,
    filename: str = "package.tar.gz",
) -> httpx.Response:
    return await client.post(
        "/api/v1/agents/upload",
        headers=auth_headers(token, workspace_id),
        data={"namespace_name": namespace_name},
        files={"package": (filename, package_bytes, "application/gzip")},
    )


async def transition_agent(
    client: httpx.AsyncClient,
    token: str,
    workspace_id: UUID,
    agent_id: UUID,
    *,
    target_status: str,
    reason: str | None = None,
) -> httpx.Response:
    return await client.post(
        f"/api/v1/agents/{agent_id}/transition",
        headers=auth_headers(token, workspace_id),
        json={"target_status": target_status, "reason": reason},
    )


async def publish_agent(
    client: httpx.AsyncClient,
    token: str,
    workspace_id: UUID,
    agent_id: UUID,
) -> None:
    validated = await transition_agent(
        client,
        token,
        workspace_id,
        agent_id,
        target_status="validated",
    )
    assert validated.status_code == 200, validated.text
    published = await transition_agent(
        client,
        token,
        workspace_id,
        agent_id,
        target_status="published",
    )
    assert published.status_code == 200, published.text


async def refresh_registry_index(
    opensearch: AsyncOpenSearchClient,
    settings: PlatformSettings,
) -> None:
    raw_client = await opensearch._ensure_client()
    await raw_client.indices.refresh(index=settings.registry.search_backing_index)


async def fetch_registry_document(
    opensearch: AsyncOpenSearchClient,
    settings: PlatformSettings,
    *,
    agent_profile_id: UUID,
) -> dict[str, object]:
    raw_client = await opensearch._ensure_client()
    response = await raw_client.get(
        index=settings.registry.search_index,
        id=str(agent_profile_id),
    )
    return dict(response["_source"])
