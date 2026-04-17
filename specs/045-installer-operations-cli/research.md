# Research: Installer and Operations CLI

**Phase**: Phase 0 — Research  
**Feature**: [spec.md](spec.md)

## Decision 1: Project Location and Package Structure

**Decision**: Create `apps/ops-cli/` as a standalone Python package with its own `pyproject.toml`, following the same layout pattern as `apps/control-plane/`.

**Rationale**: The constitution's repository structure already lists `apps/ops-cli/`. This is an operational tool, not part of the control plane monolith — it must be independently packaged and distributable. It does not run inside the platform process; it manages the platform from outside.

**Package layout**:
```
apps/ops-cli/
├── pyproject.toml
├── src/platform_cli/
│   ├── __init__.py
│   ├── main.py              # Typer app entry point
│   ├── config.py             # CLI config (Pydantic)
│   ├── commands/
│   │   ├── install.py
│   │   ├── diagnose.py
│   │   ├── backup.py
│   │   ├── restore.py
│   │   ├── upgrade.py
│   │   └── admin.py
│   ├── installers/
│   │   ├── base.py           # Abstract installer
│   │   ├── kubernetes.py
│   │   ├── local.py
│   │   ├── docker.py
│   │   ├── swarm.py
│   │   └── incus.py
│   ├── preflight/
│   │   ├── base.py
│   │   ├── kubernetes.py
│   │   ├── docker.py
│   │   └── local.py
│   ├── diagnostics/
│   │   ├── checker.py        # Health check orchestrator
│   │   └── checks/           # Per-service check modules
│   ├── backup/
│   │   ├── orchestrator.py
│   │   └── stores/           # Per-store backup strategies
│   ├── migrations/
│   │   └── runner.py         # Alembic + init script runner
│   ├── secrets/
│   │   └── generator.py      # Cryptographic secret generation
│   ├── checkpoint/
│   │   └── manager.py        # Resume-from-failure support
│   └── output/
│       ├── console.py        # Rich terminal output
│       └── structured.py     # JSON/YAML machine-readable output
└── tests/
    ├── unit/
    ├── integration/
    └── conftest.py
```

**Alternatives considered**:
- Adding CLI to `apps/control-plane/` — violates separation of concerns; the CLI must be distributable as a standalone binary without the entire monolith
- Go CLI — Python is the right choice because the CLI needs to invoke Alembic (Python), share configuration models with the control plane, and manipulate Helm values via Jinja2 templates

---

## Decision 2: CLI Framework

**Decision**: Typer 0.12+ with Rich integration for terminal output.

**Rationale**: User-specified framework. Typer provides type-annotated CLI commands that map naturally to Python function signatures. Rich provides styled terminal output (tables, progress bars, status spinners) out of the box via `typer[all]`. Typer generates `--help` documentation automatically from docstrings and type annotations.

**Command structure**:
```
platform-cli install kubernetes [--config FILE] [--namespace TEXT] [--dry-run]
platform-cli install local [--data-dir PATH]
platform-cli install docker [--config FILE]
platform-cli install swarm [--config FILE]
platform-cli install incus [--config FILE]
platform-cli diagnose [--json] [--fix] [--deployment-mode MODE]
platform-cli backup create [--tag TEXT] [--stores TEXT]
platform-cli backup restore <backup-id> [--stores TEXT] [--verify-only]
platform-cli backup list [--json]
platform-cli upgrade [--target-version TEXT] [--dry-run]
platform-cli admin users list [--json]
platform-cli admin users create <email> --role ROLE
platform-cli admin status [--json]
```

**Alternatives considered**:
- Click — mature but lacks type annotation-driven argument parsing and Rich integration
- argparse — too low-level for a multi-command CLI with subcommand groups

---

## Decision 3: Helm Integration Strategy

**Decision**: Shell out to the `helm` binary via `subprocess.run()`. No Helm SDK.

**Rationale**: There is no maintained Python Helm SDK. The Helm Go SDK is complex and would require CGo bindings. The `helm` CLI is the canonical interface — operators already have it installed and expect it. The CLI generates a `values.yaml` file (from Jinja2 templates + installer config), then runs `helm upgrade --install` for each chart.

**Helm install sequence** (dependency order from constitution):
1. `platform-data` namespace: postgresql → redis → kafka → qdrant → neo4j → clickhouse → opensearch → minio
2. `platform-execution` namespace: runtime-controller → reasoning-engine
3. `platform-simulation` namespace: simulation-controller
4. `platform-control` namespace: control-plane (all profiles)

**Chart paths**: `deploy/helm/{service-name}/` — the 12 required charts already exist in this repo;
`sandbox-manager` remains optional and can be detected later if the chart is added.

**Wait logic**: After each `helm upgrade --install`, poll `kubectl rollout status deployment/{name}` with a timeout.

**Alternatives considered**:
- pyhelm / helm-python — unmaintained, incomplete API coverage
- Direct Kubernetes API calls — would duplicate what Helm already handles (template rendering, release management, rollback)

