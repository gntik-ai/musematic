# Quickstart: Backup and Restore

**Feature**: [spec.md](spec.md)

## What This Feature Creates / Modifies

```text
apps/ops-cli/src/platform_cli/
├── backup/
│   ├── manifest.py            MODIFIED — schema_version + total_duration_seconds
│   ├── orchestrator.py        MODIFIED — lock integration, dependency order, auto-tag,
│   │                                     duration tracking, Rich progress
│   ├── scheduler.py           NEW — APScheduler-based scheduled backup + retention pruning
│   └── stores/
│       ├── common.py          MODIFIED — build_artifact() accepts duration_seconds
│       ├── postgresql.py      MODIFIED — duration tracking
│       ├── redis.py           MODIFIED — duration tracking
│       ├── qdrant.py          MODIFIED — duration tracking
│       ├── neo4j.py           MODIFIED — duration tracking
│       ├── clickhouse.py      MODIFIED — duration tracking
│       ├── opensearch.py      MODIFIED — duration tracking
│       ├── minio.py           MODIFIED — duration tracking
│       └── kafka.py           NEW — consumer group offset backup via aiokafka AdminClient
├── commands/
│   └── backup.py              MODIFIED — verify subcommand, --yes flag, remove --stores
│                                          from create, schedule subcommands
└── models.py                  MODIFIED — duration_seconds on BackupArtifact,
                                          schema_version + total_duration_seconds on BackupManifest

apps/ops-cli/tests/
├── unit/
│   ├── test_backup.py         MODIFIED — additional tests for new functionality
│   └── test_backup_scheduler.py  NEW — scheduler unit tests
└── integration/
    └── test_backup_live.py    NEW — round-trip integration tests
```

---

## Running a Full Backup

```bash
# Kubernetes deployment
platform-cli backup create

# With custom tag
platform-cli backup create --tag pre-upgrade-v2.1

# Force-skip active execution check
platform-cli backup create --force

# Headless/scripted (NDJSON events on stdout)
platform-cli --json backup create
```

## Listing Backups

```bash
platform-cli backup list

# Show more entries
platform-cli backup list --limit 50

# Headless
platform-cli --json backup list
```

## Verifying a Backup

```bash
# Verify all checksums without restoring
platform-cli backup verify bkp-<uuid>

# Or by tag (any prefix listed in 'backup list')
platform-cli backup verify backup-20260417-020000-001
```

## Restoring a Full Backup

```bash
# Interactive (shows confirmation prompt)
platform-cli backup restore bkp-<uuid>

# Skip confirmation for automation
platform-cli backup restore bkp-<uuid> --yes

# Headless
platform-cli --json backup restore bkp-<uuid> --yes
```

## Restoring a Single Store (Partial Restore)

```bash
# Restore only PostgreSQL from a backup
platform-cli backup restore bkp-<uuid> --stores postgresql --yes

# Restore two stores
platform-cli backup restore bkp-<uuid> --stores postgresql,redis --yes
```

## Scheduled Backups

```bash
# Start daemon (blocks, Ctrl+C to stop)
platform-cli backup schedule start --cron "0 2 * * *" --retention-days 30

# Single run (for cron/systemd)
platform-cli backup schedule run-once --retention-days 30
```

---

## Testing US1: Full Backup

1. Start the platform (at least PostgreSQL and one other store accessible)
2. Run `platform-cli backup create`
3. Verify output shows all 8 stores with `completed` status
4. Run `platform-cli backup list` — verify the new backup appears as the first entry
5. Inspect the manifest: `cat ~/.platform-cli/data/backups/manifests/bkp-<uuid>.json`
6. Verify `schema_version: 1` is present
7. Verify all 8 artifacts have non-empty `checksum_sha256` values

## Testing US2: Restore

1. Create a backup: `platform-cli backup create --tag test-restore`
2. Note the backup_id from the output
3. Delete a known row from PostgreSQL or a key from Redis
4. Run `platform-cli backup restore bkp-<uuid> --yes`
5. Verify the deleted data is restored
6. Run `platform-cli backup verify bkp-<uuid>` — all stores should pass

## Testing US3: List

1. Create two backups with different tags
2. Run `platform-cli backup list`
3. Verify both appear, newest first
4. Run `platform-cli --json backup list` — verify NDJSON output contains both entries

## Testing US4: Partial Restore

1. Create a backup
2. Corrupt data in Redis only
3. Run `platform-cli backup restore bkp-<uuid> --stores redis --yes`
4. Verify Redis data is restored
5. Verify PostgreSQL data is unchanged (query a known row before/after)

## Testing US5: Verify

1. Create a backup
2. Run `platform-cli backup verify bkp-<uuid>` — all stores should pass
3. Manually corrupt one artifact in the manifest directory (edit 1 byte)
4. Run `platform-cli backup verify bkp-<uuid>` again — the corrupted store should fail
5. Verify exit code is non-zero: `echo $?`

## Testing US6: Scheduled Backup

```bash
# Test with a short interval (every minute)
platform-cli backup schedule start --cron "* * * * *" --retention-days 0 &
sleep 130  # Wait for two cycles
kill %1

# Verify two backups were created
platform-cli backup list
# Expected: 2 entries (newest first)
```

---

## Kafka Offset Backup Notes

- The `kafka` store backs up **consumer group offsets only** — topic message data is ephemeral and not backed up
- This is intentional by design (see spec Assumptions)
- If Kafka is not available (e.g., local mode without Kafka), the store records a `failed` entry in the manifest and backup continues as `partial`
- Consumer groups whose topics no longer exist at restore time are skipped with a warning

## Lock Troubleshooting

```bash
# If backup fails with "lock could not be acquired":
# Kubernetes: check for stale ConfigMap
kubectl get configmap platform-backup-lock -n <namespace>
kubectl delete configmap platform-backup-lock -n <namespace>

# Local/Docker: check for stale lock file
ls -la ~/.platform-cli/backup.lock
rm ~/.platform-cli/backup.lock

# Or use --force to bypass:
platform-cli backup create --force
```
