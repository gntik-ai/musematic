"""PostgreSQL backup implementation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from time import monotonic

from platform_cli.backup.stores.common import build_artifact
from platform_cli.models import BackupArtifact


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or result.stdout.strip() or "postgresql backup failed"
        )


class PostgreSQLBackup:
    """Use ``pg_dump`` and ``pg_restore`` for PostgreSQL backups."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    async def backup(self, output_dir: Path) -> BackupArtifact:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "postgresql.dump"
        started = monotonic()
        _run(["pg_dump", "--format=custom", "-f", str(path), self.database_url])
        return build_artifact(
            store="postgresql",
            display_name="PostgreSQL",
            path=path,
            format_name="pg_dump",
            duration_seconds=monotonic() - started,
        )

    async def restore(self, artifact_path: Path) -> bool:
        _run(["pg_restore", "--clean", "--if-exists", "-d", self.database_url, str(artifact_path)])
        return True
