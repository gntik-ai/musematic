"""Redis backup implementation."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from time import monotonic

from platform_cli.backup.stores.common import build_artifact
from platform_cli.models import BackupArtifact


class RedisBackup:
    """Create Redis RDB snapshots through the Redis protocol."""

    def __init__(self, url: str, rdb_path: Path) -> None:
        self.url = url
        self.rdb_path = rdb_path

    async def backup(self, output_dir: Path) -> BackupArtifact:
        from redis.asyncio import Redis

        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "redis.rdb"
        started = monotonic()
        client = Redis.from_url(self.url, decode_responses=True)
        try:
            previous = await client.lastsave()
            await client.bgsave()
            for _ in range(50):
                if await client.lastsave() != previous:
                    break
                await asyncio.sleep(0.1)
        finally:
            await client.aclose()
        shutil.copy2(self.rdb_path, path)
        return build_artifact(
            store="redis",
            display_name="Redis",
            path=path,
            format_name="rdb",
            duration_seconds=monotonic() - started,
        )

    async def restore(self, artifact_path: Path) -> bool:
        shutil.copy2(artifact_path, self.rdb_path)
        return True
