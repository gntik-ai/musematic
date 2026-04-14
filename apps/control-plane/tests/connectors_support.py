from __future__ import annotations

import json
from pathlib import Path
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.connectors.dependencies import build_connectors_service
from platform.connectors.models import (
    ConnectorHealthStatus,
    ConnectorInstance,
    ConnectorInstanceStatus,
    ConnectorRoute,
    ConnectorType,
    DeadLetterEntry,
    DeadLetterResolution,
    DeliveryStatus,
    OutboundDelivery,
)
from platform.connectors.router import router
from platform.connectors.seed import _connector_type_seed_data
from platform.workspaces.models import Workspace
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth_support import RecordingProducer


class NoopClient:
    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def health_check(self) -> bool:
        return True


class ObjectStorageStub:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def create_bucket_if_not_exists(self, bucket: str) -> None:
        self.buckets.add(bucket)

    async def upload_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        del content_type, metadata
        self.buckets.add(bucket)
        self.objects[(bucket, key)] = data


def build_connectors_settings(
    *,
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/test",
    redis_url: str = "redis://localhost:6379",
    vault_file: Path | None = None,
    minio_endpoint: str = "http://localhost:9000",
    minio_access_key: str = "minioadmin",
    minio_secret_key: str = "minioadmin123",
) -> PlatformSettings:
    return PlatformSettings(
        POSTGRES_DSN=database_url,
        REDIS_URL=redis_url,
        REDIS_TEST_MODE="standalone",
        VAULT_MODE="mock",
        VAULT_MOCK_SECRETS_FILE=str(vault_file or Path(".vault-secrets.json")),
        MINIO_ENDPOINT=minio_endpoint,
        MINIO_ACCESS_KEY=minio_access_key,
        MINIO_SECRET_KEY=minio_secret_key,
    )


def write_mock_vault(vault_file: Path, secrets: dict[str, str]) -> None:
    vault_file.write_text(json.dumps(secrets), encoding="utf-8")


async def seed_connector_types(session: AsyncSession) -> None:
    for item in _connector_type_seed_data():
        result = await session.execute(
            select(ConnectorType).where(ConnectorType.slug == item["slug"])
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            session.add(ConnectorType(**item))
        else:
            existing.display_name = str(item["display_name"])
            existing.description = str(item["description"])
            existing.config_schema = dict(item["config_schema"])
            existing.is_deprecated = False
            existing.deprecated_at = None
            existing.deprecation_note = None
    await session.flush()


async def seed_workspace(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    owner_id: UUID,
    name: str = "Connectors",
) -> None:
    session.add(Workspace(id=workspace_id, name=name, owner_id=owner_id))
    await session.flush()


def build_app(
    *,
    settings: PlatformSettings,
    redis_client: object,
    producer: RecordingProducer | None = None,
    object_storage: object | None = None,
) -> FastAPI:
    database.configure_database(settings)
    app = FastAPI()
    app.state.settings = settings
    app.state.clients = {
        "redis": redis_client,
        "kafka": producer or RecordingProducer(),
        "minio": object_storage or ObjectStorageStub(),
    }
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    return app


async def build_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    redis_client: object,
    producer: RecordingProducer | None = None,
    object_storage: object | None = None,
):
    return build_connectors_service(
        session=session,
        settings=settings,
        producer=producer or RecordingProducer(),
        redis_client=redis_client,  # type: ignore[arg-type]
        object_storage=object_storage or ObjectStorageStub(),  # type: ignore[arg-type]
    )


def build_connector_instance(
    *,
    workspace_id: UUID | None = None,
    connector_type: ConnectorType | None = None,
    name: str = "Connector",
    config: dict[str, object] | None = None,
    status: ConnectorInstanceStatus = ConnectorInstanceStatus.enabled,
) -> ConnectorInstance:
    connector_type = connector_type or ConnectorType(
        slug="slack",
        display_name="Slack",
        description="Slack",
        config_schema={},
    )
    item = ConnectorInstance(
        id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        connector_type_id=connector_type.id,
        name=name,
        config_json=config or {},
        status=status,
        health_status=ConnectorHealthStatus.unknown,
    )
    item.connector_type = connector_type
    item.credential_refs = []
    return item


def build_route(
    *,
    workspace_id: UUID | None = None,
    connector_instance_id: UUID | None = None,
    name: str = "Route",
    channel_pattern: str | None = None,
    sender_pattern: str | None = None,
    conditions: dict[str, object] | None = None,
    target_agent_fqn: str | None = "ops:triage",
    priority: int = 100,
    is_enabled: bool = True,
) -> ConnectorRoute:
    route = ConnectorRoute(
        id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        connector_instance_id=connector_instance_id or uuid4(),
        name=name,
        channel_pattern=channel_pattern,
        sender_pattern=sender_pattern,
        conditions_json=conditions or {},
        target_agent_fqn=target_agent_fqn,
        target_workflow_id=None,
        priority=priority,
        is_enabled=is_enabled,
    )
    return route


def build_delivery(
    *,
    workspace_id: UUID | None = None,
    connector_instance_id: UUID | None = None,
    destination: str = "C123",
    status: DeliveryStatus = DeliveryStatus.pending,
    attempt_count: int = 0,
    max_attempts: int = 3,
) -> OutboundDelivery:
    return OutboundDelivery(
        id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        connector_instance_id=connector_instance_id or uuid4(),
        destination=destination,
        content_json={"content_text": "hello", "content_structured": None, "metadata": {}},
        priority=100,
        status=status,
        attempt_count=attempt_count,
        max_attempts=max_attempts,
        error_history=[],
    )


def build_dead_letter(
    *,
    workspace_id: UUID | None = None,
    connector_instance_id: UUID | None = None,
    delivery: OutboundDelivery | None = None,
) -> DeadLetterEntry:
    delivery = delivery or build_delivery(
        workspace_id=workspace_id,
        connector_instance_id=connector_instance_id,
    )
    entry = DeadLetterEntry(
        id=uuid4(),
        workspace_id=workspace_id or delivery.workspace_id,
        outbound_delivery_id=delivery.id,
        connector_instance_id=connector_instance_id or delivery.connector_instance_id,
        resolution_status=DeadLetterResolution.pending,
        dead_lettered_at=delivery.created_at,
    )
    entry.outbound_delivery = delivery
    return entry


def request_stub(
    settings: PlatformSettings,
    producer: object,
    redis_client: object,
    object_storage: object,
):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={
                    "kafka": producer,
                    "redis": redis_client,
                    "minio": object_storage,
                },
            )
        )
    )
