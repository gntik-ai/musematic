# Tenant Architecture

Musematic resolves every request to a tenant before authentication, data access, routing, branding, or audit handling. The default tenant has the well-known UUID `00000000-0000-0000-0000-000000000001`, slug `default`, and subdomain `app`; Enterprise tenants use their provisioned slug as the public subdomain.

Requests pass through the tenant resolver middleware first. It normalizes the `Host` header, supports default surfaces (`app`, `api`, `grafana`) and Enterprise surfaces (`{slug}`, `{slug}.api`, `{slug}.grafana`), caches resolved tenants in process and Redis, and returns a byte-stable opaque 404 for unknown hosts.

Tenant data isolation uses three layers:

- ORM models for tenant-scoped tables include `TenantScopedMixin`.
- Regular SQLAlchemy sessions bind `SET LOCAL app.tenant_id` and install global loader criteria.
- PostgreSQL RLS policies named `tenant_isolation` enforce `tenant_id = current_setting('app.tenant_id', true)::uuid`.

Platform-staff endpoints live under `/api/v1/platform/*` and use a separate PostgreSQL role with `BYPASSRLS`. These endpoints are reserved for cross-tenant operational workflows and must emit audit-chain entries for cross-tenant reads.

Tenant lifecycle operations are centralized in the tenants bounded context. Suspension blocks data access while preserving rows. Deletion requires 2PA, enters a grace period, and is completed by the scheduler through the tenant cascade registry. The default tenant is immutable at application and database-trigger layers.

Secrets are stored under tenant-scoped Vault paths:

```text
secret/data/musematic/{env}/tenants/{slug}/{domain}/{resource}
secret/data/musematic/{env}/_platform/{domain}/{resource}
```

Use `tenant_vault_path()` and `platform_vault_path()` rather than constructing paths manually.

## Operator topology (UPD-053)

Production runs on a Hetzner Cloud Kubernetes cluster (`musematic-prod`: 1× CCX33 control plane + 3× CCX53 workers + 1× lb21 Cloud LB; `nbg1` / `eu-central`). Dev runs the same chart on a smaller `musematic-dev` cluster (1× CCX21 + 1× CCX21 + 1× lb11) with physical network isolation. Both clusters terminate TLS at ingress-nginx using a single wildcard certificate per environment (`*.musematic.ai` for prod, `*.dev.musematic.ai` for dev), auto-renewed by cert-manager via the Hetzner DNS-01 webhook. Per-tenant subdomains (`<slug>`, `<slug>.api`, `<slug>.grafana`) are provisioned as A+AAAA records by `tenants/dns_automation.py` on tenant creation and removed on data-lifecycle phase 2; the wildcard ingress rule plus the tenant-resolver middleware (above) route each request to the correct tenant context.

For provisioning, renewal, and incident playbooks see:

- [`docs/operations/hetzner-cluster-provisioning.md`](../operations/hetzner-cluster-provisioning.md) — zero-to-running cluster (≤ 30 min).
- [`docs/operations/wildcard-tls-renewal.md`](../operations/wildcard-tls-renewal.md) — cert-renewal failure handling.
- [`docs/operations/cloudflare-pages-status.md`](../operations/cloudflare-pages-status.md) — out-of-cluster status page (rule 49).
- [`docs/operations/helm-snapshot.md`](../operations/helm-snapshot.md) — chart-snapshot CI gate.
- [`docs/architecture/dns-and-ingress.md`](../architecture/dns-and-ingress.md) — end-to-end DNS + cert + ingress flow.
