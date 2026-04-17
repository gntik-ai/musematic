# Research: Backup and Restore

**Feature**: [spec.md](spec.md)  
**Generated**: 2026-04-17  
**Status**: Complete — all unknowns resolved

---

## Decision 1: Kafka Consumer Group Offset Backup

**Decision**: Use `aiokafka.AIOKafkaAdminClient` to list all consumer groups and export their
committed offsets as a JSON file. No native CLI tool (like `kafka-consumer-groups.sh`) is
assumed available. The `KafkaBackup` store calls `list_consumer_groups()` + `list_consumer_group_offsets()` and serialises the result.

**Rationale**: The spec explicitly limits Kafka backup to consumer group offsets — topic data is
ephemeral by design. The ops-cli already depends on `aiokafka` (feature 003 installed it
project-wide). Using `aiokafka.AIOKafkaAdminClient` keeps the backup in-process, requires no
extra CLI binaries, and produces a deterministic JSON artifact that round-trips cleanly.

**Alternatives considered**:
- `kafka-consumer-groups.sh` shell script: requires the Kafka broker CLI tools installed on the
  operator machine — fragile across deployment modes.
- `confluent-kafka-go` via subprocess: requires Go binary, out of place in a Python CLI.

---

## Decision 2: Dependency Ordering for Backup and Restore

**Decision**: Hard-code the backup order as:

```
postgresql → qdrant → neo4j → clickhouse → redis → opensearch → kafka → minio
```

Restore order is exactly reversed:

```
minio → kafka → opensearch → redis → clickhouse → neo4j → qdrant → postgresql
```

**Rationale**: PostgreSQL is the system of record (FK relationships, authoritative IDs). All
other stores hold derivative or indexed data. MinIO holds artifacts referenced by FK in
PostgreSQL, so it must be restored first so object references are valid when PostgreSQL is
restored last. Redis holds cached/hot state derived from PostgreSQL and Kafka, so it can be
re-warmed from application logic. Kafka offsets must be restored before application services
start consuming, which happens only after the primary stores are in place.

**Alternatives considered**: Topological sort from declared dependencies — over-engineered; the
ordering for these 8 stores is stable and well-understood from the architecture.

---

## Decision 3: Auto-Tag Generation

**Decision**: When no custom tag is supplied, generate a tag using the format
`backup-{YYYYMMDD-HHMMSS}-{NNN}` where `NNN` is a zero-padded 3-digit sequence number
(count of existing manifests + 1). The tag is written into `BackupManifest.tag`.

**Rationale**: The spec (FR-005) mandates this exact format. The sequence number gives
operators a short, human-scannable identifier. Timestamp ensures lexicographic sort = 
chronological sort.

**Alternatives considered**: UUID-only tag — not human-readable; ISO 8601 only — no short
sequential label.

---

## Decision 4: Custom Tag Validation

**Decision**: If a custom tag is supplied, validate it against the regex `^[a-zA-Z0-9_-]+$`.
Raise `ValueError` before any backup work starts if the tag is invalid.

**Rationale**: Spec (US1 AS-5) requires alphanumeric, hyphens, and underscores only. Early
validation prevents writing a manifest with an invalid tag to storage.

---

## Decision 5: Distributed Lock Integration

**Decision**: Wire the existing `KubernetesLock` / `FileLock` into `BackupOrchestrator.create()`
before any store backup begins. Use a new dedicated lock name `platform-backup-lock` (distinct
from `platform-install-lock`). Release the lock in a `finally` block after all stores complete.
The mode selector matches `InstallerConfig.deployment_mode`: Kubernetes → `KubernetesLock`,
all others → `FileLock`.

**Rationale**: FR-007 requires preventing concurrent backup operations. The lock module already
exists from feature 045 and is the correct abstraction.

**Alternatives considered**: Redis-based distributed lock — requires Redis to be healthy, but
backup should run even when Redis is suspect. ConfigMap/file lock operates independently.

---

## Decision 6: Duration Tracking per Store Artifact

**Decision**: Extend `BackupArtifact` with a `duration_seconds: float` field. Each per-store
backup measures wall-clock time (`time.monotonic()` start/end) and injects it via `build_artifact()`.
Add `total_duration_seconds: float` to `BackupManifest`.

**Rationale**: FR-018 requires duration logging for operational planning. All existing stores
already have async `backup()` methods — adding timing around each call is non-invasive.

---

## Decision 7: Schema Version in Manifest

