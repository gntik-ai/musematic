from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from inspect import isawaitable
from pathlib import Path
from platform.common.config import Settings
from platform.common.config import settings as default_settings
from platform.common.exceptions import BucketNotFoundError, ObjectNotFoundError, ObjectStorageError
from typing import Any, Literal, cast

from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    key: str
    size: int
    last_modified: datetime
    etag: str


@dataclass(frozen=True, slots=True)
class ObjectVersion:
    version_id: str
    key: str
    size: int
    last_modified: datetime
    is_latest: bool


class AsyncObjectStorageClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self._session: Any | None = None
        self._client_kwargs = {
            "aws_access_key_id": self.settings.s3.access_key,
            "aws_secret_access_key": self.settings.s3.secret_key,
            "region_name": self.settings.s3.region,
            "config": Config(
                signature_version="s3v4",
                s3={
                    "addressing_style": (
                        "path" if self.settings.s3.use_path_style else "virtual"
                    )
                },
            ),
        }
        if self.settings.s3.endpoint_url:
            self._client_kwargs["endpoint_url"] = self.settings.s3.endpoint_url

    @classmethod
    def from_settings(cls, settings: Settings) -> AsyncObjectStorageClient:
        return cls(settings)

    async def connect(self) -> None:
        self._get_session()

    async def upload_object(
        self,
        bucket: str,
        key: str,
        data: bytes | AsyncIterator[bytes],
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        body = await self._coerce_body(data)
        try:
            async with self._client() as s3:
                await s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=body,
                    ContentType=content_type,
                    Metadata=metadata or {},
                )
        except ClientError as exc:
            raise self._translate_client_error(exc, bucket=bucket, key=key) from exc
        except Exception as exc:  # pragma: no cover - network dependent
            raise ObjectStorageError(
                f"Failed to upload object '{key}' to bucket '{bucket}': {exc}"
            ) from exc

    async def download_object(self, bucket: str, key: str, version_id: str | None = None) -> bytes:
        params: dict[str, str] = {"Bucket": bucket, "Key": key}
        if version_id is not None:
            params["VersionId"] = version_id
        try:
            async with self._client() as s3:
                response = await s3.get_object(**params)
                payload = await response["Body"].read()
                return cast(bytes, payload)
        except ClientError as exc:
            raise self._translate_client_error(exc, bucket=bucket, key=key) from exc
        except Exception as exc:  # pragma: no cover - network dependent
            raise ObjectStorageError(
                f"Failed to download object '{key}' from bucket '{bucket}': {exc}"
            ) from exc

    async def delete_object(self, bucket: str, key: str, version_id: str | None = None) -> None:
        params: dict[str, str] = {"Bucket": bucket, "Key": key}
        if version_id is not None:
            params["VersionId"] = version_id
        try:
            async with self._client() as s3:
                await s3.delete_object(**params)
        except ClientError as exc:
            translated = self._translate_client_error(exc, bucket=bucket, key=key)
            if isinstance(translated, ObjectNotFoundError):
                return
            raise translated from exc
        except Exception as exc:  # pragma: no cover - network dependent
            raise ObjectStorageError(
                f"Failed to delete object '{key}' from bucket '{bucket}': {exc}"
            ) from exc

    async def object_exists(self, bucket: str, key: str, version_id: str | None = None) -> bool:
        params: dict[str, str] = {"Bucket": bucket, "Key": key}
        if version_id is not None:
            params["VersionId"] = version_id
        try:
            async with self._client() as s3:
                await s3.head_object(**params)
                return True
        except ClientError as exc:
            translated = self._translate_client_error(exc, bucket=bucket, key=key)
            if isinstance(translated, ObjectNotFoundError):
                return False
            raise translated from exc
        except Exception as exc:  # pragma: no cover - network dependent
            raise ObjectStorageError(
                f"Failed to check object '{key}' in bucket '{bucket}': {exc}"
            ) from exc

    async def list_object_details(
        self,
        bucket: str,
        prefix: str = "",
        max_keys: int = 1000,
    ) -> list[ObjectInfo]:
        try:
            async with self._client() as s3:
                response = await s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=max_keys)
        except ClientError as exc:
            raise self._translate_client_error(exc, bucket=bucket) from exc
        except Exception as exc:  # pragma: no cover - network dependent
            raise ObjectStorageError(f"Failed to list objects in bucket '{bucket}': {exc}") from exc

        return [
            ObjectInfo(
                key=cast(str, item["Key"]),
                size=int(item["Size"]),
                last_modified=cast(datetime, item["LastModified"]),
                etag=str(item.get("ETag", "")).strip('"'),
            )
            for item in response.get("Contents", [])
        ]

    async def list_objects(self, bucket: str, prefix: str = "") -> list[str]:
        return [item.key for item in await self.list_object_details(bucket, prefix=prefix)]

    async def put_object(
        self,
        bucket: str,
        key: str,
        body: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        await self.upload_object(bucket, key, body, content_type=content_type)

    async def get_object(self, bucket: str, key: str) -> bytes:
        return await self.download_object(bucket, key)

    async def create_bucket_if_not_exists(self, bucket: str) -> None:
        try:
            async with self._client() as s3:
                await s3.head_bucket(Bucket=bucket)
        except ClientError as exc:
            translated = self._translate_client_error(exc, bucket=bucket)
            if isinstance(translated, BucketNotFoundError):
                async with self._client() as s3:
                    await s3.create_bucket(Bucket=bucket)
                return
            raise translated from exc

    async def upload_multipart(
        self,
        bucket: str,
        key: str,
        file_path: Path,
        content_type: str = "application/octet-stream",
        part_size_mb: int = 64,
    ) -> None:
        upload_id: str | None = None
        parts: list[dict[str, object]] = []
        part_size_bytes = part_size_mb * 1024 * 1024
        try:
            async with self._client() as s3:
                created = await s3.create_multipart_upload(
                    Bucket=bucket,
                    Key=key,
                    ContentType=content_type,
                )
                upload_id = cast(str, created["UploadId"])
                part_number = 1
                with file_path.open("rb") as handle:
                    while chunk := await asyncio.to_thread(handle.read, part_size_bytes):
                        response = await s3.upload_part(
                            Bucket=bucket,
                            Key=key,
                            UploadId=upload_id,
                            PartNumber=part_number,
                            Body=chunk,
                        )
                        parts.append(
                            {
                                "PartNumber": part_number,
                                "ETag": cast(str, response["ETag"]),
                            }
                        )
                        part_number += 1
                await s3.complete_multipart_upload(
                    Bucket=bucket,
                    Key=key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )
        except ClientError as exc:
            if upload_id is not None:
                await self._abort_multipart(bucket=bucket, key=key, upload_id=upload_id)
            raise self._translate_client_error(exc, bucket=bucket, key=key) from exc
        except Exception as exc:  # pragma: no cover - network dependent
            if upload_id is not None:
                await self._abort_multipart(bucket=bucket, key=key, upload_id=upload_id)
            raise ObjectStorageError(
                f"Failed multipart upload for object '{key}' in bucket '{bucket}': {exc}"
            ) from exc

    async def get_presigned_url(
        self,
        bucket: str,
        key: str,
        operation: Literal["get_object", "put_object"] = "get_object",
        expires_in_seconds: int = 3600,
    ) -> str:
        params = {"Bucket": bucket, "Key": key}
        try:
            async with self._client() as s3:
                url = await asyncio.to_thread(
                    s3.generate_presigned_url,
                    ClientMethod=operation,
                    Params=params,
                    ExpiresIn=expires_in_seconds,
                )
                if isawaitable(url):
                    url = await url
                return str(url)
        except ClientError as exc:
            raise self._translate_client_error(exc, bucket=bucket, key=key) from exc
        except Exception as exc:  # pragma: no cover - network dependent
            raise ObjectStorageError(
                f"Failed to generate presigned URL for '{key}': {exc}"
            ) from exc

    async def get_object_versions(self, bucket: str, key: str) -> list[ObjectVersion]:
        try:
            async with self._client() as s3:
                response = await s3.list_object_versions(Bucket=bucket, Prefix=key)
        except ClientError as exc:
            raise self._translate_client_error(exc, bucket=bucket, key=key) from exc
        except Exception as exc:  # pragma: no cover - network dependent
            raise ObjectStorageError(
                f"Failed to list object versions for '{key}': {exc}"
            ) from exc

        versions = response.get("Versions")
        if versions is None:
            raise ObjectStorageError(
                f"Bucket '{bucket}' does not expose object versions for key '{key}'."
            )

        return [
            ObjectVersion(
                version_id=cast(str, item["VersionId"]),
                key=cast(str, item["Key"]),
                size=int(item["Size"]),
                last_modified=cast(datetime, item["LastModified"]),
                is_latest=bool(item.get("IsLatest", False)),
            )
            for item in versions
            if item.get("Key") == key
        ]

    async def health_check(self) -> dict[str, Any]:
        probe_bucket = f"{self.settings.s3.bucket_prefix}-agent-packages"
        endpoint = self.settings.s3.endpoint_url or "aws-default"
        try:
            async with self._client() as s3:
                await s3.head_bucket(Bucket=probe_bucket)
            return {
                "status": "ok",
                "provider": self.settings.s3.provider,
                "endpoint": endpoint,
            }
        except Exception as exc:
            return {
                "status": "error",
                "provider": self.settings.s3.provider,
                "endpoint": endpoint,
                "error": str(exc),
            }

    async def __aenter__(self) -> AsyncObjectStorageClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[Any]:
        session = self._get_session()
        async with session.client("s3", **self._client_kwargs) as client:
            yield client

    def _get_session(self) -> Any:
        if self._session is None:
            aioboto3 = import_module("aioboto3")
            self._session = aioboto3.Session()
        return self._session

    async def _coerce_body(self, data: bytes | AsyncIterator[bytes]) -> bytes:
        if isinstance(data, bytes):
            return data

        chunks = bytearray()
        async for chunk in data:
            chunks.extend(chunk)
        return bytes(chunks)

    async def _abort_multipart(self, bucket: str, key: str, upload_id: str) -> None:
        try:
            async with self._client() as s3:
                await s3.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
        except Exception:  # pragma: no cover - cleanup best effort
            return

    def _translate_client_error(
        self,
        exc: ClientError,
        *,
        bucket: str,
        key: str | None = None,
    ) -> ObjectStorageError:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"NoSuchBucket"}:
            return BucketNotFoundError(f"Bucket '{bucket}' not found.")
        if code in {"404", "NotFound"} and key is None:
            return BucketNotFoundError(f"Bucket '{bucket}' not found.")
        if code in {"NoSuchKey", "NoSuchVersion", "404", "NotFound"}:
            target = f"object '{key}'" if key is not None else "object"
            return ObjectNotFoundError(f"{target} not found in bucket '{bucket}'.")
        return ObjectStorageError(f"S3 operation failed for bucket '{bucket}': {code or exc}")


async def check_object_storage(settings: Settings | None = None) -> dict[str, Any]:
    client = AsyncObjectStorageClient.from_settings(settings or default_settings)
    return await client.health_check()
