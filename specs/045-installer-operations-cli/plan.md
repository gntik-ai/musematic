# Implementation Plan: Installer and Operations CLI

**Branch**: `045-installer-operations-cli` | **Date**: 2026-04-16 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/045-installer-operations-cli/spec.md`

## Summary

Standalone Python CLI tool (`apps/ops-cli/`) for platform installation, diagnostics, backup/restore, upgrade, and administration across 5 deployment modes (Kubernetes, Docker, Swarm, Incus, local). Built with Typer + Rich for interactive terminal UX and JSON output for headless CI/CD. Manages 12 platform components (8 data stores, 3 satellite services, 1 control plane) with dependency-ordered deployment, preflight checks, secret generation, schema migrations, checkpoint/resume, distributed locking, and standalone binary distribution via PyInstaller.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: Typer 0.12+ (CLI), Rich (terminal UX), Pydantic v2 (config), PyYAML (config files), Jinja2 (Helm values), httpx (HTTP checks), grpcio (gRPC checks), asyncpg (PostgreSQL check), cryptography (RSA keys), aioboto3 (MinIO), PyInstaller (binary build)  
**Storage**: JSON files (checkpoints, manifests); no database owned by CLI  
**Testing**: pytest + pytest-asyncio 8.x, ruff 0.7+, mypy 1.11+ strict  
**Target Platform**: Linux (primary), macOS (dev); standalone binary via PyInstaller  
**Project Type**: CLI tool (pip package + standalone binary)  
**Performance Goals**: Kubernetes install <15 minutes; local install <30 seconds; diagnose <30 seconds  
**Constraints**: Must be distributable without Python runtime; must not import control plane modules (independent package); all Helm/kubectl interactions via subprocess  
**Scale/Scope**: Manages 12 components across 5 deployment modes; ~40 source files

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Project location | PASS | `apps/ops-cli/` per constitution repo structure |
| No cross-boundary DB access | PASS | CLI doesn't access bounded context tables; it calls migrations and health endpoints only |
| Secrets never in LLM context | N/A | CLI is not part of the LLM execution path |
| Dedicated data stores | PASS | CLI manages all 8 data stores via their native tools |
| Kubernetes namespace isolation | PASS | Deploys to correct namespaces (platform-data, platform-execution, platform-control, platform-simulation) |
| Local mode fallbacks | PASS | Follows constitution's Local Mode Fallbacks table exactly |
| Quality gates | PASS | pytest ≥95% coverage, ruff, mypy strict |
| Python conventions | PASS | async where needed, type annotations, docstrings, Pydantic |
| Helm charts | PASS | Uses existing charts in `deploy/helm/` |

## Project Structure

### Documentation (this feature)

```text
specs/045-installer-operations-cli/
├── plan.md              # This file
├── spec.md              # 8 user stories
├── research.md          # 12 decisions
├── data-model.md        # Python models (Pydantic)
├── quickstart.md        # Setup, commands, tests
├── contracts/
│   └── cli-commands.md  # Full CLI command schemas
└── tasks.md             # Phase 2 output (speckit.tasks)
```

### Source Code

```text
apps/ops-cli/
├── pyproject.toml
├── platform-cli.spec                 # PyInstaller
├── src/platform_cli/
│   ├── __init__.py
│   ├── main.py                       # Typer app entry point
│   ├── config.py                     # InstallerConfig + loader
│   ├── constants.py                  # PLATFORM_COMPONENTS registry
│   ├── commands/
│   │   ├── install.py                # install kubernetes/local/docker/swarm/incus
│   │   ├── diagnose.py               # diagnose [--fix] [--json]
│   │   ├── backup.py                 # backup create/restore/list
│   │   ├── upgrade.py                # upgrade [--target-version]
│   │   └── admin.py                  # admin users/status/stop
│   ├── installers/
│   │   ├── base.py                   # AbstractInstaller protocol
│   │   ├── kubernetes.py             # Preflight → secrets → Helm → migrate → admin
│   │   ├── local.py                  # SQLite + subprocess monolith
│   │   ├── docker.py                 # Docker Compose generator
│   │   ├── swarm.py                  # Swarm stack generator
│   │   └── incus.py                  # Incus profile generator
│   ├── preflight/
│   │   ├── base.py                   # PreflightCheck protocol
│   │   ├── kubernetes.py             # kubectl, namespace, storage class, ingress
│   │   ├── docker.py                 # docker, compose version
│   │   └── local.py                  # disk space, port availability
│   ├── diagnostics/
│   │   ├── checker.py                # DiagnosticRunner (asyncio.gather)
│   │   └── checks/                   # 10 check modules (8 stores + gRPC + model)
│   ├── backup/
│   │   ├── orchestrator.py           # Sequential backup per store
│   │   ├── manifest.py               # Manifest JSON read/write
│   │   └── stores/                   # 7 store-specific backup modules
│   ├── migrations/
│   │   └── runner.py                 # Alembic + init scripts
│   ├── secrets/
│   │   └── generator.py              # Passwords + RSA key pair
│   ├── checkpoint/
│   │   └── manager.py                # JSON checkpoint for resume
│   ├── locking/
│   │   ├── kubernetes.py             # ConfigMap lease
│   │   └── file.py                   # fcntl.flock
│   ├── helm/
│   │   ├── renderer.py               # Jinja2 values rendering
│   │   └── runner.py                 # helm subprocess wrapper
│   └── output/
│       ├── console.py                # Rich console output
│       └── structured.py             # NDJSON structured output
└── tests/
    ├── conftest.py
    ├── unit/                         # ~8 test files
    └── integration/                  # ~2 test files
