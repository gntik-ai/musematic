# Plans, Subscriptions, and Quotas Runbook

## Plan Publishing

Use `/admin/plans` to edit a plan and publish a new immutable version. Existing subscriptions remain pinned to their current version; new upgrades and provisions use the latest non-deprecated version.

Verify after publishing:

```sh
SELECT p.slug, pv.version, pv.published_at, pv.deprecated_at
FROM plans p
JOIN plan_versions pv ON pv.plan_id = p.id
WHERE p.slug = 'pro'
ORDER BY pv.version DESC;
```

## Plan Deprecation

Deprecation only hides a version from new use. Do not update quota fields on a published `plan_versions` row. To change a customer pin, use `/api/v1/admin/subscriptions/{id}/migrate-version`.

## Period Rollover Incidents

Symptoms: subscriptions keep an expired `current_period_end`, scheduled downgrades do not become effective, or quota resets do not happen.

Checks:

```sh
kubectl logs deploy/musematic-control-plane-scheduler -n platform-control | grep billing.period_rollover
SELECT id, status, cancel_at_period_end, current_period_end
FROM subscriptions
WHERE current_period_end <= now()
  AND status NOT IN ('canceled', 'suspended');
```

Recovery:

1. Confirm the scheduler pod is healthy and has database connectivity.
2. Restart the scheduler deployment if no heartbeat has been emitted for two intervals.
3. For a single stuck row, run the scheduler job after confirming no other scheduler instance is active.

## Overage Revocation

Workspace admins can revoke overage in the workspace billing UI. Super-admins should only revoke manually after confirming the workspace owner request.

```sql
UPDATE overage_authorizations
SET revoked_at = now(), revoked_by_user_id = :admin_user_id
WHERE id = :authorization_id
  AND revoked_at IS NULL;
```

## Reconciliation Mismatches

The daily billing reconciliation checks that recent `execution.compute.end` events have matching `processed_event_ids` rows. If mismatch rate exceeds 0.1%:

1. Check worker logs for `Billing metering event failed`.
2. Confirm Kafka consumer lag for the billing metering consumer group.
3. Replay missing `execution.compute.end` events from Kafka retention or the audit-chain projection.
4. Verify `usage_records` and provider usage reports are idempotent by event ID.
