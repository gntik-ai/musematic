# System Architecture — v6 (Post SaaS Pass)

> This document supersedes `system-architecture-v5.md` for any conflict regarding tenant-aware architecture, billing infrastructure, and Hetzner two-cluster topology. Sections not modified by the SaaS pass remain consistent with v5.

---

## 1. Overview

After the SaaS pass, Musematic operates as a **multi-tenant SaaS platform** running on **two physically separated Hetzner Cloud Kubernetes clusters** (production and development), each with its own Hetzner Cloud Load Balancer. Tenants are logical isolation units identified by subdomain, with one mandatory `default` tenant hosting all Free/Pro users and arbitrary `enterprise` tenants manually provisioned per commercial contract.

Every layer of the system is now **tenant-aware**: hostname middleware resolves tenant from `Host` header, PostgreSQL Row-Level Security enforces data isolation as defense-in-depth, Vault paths are tenant-scoped, OAuth providers per tenant, cookies subdomain-scoped, Kafka events carry `tenant_id`, observability dashboards filterable per tenant, billing per-workspace (default tenant) or per-tenant (Enterprise).

---

## 2. Cluster Topology

### Production Cluster — `musematic-prod`

```
Hetzner Cloud Network: musematic-prod-net (eu-central, nbg1)
│
├── Control Plane (1× CCX33: 8 vCPU / 32 GB / 240 GB SSD)
│
├── Workers (3× CCX53: 16 vCPU / 64 GB / 480 GB SSD)
│
├── Hetzner Cloud Load Balancer (lb21)
│   ├── IPv4: <prod-lb-ipv4>
│   ├── IPv6: <prod-lb-ipv6>
│   └── Routes:
│       ├── musematic.ai (apex)
│       ├── app.musematic.ai (default tenant frontend)
│       ├── api.musematic.ai (default tenant API)
│       ├── grafana.musematic.ai (observability)
│       ├── *.musematic.ai (Enterprise tenant frontends)
│       ├── *.api.musematic.ai (Enterprise tenant APIs)
│       └── *.grafana.musematic.ai (Enterprise observability)
│
├── PostgreSQL HA (3 replicas, 200GB each)
├── Redis HA (3 replicas)
├── Kafka (3 brokers, 3 zookeepers)
├── Vault HA (3 replicas, integrated storage)
└── cert-manager + Hetzner DNS-01 webhook
```

### Development Cluster — `musematic-dev`

```
Hetzner Cloud Network: musematic-dev-net (eu-central, nbg1)
│
├── Control Plane (1× CCX21: 4 vCPU / 16 GB / 160 GB SSD)
├── Worker (1× CCX21: 4 vCPU / 16 GB / 160 GB SSD)
├── Hetzner Cloud Load Balancer (lb11)
│   └── Routes:
│       ├── dev.musematic.ai (dev shell)
│       ├── app.dev.musematic.ai (default tenant frontend in dev)
│       ├── dev.api.musematic.ai or api.dev.musematic.ai (default tenant API)
│       ├── dev.grafana.musematic.ai
│       ├── *.dev.musematic.ai
│       ├── *.api.dev.musematic.ai
│       └── *.grafana.dev.musematic.ai
│
├── PostgreSQL standalone (1 replica, 50GB)
├── Redis standalone (1 replica)
├── Kafka 1 broker
├── Vault standalone
└── cert-manager + Hetzner DNS-01 webhook
```

### Independence

Both clusters share zero state. Different kubeconfigs, different DNS records, different Stripe modes (live vs test), different Vault namespaces. A failure in dev cannot affect prod. Promotion from dev to prod is a deliberate Helm upgrade with values overlay swap.

### Status Page Independent Infrastructure

Per UPD-045 constitution: `status.musematic.ai` and `status.dev.musematic.ai` run on **Cloudflare Pages** (or alternative dedicated VM with nginx). They are **NOT** in either platform cluster. CronJobs in each platform cluster regenerate health content and push to the independent host every 30 seconds.

---

