from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _headers(settings: object) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    api_key = getattr(settings, "QDRANT_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"api-key {api_key}"
    return headers


def _request_json(url: str, method: str, headers: dict[str, str]) -> dict[str, object]:
    req = request.Request(url, method=method, headers=headers)
    with request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())


def _request_bytes(url: str, headers: dict[str, str]) -> bytes:
    req = request.Request(url, headers=headers)
    with request.urlopen(req, timeout=60) as response:
        return response.read()


async def main() -> None:
    from platform.common.clients.object_storage import AsyncObjectStorageClient
    from platform.common.config import Settings

    settings = Settings()
    headers = _headers(settings)
    base_url = settings.QDRANT_URL.rstrip("/")
    backup_bucket = os.environ.get("BACKUP_BUCKET", "backups")
    prefix = os.environ.get("QDRANT_SNAPSHOT_PREFIX", "qdrant")
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")

    collections_response = await asyncio.to_thread(_request_json, f"{base_url}/collections", "GET", headers)
    collections = [item["name"] for item in collections_response["result"]["collections"]]

    async with AsyncObjectStorageClient(settings) as object_storage:
        for collection in collections:
            snapshot_response = await asyncio.to_thread(
                _request_json,
                f"{base_url}/collections/{collection}/snapshots",
                "POST",
                headers,
            )
            snapshot_name = str(snapshot_response["result"]["name"])
            snapshot_bytes = await asyncio.to_thread(
                _request_bytes,
                f"{base_url}/collections/{collection}/snapshots/{snapshot_name}",
                headers,
            )
            key = f"{prefix}/{collection}/{timestamp}_{snapshot_name}"
            await object_storage.upload_object(
                backup_bucket,
                key,
                snapshot_bytes,
                content_type="application/octet-stream",
            )
            print(f"uploaded {collection} -> s3://{backup_bucket}/{key}")


if __name__ == "__main__":
    asyncio.run(main())
