# Export job stuck in `processing`

## Symptom

A `data_export_jobs` row has `status='processing'` for longer than the SLO budget (10 min p95 workspace, 60 min p95 tenant). The user has not received their notification email.

## Diagnosis

1. Identify the stuck job:

   ```sql
   SELECT id, scope_type, scope_id, started_at, error_message
   FROM data_export_jobs
   WHERE status = 'processing'
     AND started_at < now() - interval '15 minutes'
   ORDER BY started_at ASC;
   ```

2. Check whether the worker holds the Redis lease:

   ```bash
   redis-cli -h musematic-redis GET "data_lifecycle:export_lease:<JOB_ID>"
   redis-cli -h musematic-redis TTL "data_lifecycle:export_lease:<JOB_ID>"
   ```

   - If the value is a worker id and TTL > 0: a worker IS still working on it. Wait or check that worker's logs.
   - If the lease is absent or TTL < 0: the worker died holding the lease; the job will be picked up by the next consumer rebalance once Kafka redelivers, but the job's `status` is stuck because no one updated it.

3. Inspect worker logs:

   ```bash
   kubectl logs -n platform deploy/control-plane -c control-plane --since=1h | \
     jq -c 'select(.bounded_context=="data_lifecycle" and .job_id=="<JOB_ID>")'
   ```

## Recovery

### Worker is alive — wait

If the lease is held by a live worker (verify by running `kubectl get pods` and matching the worker_id pattern `control-plane-<host>-<pid>`), the job will complete naturally up to the SLO budget. Mark this incident closed.

### Worker died with the lease

Force the lease release and reset the job to `pending`:

```bash
redis-cli -h musematic-redis DEL "data_lifecycle:export_lease:<JOB_ID>"
psql -h musematic-postgres-rw -U postgres -d musematic -c "
  UPDATE data_export_jobs
  SET status = 'pending', started_at = NULL
  WHERE id = '<JOB_ID>';"
```

Then re-publish the request event so a worker picks it up:

```bash
kubectl exec -n platform deploy/control-plane -- python -m platform.data_lifecycle.workers.export_redrive --job-id <JOB_ID>
```

(Or wait up to 65 minutes for the lease TTL to expire and the next rebalance to re-deliver — both paths converge to the same outcome.)

### Object storage outage

If logs show repeated `S3ConnectionError`, the export bucket is unreachable. Verify:

```bash
kubectl exec -n platform deploy/control-plane -- python -c "
import asyncio, aioboto3
async def chk():
    async with aioboto3.Session().client('s3', endpoint_url='$S3_ENDPOINT_URL') as s3:
        await s3.head_bucket(Bucket='data-lifecycle-exports')
asyncio.run(chk())
"
```

If the bucket is missing or auth fails, restore via Helm; the job's `failure_reason_code` is recorded as `s3_unreachable` and the user is notified to request a fresh export. Don't mass-redrive — the user will notice their failed job in their notifications inbox.

## Prevention

- The Grafana dashboard `Data Lifecycle - UPD-051` shows `Export jobs in flight` rate — alert if zero throughput while `data_export_jobs` has `pending` rows.
- The Redis lease TTL (`export_lease_ttl_seconds`, default 65 min) is the long-tail recovery boundary. Keep it >= the SC-002 60-min tenant export budget.
