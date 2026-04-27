# Database Migration Rollback

## Symptom

A migration fails, blocks startup, or causes a severe regression after deployment.

## Diagnosis

Identify the Alembic revision, affected tables, irreversible DDL, and whether application pods are still writing. Stop writers if data consistency is at risk.

## Remediation

Use the repository rollback target when the migration supports downgrade:

```bash
make migrate-rollback
```

If downgrade is unsafe, restore from backup or write a forward repair migration.

## Verification

Run `make migrate-check`, start the control plane, verify affected endpoints, and inspect database error logs for repeated failures.