## 3. Tenant-Aware Request Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ Browser request: GET https://acme.musematic.ai/api/v1/agents     │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
        ┌──────────────────────────────────────┐
        │ Hetzner Cloud Load Balancer (TLS)    │
        │ Wildcard TLS *.musematic.ai          │
        └──────────────────────────────────────┘
                          │
                          ▼
        ┌──────────────────────────────────────┐
        │ NGINX Ingress Controller             │
        │ Routes by Host:                      │
        │   acme.musematic.ai → frontend       │
        │   acme.api.musematic.ai → api        │
        │   acme.grafana.musematic.ai → grafana│
        └──────────────────────────────────────┘
                          │
                          ▼
        ┌──────────────────────────────────────┐
        │ Control Plane API (FastAPI)          │
        │                                      │
        │ Middleware Pipeline (in order):      │
        │ 1. TenantResolverMiddleware          │
        │    - Extract subdomain from Host     │
        │    - Lookup Tenant (Redis-cached)    │
        │    - Set request.state.tenant        │
        │    - SET LOCAL app.tenant_id = ...   │
        │ 2. AuthMiddleware                    │
        │ 3. RateLimitMiddleware               │
        │ 4. AuditMiddleware                   │
        │ 5. Route handler                     │
        │                                      │
        │ For /api/v1/platform/*:              │
        │ - Use musematic_platform_staff       │
        │   PG role (BYPASSRLS)                │
        │ - All-tenant queries allowed         │
        └──────────────────────────────────────┘
                          │
                          ▼
        ┌──────────────────────────────────────┐
        │ PostgreSQL                           │
        │ - app.tenant_id session var          │
        │ - RLS policy enforces                │
        │   tenant_id = app.tenant_id          │
        │ - Queries auto-filtered              │
        └──────────────────────────────────────┘
```

---

## 4. Subdomain Conventions

### Production

| Subdomain | Purpose | Tenant |
|---|---|---|
| `musematic.ai` (apex) | Marketing landing or 301 to app | n/a |
| `app.musematic.ai` | Default tenant frontend | default |
| `api.musematic.ai` | Default tenant API | default |
| `grafana.musematic.ai` | Default tenant observability | default |
| `acme.musematic.ai` | Enterprise tenant frontend | acme |
| `acme.api.musematic.ai` | Enterprise tenant API | acme |
| `acme.grafana.musematic.ai` | Enterprise tenant observability | acme |
| `status.musematic.ai` | Public status page | n/a (independent) |

### Development

| Subdomain | Purpose | Tenant |
|---|---|---|
| `dev.musematic.ai` | Dev cluster shell + default tenant frontend | default |
| `app.dev.musematic.ai` | Default tenant frontend (alternate form) | default |
| `dev.api.musematic.ai` | Default tenant API | default |
| `api.dev.musematic.ai` | Default tenant API (alternate form) | default |
| `dev.grafana.musematic.ai` | Default tenant observability | default |
| `acme.dev.musematic.ai` | Enterprise tenant frontend in dev | acme |
| `status.dev.musematic.ai` | Dev status page | n/a (independent) |

### Reserved Slugs

Cannot be used as tenant slugs (DB trigger enforced):

`api`, `grafana`, `status`, `www`, `admin`, `platform`, `webhooks`, `public`, `docs`, `help`, `app` (default-only).

---

## 5. Data Model — Tenant Layering

```
Tenant
  │
  ├── (default kind) ──── Workspaces (each has Subscription → Plan version)
  │                       │
  │                       ├── Members (with subscription quota: max_users_per_workspace)
  │                       ├── Agents (with subscription quota: max_agents_per_workspace)
  │                       ├── Executions (counted against quota: executions/day, executions/month, minutes/day, minutes/month)
  │                       ├── Conversations
  │                       ├── Costs
  │                       └── Audit Chain Entries
  │
  └── (enterprise kind) ── Subscription (tenant-scoped — single plan version applies to all workspaces)
                           │
                           └── Workspaces
                               │
                               ├── Members
                               ├── Agents
                               ├── Executions (no quota — unlimited per Enterprise contract by default)
                               ├── Conversations
                               ├── Costs
                               └── Audit Chain Entries
```

### Plan Versioning

```
Plan (e.g., 'pro')
  │
  ├── PlanVersion 1 (price: 49 EUR, executions/month: 5000, ...)
  │   └── Subscriptions pinned to v1 (existing customers stay here unless they opt-in)
  │
  ├── PlanVersion 2 (price: 59 EUR, executions/month: 5000, ...)
  │   └── Subscriptions pinned to v2 (new customers since publication)
  │
  └── PlanVersion 3 (price: 59 EUR, executions/month: 6000, ...)
      └── Subscriptions pinned to v3 (currently published, new signups)
```

Edits to a PlanVersion are forbidden once `published_at` set. Editing creates a new version.

---

## 6. Billing Architecture

### PaymentProvider Abstraction

```
┌─────────────────────────────────────────────────────┐
│ Bounded Contexts (Subscriptions, Quotas, ...)       │
└─────────────────────────────────────────────────────┘
                       │
                       ▼ (depends on)
┌─────────────────────────────────────────────────────┐
│ PaymentProvider Interface (abstract)                │
└─────────────────────────────────────────────────────┘
                       │
        ┌──────────────┼─────────────────┐
        ▼              ▼                  ▼
   Stripe Impl      Stub Impl       (future) Paddle Impl
   (default)       (tests/offline)
```

Methods: `create_customer`, `attach_payment_method`, `create_subscription`, `update_subscription`, `cancel_subscription`, `report_usage`, `charge_overage`, `create_customer_portal_session`, `verify_webhook_signature`, `handle_webhook_event`.

Stripe is the default, configured per-environment (live in prod, test in dev).

### Webhook Handling

```
Stripe → POST https://api.musematic.ai/api/webhooks/stripe (prod)
       → POST https://dev.api.musematic.ai/api/webhooks/stripe (dev)
       │
       ▼
HMAC signature verification (webhook secret in Vault)
       │
       ▼
Idempotency check (processed_webhooks table, key: event.id)
       │
       ▼
Resolve tenant via Stripe customer ID
       │
       ▼
Dispatch handler:
  - customer.subscription.created/updated/deleted
  - invoice.payment_succeeded/failed
  - customer.subscription.trial_will_end
  - payment_method.attached
  - charge.dispute.created
       │
       ▼
Update local subscription state
Audit chain entry
Publish Kafka event (e.g., subscription.activated)
       │
       ▼
HTTP 200 to Stripe
```

### Failed Payment Grace Period

```
Stripe webhook: invoice.payment_failed
       │
       ▼
Subscription status → past_due
PaymentFailureGrace row created (grace_ends_at = now + 7 days)
       │
       ├─ Day 1: reminder email
       ├─ Day 3: reminder email
       ├─ Day 5: reminder email + warning
       │
       ▼ (Day 7)
       
If payment recovered (any time during grace):
       Status → active
       Grace row resolution = payment_recovered
       
If still failed at day 7:
       Status → suspended
       Workspace plan → free
       Cleanup notification (data exceeding free quotas)
       Grace row resolution = downgraded_to_free
```

---

## 7. Quota Enforcement Pipeline

```
User triggers: POST /api/v1/executions/run
                       │
                       ▼
              QuotaEnforcer.check_execution(workspace_id)
                       │
        ┌──────────────┼──────────────────────────────┐
        │              │                               │
        ▼              ▼                               ▼
   Get active     Get plan_version              Get current usage
   subscription   for that subscription          for current period
        │              │                               │
        └──────────────┼───────────────────────────────┘
                       ▼
        Compare projected usage to quotas
              │                          │                   │
              │                          │                   │
        ▼ (within quota)         ▼ (exceeded, Free)    ▼ (exceeded, Pro w/ overage_price > 0)
        Proceed                  Reject HTTP 402         Check overage_authorizations
                                                                  │
                                                ┌─────────────────┼────────────────┐
                                                ▼                                  ▼
                                        Authorized? Resume     Not authorized? Pause + notify
                                                                                  │
                                                                                  ▼ (user authorizes)
                                                                          Resume + meter to Stripe
```

---

## 8. RLS Defense in Depth

```
Application Layer:
  Repository.find(workspace_id, tenant_id=?)
  - tenant_id always passed explicitly
  - WHERE clause includes tenant_id filter
  - CI static analysis enforces this
       │
       ▼
Database Session:
  SET LOCAL app.tenant_id = <uuid>
  set by middleware at start of every request
       │
       ▼
RLS Policy (every tenant-scoped table):
  CREATE POLICY tenant_isolation ON <table>
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
       │
       ▼
Even if app code forgot WHERE tenant_id, RLS filters
       │
       ▼
Result: empty result set (look like no data)
```

The `musematic_platform_staff` PG role has `BYPASSRLS` and is used by `/api/v1/platform/*` endpoints via a separate connection pool. Application code uses the regular `musematic_app` role (no BYPASSRLS).

---

## 9. Vault Path Tenancy

```
secret/data/musematic/{env}/
  ├── platform/
  │   ├── stripe/api-key
  │   ├── stripe/webhook-secret
  │   ├── cert-manager/hetzner-dns-token
  │   └── (other platform-level secrets)
  │
  └── tenants/
      ├── default/
      │   ├── oauth/google/client-secret
      │   ├── oauth/github/client-secret
      │   ├── smtp/credentials
      │   └── ...
      │
      ├── acme/
      │   ├── oauth/google/client-secret
      │   ├── sso/saml/idp-cert
      │   ├── dpa/dpa-v1.pdf
      │   └── ...
      │
      └── globex/
          └── ...
```

Vault policies grant tenant-scoped read access to each tenant's path. Cross-tenant Vault access is forbidden by policy.

---

## 10. OAuth Per Tenant

Each tenant has its own OAuth provider config:

```
tenant_oauth_providers
  - tenant_id (FK)
  - provider (google | github | microsoft | saml)
  - client_id
  - client_secret_vault_path
  - callback_url (e.g., https://acme.musematic.ai/auth/oauth/google/callback)
  - is_active
  - configured_by_user_id
```

Login flow:
1. User navigates to `acme.musematic.ai/login`.
2. Hostname middleware resolves tenant Acme.
3. UI displays OAuth providers configured for Acme.
4. User clicks "Sign in with Google".
5. OAuth flow uses Acme's Google client_id, redirects to Acme's callback.
6. Callback verifies tenant context, looks up user in Acme tenant.
7. Cookie issued with `Domain=acme.musematic.ai`.

Default tenant uses platform-default OAuth config (configured by super admin or via env vars from UPD-041 OAuth env-var bootstrap).

---

## 11. Marketplace Multi-Scope Architecture

```
agents.marketplace_scope ∈ { workspace | tenant | public_default_tenant }

┌─────────────────────────────────────────────────────────────┐
│ Default Tenant (kind=default)                                │
│                                                              │
│  Workspace W1                Workspace W2                    │
│   ├─ agents (workspace)      ├─ agents (workspace)           │
│   ├─ agents (tenant) ─┐      └─ ←── visible from W2 ─┐       │
│   └─ agents (public) ─┼─ visible to all default tenant       │
│                        │                                     │
└────────────────────────┼─────────────────────────────────────┘
                         │
                         │ (review_status = published)
                         ▼
              Public Marketplace (visible to all default tenant users)
                         │
                         │ (Enterprise tenant has consume_public_marketplace=true)
                         ▼
┌──────────────────────────────────────────────────────────────┐
│ Enterprise Tenant Acme (kind=enterprise)                     │
│                                                              │
│  Workspace E1                                                │
│   ├─ agents (workspace) ─ private to E1                      │
│   ├─ agents (tenant)    ─ visible to all Acme workspaces     │
│   └─ ← cannot publish (public scope) at all                  │
│                                                              │
│  If feature flag set: read-only access to public marketplace │
└──────────────────────────────────────────────────────────────┘
```

RLS policy on `agents` is more permissive than the default tenant_isolation:

```sql
CREATE POLICY agents_visibility ON agents
  USING (
    tenant_id = current_setting('app.tenant_id')::uuid
    OR (
      marketplace_scope = 'public_default_tenant'
      AND review_status = 'published'
      AND (
        current_setting('app.tenant_kind') = 'default'
        OR current_setting('app.consume_public_marketplace') = 'true'
      )
    )
  );
```

---

## 12. DNS and TLS Architecture

### DNS Records (Hetzner DNS, zone: musematic.ai)

```
Type    Name                    Value
─────   ─────────────────       ───────────────────────────────
A       musematic.ai            <prod-lb-ipv4>
AAAA    musematic.ai            <prod-lb-ipv6>
A       app.musematic.ai        <prod-lb-ipv4>
AAAA    app.musematic.ai        <prod-lb-ipv6>
A       api.musematic.ai        <prod-lb-ipv4>
AAAA    api.musematic.ai        <prod-lb-ipv6>
A       grafana.musematic.ai    <prod-lb-ipv4>
AAAA    grafana.musematic.ai    <prod-lb-ipv6>
A       *.musematic.ai          <prod-lb-ipv4>  ← wildcard
AAAA    *.musematic.ai          <prod-lb-ipv6>
A       dev.musematic.ai        <dev-lb-ipv4>
AAAA    dev.musematic.ai        <dev-lb-ipv6>
A       *.dev.musematic.ai      <dev-lb-ipv4>   ← wildcard
AAAA    *.dev.musematic.ai      <dev-lb-ipv6>
CAA     musematic.ai            0 issue "letsencrypt.org"
CNAME   status.musematic.ai     <cloudflare-pages-domain>
CNAME   status.dev.musematic.ai <cloudflare-pages-domain>
TXT     _dmarc.musematic.ai     v=DMARC1; p=quarantine; rua=mailto:dmarc@musematic.ai
```

### TLS

Two wildcard certs per environment:
- Prod: `*.musematic.ai` + apex `musematic.ai`
- Dev: `*.dev.musematic.ai` + apex `dev.musematic.ai`

Issued via cert-manager + Let's Encrypt + Hetzner DNS-01 webhook (`cert-manager-webhook-hetzner`). Auto-renewed 30 days before expiry.

---

## 13. Tenant Lifecycle States

```
                ┌─────────────┐
                │   Pending   │  (Enterprise only — between super admin
                │  (provision)│   create and DNS automation completion)
                └─────────────┘
                       │
                       ▼
                ┌─────────────┐
        ┌────── │   Active    │ ──────┐
        │       └─────────────┘       │
        │              ▲              │
        │              │              ▼
        │              │     ┌──────────────────┐
        │              │     │   Suspended      │
        │              │     │   (data retained,│
        │              │     │    access blocked)│
        │              │     └──────────────────┘
        │              │              │
        │              │              ▼ (90 days or super admin force)
        │              │     ┌──────────────────┐
        │              │     │  Pending         │
        │              │     │  Deletion        │
        │              │     │  (grace 30 days) │
        │              │     └──────────────────┘
        │              │              │
        │              │              ▼
        │              │     ┌──────────────────┐
        │              │     │   Deleted        │
        │              │     │   (cascade purge,│
        │              │     │   tombstone only)│
        │              │     └──────────────────┘
        │              │
        ▼              │
   Pending Deletion ───┘  (super admin can recover during grace)
```

The default tenant has a database constraint preventing transition to suspended/deleted states.

---

## 14. Comparison to v5

| Aspect | v5 (post-audit-pass) | v6 (post-saas-pass) |
|---|---|---|
| Tenancy | Single-tenant by default; multi-tenant feature-flagged | Always multi-tenant; default tenant + Enterprise tenants |
| Isolation | Workspace-level | Tenant-level (with workspace nested under tenant) |
| Subdomain handling | Single domain | Subdomain-as-tenant |
| Database | Tables without tenant_id | All tenant-scoped tables have tenant_id + RLS |
| Vault paths | Per-environment, not tenant-scoped | Tenant-scoped: `secret/data/musematic/{env}/tenants/{slug}/...` |
| OAuth providers | Platform-global | Per-tenant |
| Cookies | Shared across subdomains | Subdomain-scoped per tenant |
| Plans / Subscriptions | Conceptual (FR-499 cost budgets only) | First-class entities with versioning |
| Billing | None | Stripe via PaymentProvider abstraction |
| Quotas | Workspace-level budgets only | Plan-driven, hard-cap/overage/none modes |
| Cluster topology | Single kind/k3s/Hetzner LB | Two clusters: prod + dev with separate LBs |
| Status page | In-cluster proposal | Independent infrastructure (Cloudflare Pages or VM) |
| Marketplace | Single-scope | Three scopes: workspace, tenant, public-default-tenant |
| DPA | Conceptual | Per-tenant, uploaded for Enterprise |

---

## 15. Cross-References to Specs

- **UPD-046** Tenant Architecture — sections 2, 3, 4, 5, 8, 9, 10, 13
- **UPD-047** Plans, Subscriptions, Quotas — sections 5, 7
- **UPD-048** Public Signup — section 5
- **UPD-049** Marketplace Scope — section 11
- **UPD-050** Abuse Prevention — (non-architectural; security layer)
- **UPD-051** Data Lifecycle — section 13
- **UPD-052** Billing and Overage — section 6
- **UPD-053** Hetzner Helm — sections 2, 12
- **UPD-054** SaaS E2E — verifies the architecture
