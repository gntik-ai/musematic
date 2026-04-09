from __future__ import annotations

from hashlib import md5
from pathlib import Path
from uuid import uuid4

import pytest

from platform.common.exceptions import ObjectNotFoundError


pytestmark = pytest.mark.asyncio


async def test_upload_and_download_round_trip(object_storage_client) -> None:
    key = f"basic/{uuid4().hex}/artifact.txt"
    payload = b"hello object storage"

    await object_storage_client.upload_object(
        "execution-artifacts",
        key,
        payload,
        content_type="text/plain",
    )
    downloaded = await object_storage_client.download_object("execution-artifacts", key)

    assert md5(downloaded).hexdigest() == md5(payload).hexdigest()


async def test_upload_multipart_round_trip(object_storage_client, tmp_path: Path) -> None:
    key = f"multipart/{uuid4().hex}/large.bin"
    file_path = tmp_path / "large.bin"
    digest = md5()
    chunk = (b"0123456789abcdef" * 65536)
    with file_path.open("wb") as handle:
        for _ in range(110):
            handle.write(chunk)
            digest.update(chunk)

    await object_storage_client.upload_multipart(
        "execution-artifacts",
        key,
        file_path=file_path,
        content_type="application/octet-stream",
        part_size_mb=8,
    )
    downloaded = await object_storage_client.download_object("execution-artifacts", key)

    assert md5(downloaded).hexdigest() == digest.hexdigest()


async def test_list_objects_filters_by_prefix(object_storage_client) -> None:
    prefix = f"listing/{uuid4().hex}/"
    await object_storage_client.upload_object("execution-artifacts", f"{prefix}one.txt", b"one")
    await object_storage_client.upload_object("execution-artifacts", f"{prefix}two.txt", b"two")
    await object_storage_client.upload_object("execution-artifacts", f"other/{uuid4().hex}.txt", b"skip")

    objects = await object_storage_client.list_objects("execution-artifacts", prefix=prefix)

    assert sorted(item.key for item in objects) == [f"{prefix}one.txt", f"{prefix}two.txt"]


async def test_delete_object_removes_key(object_storage_client) -> None:
    key = f"delete/{uuid4().hex}.txt"
    await object_storage_client.upload_object("execution-artifacts", key, b"delete me")

    await object_storage_client.delete_object("execution-artifacts", key)

    assert await object_storage_client.object_exists("execution-artifacts", key) is False


async def test_download_nonexistent_object_raises(object_storage_client) -> None:
    with pytest.raises(ObjectNotFoundError):
        await object_storage_client.download_object("execution-artifacts", f"missing/{uuid4().hex}.txt")
