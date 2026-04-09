from __future__ import annotations

from uuid import uuid4

import pytest

from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.config import Settings
from platform.common.exceptions import ObjectStorageError


pytestmark = pytest.mark.asyncio


def _simulation_settings(minio_server: dict[str, object]) -> Settings:
    access_key = minio_server.get("simulation_access_key")
    secret_key = minio_server.get("simulation_secret_key")
    if not access_key or not secret_key:
        pytest.skip("Simulation credentials are only available when MINIO_TEST_MODE=external is configured.")
    return Settings(
        MINIO_ENDPOINT=str(minio_server["endpoint"]),
        MINIO_ACCESS_KEY=str(access_key),
        MINIO_SECRET_KEY=str(secret_key),
        MINIO_USE_SSL=bool(minio_server["use_ssl"]),
    )


async def test_platform_credentials_cannot_write_simulation_bucket(object_storage_client, minio_server) -> None:
    if minio_server.get("simulation_access_key") is None:
        pytest.skip("Local test container uses root credentials and cannot model IAM isolation.")

    with pytest.raises(ObjectStorageError):
        await object_storage_client.upload_object("simulation-artifacts", f"{uuid4().hex}.txt", b"forbidden")


async def test_simulation_credentials_can_write_simulation_bucket(minio_server) -> None:
    settings = _simulation_settings(minio_server)
    client = AsyncObjectStorageClient(settings)

    await client.upload_object("simulation-artifacts", f"{uuid4().hex}.txt", b"simulation-ok")


async def test_simulation_credentials_cannot_access_production_bucket(minio_server) -> None:
    settings = _simulation_settings(minio_server)
    client = AsyncObjectStorageClient(settings)

    with pytest.raises(ObjectStorageError):
        await client.list_objects("execution-artifacts")
