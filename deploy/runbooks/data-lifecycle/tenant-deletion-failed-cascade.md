# Tenant deletion - cascade failed mid-flight

## Symptom

A tenant deletion job is in `phase_2` but `cascade_completed_at` has not been set after 24 hours. The audit chain shows `data_lifecycle.tenant_deletion_phase_2` but no `tenant_deletion_completed`. The Grafana dashboard `Data Lifecycle - UPD-051` shows non-zero entries on the `Cascade duration p95` panel that exceed the 24-hour SLA.

## Diagnosis

1. Locate the stuck job:

   ```bash
   psql -h musematic-postgres-rw -U postgres -d musematic -c "
     SELECT id, scope_id, phase, cascade_started_at, cascade_completed_at
     FROM deletion_jobs
     WHERE phase = 'phase_2' AND cascade_started_at < now() - interval '6 hours';"
   ```

2. Inspect the per-store progress in the audit chain:

   ```bash
   kubectl logs -n platform deploy/control-plane | \
     jq -c 'select(.bounded_context=="data_lifecycle" and .tenant_id=="<TENANT_ID>")'
   ```

3. Look for the structured log line with `cascade_log` entries — each store reports `success`, `partial`, `failed`, `not_implemented`, or `skipped`.

## Common causes

| Cascade leg fails with... | Likely cause | Fix |
|---|---|---|
| `not_implemented` on Qdrant/Neo4j/ClickHouse/OpenSearch/S3 | Adapter has not implemented `execute_for_tenant` | Open a ticket against the privacy_compliance BC; until that lands, run the manual cleanup queries below |
| `failed` on PostgreSQL with FK violation | Late-added child table missing from `TENANT_SCOPED_TABLES` catalog | Add the table to `apps/control-plane/src/platform/tenants/table_catalog.py` AND `apps/control-plane/migrations/tenant_table_catalog_snapshot.py`, redeploy, retry |
| `failed` on S3 with `AccessDenied` | Tenant prefix in a bucket missing in the IAM policy | Update the bucket policy; retry |
| `dns_teardown_skipped` | `FEATURE_UPD053_DNS_TEARDOWN=false` or DNS service unavailable | This is non-blocking. Run the DNS teardown manually per `dns-teardown-manual.md` |

## Recovery

The cascade is idempotent. To retry:

```bash
psql -h musematic-postgres-rw -U postgres -d musematic -c "
  UPDATE deletion_jobs
  SET cascade_started_at = NULL
  WHERE id = '<JOB_ID>';"
```

Then trigger the grace monitor cron manually:

```bash
kubectl exec -n platform deploy/control-plane -- python -m platform.data_lifecycle.workers.grace_monitor_oneoff
```

(In dev, `make trigger-cron CRON=grace_monitor` does the same thing.)

## Manual store-level cleanup queries

If individual adapters refuse to advance, the SREs can run the per-store deletion manually. **Do not skip the audit emission step** — every manual deletion MUST also produce an audit chain entry per rule 9.

```sql
-- PostgreSQL: see apps/control-plane/src/platform/tenants/table_catalog.py
DELETE FROM <table> WHERE tenant_id = '<TENANT_ID>';
```

```bash
# Qdrant
curl -X DELETE "$QDRANT_URL/collections/tenant_<TENANT_ID>_*"

# Neo4j
cypher-shell "MATCH (n {tenant_id: '<TENANT_ID>'}) DETACH DELETE n"

# ClickHouse
clickhouse-client -q "ALTER TABLE <table> DELETE WHERE tenant_id = '<TENANT_ID>'"

# OpenSearch
curl -X POST "$OS_URL/<index>/_delete_by_query" -d '{"query":{"term":{"tenant_id":"<TENANT_ID>"}}}'

# S3
aws s3 rm s3://<bucket>/tenant/<TENANT_ID>/ --recursive --endpoint-url $S3_ENDPOINT_URL
```

After manual cleanup, force-complete the job:

```sql
UPDATE deletion_jobs
SET phase = 'completed', cascade_completed_at = now()
WHERE id = '<JOB_ID>';
```

And emit the closing audit entry:

```bash
kubectl exec -n platform deploy/control-plane -- python -c "
import asyncio
from platform.audit.service import AuditChainService
# ... call append('data_lifecycle.tenant_deletion_completed', payload) ...
"
```

## Prevention

- Add the `data_lifecycle.tenant_cascade_completed` rate to the SLO dashboard alert rule (fire if <1 / 24h when there are pending phase_2 jobs).
- Run the cascade-extension unit tests in CI on every privacy_compliance change.
