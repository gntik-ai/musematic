"""ExportArchiver — streaming multipart ZIP upload for workspace + tenant exports.

T032 (UPD-051): wraps an ``aioboto3``-style S3 client around a streaming ZIP
writer. Parts are flushed to S3 as soon as the in-memory buffer crosses the
``part_size_bytes`` threshold (default 8 MiB; S3 minimum non-final part is
5 MiB, so 8 MiB is a comfortable margin for chunked compression overhead).
The archiver keeps a small bookkeeping dict so the worker can persist the
``last_part_number`` and ``last_resource_emitted`` markers and resume after a
crash by replaying serializers from the marker forward.

The class is intentionally protocol-driven so unit tests can pass a fake S3
client, and integration tests can pass the real ``aioboto3`` session.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

# --- S3 protocol --------------------------------------------------------------


class _MultipartCreateResponse(Protocol):
    def __getitem__(self, key: str) -> Any: ...


class _MultipartS3Client(Protocol):
    """Subset of the aioboto3 S3 client used by ExportArchiver."""

    async def create_multipart_upload(
        self, *, Bucket: str, Key: str, ContentType: str
    ) -> _MultipartCreateResponse: ...

    async def upload_part(
        self,
        *,
        Bucket: str,
        Key: str,
        UploadId: str,
        PartNumber: int,
        Body: bytes,
    ) -> _MultipartCreateResponse: ...

    async def complete_multipart_upload(
        self,
        *,
        Bucket: str,
        Key: str,
        UploadId: str,
        MultipartUpload: dict[str, Any],
    ) -> _MultipartCreateResponse: ...

    async def abort_multipart_upload(
        self, *, Bucket: str, Key: str, UploadId: str
    ) -> _MultipartCreateResponse: ...


# --- Resume state -------------------------------------------------------------


@dataclass
class ResumeState:
    """Persisted across worker restarts so an export can resume.

    The export worker reads ``last_resource_emitted`` to determine where the
    serializer stream should pick up; ``last_part_number`` is informational
    (S3's multipart upload requires monotonically increasing part numbers but
    the archiver always restarts from part 1 on resume — old parts are
    discarded with ``abort_multipart_upload`` and the upload starts fresh).
    """

    last_part_number: int = 0
    last_resource_emitted: str | None = None
    bytes_streamed: int = 0


@dataclass
class ArchiveResult:
    object_key: str
    upload_id: str
    parts: list[dict[str, Any]] = field(default_factory=list)
    bytes_total: int = 0


# --- Archiver -----------------------------------------------------------------


# Async serializer signature — same shape used by ExportService.
AsyncSerializer = Callable[..., AsyncIterator[tuple[str, bytes]]]


_DEFAULT_PART_SIZE = 8 * 1024 * 1024  # 8 MiB; comfortably above S3's 5 MiB min.


class ExportArchiver:
    """Drives a streaming multipart ZIP upload to S3.

    Lifecycle:

    1. ``begin(bucket, key)`` opens a new ``MultipartUpload``.
    2. ``write_metadata(name, body)`` and ``stream_serializer(serializer, kwargs)``
       feed bytes into the streaming ``zipfile.ZipFile``. Whenever the
       in-memory buffer crosses ``part_size_bytes`` we flush a part to S3.
    3. ``finalize()`` closes the ZIP, flushes the trailing buffer (the last
       part can be smaller than 5 MiB by S3 spec), and calls
       ``complete_multipart_upload``.
    4. On any exception the caller MUST call ``abort()`` to release the
       partially-uploaded parts and free the multipart-upload allocation.
    """

    def __init__(
        self,
        client: _MultipartS3Client,
        *,
        part_size_bytes: int = _DEFAULT_PART_SIZE,
        content_type: str = "application/zip",
    ) -> None:
        if part_size_bytes < 5 * 1024 * 1024:
            raise ValueError(
                "S3 multipart parts (except the final one) must be at least 5 MiB"
            )
        self._client = client
        self._part_size_bytes = part_size_bytes
        self._content_type = content_type
        self._bucket: str | None = None
        self._key: str | None = None
        self._upload_id: str | None = None
        self._buffer = io.BytesIO()
        self._zip: zipfile.ZipFile | None = None
        self._parts: list[dict[str, Any]] = []
        self._part_number = 1
        self._bytes_total = 0
        self.state = ResumeState()

    @property
    def upload_id(self) -> str | None:
        return self._upload_id

    @property
    def parts(self) -> list[dict[str, Any]]:
        return list(self._parts)

    async def begin(self, bucket: str, key: str) -> None:
        if self._upload_id is not None:
            raise RuntimeError("ExportArchiver already started")
        self._bucket = bucket
        self._key = key
        created = await self._client.create_multipart_upload(
            Bucket=bucket,
            Key=key,
            ContentType=self._content_type,
        )
        self._upload_id = str(created["UploadId"])
        # The streaming ZipFile shares the same buffer; we hand-write the
        # central directory in finalize().
        self._zip = zipfile.ZipFile(
            self._buffer, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
        )

    async def write_entry(self, filepath: str, body: bytes) -> None:
        if self._zip is None:
            raise RuntimeError("ExportArchiver.begin must be called first")
        self._zip.writestr(filepath, body)
        await self._maybe_flush()

    async def stream_serializer(
        self,
        serializer: AsyncSerializer,
        /,
        **kwargs: Any,
    ) -> None:
        async for filepath, chunk in serializer(**kwargs):
            await self.write_entry(filepath, chunk)
            self.state.last_resource_emitted = filepath
            self.state.bytes_streamed += len(chunk)

    async def _maybe_flush(self) -> None:
        if self._buffer.tell() < self._part_size_bytes:
            return
        # Pull off the first ``part_size_bytes`` bytes; keep the tail in the
        # buffer because zipfile may still be writing trailing metadata.
        self._buffer.seek(0)
        head = self._buffer.read(self._part_size_bytes)
        tail = self._buffer.read()
        self._buffer.seek(0)
        self._buffer.truncate(0)
        self._buffer.write(tail)
        await self._upload_part(head)

    async def _upload_part(self, body: bytes) -> None:
        assert self._bucket is not None
        assert self._key is not None
        assert self._upload_id is not None
        if not body:
            return
        response = await self._client.upload_part(
            Bucket=self._bucket,
            Key=self._key,
            UploadId=self._upload_id,
            PartNumber=self._part_number,
            Body=body,
        )
        self._parts.append(
            {"PartNumber": self._part_number, "ETag": str(response["ETag"])}
        )
        self._bytes_total += len(body)
        self.state.last_part_number = self._part_number
        self._part_number += 1

    async def finalize(self) -> ArchiveResult:
        if self._zip is None or self._upload_id is None:
            raise RuntimeError("ExportArchiver.begin must be called first")
        # Closing the ZipFile writes the central directory into the buffer.
        self._zip.close()
        self._zip = None
        # Drain any remaining bytes as the final part — S3 allows this part
        # to be smaller than the 5 MiB minimum.
        remaining = self._buffer.getvalue()
        self._buffer = io.BytesIO()
        await self._upload_part(remaining)
        assert self._bucket is not None
        assert self._key is not None
        await self._client.complete_multipart_upload(
            Bucket=self._bucket,
            Key=self._key,
            UploadId=self._upload_id,
            MultipartUpload={"Parts": self._parts},
        )
        return ArchiveResult(
            object_key=self._key,
            upload_id=self._upload_id,
            parts=self._parts,
            bytes_total=self._bytes_total,
        )

    async def abort(self) -> None:
        if self._upload_id is None or self._bucket is None or self._key is None:
            return
        try:
            await self._client.abort_multipart_upload(
                Bucket=self._bucket,
                Key=self._key,
                UploadId=self._upload_id,
            )
        finally:
            self._upload_id = None
            if self._zip is not None:
                # Closing the ZipFile here may also flush bytes; we don't
                # care because the upload has already been aborted.
                with self._zip:
                    pass
                self._zip = None


# Convenience: wrap an async aioboto3 session-bound client builder so callers
# can pass ``session.client("s3")`` directly. The Awaitable[Awaitable[...]]
# shape is what aioboto3's context-managed client looks like under the hood.
async def open_archiver(
    client_factory: Callable[[], Awaitable[_MultipartS3Client]],
    bucket: str,
    key: str,
    *,
    part_size_bytes: int = _DEFAULT_PART_SIZE,
) -> tuple[ExportArchiver, _MultipartS3Client]:
    """Open an ExportArchiver against a freshly-created S3 client.

    Returns a tuple ``(archiver, client)`` so callers can manage the client's
    lifetime themselves (e.g. inside a ``async with`` block).
    """
    client = await client_factory()
    archiver = ExportArchiver(client, part_size_bytes=part_size_bytes)
    await archiver.begin(bucket, key)
    return archiver, client