**Decision**: Add `schema_version: int = 1` to `BackupManifest`. The restore command checks the
manifest's `schema_version`; if it exceeds the CLI's supported version, it errors with a
message suggesting a CLI upgrade.

**Rationale**: Spec assumption states that the schema version enables forward compatibility.
Starting at 1 and keeping it a simple integer avoids semver complexity.

---

## Decision 8: Remote Artifact Upload to MinIO

**Decision**: After all local artifacts are written, if `InstallerConfig.backup_storage` starts
with `s3://` or `minio://`, upload all artifacts to the designated bucket using `aioboto3`.
Update each `BackupArtifact.path` to the remote S3 key. The default storage remains local (no
upload required for local/docker/incus modes).

**Rationale**: FR-006 requires a configurable storage location. MinIO is the project's object
store (feature 004). Using `aioboto3` is consistent with the stack (feature 004 + 013 use it).

**Alternatives considered**: `mc` CLI subprocess — fragile, depends on mc being installed and
configured; using httpx directly — more code than aioboto3 already provides.

---

## Decision 9: `verify` Subcommand

**Decision**: Add a new `platform-cli backup verify <backup_id>` subcommand that calls
`orchestrator.restore(backup_id, verify_only=True)`. This is a thin wrapper over the existing
`verify_only` path, exposed as a first-class command rather than a hidden flag.

**Rationale**: The spec (US5) defines verification as a distinct user action. Making it a
subcommand matches the operator mental model and avoids confusion with `restore`.

---

## Decision 10: Confirmation Prompt Before Restore

**Decision**: The `backup restore` command calls `typer.confirm()` (Rich-backed) before
proceeding, listing the stores to be restored. Add a `--yes` / `-y` flag to bypass the prompt
for scripted/automation use.

**Rationale**: FR-011 requires explicit operator confirmation. The `--yes` bypass is standard
CLI UX and required for automation pipelines.

---

## Decision 11: Rich Progress Display

**Decision**: Use `rich.progress.Progress` in the orchestrator's `create()` and `restore()`
methods to show a per-store progress row with store name, status (spinner → completed/failed),
and elapsed time. A `headless` parameter suppresses Rich output when `json_output=True`.

**Rationale**: US1 AS-6 and US2 AS-5 require real-time terminal progress. Rich is already
imported in `output/console.py`.

---

## Decision 12: Scheduled Backup Implementation

**Decision**: Add a `BackupScheduler` class in `backup/scheduler.py` using `APScheduler 3.x`
(`BlockingScheduler` for standalone process, `AsyncScheduler` for async context). Configuration
is read from `InstallerConfig` (add `backup_schedule_cron: str | None` and
`backup_retention_days: int = 30`). Two new CLI commands: `backup schedule start` (blocks) and
`backup schedule run-once` (for cron/systemd integration). After each successful backup,
prune manifests older than retention window.

**Rationale**: US6 requires automated scheduled backups. APScheduler 3.x is already in the
constitution stack. Providing both a blocking `start` mode and a `run-once` mode lets operators
choose between long-running daemon or cron/systemd-triggered execution.

**Alternatives considered**: Kubernetes CronJob — out of scope for the CLI; systemd timer —
requires OS-level setup, not portable.

---

## Decision 13: Integration Test Strategy

**Decision**: Integration tests live in `tests/integration/test_backup_live.py` and use
`pytest` with a `tmp_path` fixture. They mock native tools (pg_dump, mc, etc.) via
`monkeypatch` on `subprocess.run` but start a real in-process `aiokafka` admin client
against a local Kafka broker (if `KAFKA_BOOTSTRAP_SERVERS` env var is set) or skip. Backup
round-trip (create → verify → restore) is tested against the `FakeStore` pattern already
established in `test_backup.py`.

**Rationale**: User implementation step 5 specifies "integration tests with test databases".
The existing unit tests use a `FakeStore` pattern — integration tests extend that with
real subprocess calls where possible, skipping where external dependencies aren't available.

---

## Decision 14: `stores_filter` on `create()` — Removal

**Decision**: Remove the `stores` CLI option from `backup create`. The spec (FR-001, spec
Assumptions) explicitly states "full backup only for creation; partial restore is supported."
The `stores_filter` parameter stays on `BackupOrchestrator.create()` for internal use but
the CLI flag is removed.

**Rationale**: Exposing partial backup in the CLI would contradict the spec scope boundary.
Keeping the internal parameter allows future extension without breaking the contract.
