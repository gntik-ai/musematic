# Data Model: Installer and Operations CLI

**Phase**: Phase 1 — Design  
**Feature**: [spec.md](spec.md)

## Python Types

### Enumerations

```python
from enum import StrEnum

class DeploymentMode(StrEnum):
    """Target infrastructure type for deployment."""
    KUBERNETES = "kubernetes"
    DOCKER = "docker"
    SWARM = "swarm"
    INCUS = "incus"
    LOCAL = "local"

class CheckStatus(StrEnum):
    """Health check result status — maps to green/yellow/red terminal output."""
    HEALTHY = "healthy"       # green
    DEGRADED = "degraded"     # yellow
    UNHEALTHY = "unhealthy"   # red
    UNKNOWN = "unknown"       # gray (timeout or not checked)

class InstallStepStatus(StrEnum):
    """Status of a single installation step in the checkpoint."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class BackupStatus(StrEnum):
    """Status of a backup manifest."""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"       # some stores failed

class ComponentCategory(StrEnum):
    """Classification of a platform component."""
    DATA_STORE = "data_store"
    SATELLITE_SERVICE = "satellite_service"
    CONTROL_PLANE = "control_plane"

class ExitCode(StrEnum):
    """CLI exit codes for headless/CI-CD consumption."""
    SUCCESS = "0"
    GENERAL_ERROR = "1"
    PREFLIGHT_FAILURE = "2"
    PARTIAL_FAILURE = "3"
```

---

### Configuration Entities

```python
from pydantic import BaseModel, Field
from pathlib import Path

class IngressConfig(BaseModel):
    """Ingress controller configuration."""
    enabled: bool = True
    hostname: str = "platform.local"
    tls_enabled: bool = False
    tls_secret_name: str | None = None

class ResourceOverride(BaseModel):
    """Per-component Kubernetes resource overrides."""
    replicas: int | None = None
    storage: str | None = None        # e.g., "50Gi"
    cpu_limit: str | None = None      # e.g., "2000m"
    memory_limit: str | None = None   # e.g., "4Gi"

class AdminConfig(BaseModel):
    """Initial administrator account configuration."""
    email: str = "admin@platform.local"

class SecretsConfig(BaseModel):
    """Secret generation/provision configuration."""
    generate: bool = True             # auto-generate all secrets
    postgresql_password: str | None = None
    redis_password: str | None = None
    neo4j_password: str | None = None
    clickhouse_password: str | None = None
    opensearch_password: str | None = None
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    jwt_private_key_pem: str | None = None

class InstallerConfig(BaseModel):
    """Top-level installer configuration — loaded from platform-install.yaml."""
    deployment_mode: DeploymentMode = DeploymentMode.KUBERNETES
    namespace: str = "platform"
    storage_class: str = "standard"
    ingress: IngressConfig = Field(default_factory=IngressConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
    resources: dict[str, ResourceOverride] = Field(default_factory=dict)
    image_registry: str = "ghcr.io"
    image_tag: str = "latest"
    air_gapped: bool = False
    local_registry: str | None = None   # for air-gapped mode
    data_dir: Path = Path.home() / ".platform-cli" / "data"
```

---

### Platform Component Registry

```python
class PlatformComponent(BaseModel):
    """A single deployable platform unit — data store or service."""
    name: str                         # e.g., "postgresql", "runtime-controller"
    display_name: str                 # e.g., "PostgreSQL", "Runtime Controller"
    category: ComponentCategory
    helm_chart: str | None            # relative path under deploy/helm/, None for local-only
    namespace: str                    # Kubernetes namespace for this component
    depends_on: list[str]             # component names that must be healthy first
    health_check_type: str            # "tcp", "http", "grpc", "sql"
    health_check_target: str          # endpoint/port/query for health check
    has_migration: bool               # whether this component needs schema init
    backup_supported: bool            # whether backup/restore is available

# Static registry — all 12 components in dependency order
PLATFORM_COMPONENTS: list[PlatformComponent]  # defined as a constant
```

**Component registry** (dependency order):

| Name | Category | Namespace | Depends On | Health Check | Migration |
|------|----------|-----------|------------|-------------|-----------|
| postgresql | data_store | platform-data | — | SQL: `SELECT 1` | Alembic |
| redis | data_store | platform-data | — | TCP: `PING` | — |
| kafka | data_store | platform-data | — | HTTP: broker metadata | Topic creation |
| qdrant | data_store | platform-data | — | HTTP: `/healthz` | Collection init |
| neo4j | data_store | platform-data | — | Cypher: `RETURN 1` | Constraint init |
| clickhouse | data_store | platform-data | — | SQL: `SELECT 1` | Table init |
| opensearch | data_store | platform-data | — | HTTP: `/_cluster/health` | Index template init |
| minio | data_store | platform-data | — | HTTP: `HEAD` bucket | Bucket creation |
| runtime-controller | satellite | platform-execution | postgresql, redis, kafka, minio | gRPC health | — |
| reasoning-engine | satellite | platform-execution | postgresql, redis, kafka | gRPC health | — |
| simulation-controller | satellite | platform-simulation | postgresql, kafka, minio | gRPC health | — |
| control-plane | control_plane | platform-control | all of the above | HTTP: `/health` | — |

