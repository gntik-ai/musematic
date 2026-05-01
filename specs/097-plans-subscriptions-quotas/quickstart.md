# Quickstart — UPD-047 Plans, Subscriptions, and Quotas (Local Validation)

**Audience**: An engineer about to start building Track A, B, or C, or wanting to validate the feature end-to-end on the local kind cluster.

**Preconditions**: UPD-046 (tenant architecture) is fully landed (default tenant exists, hostname resolver is wired, RLS policies active). The local E2E harness from UPD-046 is reachable at `http://localhost:8081`. The `app.localhost` and Enterprise-tenant subdomains (e.g., `acme.localhost`) resolve correctly.

This walkthrough takes the freshly-deployed UPD-047 schema (migrations 103 + 104) and exercises the end-to-end flows: super admin publishes a Pro version, a Free workspace is hard-capped, a Pro workspace authorises overage, an Enterprise workspace runs unlimited.

## 0. Preconditions and seeded plans

```bash
make dev-up
export PLATFORM_API_URL=http://localhost:8081
export DEFAULT_TENANT_HOST=app.localhost
export PLATFORM_TENANT_ENFORCEMENT_LEVEL=strict     # the rollout flag from UPD-046; UPD-047 builds on strict
```

Confirm the seeder created the three default plans plus their initial published versions:

```bash
kubectl -n platform-data exec pod/musematic-postgres-1 -- \
  env PGPASSWORD=change-me psql -h 127.0.0.1 -U musematic -d musematic -c \
  "SELECT p.slug, pv.version, pv.price_monthly, pv.executions_per_month, pv.minutes_per_month
     FROM plans p JOIN plan_versions pv ON pv.plan_id = p.id
    WHERE pv.published_at IS NOT NULL AND pv.deprecated_at IS NULL
    ORDER BY p.slug;"
```

Expected:

```
   slug    | version | price_monthly | executions_per_month | minutes_per_month
-----------+---------+---------------+----------------------+-------------------
 enterprise|       1 |         0.00  |                    0 |                 0
 free      |       1 |         0.00  |                  100 |               100
 pro       |       1 |        49.00  |                 5000 |              2400
```

Confirm every existing default-tenant workspace has a Free subscription:

```bash
kubectl -n platform-data exec pod/musematic-postgres-1 -- \
  env PGPASSWORD=change-me psql -h 127.0.0.1 -U musematic -d musematic -c \
  "SELECT count(*) AS workspaces_without_subscription
     FROM workspaces w
     LEFT JOIN subscriptions s
       ON s.scope_type = 'workspace' AND s.scope_id = w.id
    WHERE s.id IS NULL;"
# Expect: 0
```

## 1. Public pricing endpoint

```bash
curl -sS -H "Host: $DEFAULT_TENANT_HOST" \
  "$PLATFORM_API_URL/api/v1/public/plans" | jq '.plans[].slug'
```

Expected: `"free"` and `"pro"` (Enterprise is hidden because `is_public=false`).

## 2. Super admin publishes a new Pro version

Mint a super-admin token and publish Pro v2 with a higher price:

```bash
SUPERADMIN_TOKEN=$(python tests/e2e/scripts/dev_auth.py mint \
  --email superadmin@e2e.test \
  --role superadmin)

curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "price_monthly": 59.00,
    "executions_per_day": 500,
    "executions_per_month": 5000,
    "minutes_per_day": 240,
    "minutes_per_month": 2400,
    "max_workspaces": 5,
    "max_agents_per_workspace": 50,
    "max_users_per_workspace": 25,
    "overage_price_per_minute": 0.10,
    "trial_days": 14,
    "quota_period_anchor": "subscription_anniversary"
  }' \
  "$PLATFORM_API_URL/api/v1/admin/plans/pro/versions" | jq
```

Verify the diff was recorded and version 1 was deprecated:

```bash
curl -sS -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  "$PLATFORM_API_URL/api/v1/admin/plans/pro/versions" | jq '.items[] | {version, deprecated_at, subscription_count}'
```

Expected: version 2 has `deprecated_at: null`; version 1 has `deprecated_at: "<timestamp>"` and `subscription_count: <count of existing Pro subs>`.

Confirm existing Pro subscriptions stayed on version 1:

```bash
kubectl -n platform-data exec pod/musematic-postgres-1 -- \
  env PGPASSWORD=change-me psql -h 127.0.0.1 -U musematic -d musematic -c \
  "SELECT plan_version, count(*) FROM subscriptions
     WHERE plan_id = (SELECT id FROM plans WHERE slug='pro')
     GROUP BY plan_version;"
# Expect: only version 1 exists right now
```

