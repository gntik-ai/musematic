"""Shared helpers for backup store implementations."""

from __future__ import annotations

import hashlib
from pathlib import Path

from platform_cli.models import BackupArtifact, utc_now_iso


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 checksum for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_artifact(
    *,
    store: str,
    display_name: str,
    path: Path,
    format_name: str,
) -> BackupArtifact:
    """Create a backup artifact model for one file."""

    return BackupArtifact(
        store=store,
        display_name=display_name,
        path=str(path),
        size_bytes=path.stat().st_size,
        checksum_sha256=sha256_file(path),
        format=format_name,
        created_at=utc_now_iso(),
    )
