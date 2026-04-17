# Quickstart: Installer and Operations CLI

## Prerequisites

- Python 3.12+ (for development; standalone binary requires no Python)
- pip or pipx for package installation
- For Kubernetes mode: kubectl 1.28+, Helm 3.x, cluster access
- For Docker mode: Docker Engine 24+, Docker Compose v2+
- For local mode: no external dependencies

## New Dependencies

**Python packages** (new for `apps/ops-cli/`):

| Package | Version | Purpose |
|---------|---------|---------|
| `typer[all]` | 0.12+ | CLI framework + Rich integration |
| `pydantic` | 2.x | Configuration validation |
| `pydantic-settings` | 2.x | Environment variable binding |
| `PyYAML` | 6.x | Config file parsing |
| `Jinja2` | 3.x | Helm values template rendering |
| `httpx` | 0.27+ | HTTP health checks (async) |
| `asyncpg` | 0.29+ | PostgreSQL health check |
| `redis` | 5.x | Redis health check |
| `grpcio` | 1.65+ | gRPC health checks |
| `grpcio-health-checking` | 1.65+ | gRPC standard health proto |
| `cryptography` | 42+ | RSA key pair generation |
| `aioboto3` | latest | MinIO/S3 operations |

**Build-time only**:

| Package | Version | Purpose |
|---------|---------|---------|
| `PyInstaller` | 6.x | Standalone binary packaging |

**Testing**:

| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | 8.x | Test runner |
| `pytest-asyncio` | 0.23+ | Async test support |
| `pytest-cov` | 5.x | Coverage reporting |
| `ruff` | 0.7+ | Linting |
| `mypy` | 1.11+ | Type checking (strict) |

## Project Setup

```bash
cd apps/ops-cli
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Commands

```bash
# Via installed entry point
platform-cli --help
platform-cli install kubernetes --dry-run
platform-cli install local --port 8000
platform-cli diagnose --json
platform-cli backup create --tag "pre-upgrade"
platform-cli backup list
platform-cli backup restore bkp-20260416-143000-042
platform-cli upgrade --dry-run
platform-cli admin status

# Via Python module
python -m platform_cli install kubernetes --help
```

## Running Tests

```bash
cd apps/ops-cli

# All tests
pytest

# With coverage
pytest --cov=platform_cli --cov-report=term-missing

# Specific test files
pytest tests/unit/test_preflight.py
pytest tests/unit/test_diagnostics.py
pytest tests/integration/test_install_local.py
pytest tests/integration/test_diagnose_live.py

