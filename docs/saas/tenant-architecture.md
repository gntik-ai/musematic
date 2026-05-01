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