## 3. Free workspace hits the hard cap

Create a Free workspace, prefill its monthly executions counter to 100, attempt execution #101:

```bash
USER_TOKEN=$(python tests/e2e/scripts/dev_auth.py mint \
  --email free-user@e2e.test \
  --role workspace_member)

WORKSPACE_ID=$(curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Free workspace test"}' \
  "$PLATFORM_API_URL/api/v1/workspaces" | jq -r .id)

# Prefill the monthly executions counter using the dev-only test helper (gated behind FEATURE_E2E_MODE)
curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"executions": 100}' \
  "$PLATFORM_API_URL/api/v1/_e2e/billing/seed-usage?workspace_id=$WORKSPACE_ID"

# Attempt execution #101
curl -isS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"workspace_id":"'"$WORKSPACE_ID"'", "agent_fqn":"sandbox:hello-world"}' \
  "$PLATFORM_API_URL/api/v1/executions"
```

Expected response:

```
HTTP/1.1 402 Payment Required
Content-Type: application/json

{
  "code": "quota_exceeded",
  "message": "This workspace has reached its monthly execution cap.",
  "details": {
    "quota_name": "executions_per_month",
    "current": 100,
    "limit": 100,
    "reset_at": "<next month start>",
    "plan_slug": "free",
    "upgrade_url": "/workspaces/<id>/billing/upgrade",
    "overage_available": false
  }
}
```

Verify no execution row was created:

```bash
kubectl -n platform-data exec pod/musematic-postgres-1 -- \
  env PGPASSWORD=change-me psql -h 127.0.0.1 -U musematic -d musematic -c \
  "SELECT count(*) FROM executions WHERE workspace_id = '$WORKSPACE_ID';"
# Expect: 100 (not 101)
```

## 4. Pro workspace authorises overage

Upgrade the Free workspace to Pro:

```bash
curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_plan_slug":"pro","payment_method_token":"stub_pm_test"}' \
  "$PLATFORM_API_URL/api/v1/workspaces/$WORKSPACE_ID/billing/upgrade" | jq
```

Prefill the monthly minutes counter to 2400 (the Pro v2 cap):

```bash
curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"minutes": 2400}' \
  "$PLATFORM_API_URL/api/v1/_e2e/billing/seed-usage?workspace_id=$WORKSPACE_ID"
```

Attempt a new execution:

```bash
EXEC_RESPONSE=$(curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"workspace_id":"'"$WORKSPACE_ID"'", "agent_fqn":"sandbox:hello-world"}' \
  "$PLATFORM_API_URL/api/v1/executions")
echo "$EXEC_RESPONSE" | jq
# Expect: HTTP 202; body includes "status": "paused_quota_exceeded"
```

Confirm the workspace admin received an overage-authorization notification:

```bash
curl -sS -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $USER_TOKEN" \
  "$PLATFORM_API_URL/api/v1/me/notifications?type=billing.overage.required" | jq
```

Authorise overage:

```bash
curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"max_overage_eur": 50.00}' \
  "$PLATFORM_API_URL/api/v1/workspaces/$WORKSPACE_ID/billing/overage-authorization" | jq
```

Verify the previously-paused execution resumed:

```bash
EXEC_ID=$(echo "$EXEC_RESPONSE" | jq -r .id)
sleep 5
kubectl -n platform-data exec pod/musematic-postgres-1 -- \
  env PGPASSWORD=change-me psql -h 127.0.0.1 -U musematic -d musematic -c \
  "SELECT status FROM executions WHERE id='$EXEC_ID';"
# Expect: 'running' or 'completed', not 'paused_quota_exceeded'
```

## 5. Concurrent overage authorisation idempotency

Issue two simultaneous authorisation requests in different terminals:

```bash
# Terminal A
curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"max_overage_eur": 50.00}' \
  "$PLATFORM_API_URL/api/v1/workspaces/$WORKSPACE_ID/billing/overage-authorization" &

# Terminal B (simultaneous)
curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"max_overage_eur": 100.00}' \
  "$PLATFORM_API_URL/api/v1/workspaces/$WORKSPACE_ID/billing/overage-authorization" &

wait
```

Verify exactly one row exists (the first writer wins; the second is a no-op success):