---

## Decision 4: Configuration Format

**Decision**: YAML configuration file (`platform-install.yaml`) validated by Pydantic models.

**Rationale**: YAML is the standard format in the Kubernetes ecosystem (Helm values, kube manifests). Operators are familiar with YAML editing. Pydantic models validate the configuration at load time, providing clear error messages for misconfiguration. The config file is optional — sensible defaults are used for everything, and individual values can be overridden via CLI flags or environment variables (Pydantic settings precedence: env vars > CLI flags > config file > defaults).

**Config structure**:
```yaml
deployment_mode: kubernetes
namespace: platform
storage_class: standard
ingress:
  enabled: true
  hostname: platform.example.com
admin:
  email: admin@example.com
secrets:
  generate: true   # auto-generate all, or provide specific values below
resources:
  postgresql:
    replicas: 3
    storage: 50Gi
  # ... per-service resource overrides
```

**Alternatives considered**:
- TOML — less familiar to Kubernetes operators; lacks multi-line string support
- JSON — no comments; harder to hand-edit
- Environment variables only — insufficient for complex nested config; hard to version-control

---

## Decision 5: Secret Generation

**Decision**: Python `secrets` module for cryptographic random generation. Passwords are 32-character alphanumeric. The API signing key is a 4096-bit RSA key pair generated via `cryptography`.

**Rationale**: The `secrets` module is the standard library's cryptographically secure random generator. Generated secrets are stored in Kubernetes Secrets (for k8s mode), `.env` files (for Docker/Swarm), or `~/.platform-cli/secrets/` (for local mode). Secrets are never printed to the terminal except the one-time admin password.

**Secrets generated**:
- Admin user password (displayed once)
- PostgreSQL superuser password
- Redis authentication password
- Neo4j password
- ClickHouse admin password
- OpenSearch admin password
- MinIO root credentials (access key + secret key)
- JWT RS256 signing key pair (PEM)

**Alternatives considered**:
- External secret manager (Vault, AWS Secrets Manager) — over-engineered for first install; can be added as an option later
- Let operators provide all secrets — too much friction for first install; the `--secrets-from` flag is an option for advanced operators

---

## Decision 6: Checkpoint / Resume Mechanism

**Decision**: JSON checkpoint file at `~/.platform-cli/checkpoints/{install-id}.json` recording completed steps.

**Rationale**: Installation involves ~20 sequential steps across 12+ services. Network failures, transient errors, and timeouts are common in Kubernetes environments. Rather than restarting from scratch, the CLI records each completed step in a checkpoint file. On `--resume`, it skips completed steps and resumes from the first incomplete one. The checkpoint includes the full configuration used, so configuration drift between attempts is detected.

**Checkpoint schema** (simplified):
```json
{
  "installId": "uuid",
  "startedAt": "ISO8601",
  "config": { ... },
  "steps": [
    { "name": "preflight", "status": "completed", "completedAt": "..." },
    { "name": "secrets-generate", "status": "completed", "completedAt": "..." },
    { "name": "helm-postgresql", "status": "failed", "error": "timeout", "failedAt": "..." }
  ]
}
```

**Alternatives considered**:
- No resume — unacceptable for 15-minute installations that fail at step 11 of 20
- Database-backed checkpoint — the database may not exist yet during installation

---

## Decision 7: Distributed Lock

**Decision**: Kubernetes ConfigMap lease for k8s mode; file lock (`fcntl.flock`) for local/Docker modes.

**Rationale**: The spec requires preventing concurrent installations on the same target. In Kubernetes, a ConfigMap in the target namespace serves as a lock (create with a unique holder ID; delete on completion/timeout). For local/Docker modes, a file lock at `~/.platform-cli/install.lock` prevents concurrent processes. Lock timeout is 30 minutes (matches max expected install duration).

**Alternatives considered**:
- Kubernetes Lease API — more semantically correct but not available in all RBAC configurations
- Redis lock — Redis may not exist yet during installation

---

## Decision 8: PyInstaller Packaging

**Decision**: PyInstaller spec file for building a standalone binary. One binary per target platform (linux-amd64, linux-arm64, darwin-amd64, darwin-arm64).

**Rationale**: Operators need the CLI without installing Python. PyInstaller bundles the Python interpreter, all dependencies, and the CLI code into a single executable. The spec file explicitly lists hidden imports (Pydantic, Rich, cryptography) to avoid runtime import failures. GitHub Actions builds the binary for each platform on release tags.

**Alternatives considered**:
- Nuitka — faster binaries but harder to configure for complex dependency trees
- Docker-based CLI — requires Docker installed, which defeats the purpose for initial Docker installation
- pip install — acceptable as a secondary distribution channel but requires Python 3.12+

---

## Decision 9: Local Mode Implementation

**Decision**: The local installer starts the control plane monolith as a subprocess with overridden environment variables pointing to local fallbacks. It does not embed the monolith in the CLI process.

