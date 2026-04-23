# Backup & Restore

Backup and restore are handled by the operations CLI documented in
[spec 048][s048] (`apps/ops-cli/`). The CLI wraps backup operations
across every data store the platform uses and produces JSON manifests
either on local disk or in an S3-compatible bucket.

!!! warning "No fully-integrated backup job runs by default"

    The ops-cli provides **procedures**, not a continuous backup
    daemon. Scheduling backups is the operator's responsibility — see
    [Scheduling](#scheduling) below.

## What needs to be backed up

| Store | Contents | Backup tool |
|---|---|---|
| PostgreSQL | All control-plane tables. | `ops-cli backup postgres` / `pg_dump` |
| Redis | Hot state only (sessions, budgets, locks). **Regeneratable.** | Optional — not typically backed up. |
| Kafka | Event bus. **Regeneratable** in part; consider compacted topics. | Topic-replay tooling. |
| Qdrant | Vector memory. | `ops-cli backup qdrant` / Qdrant snapshots |
| Neo4j | Knowledge graph. | `ops-cli backup neo4j` / `neo4j-admin dump` |
| ClickHouse | Analytics rollups. | `ops-cli backup clickhouse` / `altinity/clickhouse-backup` |
| OpenSearch | Search indexes. | `ops-cli backup opensearch` / Snapshot Management |
| S3 | Agent packages, traces, evidence, simulation artifacts. | Provider-specific; versioning strongly recommended. |

## Running a backup

```bash
platform-cli backup all \
  --destination s3://musematic-backups \
  --timestamp $(date -Iseconds)
```

Per-store granularity:

```bash
platform-cli backup postgres --destination s3://musematic-backups
platform-cli backup qdrant   --destination s3://musematic-backups
platform-cli backup neo4j    --destination s3://musematic-backups
platform-cli backup clickhouse --destination s3://musematic-backups
platform-cli backup opensearch --destination s3://musematic-backups
```

The CLI produces a manifest JSON file alongside the data dumps:

```json
{
  "timestamp": "2026-04-23T12:00:00Z",
  "stores": {
    "postgres": { "path": "...", "size_bytes": 1234567, "sha256": "..." },
    "qdrant":   { "path": "...", "size_bytes": 654321,  "sha256": "..." }
  }
}
```

TODO(andrea): confirm the exact manifest schema and CLI subcommand
names by reading `apps/ops-cli/src/platform_cli/commands/backup.py`
(or wherever backup commands live in the current main branch). The
commands above reflect the contract described in
[spec 048][s048].

## Restoring

```bash
platform-cli restore all \
  --source s3://musematic-backups \
  --manifest 2026-04-23T12:00:00Z.json
```

Order of operations matters:

1. Drain traffic — enable maintenance mode or scale the control plane
   to zero (maintenance mode is planned but not yet shipped; until
   then, use `kubectl scale deployment/control-plane --replicas=0`).
2. Restore Postgres first.
3. Run `make migrate` to bring schemas up to the current version if the
   restore is older than the current release.
4. Restore the other stores in parallel.
5. Scale the control plane back up.
6. Run smoke tests.

## Restore drills

Regular restore drills are the only reliable way to know your backups
work. Recommended cadence: **monthly** on a staging environment using
the previous production backup.

## Scheduling

No built-in scheduler. Options:

- Kubernetes `CronJob` invoking `platform-cli backup all`.
- External scheduler (Jenkins, GitHub Actions on self-hosted runner).
- Systemd timers on a host with cluster access.

Example `CronJob` skeleton:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: musematic-nightly-backup
  namespace: platform-control
spec:
  schedule: "0 2 * * *"   # 02:00 daily
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: ghcr.io/gntik-ai/musematic-ops-cli:latest
              args:
                - backup
                - all
                - --destination
                - s3://musematic-backups
              envFrom:
                - secretRef:
                    name: musematic-backup-credentials
          restartPolicy: OnFailure
```

## Retention

No automatic retention. Apply S3 lifecycle rules on the backup bucket
(e.g. move to Glacier after 30 days, delete after 365 days).

[s048]: https://github.com/gntik-ai/musematic/tree/main/specs/048-backup-restore