```bash
kubectl -n platform-data exec pod/musematic-postgres-1 -- \
  env PGPASSWORD=change-me psql -h 127.0.0.1 -U musematic -d musematic -c \
  "SELECT count(*) FROM overage_authorizations
    WHERE workspace_id='$WORKSPACE_ID';"
# Expect: 1
```

## 6. Enterprise workspace runs unlimited

Provision an Enterprise tenant and a tenant-scoped Enterprise subscription:

```bash
ACME_TENANT_ID=$(./scripts/dev/provision-enterprise-tenant.sh acme)
ACME_TOKEN=$(python tests/e2e/scripts/dev_auth.py mint \
  --email cto@acme.test \
  --role workspace_admin --tenant acme)

ACME_WORKSPACE_ID=$(curl -sS -X POST -H "Host: acme.localhost" \
  -H "Authorization: Bearer $ACME_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Acme research"}' \
  "$PLATFORM_API_URL/api/v1/workspaces" | jq -r .id)

# Run 100 executions in quick succession
for i in $(seq 1 100); do
  curl -sS -X POST -H "Host: acme.localhost" \
    -H "Authorization: Bearer $ACME_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"workspace_id":"'"$ACME_WORKSPACE_ID"'", "agent_fqn":"sandbox:hello-world"}' \
    "$PLATFORM_API_URL/api/v1/executions" > /dev/null
done
```

Verify zero rejections:

```bash
kubectl -n platform-data exec pod/musematic-postgres-1 -- \
  env PGPASSWORD=change-me psql -h 127.0.0.1 -U musematic -d musematic -c \
  "SELECT count(*) FROM executions WHERE workspace_id='$ACME_WORKSPACE_ID';"
# Expect: 100
```

Verify the quota-enforcer overhead is below the SC-004 threshold (the resolver short-circuits because all caps are zero):

```bash
curl -sS "$PLATFORM_API_URL/metrics" | grep -E '^quota_enforcer_check_seconds_(sum|count)\{plan_tier="enterprise"'
# Compute average; expect < 0.001 seconds (1 ms)
```

## 7. Period rollover

Force the period boundary to elapse using the dev-only test helper, then verify counters reset:

```bash
curl -sS -X POST -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  "$PLATFORM_API_URL/api/v1/_e2e/billing/force-period-rollover?subscription_id=<sub-id>"

# Wait one scheduler tick (~60 seconds in production; 5 seconds in dev with the accelerated config)
sleep 5

kubectl -n platform-data exec pod/musematic-postgres-1 -- \
  env PGPASSWORD=change-me psql -h 127.0.0.1 -U musematic -d musematic -c \
  "SELECT current_period_start, current_period_end FROM subscriptions WHERE id='<sub-id>';"
# Expect: new period boundaries

curl -sS -H "Host: $DEFAULT_TENANT_HOST" \
  -H "Authorization: Bearer $USER_TOKEN" \
  "$PLATFORM_API_URL/api/v1/workspaces/$WORKSPACE_ID/billing" | jq '.usage.minutes_this_period'
# Expect: 0 (counters reset)
```

## 8. Run the E2E suites

```bash
PLATFORM_API_URL=$PLATFORM_API_URL RUN_PLANS_SUBSCRIPTIONS_E2E=true \
  pytest apps/control-plane/tests/e2e/suites/plans_subscriptions/ -v
```

Expected: J23 (Quota Enforcement), J30 (Plan Versioning), J37 (Free Cost Protection), and the supporting suites all pass.

## 9. Subscription scope constraint enforcement

Attempt to insert a workspace-scoped subscription on the Acme (Enterprise) tenant directly via SQL:

```bash
kubectl -n platform-data exec pod/musematic-postgres-1 -- \
  env PGPASSWORD=change-me psql -h 127.0.0.1 -U musematic -d musematic -c \
  "INSERT INTO subscriptions (tenant_id, scope_type, scope_id, plan_id, plan_version, status,
                               current_period_start, current_period_end)
   VALUES ('$ACME_TENANT_ID', 'workspace', '$ACME_WORKSPACE_ID',
           (SELECT id FROM plans WHERE slug='free'), 1, 'active',
           now(), now() + interval '1 month');"
# Expect: ERROR: workspace-scoped subscriptions are not permitted on Enterprise tenants
#         (from subscriptions_scope_check trigger)
```

## Done

If every step above succeeds, your local-dev cluster has a working plans/subscriptions/quotas stack and you are ready to build Tracks A–C and the E2E phase.