---

### Installation Checkpoint Entities

```python
class InstallStep(BaseModel):
    """A single step in the installation process."""
    name: str                         # e.g., "preflight", "helm-postgresql"
    description: str
    status: InstallStepStatus = InstallStepStatus.PENDING
    started_at: str | None = None     # ISO 8601
    completed_at: str | None = None
    failed_at: str | None = None
    error: str | None = None
    duration_seconds: float | None = None

class InstallationCheckpoint(BaseModel):
    """Checkpoint file for resume-from-failure support."""
    install_id: str                   # UUID
    deployment_mode: DeploymentMode
    config_hash: str                  # SHA-256 of the full config — detects drift
    started_at: str
    updated_at: str
    steps: list[InstallStep]
    completed: bool = False
    admin_credentials_displayed: bool = False
```

---

### Diagnostic Entities

```python
class DiagnosticCheck(BaseModel):
    """Result of a single health check."""
    component: str                    # component name
    display_name: str
    category: ComponentCategory
    status: CheckStatus
    latency_ms: float | None = None
    error: str | None = None
    remediation: str | None = None    # suggested fix when unhealthy

class DiagnosticReport(BaseModel):
    """Full diagnostic report — all checks."""
    deployment_mode: DeploymentMode
    checked_at: str                   # ISO 8601
    duration_seconds: float
    overall_status: CheckStatus       # worst status across all checks
    checks: list[DiagnosticCheck]
    auto_fix_results: list[AutoFixResult] | None = None  # only with --fix

class AutoFixResult(BaseModel):
    """Result of an auto-remediation attempt."""
    component: str
    action: str                       # what was attempted
    success: bool
    message: str
```

---

### Backup / Restore Entities

```python
class BackupArtifact(BaseModel):
    """A single data store's backup snapshot."""
    store: str                        # component name
    display_name: str
    path: str                         # URI or local path to backup file
    size_bytes: int
    checksum_sha256: str
    format: str                       # e.g., "pg_dump", "rdb", "snapshot"
    created_at: str

class BackupManifest(BaseModel):
    """A complete backup run — all stores."""
    backup_id: str                    # UUID
    tag: str | None = None            # user-provided label
    sequence_number: int              # monotonically increasing
    deployment_mode: DeploymentMode
    status: BackupStatus
    created_at: str
    completed_at: str | None = None
    artifacts: list[BackupArtifact]
    total_size_bytes: int
    storage_location: str             # bucket URI or local directory

class RestoreRequest(BaseModel):
    """Input for a restore operation."""
    backup_id: str
    stores: list[str] | None = None   # None = restore all; list = selective
    verify_only: bool = False         # just verify checksums, don't restore
```

---

### Upgrade Entities

```python
class ComponentVersion(BaseModel):
    """Detected version of a platform component."""
    component: str
    current_version: str
    target_version: str
    upgrade_required: bool
    has_migration: bool

class UpgradePlan(BaseModel):
    """Planned upgrade sequence."""
    source_version: str
    target_version: str
    components: list[ComponentVersion]
    pending_migrations: list[str]     # Alembic revision IDs
    estimated_duration_minutes: int
    requires_downtime: bool

class UpgradeResult(BaseModel):
    """Result of an upgrade operation."""
    plan: UpgradePlan
    status: str                       # "completed", "failed", "rolled_back"
    components_upgraded: list[str]
    failed_component: str | None = None
    error: str | None = None
    rollback_instructions: str | None = None
```

---

### Generated Secrets

```python
class GeneratedSecrets(BaseModel):
    """All secrets generated during installation."""
    admin_password: str               # displayed once, then cleared from memory
    postgresql_password: str
    redis_password: str
    neo4j_password: str
    clickhouse_password: str
    opensearch_password: str
    minio_access_key: str
    minio_secret_key: str
    jwt_private_key_pem: str          # RS256 4096-bit
    jwt_public_key_pem: str
```

---

## Entity Relationships

```text
InstallerConfig
  └─ drives the entire install/upgrade/backup flow
  └─ references DeploymentMode

PlatformComponent[]
  └─ static registry defining dependency order
  └─ used by: installer (deploy order), diagnostics (check list), backup (store list)

InstallationCheckpoint
  └─ records progress of an install/upgrade run
  └─ contains InstallStep[] (one per PlatformComponent + setup steps)
  └─ persisted as JSON file for resume support

DiagnosticReport
  └─ contains DiagnosticCheck[] (one per PlatformComponent + model providers)
  └─ optionally contains AutoFixResult[] (with --fix flag)

BackupManifest
  └─ contains BackupArtifact[] (one per backed-up store)
  └─ used by RestoreRequest to identify what to restore

UpgradePlan
  └─ contains ComponentVersion[] (one per PlatformComponent)
  └─ drives UpgradeResult

GeneratedSecrets
  └─ created during install
  └─ stored in Kubernetes Secrets / .env files / local file
  └─ admin_password displayed once then discarded
```