```

## Implementation Phases

### Phase 1: Package Scaffold + Config + Output

**Goal**: Empty but runnable `platform-cli --help` with config loading.

- Create `apps/ops-cli/pyproject.toml` with all dependencies, entry point `platform-cli = "platform_cli.main:app"`
- Create `src/platform_cli/main.py` with Typer app and command group stubs (install, diagnose, backup, upgrade, admin)
- Create `src/platform_cli/config.py` with `InstallerConfig` Pydantic model + YAML loader + env var binding
- Create `src/platform_cli/constants.py` with `PLATFORM_COMPONENTS` registry (12 components with dependency order)
- Create `src/platform_cli/output/console.py` (Rich-based) + `structured.py` (NDJSON)
- Create all `__init__.py` files for package structure

### Phase 2: Preflight + Secrets + Checkpoint + Locking

**Goal**: Infrastructure modules used by all installers.

- `preflight/base.py` — `PreflightCheck` protocol + `PreflightRunner` that runs checks and reports results
- `preflight/kubernetes.py` — 4 checks: kubectl access, namespace permissions, StorageClass, IngressController
- `preflight/docker.py` — checks: Docker daemon, Compose v2 version
- `preflight/local.py` — checks: disk space, port availability
- `secrets/generator.py` — generate 8 passwords + RSA key pair; store in K8s Secrets / .env / local file
- `checkpoint/manager.py` — write/read/resume JSON checkpoint; detect config drift via SHA-256
- `locking/kubernetes.py` — ConfigMap lease acquire/release with timeout
- `locking/file.py` — fcntl.flock acquire/release

### Phase 3: Helm Integration + Migrations

**Goal**: Core deployment primitives for Kubernetes installer.

- `helm/renderer.py` — Jinja2 template for values.yaml; merge config overrides + generated secrets
- `helm/runner.py` — `helm upgrade --install` subprocess wrapper; `kubectl rollout status` wait loop; timeout handling
- `migrations/runner.py` — invoke Alembic `upgrade head` for PostgreSQL; run init scripts for Qdrant collection, Neo4j constraints, ClickHouse tables, OpenSearch index templates, Kafka topics, MinIO buckets; admin user creation via control plane API

### Phase 4: Kubernetes Installer — US1

**Goal**: `platform-cli install kubernetes` end-to-end.

- `installers/base.py` — `AbstractInstaller` protocol: `preflight()`, `generate_secrets()`, `deploy()`, `migrate()`, `create_admin()`, `verify()`
- `installers/kubernetes.py` — `KubernetesInstaller` implementing the full flow: acquire lock → preflight → secrets → Helm deploy (12 components in order, with wait) → migrate → admin → verify → release lock; checkpoint each step; resume support
- `commands/install.py` — `install kubernetes` Typer command wiring flags to `KubernetesInstaller`
- Wire into `main.py`

### Phase 5: Local Installer — US2

**Goal**: `platform-cli install local` starting platform in <30s.

- `installers/local.py` — `LocalInstaller`: create data dir → init SQLite → start in-memory Qdrant subprocess → set env vars → start monolith subprocess (uvicorn with all profiles) → wait for `/health` → create admin → display credentials; PID file management for stop
- `commands/install.py` — `install local` subcommand
- `commands/admin.py` — `admin stop` for local mode (kill by PID)

### Phase 6: Diagnose Command — US3

**Goal**: `platform-cli diagnose` checking all components in <30s.

- `diagnostics/checker.py` — `DiagnosticRunner`: discover deployment mode → build check list → `asyncio.gather()` all checks with per-check timeout → aggregate results → compute overall status
- `diagnostics/checks/postgresql.py` through `model_providers.py` — 10 check modules
- `diagnostics/checker.py` auto-fix logic (for `--fix`): restart deployments, clear Redis locks, recreate Kafka topics
- `commands/diagnose.py` — Typer command with `--json`, `--fix`, `--timeout` flags

### Phase 7: Backup and Restore — US4

**Goal**: `platform-cli backup create/restore/list`.

- `backup/stores/postgresql.py` through `minio.py` — 7 per-store backup modules calling native tools
- `backup/orchestrator.py` — `BackupOrchestrator`: sequential backup → checksum → upload → manifest; restore: verify checksums → sequential restore
- `backup/manifest.py` — read/write `BackupManifest` JSON to backup storage
- `commands/backup.py` — `backup create`, `backup restore`, `backup list` Typer commands

### Phase 8: Docker / Swarm / Incus Installers — US5

**Goal**: Additional deployment modes.

- `installers/docker.py` — generate `docker-compose.yml` from templates + config; `docker compose up -d`; wait; migrate; admin
- `installers/swarm.py` — generate Swarm stack YAML; `docker stack deploy`
- `installers/incus.py` — create Incus profiles + containers
- `commands/install.py` — wire `install docker`, `install swarm`, `install incus`

### Phase 9: Upgrade Command — US6

**Goal**: `platform-cli upgrade` with rolling upgrades.

- `commands/upgrade.py` — detect current version → compute `UpgradePlan` → pre-upgrade backup → rolling Helm upgrade per component → run pending migrations → verify health → report; halt + rollback instructions on failure

### Phase 10: Admin + Headless + PyInstaller — US7, US8

**Goal**: Admin subcommands, headless mode verification, standalone binary.

- `commands/admin.py` — `admin users list`, `admin users create`, `admin status` calling control plane API
- Verify all commands work with `--json` flag and env-var-only config (no prompts)
- `platform-cli.spec` — PyInstaller spec with hidden imports; GitHub Actions workflow for multi-platform builds

### Phase 11: Tests + Polish

**Goal**: ≥95% test coverage; linting; type checking.

- Unit tests for config, preflight, secrets, checkpoint, diagnostics, backup, helm, output
- Integration test for local install (start/stop cycle)
- Integration test for diagnose against mocked services
- ruff check, mypy strict
- README.md for the package (not the repo)

## Key Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Package location | `apps/ops-cli/` | Constitution repo structure; independent from monolith |
| CLI framework | Typer + Rich | Type-annotated commands; styled terminal output |
| Helm integration | subprocess to `helm` binary | No Python Helm SDK; operators have Helm installed |
| Config format | YAML + Pydantic | Kubernetes ecosystem standard; validated at load |
| Secrets | `secrets` module + `cryptography` RSA | Stdlib CSPRNG; standard RSA for JWT signing |
| Checkpoint | JSON file at `~/.platform-cli/` | DB may not exist during install; simple and portable |
| Distributed lock | K8s ConfigMap lease / file lock | Available before any service is deployed |
| Standalone binary | PyInstaller | No Python required on target; single file distribution |
| Local mode | Subprocess monolith + env var overrides | Reuses existing `create_app()` + profiles |
| Backup strategy | Per-store native tools | Consistent, complete, portable backups |
| Diagnostics | `asyncio.gather()` concurrent checks | Meets <30s requirement (13 checks × 5s timeout) |
| Output | Rich (interactive) / NDJSON (headless) | Best of both worlds for operators and pipelines |
