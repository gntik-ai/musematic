# Data Model: Backup and Restore

**Feature**: [spec.md](spec.md)  
**Generated**: 2026-04-17

No new database tables are introduced by this feature. Backup manifests are stored as JSON files on the local filesystem or in object storage (MinIO bucket). All models are Pydantic (`BaseModel`).

---

## Existing Models (extended)

### `BackupArtifact`

File: `apps/ops-cli/src/platform_cli/models.py`

| Field | Type | Notes |
|---|---|---|
| `store` | `str` | Store key (e.g., `"postgresql"`, `"kafka"`) |
| `display_name` | `str` | Human-readable name |
| `path` | `str` | Local file path or remote S3 key |
| `size_bytes` | `int` | Artifact file size |
| `checksum_sha256` | `str` | SHA-256 hex digest |
| `format` | `str` | Format name (e.g., `"pg_dump"`, `"rdb"`, `"json"`) |
| `created_at` | `str` | ISO 8601 UTC timestamp |
| **`duration_seconds`** | **`float`** | **NEW — wall-clock backup duration** |

**Validation**: `checksum_sha256` must be a 64-character hex string. `size_bytes` ≥ 0. `duration_seconds` ≥ 0.

---

### `BackupManifest`

File: `apps/ops-cli/src/platform_cli/models.py`

| Field | Type | Notes |
|---|---|---|
| `backup_id` | `str` | Unique ID: `bkp-{uuid4}` |
| `tag` | `str \| None` | Human label: `backup-{YYYYMMDD-HHMMSS}-{NNN}` or custom |
| `sequence_number` | `int` | Monotonically increasing (1-based) |
| `deployment_mode` | `DeploymentMode` | Deployment mode at backup time |
| `status` | `BackupStatus` | `completed`, `partial`, `failed`, `in_progress` |
| `created_at` | `str` | ISO 8601 UTC timestamp |
| `completed_at` | `str \| None` | ISO 8601 UTC timestamp on completion |
| `artifacts` | `list[BackupArtifact]` | Per-store artifacts (8 max) |
| `total_size_bytes` | `int` | Sum of all artifact sizes |
| `storage_location` | `str` | Local path or S3 prefix for artifacts |
| **`schema_version`** | **`int`** | **NEW — manifest schema version (starts at 1)** |
| **`total_duration_seconds`** | **`float`** | **NEW — total wall-clock duration** |

**Compatibility**: Restore command checks `schema_version ≤ CURRENT_SCHEMA_VERSION = 1`. If schema is newer, aborts with a CLI upgrade suggestion.

---

## New Models

### `BackupScheduleConfig`

File: `apps/ops-cli/src/platform_cli/backup/scheduler.py`  
*(Not persisted — loaded from `InstallerConfig` fields)*

| Field | Type | Notes |
|---|---|---|
| `cron_expression` | `str` | APScheduler cron string (e.g., `"0 2 * * *"`) |
| `retention_days` | `int` | Delete manifests older than N days (default: 30) |
| `storage_location` | `str \| None` | Override storage location for scheduled backups |
| `tag_prefix` | `str` | Prefix for auto-generated scheduled backup tags (default: `"scheduled"`) |

---

### `ScheduledBackupResult`

File: `apps/ops-cli/src/platform_cli/backup/scheduler.py`

| Field | Type | Notes |
|---|---|---|
| `run_at` | `str` | ISO 8601 UTC timestamp of scheduled fire |
| `backup_id` | `str \| None` | ID of created backup (None on failure) |
| `status` | `BackupStatus` | Outcome of the scheduled run |
| `error` | `str \| None` | Error message if status is `failed` |
| `pruned_count` | `int` | Number of old backups deleted in retention sweep |

---

## Kafka Offset Artifact Format

The `KafkaBackup` store produces a JSON file with this structure:

```json
{
  "schema_version": 1,
  "captured_at": "2026-04-17T02:00:00+00:00",
  "bootstrap_servers": "kafka.platform-data.svc.cluster.local:9092",
  "consumer_groups": [
    {
      "group_id": "ws-hub-podname-1234",
      "offsets": [
        {
          "topic": "interaction.events",
          "partition": 0,
          "offset": 142857,
          "metadata": ""
        }
      ]
    }
  ]
}
```

On restore, the offsets are committed back to the Kafka broker via `aiokafka.AIOKafkaAdminClient`. Groups that no longer exist are re-created with the stored offsets.

---

## Backup Manifest File Layout

```
{storage_root}/
├── manifests/
│   ├── bkp-<uuid>.json    ← BackupManifest (one per backup run)
│   └── ...
└── bkp-<uuid>/
    ├── postgresql/
    │   └── postgresql.dump
    ├── redis/
    │   └── redis.rdb
    ├── qdrant/
    │   └── <snapshot-name>.snapshot
    ├── neo4j/
    │   └── neo4j.dump
    ├── clickhouse/
    │   └── platform.clickhouse
    ├── opensearch/
    │   └── <snapshot-name>.json
    ├── kafka/
    │   └── kafka-offsets.json
    └── minio/
        ├── platform-assets/   ← mirrored bucket contents
        └── minio.mirror       ← pointer file for mc restore
```

---

## State Transitions

### `BackupStatus`

```
IN_PROGRESS → COMPLETED   (all stores backed up successfully)
IN_PROGRESS → PARTIAL     (one or more stores failed, at least one succeeded)
IN_PROGRESS → FAILED      (all stores failed or lock acquisition failed)
```

Restore does not create a manifest. It reads and validates an existing manifest.
