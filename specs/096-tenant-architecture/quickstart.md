# Quickstart — UPD-046 Tenant Architecture (Local Validation)

**Audience**: An engineer about to start building Track A or wanting to validate the feature end-to-end on a local kind cluster.

This walkthrough assumes the existing local-dev kind cluster (per the existing `docs/quickstart.md`) is up and reachable. We use `*.localtest.me` as the platform-domain shim because every label of `localtest.me` resolves to `127.0.0.1` and therefore matches whatever the local ingress serves. Set `PLATFORM_DOMAIN=localtest.me` in your dev shell.

## 0. Preconditions

```bash
make dev-up                                    # the existing one-shot bring-up
export PLATFORM_DOMAIN=localtest.me
export PLATFORM_TENANT_ENFORCEMENT_LEVEL=lenient
```

Confirm the seeder ran:

```bash
psql -U musematic_app -d musematic_dev -c \
  "SELECT id, slug, kind, subdomain FROM tenants;"
# Expect: 00000000-0000-0000-0000-000000000001 | default | default | app
```

## 1. Resolve the default tenant

```bash
curl -sS -H "Host: app.localtest.me" http://localhost:8000/api/v1/me/tenant | jq
```

Expected:

```jsonc
{
  "id": "00000000-0000-0000-0000-000000000001",
  "slug": "default",
  "kind": "default",
  "subdomain": "app",
  "status": "active",
  "branding": {}
}
```

## 2. Provision an Enterprise tenant (super admin)

Authenticate as the local super admin (default credentials per `docs/installation.md`). Then:

```bash
# Upload a placeholder DPA
DPA_ID=$(curl -sS -X POST -H "Host: app.localtest.me" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -F "file=@./tests/fixtures/dpa-sample.pdf" \
  http://localhost:8000/api/v1/admin/tenants/dpa-upload \
  | jq -r .dpa_artifact_id)

# Create the tenant
curl -sS -X POST -H "Host: app.localtest.me" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "acme",
    "display_name": "Acme Corp",
    "region": "eu-central",
    "first_admin_email": "cto@acme.test",
    "dpa_artifact_id": "'"$DPA_ID"'",
    "dpa_version": "v3-2026-01"
  }' \
  http://localhost:8000/api/v1/admin/tenants | jq
```

In a local cluster the Hetzner DNS step is mocked to return success and the wildcard ingress already covers `*.localtest.me`, so the new subdomain `acme.localtest.me` is reachable immediately.

## 3. Resolve the new Enterprise tenant

```bash
curl -sS -H "Host: acme.localtest.me" http://localhost:8000/api/v1/me/tenant | jq
```

Expected:

```jsonc
{
  "slug": "acme",
  "kind": "enterprise",
  "subdomain": "acme",
  "status": "active",
  "branding": {}
}
```

## 4. Verify cross-tenant isolation

Create a workspace in Acme via the admin API:

```bash
ACME_TOKEN=$(./scripts/dev/login-as-tenant-admin.sh acme cto@acme.test)
WORKSPACE_ID=$(curl -sS -X POST -H "Host: acme.localtest.me" \
  -H "Authorization: Bearer $ACME_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Acme research"}' \
  http://localhost:8000/api/v1/workspaces | jq -r .id)
```

Now log into the default tenant and try to fetch Acme's workspace:

```bash
DEFAULT_TOKEN=$(./scripts/dev/login-as-tenant-admin.sh default admin@musematic.test)

curl -isS -H "Host: app.localtest.me" \
  -H "Authorization: Bearer $DEFAULT_TOKEN" \
  http://localhost:8000/api/v1/workspaces/$WORKSPACE_ID
# Expect: HTTP/1.1 404 Not Found
# Expect body: {"detail":"Not Found"}
```

Confirm via psql that RLS filtered the query, not the application:

```bash
psql -U musematic_app -d musematic_dev <<SQL
BEGIN;
SET LOCAL app.tenant_id = '00000000-0000-0000-0000-000000000001';
SELECT id, name, tenant_id FROM workspaces WHERE id = '$WORKSPACE_ID';
ROLLBACK;
SQL
# Expect: zero rows (RLS filtered)
```

Now run the same query as platform staff (BYPASSRLS):

```bash
psql -U musematic_platform_staff -d musematic_dev -c \
  "SELECT id, name, tenant_id FROM workspaces WHERE id = '$WORKSPACE_ID';"
# Expect: one row with tenant_id = Acme's UUID
```

## 5. Verify unknown-subdomain opacity (SC-009)

```bash
for slug in bogus xyz123 deleted-tenant test-probe; do
  curl -isS -o /tmp/$slug.body -D /tmp/$slug.headers \
    -H "Host: $slug.localtest.me" \
    http://localhost:8000/
done

# All bodies and headers must be byte-identical:
sha256sum /tmp/*.body
sha256sum /tmp/*.headers
```

All four `.body` SHA-256 hashes match; all four `.headers` SHA-256 hashes match (after stripping the `X-Request-ID` echo, which is intentionally absent for unresolved hosts).

## 6. Suspend and reactivate the Enterprise tenant

```bash
curl -sS -X POST -H "Host: app.localtest.me" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"local-dev test"}' \
  http://localhost:8000/api/v1/admin/tenants/$ACME_TENANT_ID/suspend

# Verify the suspension banner renders
curl -sS -H "Host: acme.localtest.me" http://localhost:8000/login | grep -q "suspended"

# Reactivate
curl -sS -X POST -H "Host: app.localtest.me" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  http://localhost:8000/api/v1/admin/tenants/$ACME_TENANT_ID/reactivate

# Verify access restored
curl -sS -H "Host: acme.localtest.me" http://localhost:8000/login | grep -q "Sign in"
```

## 7. Verify default-tenant immutability (SC-008)

```bash
# Try to delete via API
curl -isS -X POST -H "Host: app.localtest.me" \
  -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  http://localhost:8000/api/v1/admin/tenants/00000000-0000-0000-0000-000000000001/schedule-deletion
# Expect: 409 Conflict, code=default_tenant_immutable

# Try to delete directly in DB (with platform-staff role)
psql -U musematic_platform_staff -d musematic_dev -c \
  "DELETE FROM tenants WHERE id = '00000000-0000-0000-0000-000000000001';"
# Expect: ERROR: default tenant cannot be deleted (from tenants_default_immutable trigger)
```

## 8. Run the journey suites

```bash
pytest tests/e2e/suites/tenant_architecture/ -v
```

Expected: J22 (provisioning), J31 (cross-tenant isolation), J36 (default-tenant constraints) and the supporting suites all pass.

## 9. Promote to strict enforcement (production runbook excerpt)

After seven consecutive days with zero rows in `tenant_enforcement_violations`:

```bash
kubectl set env deployment/control-plane PLATFORM_TENANT_ENFORCEMENT_LEVEL=strict
kubectl rollout status deployment/control-plane
```

The lenient/strict rollout is documented in full at `deploy/runbooks/tenant-provisioning.md`.

## Done

If every step above succeeds, your local-dev cluster has a working tenant architecture and you are ready to build Tracks B–G.
