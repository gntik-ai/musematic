# DNS, Ingress, and Wildcard TLS

**Owner**: Platform / Architecture
**Last updated**: 2026-05-05 (UPD-053 / 106)

This page explains how the apex zone, the per-tenant subdomains, the
wildcard TLS certificate, and the ingress wildcard rule compose to
serve `https://<tenant>.musematic.ai/...` traffic end-to-end.

## Components

| Layer | Component | Owner |
|---|---|---|
| Authoritative DNS | Hetzner DNS — apex zone `musematic.ai` | `terraform/modules/hetzner-dns-zone/` |
| Bootstrap A/AAAA records (apex/app/api/grafana/status) | Hetzner DNS records | `terraform/modules/hetzner-dns-zone/` |
| Per-tenant A/AAAA records (`<slug>` / `<slug>.api` / `<slug>.grafana`) | Hetzner DNS records | `apps/control-plane/src/platform/tenants/dns_automation.py` |
| Wildcard cert (`*.musematic.ai` + `musematic.ai`) | cert-manager `Certificate` via Let's Encrypt DNS-01 | `deploy/helm/platform/templates/certmanager-certificate-wildcard.yaml` |
| DNS-01 challenge solver | `cert-manager-webhook-hetzner` | `deploy/helm/platform/Chart.yaml` (sub-dependency) |
| Ingress (HTTP/S termination) | ingress-nginx with wildcard rule | `deploy/helm/platform/templates/ingress-platform.yaml` |
| Hostname → tenant resolution | `tenant_resolver` middleware (UPD-046) | `apps/control-plane/src/platform/tenants/resolver.py` |

## Ownership rule

**Terraform owns the apex zone and bootstrap records.** Application code
(`tenants/dns_automation.py`) owns per-tenant subdomains. The wildcard
record `*` is intentionally NOT created in Terraform — TLS for
`<slug>.musematic.ai` is provided by the wildcard cert; A/AAAA records
for the slug are provisioned at tenant-creation time by the application.

## End-to-end flow

Concrete example: provisioning the `acme` tenant and serving the first
HTTPS request to `https://acme.musematic.ai`.

1. **Tenant creation** — A super-admin POSTs to
   `/api/v1/admin/tenants/`. `TenantsService.create_tenant` calls
   `dns_automation.create_tenant_subdomain("acme", ...)`.
2. **DNS write** — `HetznerDnsAutomationClient` POSTs 6 records
   (`acme`, `acme.api`, `acme.grafana` × {A, AAAA}) to the Hetzner DNS
   API. Each record's value is the cluster's Cloud LB IPv4/IPv6
   (resolved from `TENANT_DNS_IPV4_ADDRESS` / `TENANT_DNS_IPV6_ADDRESS`).
   Audit chain receives one `tenants.dns.records_created` entry; the
   `tenants_dns_automation_duration_seconds` histogram is observed.
3. **Propagation** — `verify_propagation` polls `1.1.1.1` for up to 60s
   for `acme.musematic.ai → 192.0.2.1`. Returns `True` once the public
   resolver agrees.
4. **First HTTPS request** — A user browses
   `https://acme.musematic.ai/`. DNS resolves via the Hetzner zone to
   the LB IPv4. The LB routes to `ingress-nginx` on the worker pool.
5. **TLS handshake** — `ingress-nginx` selects the TLS certificate
   matching `acme.musematic.ai` from the `wildcard-musematic-ai`
   Secret, which holds the cert issued by Let's Encrypt for
   `*.musematic.ai` + `musematic.ai`. Handshake succeeds.
6. **Routing** — The wildcard ingress rule (`spec.rules[].host:
   "*.musematic.ai"`) matches `acme.musematic.ai`. The `Host:` header
   passes to the control plane.
7. **Tenant resolution** — The `tenant_resolver` middleware extracts
   the slug `acme` from the `Host:` header, looks up the tenant id in
   the resolver cache (Redis-backed; see UPD-046), and binds the
   tenant context to the request via `set_config('app.tenant_id', ...)`
   for RLS enforcement on every downstream query.

## Renewal

cert-manager renews the wildcard cert ≥ 30 days before expiry
(`renewBefore: 720h`), via the same Hetzner DNS-01 webhook. The renewed
cert is written to the same Secret in place — ingress-nginx hot-reloads
without dropping in-flight requests. Renewal failures fire
`WildcardCertRenewalFailing` in Prometheus; runbook at
[wildcard-tls-renewal.md](../operations/wildcard-tls-renewal.md).

## Why wildcard, not per-tenant cert?

Let's Encrypt enforces a 50-cert-per-week-per-registered-domain limit.
A per-tenant cert (`acme.musematic.ai`) would consume budget linearly
with onboarding rate. A single wildcard collapses every per-tenant
subdomain into one issuance — even an aggressive onboarding day stays
well under the limit. The trade-off is that one renewal failure breaks
TLS for *all* tenants, which the alert + runbook explicitly target.

## Tenant deletion

When a tenant moves to data-lifecycle phase 2 (after the grace
window), the `dispatch_tenant_cascade` orchestrator calls
`DnsTeardownService.teardown(slug)`, which in turn invokes
`HetznerDnsAutomationClient.remove_tenant_subdomain`. The 6 records
are deleted idempotently (404 treated as success). Audit chain
records the removal.

## Related runbooks

- [Hetzner cluster provisioning](../operations/hetzner-cluster-provisioning.md)
- [Wildcard TLS renewal](../operations/wildcard-tls-renewal.md)
- [Cloudflare Pages status](../operations/cloudflare-pages-status.md)
- [Helm snapshot workflow](../operations/helm-snapshot.md)
