"""Shared models used across diagnostics, backup, upgrade, and installers."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from platform_cli.config import DeploymentMode
from platform_cli.constants import ComponentCategory


class CheckStatus(StrEnum):
    """Terminal health states for diagnostics and verification."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class BackupStatus(StrEnum):
    """Lifecycle states for a backup manifest."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class DiagnosticCheck(BaseModel):
    """Result of a single health check."""

    component: str
    display_name: str
    category: ComponentCategory
    status: CheckStatus
    latency_ms: float | None = None
    error: str | None = None
    remediation: str | None = None


class AutoFixResult(BaseModel):
    """Outcome of an attempted auto-remediation."""

    component: str
    action: str
    success: bool
    message: str


class DiagnosticReport(BaseModel):
    """Aggregated diagnostics report."""

    deployment_mode: DeploymentMode
    checked_at: str
    duration_seconds: float
    overall_status: CheckStatus
    checks: list[DiagnosticCheck]
    auto_fix_results: list[AutoFixResult] | None = None


class BackupArtifact(BaseModel):
    """A single store backup artifact."""

    store: str
    display_name: str
    path: str
    size_bytes: int
    checksum_sha256: str
    format: str
    created_at: str


class BackupManifest(BaseModel):
    """A complete backup run manifest."""

    backup_id: str
    tag: str | None = None
    sequence_number: int
    deployment_mode: DeploymentMode
    status: BackupStatus
    created_at: str
    completed_at: str | None = None
    artifacts: list[BackupArtifact] = Field(default_factory=list)
    total_size_bytes: int = 0
    storage_location: str


class RestoreRequest(BaseModel):
    """User request to restore one backup."""

    backup_id: str
    stores: list[str] | None = None
    verify_only: bool = False


class ComponentVersion(BaseModel):
    """Detected version information for one component."""

    component: str
    current_version: str
    target_version: str
    upgrade_required: bool
    has_migration: bool


class UpgradePlan(BaseModel):
    """Rolling upgrade plan."""

    source_version: str
    target_version: str
    components: list[ComponentVersion]
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class InstallerResult(BaseModel):
    """Top-level outcome returned by installer flows."""

    deployment_mode: DeploymentMode
    duration_seconds: float
    admin_email: str | None = None
    admin_password: str | None = None
    verification_status: CheckStatus | None = None
    checkpoint_path: str | None = None


def utc_now_iso() -> str:
    """Return the current UTC timestamp as ISO 8601."""

    return datetime.now(UTC).isoformat()