# Linting
ruff check src/ tests/
mypy src/ --strict
```

## Building Standalone Binary

```bash
cd apps/ops-cli
pip install pyinstaller
pyinstaller platform-cli.spec --clean
# Output: dist/platform-cli (single file)
```

## Project Structure

```text
apps/ops-cli/
├── pyproject.toml                    # Package config + dependencies
├── platform-cli.spec                 # PyInstaller build spec
├── src/platform_cli/
│   ├── __init__.py                   # Version constant
│   ├── __main__.py                   # `python -m platform_cli` entry point
│   ├── main.py                       # Typer app, command registration
│   ├── config.py                     # InstallerConfig Pydantic model + loader
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── install.py                # install kubernetes/local/docker/swarm/incus/uninstall
│   │   ├── diagnose.py               # diagnose [--fix] [--json]
│   │   ├── backup.py                 # backup create/restore/list
│   │   ├── upgrade.py                # upgrade [--target-version]
│   │   └── admin.py                  # admin users/status/stop
│   ├── installers/
│   │   ├── __init__.py
│   │   ├── base.py                   # AbstractInstaller protocol
│   │   ├── kubernetes.py             # KubernetesInstaller
│   │   ├── local.py                  # LocalInstaller
│   │   ├── docker.py                 # DockerComposeInstaller
│   │   ├── swarm.py                  # SwarmInstaller
│   │   └── incus.py                  # IncusInstaller
│   ├── preflight/
│   │   ├── __init__.py
│   │   ├── base.py                   # PreflightCheck protocol + runner
│   │   ├── kubernetes.py             # K8s-specific checks
│   │   ├── docker.py                 # Docker-specific checks
│   │   └── local.py                  # Local-mode checks (disk space, ports)
│   ├── diagnostics/
│   │   ├── __init__.py
│   │   ├── checker.py                # DiagnosticRunner (asyncio.gather)
│   │   └── checks/
│   │       ├── __init__.py
│   │       ├── postgresql.py
│   │       ├── redis.py
│   │       ├── kafka.py
│   │       ├── qdrant.py
│   │       ├── neo4j.py
│   │       ├── clickhouse.py
│   │       ├── opensearch.py
│   │       ├── minio.py
│   │       ├── grpc_services.py      # All 4 gRPC satellite checks
│   │       └── model_providers.py
│   ├── backup/
│   │   ├── __init__.py
│   │   ├── orchestrator.py           # BackupOrchestrator
│   │   ├── manifest.py               # BackupManifest read/write
│   │   └── stores/
│   │       ├── __init__.py
│   │       ├── postgresql.py         # pg_dump / pg_restore
│   │       ├── redis.py              # BGSAVE + copy
│   │       ├── qdrant.py             # Snapshot API
│   │       ├── neo4j.py              # neo4j-admin dump/load
│   │       ├── clickhouse.py         # clickhouse-backup
│   │       ├── opensearch.py         # Snapshot API
│   │       └── minio.py              # mc mirror
│   ├── migrations/
│   │   ├── __init__.py
│   │   └── runner.py                 # Alembic invoke + init scripts
│   ├── secrets/
│   │   ├── __init__.py
│   │   └── generator.py              # Cryptographic secret generation
│   ├── checkpoint/
│   │   ├── __init__.py
│   │   └── manager.py                # JSON checkpoint read/write/resume
│   ├── locking/
│   │   ├── __init__.py
│   │   ├── kubernetes.py             # ConfigMap lease lock
│   │   └── file.py                   # fcntl.flock file lock
│   ├── helm/
│   │   ├── __init__.py
│   │   ├── renderer.py               # Jinja2 values.yaml rendering
│   │   └── runner.py                 # helm upgrade --install subprocess
│   └── output/
│       ├── __init__.py
│       ├── console.py                # Rich tables, progress, panels
│       └── structured.py             # NDJSON output formatter
└── tests/
    ├── conftest.py                   # Shared fixtures
    ├── unit/
    │   ├── test_config.py
    │   ├── test_branch_closure.py
    │   ├── test_preflight.py
    │   ├── test_secrets.py
    │   ├── test_checkpoint.py
    │   ├── test_diagnostics.py
    │   ├── test_backup.py
    │   ├── test_helm.py
    │   └── test_output.py
    └── integration/
        ├── test_install_local.py
        └── test_diagnose_live.py
```

Repository-level automation lives in `.github/workflows/build-cli.yml`.

## Key Configuration

**Environment variables** (all prefixed `PLATFORM_CLI_`):

| Variable | Purpose |
|----------|---------|
| `PLATFORM_CLI_CONFIG` | Path to config YAML |
| `PLATFORM_CLI_DEPLOYMENT_MODE` | Override deployment mode |
| `PLATFORM_CLI_NAMESPACE` | Kubernetes namespace prefix |
| `PLATFORM_CLI_DATA_DIR` | Local mode data directory |
| `PLATFORM_CLI_BACKUP_STORAGE` | Backup storage URI |

**Config file**: `platform-install.yaml` (see data-model.md `InstallerConfig`)

## Helm Chart Assumptions

The CLI assumes Helm charts exist at `deploy/helm/{service-name}/` for the components that are
actually present in this repo:

1. `postgresql` (CloudNativePG)
2. `redis` (Bitnami redis-cluster)
3. `kafka` (Strimzi)
4. `qdrant`
5. `neo4j`
6. `clickhouse`
7. `opensearch`
8. `minio`
9. `runtime-controller`
10. `reasoning-engine`
11. `simulation-controller`
12. `control-plane`

Each chart has a `values.yaml` that the CLI overrides via Jinja2-rendered values files.

If a `sandbox-manager` chart appears later under `deploy/helm/sandbox-manager/`, diagnostics will
pick it up automatically and add its gRPC health check without changing the installer registry.
