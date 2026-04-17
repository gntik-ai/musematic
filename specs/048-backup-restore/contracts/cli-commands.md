# CLI Command Contracts: Backup and Restore

**Feature**: [spec.md](../spec.md)  
**Generated**: 2026-04-17

All commands live under the `backup` sub-app registered in `apps/ops-cli/src/platform_cli/main.py`.

---

## `platform-cli backup create`

```
Usage: platform-cli backup create [OPTIONS]

  Create a full platform backup of all 8 data stores.

Options:
  --tag TEXT                  Custom backup tag (alphanumeric, hyphens, underscores).
                              Auto-generated as backup-{YYYYMMDD-HHMMSS}-{NNN} if omitted.
  --storage-location TEXT     Override backup storage path or S3 URL.
                              [env: PLATFORM_CLI_BACKUP_STORAGE]
  --force                     Skip active-execution check and proceed anyway.
  --help                      Show this message and exit.

Exit codes:
  0   All stores backed up (status: completed)
  3   One or more stores failed (status: partial)   [ExitCode.PARTIAL_FAILURE]
  1   All stores failed or lock could not be acquired
```

**Normal output (Rich)**:
```
Creating backup backup-20260417-020000-001
  ✓ postgresql   completed  (12.3s)
  ✓ qdrant       completed   (4.1s)
  ✓ neo4j        completed   (8.7s)
  ✓ clickhouse   completed  (11.2s)
  ✓ redis        completed   (0.8s)
  ✓ opensearch   completed   (6.3s)
  ✓ kafka        completed   (0.4s)
  ✓ minio        completed  (22.5s)

Backup bkp-<uuid> created — status: completed — 66.3s total
```

**JSON/headless output (NDJSON event)**:
```json
{
  "stage": "backup-create",
  "status": "completed",
  "message": "backup created",
  "details": {
    "backup_id": "bkp-...",
    "tag": "backup-20260417-020000-001",
    "schema_version": 1,
    "status": "completed",
    "total_size_bytes": 1073741824,
    "total_duration_seconds": 66.3,
    "artifacts": [
      {
        "store": "postgresql",
        "display_name": "PostgreSQL",
        "path": "/home/operator/.platform-cli/data/backups/bkp-.../postgresql/postgresql.dump",
        "size_bytes": 524288000,
        "checksum_sha256": "a3f...",
        "format": "pg_dump",
        "duration_seconds": 12.3,
        "created_at": "2026-04-17T02:00:12+00:00"
      }
    ]
  }
}
```

**Constraint**: The `--stores` flag (partial backup creation) is NOT available. Full backup only.

---

## `platform-cli backup restore <backup-id>`

```
Usage: platform-cli backup restore [OPTIONS] BACKUP_ID

  Restore the platform from a backup. Verifies all checksums before modifying any store.

Arguments:
  BACKUP_ID  The backup identifier (e.g., bkp-<uuid> or tag).   [required]

Options:
  --stores TEXT   Comma-separated store names for partial restore.
                  Example: --stores postgresql,redis
  --yes, -y       Skip confirmation prompt (for automation).
  --help          Show this message and exit.

Exit codes:
  0   All selected stores restored successfully
  1   Checksum verification failed (no stores modified) or restore error
```

**Interactive confirmation (unless --yes)**:
```
The following stores will be restored from backup bkp-<uuid> (tag: backup-20260417-020000-001):
  • postgresql
  • qdrant
  • neo4j
  • clickhouse
  • redis
  • opensearch
  • kafka
  • minio

Warning: This will overwrite current data. Continue? [y/N]:
```

**Verification failure**:
```
✗ Checksum mismatch for store: opensearch
  Expected: a3f4...
  Got:      deadbeef...
Aborting restore — no stores have been modified.
```

