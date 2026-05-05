# UPD-053 — Phase 1 Data Model

This feature is overwhelmingly infrastructure-as-code (Helm chart, Terraform, cert-manager) plus an in-place extension of the existing `tenants/dns_automation.py` Protocol. It introduces **no new PostgreSQL tables, no new Redis key namespaces, no new Kafka topics, and no new Vault paths beyond an additive token entry**.

## What changes (data layer)

### PostgreSQL — no schema changes

No DDL. No Alembic migration. The DNS records this feature manages live in Hetzner DNS (the source of truth); the audit chain (`security_compliance/services/audit_chain_service.py`) records each create/remove call with the Hetzner record ids returned by the API. Persisting record ids in PostgreSQL was rejected in research R2 — the zone state is small and the Hetzner API list endpoint is the canonical idempotent removal path.

### Vault — one new token path (additive)

| Path | Purpose | Producer | Consumer |
|---|---|---|---|
| `secret/data/musematic/{env}/dns/hetzner/api-token` | Hetzner DNS API token (scoped to the `musematic.ai` zone) | Operator runbook (US1, US2) | `tenants/dns_automation.py` (read at startup via `SecretProvider`); cert-manager Hetzner DNS-01 webhook (read via `VaultStaticSecret` sync to `Secret/hetzner-dns-token`) |

The existing `SecretProvider` interface (`security_compliance/providers/`) already abstracts Vault access; `dns_automation.py` reads the token through it. No env-var fallback (rule 39).

### Kafka — no new topics

Tenant create/delete already publishes on `tenants.events` (UPD-046). DNS automation does NOT add a new event type — it emits an audit chain entry per DNS change (FR-A3) and logs structured events. The existing `TenantCreatedPayload` / `TenantDeletedPayload` carry enough metadata for downstream consumers; adding a per-DNS-change event would be redundant noise.

### Redis — no new keys

DNS API calls are serialised per zone via the Hetzner API's own concurrency model (idempotent inserts; conflicts return 422 which we retry). The user input's "queue serialization" mitigation is implemented as in-process `asyncio.Lock` keyed by `(zone_id, slug)` inside `DnsAutomationClient`, not via a Redis distributed lock — the control plane is one process per profile, and concurrent provisioning of the *same* slug is already guarded by tenant-creation idempotency (the `tenants.slug` UNIQUE constraint refuses the second creation).

### S3 — none.

## Audit chain entries (rule 9 / AD-18)

Every successful or failed DNS change emits one entry via `AuditChainService.append`:

| Field | Source |
|---|---|
| `actor_id` | `actor["id"]` from the calling context (super-admin user id for create, system principal for cascade delete) |
| `tenant_id` | `tenant.id` (the tenant whose subdomain is being touched) |
| `event_type` | `tenants.dns.records_created` / `tenants.dns.records_removed` / `tenants.dns.records_failed` |
| `before_state` | `null` for create, list of record ids for remove |
| `after_state` | list of `{ name, type, hetzner_record_id }` for create, `null` for remove |
| `correlation_id` | propagated from the request |

No record values (IPv4/IPv6) or tokens enter the audit chain payload — addresses are non-sensitive but dropping them keeps the audit row small and avoids leaking infra topology.

## Entities (logical, not persisted by this feature)

These are conceptual entities used by the spec and the implementation; the only one that resolves to a database row is the `Tenant` (already owned by `tenants/`).

### `DnsAutomationRecordSet`

The 6-record bundle (3 subdomains × A + AAAA) that `create_tenant_subdomain(slug)` adds and `remove_tenant_subdomain(slug)` removes.

| Field | Type | Source |
|---|---|---|
| `slug` | string | `tenant.slug` (must not appear in `RESERVED_SLUGS`) |
| `subdomains` | `["{slug}", "{slug}.api", "{slug}.grafana"]` | derived |
| `record_types` | `["A", "AAAA"]` | constant |
| `ipv4` | string | `settings.TENANT_DNS_IPV4_ADDRESS` (LB public IPv4, fed from Terraform output) |
| `ipv6` | string \| null | `settings.TENANT_DNS_IPV6_ADDRESS` (LB public IPv6) |
| `ttl` | int | 300 (constant; matches the user input) |
| `hetzner_record_ids` | list[string] | populated post-create from the Hetzner API response |

### `WildcardCertificate`

The cert-manager `Certificate` CRD instances rendered by the chart. Two per env (wildcard + apex); not a database entity.

| Field | Source |
|---|---|
| `name` | `wildcard-musematic-ai` (prod) / `wildcard-dev-musematic-ai` (dev) |
| `secretName` | same |
| `dnsNames` | `["*.musematic.ai", "musematic.ai"]` (prod) / `["*.dev.musematic.ai", "dev.musematic.ai"]` (dev) |
| `issuerRef.name` | `letsencrypt-prod` (cluster issuer) |
| `renewBefore` | 720h (cert-manager default ≥30 days; explicit so renewal SLO is verifiable) |

### `HelmOverlay`

`values.prod.yaml` and `values.dev.yaml` (dotted convention; see research R3). Each layers on top of `values.yaml`. Modified blocks (additive; existing keys preserved):

