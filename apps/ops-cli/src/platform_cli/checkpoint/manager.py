"""Checkpoint persistence helpers for resumable operations."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from platform_cli.config import InstallerConfig


class InstallStepStatus(StrEnum):
    """Install step lifecycle states."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class InstallStep(BaseModel):
    """A single tracked installation step."""

    name: str
    description: str
    status: InstallStepStatus = InstallStepStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    failed_at: str | None = None
    error: str | None = None
    duration_seconds: float | None = None


class InstallationCheckpoint(BaseModel):
    """Persisted checkpoint document."""

    install_id: str
    deployment_mode: str
    config_hash: str
    started_at: str
    updated_at: str
    steps: list[InstallStep]
    completed: bool = False
    admin_credentials_displayed: bool = False


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CheckpointManager:
    """Create, update, and restore JSON checkpoints."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path.home() / ".platform-cli" / "checkpoints"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoint: InstallationCheckpoint | None = None
        self._checkpoint_path: Path | None = None

    @staticmethod
    def compute_config_hash(config: InstallerConfig) -> str:
        """Compute a stable SHA-256 hash for a config payload."""

        serialized = json.dumps(config.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def create(self, config: InstallerConfig, steps: list[str]) -> InstallationCheckpoint:
        """Create a fresh checkpoint document and persist it to disk."""

        now = _utc_now().isoformat()
        checkpoint = InstallationCheckpoint(
            install_id=str(uuid4()),
            deployment_mode=config.deployment_mode.value,
            config_hash=self.compute_config_hash(config),
            started_at=now,
            updated_at=now,
            steps=[
                InstallStep(name=step, description=step.replace("-", " ").title()) for step in steps
            ],
        )
        self._checkpoint = checkpoint
        self._checkpoint_path = self.base_dir / f"{checkpoint.install_id}.json"
        self._write()
        return checkpoint

    def update_step(
        self,
        name: str,
        status: InstallStepStatus,
        error: str | None = None,
    ) -> InstallationCheckpoint:
        """Update one step in the current checkpoint and persist the change."""

        if self._checkpoint is None:
            raise RuntimeError("No checkpoint loaded or created.")
        step = next((item for item in self._checkpoint.steps if item.name == name), None)
        if step is None:
            raise KeyError(f"Unknown checkpoint step: {name}")

        now = _utc_now()
        if status == InstallStepStatus.IN_PROGRESS and step.started_at is None:
            step.started_at = now.isoformat()
        if status == InstallStepStatus.COMPLETED:
            step.completed_at = now.isoformat()
            step.duration_seconds = self._duration_from_start(step.started_at, now)
        if status == InstallStepStatus.FAILED:
            step.failed_at = now.isoformat()
            step.duration_seconds = self._duration_from_start(step.started_at, now)
        step.status = status
        step.error = error
        self._checkpoint.updated_at = now.isoformat()
        self._checkpoint.completed = all(
            item.status == InstallStepStatus.COMPLETED for item in self._checkpoint.steps
        )
        self._write()
        return self._checkpoint

    def load_latest(self, config_hash: str) -> InstallationCheckpoint | None:
        """Load the most recent checkpoint matching a config hash."""

        candidates: list[tuple[float, Path, InstallationCheckpoint]] = []
        for path in self.base_dir.glob("*.json"):
            checkpoint = InstallationCheckpoint.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            if checkpoint.config_hash != config_hash:
                continue
            candidates.append((path.stat().st_mtime, path, checkpoint))
        if not candidates:
            return None
        _, path, checkpoint = max(candidates, key=lambda item: item[0])
        self._checkpoint = checkpoint
        self._checkpoint_path = path
        return checkpoint

    def get_resume_point(self) -> str | None:
        """Return the first step that is not already completed."""

        if self._checkpoint is None:
            return None
        for step in self._checkpoint.steps:
            if step.status != InstallStepStatus.COMPLETED:
                return step.name
        return None

    @property
    def checkpoint_path(self) -> Path | None:
        """Return the currently loaded checkpoint path."""

        return self._checkpoint_path

    @property
    def checkpoint(self) -> InstallationCheckpoint | None:
        """Return the in-memory checkpoint, when one is loaded."""

        return self._checkpoint

    def _write(self) -> None:
        if self._checkpoint is None or self._checkpoint_path is None:
            raise RuntimeError("No checkpoint loaded or created.")
        self._checkpoint_path.write_text(
            json.dumps(self._checkpoint.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def _duration_from_start(started_at: str | None, end: datetime) -> float | None:
        if started_at is None:
            return None
        started = datetime.fromisoformat(started_at)
        return round((end - started).total_seconds(), 3)