**JSON/headless output**:
```json
{
  "stage": "backup-restore",
  "status": "completed",
  "message": "backup restored",
  "details": {
    "backup_id": "bkp-...",
    "stores_restored": ["minio", "kafka", "opensearch", "redis", "clickhouse", "neo4j", "qdrant", "postgresql"],
    "verify_only": false
  }
}
```

---

## `platform-cli backup verify <backup-id>`

```
Usage: platform-cli backup verify [OPTIONS] BACKUP_ID

  Verify backup integrity without restoring any data.

Arguments:
  BACKUP_ID  [required]

Options:
  --help  Show this message and exit.

Exit codes:
  0   All artifacts verified (checksums match)
  1   One or more checksums failed or artifacts missing
```

**Normal output**:
```
Verifying backup bkp-<uuid>
  ✓ postgresql   sha256 ok
  ✓ qdrant       sha256 ok
  ✓ neo4j        sha256 ok
  ✓ clickhouse   sha256 ok
  ✓ redis        sha256 ok
  ✓ opensearch   sha256 ok
  ✓ kafka        sha256 ok
  ✓ minio        sha256 ok

All 8 artifacts verified successfully.
```

**JSON/headless output**:
```json
{
  "stage": "backup-verify",
  "status": "completed",
  "message": "backup verified",
  "details": {
    "backup_id": "bkp-...",
    "results": [
      {"store": "postgresql", "ok": true},
      {"store": "opensearch", "ok": false, "error": "file missing"}
    ]
  }
}
```

---

## `platform-cli backup list`

```
Usage: platform-cli backup list [OPTIONS]

  List available backups sorted by creation date (newest first).

Options:
  --limit INTEGER  Maximum number of backups to show.   [default: 20]
  --help           Show this message and exit.
```

**Normal output (Rich table)**:
```
 #    Tag                          Created                    Size      Stores   Status
─────────────────────────────────────────────────────────────────────────────────────
 001  backup-20260417-020000-001   2026-04-17 02:00:00 UTC    1.0 GiB   8/8      completed
 002  backup-20260416-020000-002   2026-04-16 02:00:01 UTC    998 MiB   8/8      completed
```

**JSON/headless output**:
```json
{
  "stage": "backup-list",
  "status": "completed",
  "message": "listed backups",
  "details": {
    "count": 2,
    "items": [
      {
        "backup_id": "bkp-...",
        "tag": "backup-20260417-020000-001",
        "created_at": "2026-04-17T02:00:00+00:00",
        "total_size_bytes": 1073741824,
        "store_count": 8,
        "status": "completed"
      }
    ]
  }
}
```

---

## `platform-cli backup schedule start`

```
Usage: platform-cli backup schedule start [OPTIONS]

  Start the backup scheduler as a blocking process (daemon mode).

Options:
  --cron TEXT               Cron expression for backup schedule.   [required]
                            Example: "0 2 * * *" (daily at 2 AM)
  --retention-days INTEGER  Delete backups older than N days.      [default: 30]
  --storage-location TEXT   Override backup storage path or S3 URL.
  --help                    Show this message and exit.
```

## `platform-cli backup schedule run-once`

```
Usage: platform-cli backup schedule run-once [OPTIONS]

  Run one scheduled backup immediately (for cron/systemd integration).

Options:
  --retention-days INTEGER   [default: 30]
  --storage-location TEXT
  --help
```

---

## Lock Behavior Contract

| Deployment Mode | Lock Mechanism | Lock Name | Timeout |
|---|---|---|---|
| `kubernetes` | ConfigMap (`kubectl`) | `platform-backup-lock` | 60 min |
| `docker`, `swarm`, `incus`, `local` | File lock | `~/.platform-cli/backup.lock` | 60 min |

If lock acquisition fails, the command exits with code 1 and message:
```
A backup is already in progress (or a previous backup lock was not released).
Run with --force to override the stale lock.
```

`--force` on `backup create` bypasses both the active-execution check AND releases any stale lock before acquiring.
