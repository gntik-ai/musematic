"""ClickHouse backup implementation."""

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
            result.stderr.strip() or result.stdout.strip() or "clickhouse backup failed"
        )


class ClickHouseBackup:
    """Use ``clickhouse-backup``."""

    def __init__(self, backup_name: str = "platform") -> None:
        self.backup_name = backup_name

    async def backup(self, output_dir: Path) -> BackupArtifact:
        output_dir.mkdir(parents=True, exist_ok=True)
        started = monotonic()
        _run(["clickhouse-backup", "create", self.backup_name])
        path = output_dir / f"{self.backup_name}.clickhouse"
        path.write_text(self.backup_name, encoding="utf-8")
        return build_artifact(
            store="clickhouse",
            display_name="ClickHouse",
            path=path,
            format_name="clickhouse-backup",
            duration_seconds=monotonic() - started,
        )

    async def restore(self, artifact_path: Path) -> bool:
        _run(["clickhouse-backup", "restore", artifact_path.read_text(encoding="utf-8").strip()])
        return True