**Rationale**: The control plane already supports profile-based startup via `create_app(profile)`. The local installer:
1. Creates a local data directory (`~/.platform-cli/data/`)
2. Initializes an SQLite database (replacing PostgreSQL)
3. Starts an in-memory Qdrant instance (single-node, no persistence) as a subprocess
4. Sets environment variables to point the monolith at local resources
5. Starts the monolith process with `profile=api` and all worker profiles enabled

The CLI manages the process lifecycle — start, stop, status — via PID file tracking.

**Local mode services** (per constitution):
| Production | Local Fallback | How |
|---|---|---|
| PostgreSQL | SQLite | `DATABASE_URL=sqlite+aiosqlite:///~/.platform-cli/data/platform.db` |
| Qdrant | In-memory | `qdrant` binary with `--storage :memory:` |
| Redis | In-process dict | `REDIS_TEST_MODE=standalone` + `fakeredis` |
| Neo4j | SQLite CTEs | Adapter layer (planned, not in this feature) |
| ClickHouse | SQLite | Adapter layer (planned, not in this feature) |
| OpenSearch | SQLite FTS5 | Adapter layer (planned, not in this feature) |
| Kafka | asyncio Queue | `KAFKA_MODE=local` (in-process queue in monolith) |
| MinIO | Filesystem | `MINIO_ENDPOINT=file:///~/.platform-cli/data/storage/` |
| Reasoning engine | Subprocess | Start Go binary from `services/reasoning-engine/` |

**Alternatives considered**:
- Docker Compose for "local" mode — too slow to start (>30s), requires Docker
- Embedding the monolith in the CLI — couples the CLI to the full monolith dependency tree; breaks standalone binary packaging

---

## Decision 10: Backup Orchestration Strategy

**Decision**: Per-store backup modules that call each store's native backup tool. The orchestrator runs them sequentially (for consistency) and uploads artifacts to a configurable backup location.

**Backup tools per store**:
| Store | Backup Method | Tool |
|---|---|---|
| PostgreSQL | Logical dump | `pg_dump` via subprocess |
| Redis | RDB snapshot | `redis-cli BGSAVE` + copy RDB file |
| Kafka | Topic offsets only | Store consumer group offsets (data is ephemeral) |
| Qdrant | Collection snapshot | Qdrant HTTP API `POST /collections/{name}/snapshots` |
| Neo4j | Database dump | `neo4j-admin database dump` via subprocess |
| ClickHouse | Native backup | `clickhouse-backup` tool via subprocess |
| OpenSearch | Repository snapshot | OpenSearch snapshot API (MinIO as snapshot repository) |
| MinIO | Mirror | `mc mirror` or direct S3 copy |

**Backup storage**: Configurable — MinIO bucket (default), local directory, or S3-compatible remote.

**Alternatives considered**:
- Volume snapshots (Kubernetes CSI) — not portable across storage providers; doesn't support selective restore
- Application-level backup (read all data via API) — too slow and incomplete for large data stores

---

## Decision 11: Diagnostic Health Checks

**Decision**: Concurrent health checks using `asyncio.gather()`. Each check is a separate async function with a 5-second timeout. Results are aggregated and displayed as a table (Rich) or JSON.

**Checks performed**:
1. PostgreSQL: `SELECT 1` via `asyncpg`
2. Redis: `PING` via `redis-py`
3. Kafka: `AdminClient.list_topics()` via `aiokafka`
4. Qdrant: `GET /healthz` via `httpx`
5. Neo4j: `RETURN 1` via `neo4j-driver`
6. ClickHouse: `SELECT 1` via `clickhouse-connect`
7. OpenSearch: `GET /_cluster/health` via `httpx`
8. MinIO: `HEAD` bucket via `boto3`
9. Runtime Controller: gRPC health check on port 50051
10. Reasoning Engine: gRPC health check on port 50052
11. Sandbox Manager: gRPC health check on port 50053
12. Simulation Controller: gRPC health check on port 50055
13. Model providers: HTTP health check on configured endpoints

**Auto-remediation (`--fix`)**:
- Restart failed Kubernetes deployments (`kubectl rollout restart`)
- Clear stuck Redis locks
- Recreate missing Kafka topics

**Alternatives considered**:
- Polling the control plane's `/health` endpoint — not available during initial installation or when the control plane is down
- Sequential checks — too slow; 13 checks × 5s timeout = 65s exceeds the 30s requirement

---

## Decision 12: Output Formatting

**Decision**: Rich library for interactive terminal output; JSON for `--json` flag (headless mode).

**Rationale**: Rich provides tables, progress bars, spinners, color-coded status labels, and tree displays out of the box. The `--json` flag switches all output to newline-delimited JSON (NDJSON) for CI/CD pipeline consumption. Exit codes follow Unix convention: 0=success, 1=general error, 2=preflight failure, 3=partial failure (some components failed).

**Alternatives considered**:
- Plain text only — too hard to scan for operators; no progress indication
- YAML output — less standard than JSON for machine consumption
