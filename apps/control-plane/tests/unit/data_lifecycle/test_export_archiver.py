"""T032 — unit tests for ExportArchiver streaming multipart upload."""

from __future__ import annotations

import io
import zipfile
from collections.abc import AsyncIterator
from platform.data_lifecycle.services.export_archiver import ExportArchiver
from typing import Any

import pytest


class FakeS3Client:
    """In-memory aioboto3 stand-in for ExportArchiver."""

    def __init__(self) -> None:
        self.uploads: dict[str, dict[str, Any]] = {}
        self.completed: dict[str, bytes] = {}
        self.aborted: list[str] = []
        self._next_upload_id = 1
        self._next_etag = 1

    async def create_multipart_upload(
        self, *, Bucket: str, Key: str, ContentType: str
    ) -> dict[str, Any]:
        upload_id = f"upload-{self._next_upload_id}"
        self._next_upload_id += 1
        self.uploads[upload_id] = {
            "Bucket": Bucket,
            "Key": Key,
            "ContentType": ContentType,
            "Parts": {},
        }
        return {"UploadId": upload_id}

    async def upload_part(
        self,
        *,
        Bucket: str,
        Key: str,
        UploadId: str,
        PartNumber: int,
        Body: bytes,
    ) -> dict[str, Any]:
        etag = f'"etag-{self._next_etag}"'
        self._next_etag += 1
        self.uploads[UploadId]["Parts"][PartNumber] = Body
        return {"ETag": etag}

    async def complete_multipart_upload(
        self,
        *,
        Bucket: str,
        Key: str,
        UploadId: str,
        MultipartUpload: dict[str, Any],
    ) -> dict[str, Any]:
        parts = self.uploads.pop(UploadId)
        ordered_keys = [item["PartNumber"] for item in MultipartUpload["Parts"]]
        body = b"".join(parts["Parts"][num] for num in ordered_keys)
        self.completed[Key] = body
        return {"ETag": '"final-etag"'}

    async def abort_multipart_upload(
        self, *, Bucket: str, Key: str, UploadId: str
    ) -> dict[str, Any]:
        self.aborted.append(UploadId)
        self.uploads.pop(UploadId, None)
        return {}


async def _make_serializer(
    items: list[tuple[str, bytes]],
) -> AsyncIterator[tuple[str, bytes]]:
    for filepath, chunk in items:
        yield filepath, chunk


@pytest.mark.asyncio
async def test_archiver_writes_valid_zip_via_multipart_upload() -> None:
    client = FakeS3Client()
    archiver = ExportArchiver(client, part_size_bytes=5 * 1024 * 1024)
    await archiver.begin("test-bucket", "exports/job-1.zip")

    await archiver.write_entry("metadata.json", b'{"format_version": 1}')
    await archiver.stream_serializer(
        lambda **_kwargs: _make_serializer(
            [
                ("agents/agent-1.json", b'{"id": "agent-1"}'),
                ("audit/chain.ndjson", b'{"seq": 1}\n'),
            ]
        ),
    )
    result = await archiver.finalize()

    assert result.object_key == "exports/job-1.zip"
    assert result.upload_id.startswith("upload-")
    assert client.completed["exports/job-1.zip"]

    archive_bytes = client.completed["exports/job-1.zip"]
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
        names = zf.namelist()
        assert "metadata.json" in names
        assert "agents/agent-1.json" in names
        assert "audit/chain.ndjson" in names
        assert zf.read("metadata.json") == b'{"format_version": 1}'


@pytest.mark.asyncio
async def test_archiver_flushes_parts_when_buffer_exceeds_threshold() -> None:
    import secrets

    client = FakeS3Client()
    archiver = ExportArchiver(client, part_size_bytes=5 * 1024 * 1024)
    await archiver.begin("bucket", "key")

    # Use cryptographic random bytes so DEFLATE cannot compress them — that
    # forces the buffer to actually exceed the part-size threshold.
    payload = secrets.token_bytes(6 * 1024 * 1024)
    await archiver.write_entry("blob.bin", payload)
    await archiver.stream_serializer(
        lambda **_kwargs: _make_serializer([("trailer.json", b'{"ok": true}')]),
    )

    result = await archiver.finalize()

    # The streaming archiver should have produced 2+ parts: one mid-stream
    # flush plus the final part holding the central directory.
    assert len(result.parts) >= 2
    assert archiver.state.last_part_number >= 1
    assert archiver.state.last_resource_emitted == "trailer.json"


@pytest.mark.asyncio
async def test_archiver_abort_releases_upload() -> None:
    client = FakeS3Client()
    archiver = ExportArchiver(client, part_size_bytes=5 * 1024 * 1024)
    await archiver.begin("bucket", "key")
    await archiver.write_entry("metadata.json", b"{}")

    await archiver.abort()

    assert client.aborted == ["upload-1"]
    assert archiver.upload_id is None


@pytest.mark.asyncio
async def test_archiver_rejects_part_size_below_s3_minimum() -> None:
    client = FakeS3Client()
    with pytest.raises(ValueError, match="5 MiB"):
        ExportArchiver(client, part_size_bytes=1024 * 1024)


@pytest.mark.asyncio
async def test_archiver_finalize_without_begin_raises() -> None:
    client = FakeS3Client()
    archiver = ExportArchiver(client)
    with pytest.raises(RuntimeError):
        await archiver.finalize()


@pytest.mark.asyncio
async def test_archiver_double_begin_raises() -> None:
    client = FakeS3Client()
    archiver = ExportArchiver(client)
    await archiver.begin("bucket", "key")
    with pytest.raises(RuntimeError, match="already started"):
        await archiver.begin("bucket", "other-key")
    await archiver.abort()


@pytest.mark.asyncio
async def test_archiver_write_entry_before_begin_raises() -> None:
    client = FakeS3Client()
    archiver = ExportArchiver(client)
    with pytest.raises(RuntimeError, match="begin must be called first"):
        await archiver.write_entry("file.json", b"{}")


@pytest.mark.asyncio
async def test_archiver_parts_property_returns_copy() -> None:
    client = FakeS3Client()
    archiver = ExportArchiver(client)
    await archiver.begin("bucket", "key")
    await archiver.write_entry("a.json", b"{}")
    await archiver.finalize()
    parts_snapshot = archiver.parts
    assert isinstance(parts_snapshot, list)
    parts_snapshot.append({"PartNumber": 999})
    assert archiver.parts != parts_snapshot


@pytest.mark.asyncio
async def test_archiver_abort_before_begin_is_noop() -> None:
    client = FakeS3Client()
    archiver = ExportArchiver(client)
    # abort() before begin() must not raise.
    await archiver.abort()
    assert client.aborted == []


@pytest.mark.asyncio
async def test_open_archiver_helper_starts_upload() -> None:
    from platform.data_lifecycle.services.export_archiver import open_archiver

    client = FakeS3Client()

    async def factory() -> FakeS3Client:
        return client

    archiver, returned = await open_archiver(factory, "bucket", "key")
    assert returned is client
    assert archiver.upload_id is not None
    await archiver.write_entry("a.json", b"{}")
    await archiver.finalize()
    assert "key" in client.completed
