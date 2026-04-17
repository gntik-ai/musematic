"""Neo4j backup implementation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from platform_cli.backup.stores.common import build_artifact
from platform_cli.models import BackupArtifact


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "neo4j backup failed")


class Neo4jBackup:
    """Use ``neo4j-admin`` dump/load commands."""

    def __init__(self, database_name: str = "neo4j") -> None:
        self.database_name = database_name

    async def backup(self, output_dir: Path) -> BackupArtifact:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "neo4j.dump"
        _run(["neo4j-admin", "database", "dump", self.database_name, f"--to-path={output_dir}"])
        return build_artifact(store="neo4j", display_name="Neo4j", path=path, format_name="dump")

    async def restore(self, artifact_path: Path) -> bool:
        _run(
            [
                "neo4j-admin",
                "database",
                "load",
                self.database_name,
                f"--from-path={artifact_path.parent}",
            ]
        )
        return True
