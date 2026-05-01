# Tenant Migration Runbook

This runbook covers the UPD-046 tenant migration from a pre-tenant audit-pass
database to the default-plus-enterprise tenant architecture.

## Preconditions

- Confirm the application is running with `PLATFORM_TENANT_ENFORCEMENT_LEVEL=lenient`.
- Confirm the rollback window is set to `TENANT_MIGRATION_ROLLBACK_WINDOW_HOURS=24`.
- Confirm the target branch contains Alembic revisions 096 through 101.
- Confirm the default tenant UUID is `00000000-0000-0000-0000-000000000001`.

## Snapshot

1. Stop scheduled write-heavy jobs.
2. Capture a physical or logical PostgreSQL snapshot.
3. Record row counts for tenant-scoped tables:

```bash
psql "$DATABASE_URL" -c "\dt public.*"
pg_dump "$DATABASE_URL" --schema-only > pre-tenant-schema.sql
pg_dump "$DATABASE_URL" --data-only > pre-tenant-data.sql
```

Keep the snapshot for at least the configured rollback window.

## Upgrade

1. Deploy the control plane with lenient mode:

```bash
kubectl set env deployment/control-plane PLATFORM_TENANT_ENFORCEMENT_LEVEL=lenient
kubectl rollout status deployment/control-plane
```

2. Run migrations:

```bash
cd apps/control-plane
alembic upgrade 101_platform_staff_role
```

3. Verify the default tenant:

```sql
SELECT id, slug, subdomain, kind, status
FROM tenants
WHERE id = '00000000-0000-0000-0000-000000000001';
```

4. Verify no rows remain without a tenant:

```sql
SELECT table_name, completed_phase, completed_at
FROM _alembic_tenant_backfill_checkpoint
ORDER BY table_name;
```

## Interruption Recovery

Revision 098 is checkpointed per table. If migration execution is interrupted:

1. Keep the database online only if application writes are still paused.
2. Re-run `alembic upgrade 101_platform_staff_role`.
3. Confirm `_alembic_tenant_backfill_checkpoint` contains one row per migrated table.
4. Confirm every tenant-scoped table has zero `tenant_id IS NULL` rows.

Do not manually delete checkpoint rows unless restoring from the pre-migration snapshot.

## Lenient Telemetry

Lenient mode records suspected tenant filter misses in
`tenant_enforcement_violations` and emits a structured warning named
`tenant_enforcement_violation`.

Review violations during the soak:

```sql
SELECT occurred_at, table_name, expected_tenant_id, observed_violation
FROM tenant_enforcement_violations
ORDER BY occurred_at DESC
LIMIT 100;
```

Promotion to strict mode requires seven consecutive days with zero new rows.

## Rollback

Rollback is supported inside the 24 hour rollback window:

```bash
cd apps/control-plane
alembic downgrade 095_status_page_and_scenarios
```

Then verify:

```sql
SELECT to_regclass('public.tenants');
SELECT to_regclass('public.tenant_enforcement_violations');
SELECT to_regclass('public._alembic_tenant_backfill_checkpoint');
```

All three should return `NULL`. Tenant data columns are removed, but business
rows are preserved.

## Troubleshooting

- Missing default tenant: rerun the application startup seeder or migration 096.
- Backfill stopped mid-table: rerun the migration; tables without a checkpoint are
  processed again and already-filled rows are skipped.
- RLS returns zero rows after upgrade: inspect `tenant_enforcement_violations`,
  verify `current_tenant` is set by hostname middleware, and confirm the SQLAlchemy
  regular engine is setting `SET LOCAL app.tenant_id`.
- Platform-staff query fails under RLS: verify the connection uses
  `musematic_platform_staff` and that role has `BYPASSRLS`.
