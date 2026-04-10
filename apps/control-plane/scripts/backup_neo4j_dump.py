from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


async def main() -> int:
    from platform.common.clients.object_storage import AsyncObjectStorageClient
    from platform.common.config import Settings

    settings = Settings()
    backup_bucket = os.environ.get("BACKUP_BUCKET", "backups")
    backup_prefix = os.environ.get("BACKUP_PREFIX", "neo4j")
    dumps_dir = Path(os.environ.get("NEO4J_DUMP_DIR", "/dumps"))
    dump_file = dumps_dir / "neo4j.dump"
    dumps_dir.mkdir(parents=True, exist_ok=True)

    dump_started_at = time.perf_counter()
    dump_command = [
        "neo4j-admin",
        "database",
        "dump",
        "--database=neo4j",
        f"--to-path={dumps_dir}",
    ]
    completed = await asyncio.to_thread(
        subprocess.run,
        dump_command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        return 1

    if not dump_file.exists():
        sys.stderr.write(f"Expected dump file {dump_file} was not created.\n")
        return 1

    dump_size = dump_file.stat().st_size
    dump_duration = time.perf_counter() - dump_started_at
    date_prefix = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    object_key = f"{backup_prefix}/{date_prefix}/neo4j.dump"

    upload_started_at = time.perf_counter()
    async with AsyncObjectStorageClient(settings) as storage:
        await storage.upload_multipart(
            backup_bucket,
            object_key,
            file_path=dump_file,
            content_type="application/octet-stream",
            part_size_mb=32,
        )
    upload_duration = time.perf_counter() - upload_started_at

    print(f"dump_size_bytes={dump_size}")
    print(f"dump_duration_seconds={dump_duration:.2f}")
    print(f"upload_duration_seconds={upload_duration:.2f}")
    print(f"uploaded=s3://{backup_bucket}/{object_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
