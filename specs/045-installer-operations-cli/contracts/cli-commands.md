# CLI Command Contracts: Installer and Operations CLI

**Phase**: Phase 1 — Design  
**Feature**: [../spec.md](../spec.md)

---

## Command Entry Point

```
platform-cli [GLOBAL OPTIONS] COMMAND [SUBCOMMAND] [COMMAND OPTIONS]
```

**Global Options**:

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--config` | PATH | `platform-install.yaml` in CWD | Path to installer config YAML |
| `--verbose` / `-v` | FLAG | false | Verbose output (debug logging) |
| `--json` | FLAG | false | Machine-readable JSON output (NDJSON for streaming) |
| `--no-color` | FLAG | false | Disable Rich color/style output |

---

## install

**Purpose**: Deploy the platform to the target infrastructure.

### install kubernetes

```
platform-cli install kubernetes [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--namespace` | TEXT | `platform` | Kubernetes namespace prefix |
| `--storage-class` | TEXT | `standard` | StorageClass for PVCs |
| `--dry-run` | FLAG | false | Generate manifests without applying |
| `--resume` | FLAG | false | Resume from last checkpoint |
| `--air-gapped` | FLAG | false | Use local registry for images |
| `--local-registry` | TEXT | — | Local registry URL (required if air-gapped) |
| `--image-tag` | TEXT | `latest` | Container image tag |
| `--skip-preflight` | FLAG | false | Skip preflight checks (dangerous) |
| `--skip-migrations` | FLAG | false | Skip schema migrations |

**Output** (interactive):
```
✓ Preflight checks passed (4/4)
✓ Secrets generated (8 credentials + JWT key pair)
✓ [1/12] PostgreSQL deployed (platform-data)          [32s]
✓ [2/12] Redis deployed (platform-data)               [18s]
...
✓ [12/12] Control Plane deployed (platform-control)    [45s]
✓ Schema migrations completed
✓ Admin user created

┌─────────────────────────────────────────┐
│  Admin Credentials (shown once only!)   │
│  Email:    admin@platform.local         │
│  Password: <generated-password>         │
│  URL:      https://platform.local       │
└─────────────────────────────────────────┘

Installation completed in 8m 42s
```

**Output** (JSON):
```json
{"stage": "preflight", "status": "passed", "checks": 4}
{"stage": "secrets", "status": "generated", "count": 9}
{"stage": "deploy", "component": "postgresql", "status": "ready", "duration_s": 32}
...
{"stage": "complete", "duration_s": 522, "admin_email": "admin@platform.local", "admin_password": "..."}
```

**Exit codes**: 0=success, 1=error, 2=preflight failure

---

### install local

```
platform-cli install local [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--data-dir` | PATH | `~/.platform-cli/data` | Directory for SQLite, object storage, logs |
| `--port` | INT | `8000` | Port for the local platform API |
| `--foreground` | FLAG | false | Run in foreground (don't daemonize) |

**Output** (interactive):
```
✓ Data directory initialized: ~/.platform-cli/data
✓ SQLite database created
✓ In-memory Qdrant started
✓ Local storage directories created
✓ Control plane starting...
✓ Platform ready at http://localhost:8000

Admin credentials:
  Email:    admin@localhost
  Password: <generated-password>

Started in 12s. Press Ctrl+C to stop (or use: platform-cli admin stop)
```

**Exit codes**: 0=success, 1=error

---

### install docker

```
platform-cli install docker [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--compose-file` | PATH | `docker-compose.yml` | Output path for generated Compose file |
| `--project-name` | TEXT | `platform` | Docker Compose project name |

**Behavior**: Generates `docker-compose.yml` from templates + config, then runs `docker compose up -d`. Waits for all services healthy. Runs migrations. Creates admin user.

---

### install swarm

```
platform-cli install swarm [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--stack-name` | TEXT | `platform` | Docker Swarm stack name |

**Behavior**: Generates stack YAML, runs `docker stack deploy`. Similar flow to Docker but with Swarm service definitions.

---

### install incus

```
platform-cli install incus [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--profile` | TEXT | `platform` | Incus profile name |

**Behavior**: Creates Incus container profiles, launches containers, runs setup scripts inside containers.

---

## diagnose

```
platform-cli diagnose [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--deployment-mode` | TEXT | auto-detect | Force deployment mode for connection config |
| `--fix` | FLAG | false | Attempt auto-remediation for known issues |
| `--timeout` | INT | `5` | Per-check timeout in seconds |
| `--checks` | TEXT | — | Comma-separated list of specific checks to run |

**Output** (interactive):
```
Platform Diagnostics
────────────────────────────────────────────
 Data Stores
  ✓ PostgreSQL     healthy    3ms
  ✓ Redis          healthy    1ms
  ✓ Kafka          healthy    12ms
  ✓ Qdrant         healthy    5ms
  ✗ Neo4j          unhealthy  —     Connection refused
  ✓ ClickHouse     healthy    8ms
  ✓ OpenSearch     healthy    15ms
  ✓ MinIO          healthy    4ms

 Satellite Services
  ✓ Runtime Controller        healthy    2ms
  ✓ Reasoning Engine          healthy    3ms
  ✓ Sandbox Manager           healthy    2ms
  ✓ Simulation Controller     healthy    4ms

 Model Providers
  ✓ Anthropic API             healthy    89ms

Overall: DEGRADED (12/13 healthy)
Completed in 2.3s
```

**Output** (JSON):
```json
{
  "deployment_mode": "kubernetes",
  "checked_at": "2026-04-16T14:30:00Z",
  "duration_seconds": 2.3,
  "overall_status": "degraded",
  "checks": [
    {"component": "postgresql", "status": "healthy", "latency_ms": 3},
    {"component": "neo4j", "status": "unhealthy", "error": "Connection refused", "remediation": "Check neo4j pod status: kubectl -n platform-data get pods -l app=neo4j"}
  ]
}
```

**Exit codes**: 0=all healthy, 1=error, 3=some degraded/unhealthy

---

## backup

### backup create

```
platform-cli backup create [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--tag` | TEXT | — | Human-readable label for this backup |
| `--stores` | TEXT | all | Comma-separated list of stores to back up |
| `--storage-location` | TEXT | from config | Override backup storage URI |
| `--force` | FLAG | false | Proceed even with active executions |

**Output** (interactive):
```
Creating backup #42 (tag: pre-upgrade)
  ✓ PostgreSQL     pg_dump      1.2 GB   [45s]
  ✓ Redis          RDB snapshot 256 MB   [3s]
  ✓ Qdrant         snapshot     890 MB   [12s]
  ✓ Neo4j          dump         340 MB   [8s]
  ✓ ClickHouse     native       2.1 GB   [30s]
  ✓ OpenSearch     snapshot     1.5 GB   [20s]
  ✓ MinIO          mirror       4.2 GB   [60s]

Backup completed: 10.5 GB total
ID: bkp-20260416-143000-042
Stored at: s3://platform-backups/bkp-20260416-143000-042/
Checksums verified ✓
```

**Exit codes**: 0=success, 1=error, 3=partial (some stores failed)

---

### backup restore

```
platform-cli backup restore <BACKUP_ID> [OPTIONS]
```

| Argument/Flag | Type | Default | Description |
|------|------|---------|-------------|
| `BACKUP_ID` | TEXT (required) | — | Backup identifier |
| `--stores` | TEXT | all | Comma-separated list of stores to restore |
| `--verify-only` | FLAG | false | Only verify checksums, don't restore |
| `--force` | FLAG | false | Skip confirmation prompt |

**Exit codes**: 0=success, 1=error (including checksum failure)

---

### backup list

```
platform-cli backup list [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--limit` | INT | `20` | Maximum backups to display |

**Output** (interactive):
```
Available Backups
──────────────────────────────────────────────
 #   ID                          Tag            Size     Date
 42  bkp-20260416-143000-042     pre-upgrade    10.5 GB  2026-04-16 14:30
 41  bkp-20260415-020000-041     daily          9.8 GB   2026-04-15 02:00
 40  bkp-20260414-020000-040     daily          9.7 GB   2026-04-14 02:00
```

---

## upgrade

```
platform-cli upgrade [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--target-version` | TEXT | latest | Version to upgrade to |
| `--dry-run` | FLAG | false | Show upgrade plan without applying |
| `--skip-backup` | FLAG | false | Skip pre-upgrade backup (dangerous) |
| `--force` | FLAG | false | Skip confirmation prompt |

**Behavior**: Detects current version → computes upgrade plan → creates pre-upgrade backup (unless skipped) → rolling upgrade in dependency order → run migrations → verify health.

**Exit codes**: 0=success, 1=error, 3=partial (upgrade halted mid-way)

---

## admin

### admin users list

```
platform-cli admin users list [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--role` | TEXT | — | Filter by role |
| `--status` | TEXT | — | Filter by status |

### admin users create

```
platform-cli admin users create <EMAIL> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--role` | TEXT (required) | — | User role |
| `--password` | TEXT | — | Password (generated if omitted) |

### admin status

```
platform-cli admin status [OPTIONS]
```

**Output**: Platform version, deployment mode, component count, active executions, uptime.

### admin stop (local mode only)

```
platform-cli admin stop
```

**Behavior**: Stops the local platform process (by PID file). Only available in local deployment mode.

---

## Environment Variables

All CLI flags can be set via environment variables with `PLATFORM_CLI_` prefix:

| Environment Variable | Maps To |
|---------------------|---------|
| `PLATFORM_CLI_CONFIG` | `--config` |
| `PLATFORM_CLI_DEPLOYMENT_MODE` | `--deployment-mode` |
| `PLATFORM_CLI_NAMESPACE` | `--namespace` |
| `PLATFORM_CLI_STORAGE_CLASS` | `--storage-class` |
| `PLATFORM_CLI_IMAGE_TAG` | `--image-tag` |
| `PLATFORM_CLI_JSON` | `--json` |
| `PLATFORM_CLI_VERBOSE` | `--verbose` |
| `PLATFORM_CLI_DATA_DIR` | `--data-dir` |
| `PLATFORM_CLI_BACKUP_STORAGE` | `--storage-location` |

---

## Structured Log Format (headless mode)

When `--json` is enabled, each output line is a JSON object:

```typescript
{
  "timestamp": string,        // ISO 8601
  "level": "info" | "warning" | "error",
  "stage": string,            // "preflight" | "secrets" | "deploy" | "migrate" | "complete"
  "component": string | null, // component name when applicable
  "status": string,           // "started" | "completed" | "failed" | "skipped"
  "message": string,
  "details": object | null    // additional structured data
}
```