| Top-level key | Owner | Notes |
|---|---|---|
| `hetzner.loadBalancer` | NEW | location, networkZone, usePrivateIp, proxyProtocol, name, type (lb21/lb11) — feeds `service-loadbalancer.yaml` annotations |
| `hetzner.dns` | NEW | provider, zone, apiTokenSecretRef — feeds DNS-01 webhook + `dns_automation` startup config |
| `certManager` | NEW | enabled, clusterIssuer (name/email/server), hetznerDnsWebhook (image), certificates (list of name/secretName/dnsNames) |
| `ingress.wildcardHosts` | NEW | rendered as a wildcard rule in `templates/ingress-platform.yaml` |
| `webStatus.deployedHere` | NEW | `false` for prod (Cloudflare Pages); `true` for dev (in-cluster fallback per R6) |
| `webStatus.pushDestination` | NEW | `cloudflare-pages` (prod) / `none` (dev) |
| `webStatus.pushIntervalSeconds` | NEW | 30 (prod) / 60 (dev) |
| `billing.stripe.webhookUrl` | EXTEND | per-env: `https://api.musematic.ai/api/webhooks/stripe` (prod) / `https://dev.api.musematic.ai/api/webhooks/stripe` (dev) |

### `TerraformWorkspace`

Existing under `terraform/`. Modified:

| File | Change |
|---|---|
| `terraform/modules/hetzner-cluster/variables.tf` | Add defaults for `load_balancer_type` per the env's tfvars (no default in module; default lives in env overlay). |
| `terraform/modules/hetzner-cluster/outputs.tf` | NEW outputs: `lb_ipv4`, `lb_ipv6` (consumed by the DNS module). |
| `terraform/modules/hetzner-dns-zone/` | NEW module — owns the apex zone via `hetznerdns_zone` and the apex/app/api/grafana/status/`*` wildcard records via `hetznerdns_record`. |
| `terraform/environments/production/main.tf` | Wire the DNS module + set `load_balancer_type = "lb21"` in the cluster module call. |
| `terraform/environments/dev/main.tf` | Wire the DNS module (different zone subtree) + set `load_balancer_type = "lb11"`. |
| `terraform/environments/{production,dev}/terraform.tfvars.example` | Add example values for the DNS-related variables; production uses `musematic.ai` zone with apex/app/api/grafana/status/`*` records, dev uses `dev.*` subtree. |

## State transitions

The only state machine added by this feature is the DNS-record lifecycle, which is implicit:

```text
[no records] --create_tenant_subdomain--> [6 records present in Hetzner]
                                           --tenant scheduled for deletion--> [6 records present, marked for cleanup]
                                           --remove_tenant_subdomain (data_lifecycle phase 2)--> [no records]
```

Failure modes:
- *create fails partway* (e.g. 3 of 6 created, 4th 5xx): the service retries with exponential backoff up to a bounded ceiling (FR-785); on permanent failure the tenant creation is left in a `degraded_dns` state and an admin alert is raised. The partially-created records are NOT rolled back automatically (so the next retry can complete the set without colliding with a "name already exists" 422).
- *remove fails partway*: data_lifecycle phase 2 retries via the existing cascade retry loop (UPD-051); if the ceiling is hit, an audit entry records the partial removal and the data_lifecycle escalation surface picks it up.

## Cross-references to brownfield code

| Site | What changes |
|---|---|
| `apps/control-plane/src/platform/tenants/dns_automation.py` | Add 3-record-set methods + remove + propagation verifier; keep `ensure_records` as a deprecated facade that calls `create_tenant_subdomain` for one release |
| `apps/control-plane/src/platform/tenants/service.py:139` | Replace `await self.dns_automation.ensure_records(tenant.subdomain)` with `await self.dns_automation.create_tenant_subdomain(tenant.slug)` |
| `apps/control-plane/src/platform/tenants/cascade.py` | Add a `tenant_dns_cascade_handler` registered in `tenant_cascade_handlers` (UPD-051 phase 2) that calls `remove_tenant_subdomain(slug)` |
| `apps/control-plane/src/platform/common/config.py` | Add `HETZNER_DNS_API_TOKEN` (already present on the settings class), `HETZNER_DNS_ZONE_ID`, `TENANT_DNS_IPV4_ADDRESS`, `TENANT_DNS_IPV6_ADDRESS` (also already present per the existing `dns_automation.py` reads) — confirm and document in env-var docs |
| `deploy/helm/platform/Chart.yaml` | Add `cert-manager` (chart subdependency) and `cert-manager-webhook-hetzner` (community chart) under `dependencies:` |
| `deploy/helm/platform/templates/` | NEW templates: `certmanager-clusterissuer.yaml`, `certmanager-certificate-wildcard.yaml`, `certmanager-certificate-apex.yaml`, `service-loadbalancer.yaml` (Hetzner annotations); EXTEND: `ingress-platform.yaml` (wildcard rule), `status-snapshot-cronjob.yaml` (push-to-Cloudflare-Pages branch) |
| `deploy/helm/platform/values.prod.yaml` / `values.dev.yaml` | Add the `hetzner.*`, `certManager.*`, `ingress.wildcardHosts`, `webStatus.deployedHere/pushDestination/pushIntervalSeconds`, `billing.stripe.webhookUrl` blocks |
| `terraform/modules/hetzner-cluster/outputs.tf` | NEW |
| `terraform/modules/hetzner-dns-zone/` | NEW module |
| `terraform/environments/{production,dev}/main.tf` | Wire DNS module + default LB type |
| `.github/workflows/ci.yml` | Add `helm-snapshot-diff` step in the `helm-lint` job; add `helm-dry-run` step in the `e2e` job |
| `deploy/helm/platform/.snapshots/{prod,dev}.rendered.yaml` | NEW committed snapshot fixtures |
| `docs/operations/` | NEW runbook docs: `hetzner-cluster-provisioning.md`, `helm-snapshot.md`, `wildcard-tls-renewal.md`, `cloudflare-pages-status.md` |
