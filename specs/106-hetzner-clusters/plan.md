# Implementation Plan: UPD-053 — Hetzner Production+Dev Clusters with Helm Overlays and Ingress Topology

**Branch**: `106-hetzner-clusters` | **Date**: 2026-05-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/106-hetzner-clusters/spec.md`

## Summary

Finalises the production+dev Kubernetes topology on Hetzner Cloud by **extending** existing scaffolding rather than creating new BCs:

1. The Helm chart at `deploy/helm/platform/` already ships `values.yaml`, `values.prod.yaml`, and `values.dev.yaml`. UPD-053 adds five top-level overlay blocks (`hetzner`, `certManager`, `ingress.wildcardHosts`, `webStatus.deployedHere/pushDestination`, `billingStripe.webhookUrl`) and three new templates (cert-manager `ClusterIssuer` + `Certificate` + Hetzner-annotated LoadBalancer Service) so a freshly cloned operator can take a Hetzner project from `terraform apply` to a fully healthy cluster in ≤ 30 minutes (SC-001).
2. The existing `apps/control-plane/src/platform/tenants/dns_automation.py` (which today exposes only `ensure_records(subdomain)`) gains `create_tenant_subdomain(slug)` (3 subdomains × A+AAAA), `remove_tenant_subdomain(slug)`, and `verify_propagation(...)` per the contract in `contracts/dns-automation-service.md`. The wiring point in `tenants/service.py:139` is updated; a new cascade handler in `tenants/cascade.py` removes records when `data_lifecycle/` enters phase 2 (UPD-051).
3. The existing Terraform under `terraform/modules/hetzner-cluster/` and `terraform/environments/{production,dev}/` is extended with a new `hetzner-dns-zone/` module, per-env LB-type defaults (`lb21`/`lb11`), and module outputs for `lb_ipv4` / `lb_ipv6` so the DNS module wires automatically.
4. Constitution rule 49 (status page independence) is satisfied for prod via Cloudflare Pages with a CronJob inside the cluster pushing snapshot content. Dev keeps the in-cluster status deployment for cost (research R6).
5. CI gains a snapshot-diff step inside `helm-lint` and a `helm install --dry-run` step inside `e2e` (research R7) — both inside existing jobs to avoid a new workflow file.

No new database tables, no new Kafka topics, no new Vault path families beyond an additive Hetzner DNS token entry. The feature is overwhelmingly infrastructure-as-code.

## Technical Context

**Language/Version**: Python 3.12+ (control plane DnsAutomationClient extension), HCL (Terraform 1.6+), YAML (Helm 3.14+, Kubernetes 1.29+), shell (CI). No Go, no TypeScript, no SQL DDL. Frontend: no changes (per-tenant subdomains are routed transparently by the wildcard ingress; the existing UPD-046 hostname-extraction middleware handles the slug).
**Primary Dependencies (existing, reused)**: FastAPI 0.115+ (control plane), Pydantic v2, httpx 0.27+ (Hetzner DNS API client — already used by `dns_automation.py`), APScheduler 3.x (cert renewal monitor — uses cert-manager directly so no new schedule), `SecretProvider` (Vault), `AuditChainService` (UPD-024), `AsyncRedisClient` (no new keys; per-zone-slug locking is in-process `asyncio.Lock`). Helm: `cert-manager` v1.16.0 sub-dependency, `cert-manager-webhook-hetzner` v0.6.0 community chart, existing `external-secrets` operator (UPD-040) for Vault → Kubernetes Secret sync.
**Primary Dependencies (NEW)**:
- *Helm*: `cert-manager` (jetstack), `cert-manager-webhook-hetzner` (vadimkim) added as conditional sub-dependencies in `Chart.yaml`.
- *Terraform*: `hetznerdns/hetznerdns ~> 2.2` provider added (alongside existing `hetznercloud/hcloud ~> 1.50`).
- *None at the Python level* — no new pip packages.
**Storage**:
- **PostgreSQL** — no DDL, no Alembic migration. The DNS records this feature manages live in Hetzner DNS; the audit chain captures Hetzner record ids per change. Persisting record ids in PostgreSQL was rejected (research R2).
- **Vault** — 1 new path family: `secret/data/musematic/{env}/dns/hetzner/api-token`. Cloudflare Pages token already added by the operator runbook at `secret/data/musematic/{env}/cloudflare/pages-token`. Both read via the existing `SecretProvider` (rule 39) and synced to Kubernetes Secrets via the existing `external-secrets` operator (rule 38 failure-closed: cert-manager and `dns_automation.py` both fail-closed if the Secret is unset).
- **Redis** — no new keys. Per-zone-slug serialization is in-process `asyncio.Lock` (single-process control plane per profile; concurrent-creation-of-same-slug already guarded by the `tenants.slug` UNIQUE constraint upstream).
- **Kafka** — no new topics. DNS create/delete are recorded via the audit chain only (the existing `tenants.events` envelope `TenantCreatedPayload` / `TenantDeletedPayload` carries enough downstream metadata; per-DNS-change events would be redundant noise — research R2).
- **S3** — none.
**Testing**:
- *Unit (`tests/unit/tenants/`)* — extend `test_dns_automation.py` (add cases for `create_tenant_subdomain` 3-record-set, `remove_tenant_subdomain` list-and-filter, `verify_propagation` happy-path + timeout, retry/backoff on transient 5xx, `ReservedSlugError` guard, audit chain emission shape, mock client parity).
- *Helm (`deploy/helm/platform/tests/`)* — extend the existing `helm-unittest` suite with assertions on the new templates (`certmanager-clusterissuer.yaml`, `certmanager-certificate-wildcard.yaml`, `service-loadbalancer.yaml`, `ingress-platform.yaml` wildcard rule, `status-snapshot-cronjob.yaml` push-to-Pages branch).
- *Snapshot fixtures (`deploy/helm/platform/.snapshots/`)* — new committed `prod.rendered.yaml` and `dev.rendered.yaml` regenerated via `make helm-snapshot-update` per the CI contract.
- *E2E (`tests/e2e/suites/hetzner_topology/`)* — 6 skip-marked scaffolds per the user input plus the J29 cluster-isolation journey at `tests/e2e/journeys/test_j29_hetzner_topology.py`. All skip-marked by default (run only against a real Hetzner project gated by `RUN_J29=1`); the J35 wildcard-TLS renewal journey from US4 lives at `tests/e2e/journeys/test_j35_wildcard_tls_renewal.py`.
- *Coverage*: rule 14 (≥95%) applies to the Python extension (`dns_automation.py`); the Helm/Terraform/CI work is covered by the snapshot diff and helm-unittest gates rather than line coverage.
**Target Platform**: Existing Helm umbrella chart at `deploy/helm/platform/`. Two physically separated Hetzner Cloud Kubernetes clusters per the spec (`musematic-prod` and `musematic-dev`). Production: 1× CCX33 control plane + 3× CCX53 workers + 1× lb21 Cloud LB (eu-central, nbg1). Dev: 1× CCX21 + 1× CCX21 + 1× lb11. Each cluster has its own private network (`hcloud_network`) so dev cannot reach prod private IPs (FR-A2).
**Project Type**: Infrastructure-as-code feature. One Python BC extension (`tenants/dns_automation.py`), one Terraform module addition (`hetzner-dns-zone/`), Helm chart additions, CI gate additions. No frontend changes.
**Performance Goals**:
- Operator-runbook wall-clock end-to-end (terraform apply → helm install → wildcard cert Ready → first healthcheck): ≤ 30 min p95 (SC-001).
- Tenant subdomain provisioning resolvable in public DNS: ≤ 5 min p95 from create-tenant API call (SC-003); per-call DNS automation latency (Hetzner API + propagation check + audit) ≤ 65 s p95.
- Wildcard cert auto-renewal success rate: ≥ 95%/year (SC-004); failure alert latency: ≤ 15 min from the second consecutive failed attempt.
- Status-page push tick: every 30 s for live data (prod), 60 s (dev); stale-content alert if push age > 10 min.
- Helm `--dry-run` in CI: ≤ 90 s wall-clock per env.
**Constraints**:
- **Hetzner DNS API rate limits** — 1 req/s burst per token per Hetzner docs; the per-(zone, slug) `asyncio.Lock` plus exponential backoff on 5xx keeps us under (FR-785, edge case 2).
- **Let's Encrypt rate limits** — 50 certs/registered-domain/week. Wildcards collapse all per-tenant subdomains into a single cert, so even a busy onboarding day stays under (rule out the FR-787 risk path).
- **Reserved-slug guard mandatory** — `RESERVED_SLUGS` from `tenants/reserved_slugs.py` is the source of truth; `DnsAutomationClient.create_tenant_subdomain` checks it as defence-in-depth (FR-786).
- **Vault failure-closed** — cert-manager Hetzner DNS-01 webhook AND `dns_automation.py` both refuse to operate if the `hetzner-dns-token` Secret is missing (rule 38, rule 41).
- **Production status page MUST live outside the cluster** — `webStatus.deployedHere=false` for `values.prod.yaml`; the in-cluster `web-status-deployment.yaml` is rendered only when `deployedHere=true` (the chart already supports this; the prod overlay flips it). Constitution rule 49.
- **Audit chain on every DNS change** — `tenants.dns.records_created` / `records_removed` / `records_failed` entries via `AuditChainService.append`; verifiable end-to-end by `tools/verify_audit_chain.py` (SC-010).
- **Brownfield rule 1 (never rewrite)** — file naming follows the dotted convention (`values.prod.yaml`); existing `dns_automation.py` is extended in place; existing `terraform/modules/hetzner-cluster/` is extended with new outputs only.
- **CI gate paths-filter** — the existing `.github/workflows/ci.yml:73` already filters on `deploy/helm/**`; UPD-053 adds a `terraform/**` filter for the `terraform-validate` job.
**Scale/Scope**:
- ~3 new methods on `DnsAutomationClient` Protocol; ~150 new lines of Python in `dns_automation.py`; ~30 new lines in `tenants/cascade.py`; ~20 new lines in `tenants/service.py`.
- 4 new Helm templates (`certmanager-clusterissuer.yaml`, `certmanager-certificate-wildcard.yaml`, `service-loadbalancer.yaml`, `vaultstaticsecret-hetzner-dns-token.yaml`) + 2 extended templates (`ingress-platform.yaml`, `status-snapshot-cronjob.yaml`).
- 2 extended `values.{prod,dev}.yaml` files (5 new top-level blocks each).
- 1 new Terraform module (`hetzner-dns-zone/`) + 1 new outputs file on the existing module + 2 extended env overlays.
- 2 new CI steps inside existing jobs.
- 4 new operator runbooks under `docs/operations/`.
- 6 new E2E scaffolds + 2 new journey scaffolds. No frontend changes.

## Constitution Check

Mapped to Constitution v1.3.0 principles I–XVI plus audit-pass rules (1–50). One verdict per gate; gaps tracked in **Complexity Tracking**.

| Principle / Rule | Verdict | Notes |
|---|---|---|
| **I. Modular Monolith** | ✅ | DNS automation extension lives inside the existing `tenants/` BC; no new top-level service or BC. |
| **II. Go Reasoning Engine separate** | ✅ | No Go work; Go satellites don't own DNS or cluster topology. |
| **III. Dedicated data stores** | ✅ | No data store changes; Hetzner DNS is the source of truth for records. |
| **IV. No cross-boundary DB access** | ✅ | `tenants/dns_automation.py` only writes via the audit chain service (existing public interface) and reads no other BC's tables. |
| **V. Append-only execution journal** | N/A | Not a workflow runtime feature. |
| **VI. Policy is machine-enforced** | ✅ | Reserved-slug guard enforced in `DnsAutomationClient.create_tenant_subdomain` server-side (defence-in-depth on top of `TenantsService` upstream). |
| **VII. Simulation isolation** | N/A | |
| **VIII. FQN addressing** | N/A | |
| **IX. Zero-trust default visibility** | ✅ | Tenant subdomain creation is gated by super-admin `provision_enterprise_tenant`; no public DNS API endpoint added. |
| **X. GID correlation** | ✅ | DNS audit/log entries carry the existing correlation-context fields. |
| **XI. Secrets never in LLM context** | ✅ | Hetzner DNS token, Cloudflare Pages token never serialized into log/audit payloads. |
| **XII. Task plans persisted** | N/A | |
| **XIII. Attention pattern** | N/A | |
| **XIV. A2A** | N/A | |
| **XV. MCP** | N/A | |
| **XVI. Generic S3** | N/A | No object storage. |
| **Brownfield rule 1 (never rewrite)** | ✅ | `dns_automation.py`, `tenants/service.py`, `tenants/cascade.py`, `terraform/modules/hetzner-cluster/`, `values.{prod,dev}.yaml`, `Chart.yaml`, `ci.yml` all extended in place. The existing `ensure_records` Protocol method is kept as a deprecated facade for one release. |
| **Brownfield rule 2 (every change is an Alembic migration)** | ✅ | No DDL; no migration. The "every change" rule is for schema changes — IaC isn't schema. |
| **Brownfield rule 3 (preserve tests)** | ✅ | Existing `test_dns_automation.py` cases keep passing because the legacy `ensure_records` path is preserved. |
| **Brownfield rule 4 (use existing patterns)** | ✅ | Protocol seam, `SecretProvider`, `AuditChainService`, `external-secrets`-driven Vault sync, helm-unittest, dotted overlay naming — all reused. |
| **Brownfield rule 5 (cite exact files)** | ✅ | Every modified file is named in `data-model.md` § Cross-references. |
| **Brownfield rule 6 (additive enums)** | N/A | No enum changes. |
| **Brownfield rule 7 (backward-compatible APIs)** | ✅ | The deprecated `ensure_records` facade preserves the old call shape. |
| **Brownfield rule 8 (feature flags)** | ✅ | `certManager.enabled`, `certManager.hetznerDnsWebhook.enabled`, `webStatus.deployedHere`, `webStatus.pushDestination` — every behaviour change is gated. |
| **Rule 9 audit chain integrity** | ✅ | `AuditChainService.append` invoked on every DNS create/remove/failure (FR-A3). |
| **Rule 10 every credential goes through Vault** | ✅ | Hetzner DNS API token + Cloudflare Pages token both in Vault; cert-manager webhook reads via `external-secrets` sync. |
| **Rule 11 SecretProvider only** | ✅ | `dns_automation.py` reads token via existing `SecretProvider`; no `os.getenv` in the modified paths. |
| **Rule 14 ≥95% coverage** | ✅ | `dns_automation.py` extension hits 95%+ in unit tests; the Hetzner-API integration paths (live network) are covered by skip-marked integration tests + audit-pass omit list, mirroring UPD-052's pattern. |
| **Rule 15 BC boundary** | ✅ | `dns_automation.py` lives under `tenants/`; cert-manager templates live under `deploy/helm/platform/templates/`; Terraform under `terraform/`. No cross-boundary leakage. |
| **Rule 17 outbound webhooks HMAC-signed** | N/A | This feature has no outbound webhooks. The Cloudflare Pages push uses `wrangler` (Cloudflare's CLI), not a webhook. |
| **Rule 24 dashboard per BC** | ✅ | Extends the existing `tenants.yaml` Grafana dashboard at `deploy/helm/observability/templates/dashboards/` with three new panels: DNS-automation latency p50/p95, DNS-automation failures by slug, wildcard-cert days-until-expiry. No new dashboard file (the BC `tenants/` already has one). |
| **Rule 25 E2E suite + journey crossing** | ✅ | New suite `tests/e2e/suites/hetzner_topology/` (6 scaffolds); journey J29 (cluster isolation) and J35 (wildcard TLS renewal); each crosses `tenants/` ↔ `data_lifecycle/` ↔ infrastructure boundaries. |
| **Rule 26 real observability backends in journey tests** | ✅ | J29/J35 run against the kind cluster with the full observability stack from UPD-047. |
| **Rule 27 dashboards in unified Helm bundle** | ✅ | The new dashboard panels ship in the existing `deploy/helm/observability/` chart. |
| **Rule 28 a11y tested** | N/A | No frontend surface; no a11y assertions. |
| **Rule 33 2PA enforced server-side** | N/A | No 2PA-required action; tenant provisioning already uses the existing super-admin path. |
| **Rule 38 SecretProvider Vault failure closed** | ✅ | `dns_automation.py` and the cert-manager webhook both fail-closed when the `hetzner-dns-token` Secret is missing or stale. |
| **Rule 39 Vault paths only** | ✅ | `secret/data/musematic/{env}/dns/hetzner/api-token` follows the established Vault layout convention. |
| **Rule 49 outage independence** | ✅ | Production `webStatus.deployedHere=false`; CronJob pushes to Cloudflare Pages every 30 s; in-cluster `web-status-deployment.yaml` rendered only on dev. |
| **Rule 50 mock LLM in creator previews** | N/A | |

**Constitution Check verdict**: PASS. No principle violations. The narrowing of "create a new `dns_automation/` BC" (user input wording) to "extend the existing `tenants/dns_automation.py`" is justified in **Complexity Tracking** below and traced back to research R1.

## Project Structure

### Documentation (this feature)

```text
specs/106-hetzner-clusters/
├── plan.md                       # This file
├── research.md                   # Phase 0 — 8 decisions
├── data-model.md                 # Phase 1 — no DDL; cross-refs to brownfield code
├── quickstart.md                 # Phase 1 — operator runbook (≤30 min E2E)
├── contracts/
│   ├── dns-automation-service.md # extended Python Protocol
│   ├── helm-overlay-shape.md     # values.{prod,dev}.yaml deltas
│   ├── terraform-modules.md      # hetzner-dns-zone module + per-env tfvars
│   ├── cert-manager-clusterissuer.md  # 3 new templates + Vault sync
│   ├── ci-helm-snapshot.md       # snapshot diff + dry-run gates
│   └── cloudflare-pages-status.md     # rule 49 status independence
├── checklists/
│   └── requirements.md
└── tasks.md                      # Phase 2 (/speckit-tasks command — NOT created here)
```

### Source Code (repository root)

```text
apps/control-plane/
├── src/platform/tenants/
│   ├── dns_automation.py             # EXTEND — add create_tenant_subdomain,
│   │                                 #   remove_tenant_subdomain, verify_propagation;
│   │                                 #   keep ensure_records as deprecated facade
│   ├── service.py                    # EXTEND — call create_tenant_subdomain at line 139
│   │                                 #   (replaces existing ensure_records call)
│   ├── cascade.py                    # EXTEND — register tenant_dns_cascade_handler
│   │                                 #   in tenant_cascade_handlers (UPD-051 phase 2)
│   └── exceptions.py                 # EXTEND — add DnsAutomationPropagationTimeoutError
├── src/platform/common/config.py     # CONFIRM — HETZNER_DNS_API_TOKEN, HETZNER_DNS_ZONE_ID,
│                                     #   TENANT_DNS_IPV4_ADDRESS, TENANT_DNS_IPV6_ADDRESS already
│                                     #   present per current dns_automation.py reads; document in
│                                     #   docs/configuration/environment-variables.md (regenerate)
└── tests/unit/tenants/
    └── test_dns_automation.py        # EXTEND — new cases for the 3 new methods,
                                      #   reserved-slug guard, retry/backoff, audit emission

deploy/helm/platform/
├── Chart.yaml                        # EXTEND — add cert-manager + cert-manager-webhook-hetzner
│                                     #   conditional sub-dependencies
├── values.yaml                       # EXTEND — add hetzner.* / certManager.* / ingress.wildcardHosts
│                                     #   skeleton with empty/disabled defaults; non-breaking
├── values.prod.yaml                  # EXTEND — populate hetzner.* (lb21, prod LB),
│                                     #   certManager.* (Let's Encrypt prod, wildcard-musematic-ai),
│                                     #   ingress.wildcardHosts (*.musematic.ai),
│                                     #   webStatus.deployedHere=false / pushDestination=cloudflare-pages,
│                                     #   billingStripe.webhookUrl=https://api.musematic.ai/api/webhooks/stripe
├── values.dev.yaml                   # EXTEND — dev variants per the spec's US2
├── templates/
│   ├── certmanager-clusterissuer.yaml             # NEW
│   ├── certmanager-certificate-wildcard.yaml      # NEW (renders one per certManager.certificates entry)
│   ├── service-loadbalancer.yaml                  # NEW (Hetzner-annotated Service for ingress-nginx)
│   ├── vaultstaticsecret-hetzner-dns-token.yaml   # NEW (ExternalSecret syncing Vault → Secret)
│   ├── ingress-platform.yaml                      # EXTEND — add wildcard rule block
│   └── status-snapshot-cronjob.yaml               # EXTEND — add Cloudflare Pages push branch
├── tests/                                         # EXTEND helm-unittest cases for new templates
└── .snapshots/
    ├── prod.rendered.yaml             # NEW committed snapshot (generated via make helm-snapshot-update)
    └── dev.rendered.yaml              # NEW committed snapshot

terraform/
├── modules/
│   ├── hetzner-cluster/
│   │   ├── main.tf                    # UNCHANGED (already provisions servers + LB)
│   │   ├── variables.tf               # UNCHANGED (no defaults for load_balancer_type)
│   │   └── outputs.tf                 # NEW — lb_ipv4, lb_ipv6, kubeconfig
│   └── hetzner-dns-zone/              # NEW MODULE
│       ├── main.tf                    # apex zone + bootstrap A/AAAA records (apex/app/api/grafana/status)
│       ├── variables.tf
│       └── outputs.tf
└── environments/
    ├── production/
    │   ├── main.tf                    # EXTEND — wire hetzner-dns-zone module + lb21 default
    │   ├── variables.tf               # EXTEND — add cloudflare_pages_ipv4
    │   └── terraform.tfvars.example   # EXTEND — add example values
    └── dev/
        ├── main.tf                    # EXTEND — wire dev.* records + lb11 default
        ├── variables.tf
        └── terraform.tfvars.example

deploy/helm/observability/templates/dashboards/
└── tenants.yaml                       # EXTEND — add 3 panels (DNS automation latency,
                                       #   failures by slug, wildcard cert days-until-expiry)

.github/workflows/
└── ci.yml                             # EXTEND — add Render+Diff snapshots steps to helm-lint job;
                                       #   add Helm install --dry-run step to e2e job;
                                       #   add terraform-validate job (paths-filter on terraform/**)

docs/operations/                       # NEW runbook docs
├── hetzner-cluster-provisioning.md
├── helm-snapshot.md
├── wildcard-tls-renewal.md
└── cloudflare-pages-status.md

tests/e2e/suites/hetzner_topology/     # NEW skip-marked scaffolds
├── test_helm_install.py
├── test_wildcard_tls.py
├── test_dns_automation_create.py
├── test_dns_automation_remove.py
├── test_status_page_independent.py
└── test_tenant_subdomain_provisioning.py

tests/e2e/journeys/
├── test_j29_hetzner_topology.py        # NEW skip-marked
└── test_j35_wildcard_tls_renewal.py    # NEW skip-marked

Makefile                                # EXTEND — add helm-snapshot-update target
```

**Structure Decision**: This is an **infrastructure-as-code feature** that extends one existing Python BC (`tenants/`) with one new Protocol surface (`DnsAutomationClient` extended), one existing Helm chart (`deploy/helm/platform/`) with new templates and overlay blocks, one existing Terraform module set with a new sibling module, and one existing CI workflow with new steps inside existing jobs. No new bounded context. No new database tables. No new Kafka topics. The decision to NOT spin up a `dns_automation/` BC is justified by research R1 and tracked in Complexity Tracking.

## Complexity Tracking

| Violation / Choice | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| **Narrowing user input's "DNS automation service (new)" to "extend `tenants/dns_automation.py`"** | The brownfield code already exposes a Protocol-shaped seam for DNS automation; adding a new BC would duplicate scaffolding (`models.py`/`repository.py`/`events.py`) for what is one additional Protocol method (`remove_*`) plus a richer record set (3 subdomains × 2 record types). The records have no PostgreSQL persistence (research R2), so `models.py` would be empty. | A new `dns_automation/` BC would: (a) violate Brownfield rule 1 (never rewrite — the existing seam is already the right shape), (b) require updating every test that constructs `TenantsService` to inject a different DI shape, (c) split DNS-related code across two BCs (`tenants/dns_automation.py` already, plus the new BC) which is harder to navigate. Documented in research R1. |
| **Helm overlay file naming uses dotted form (`values.prod.yaml`) instead of dashed (`values-prod.yaml`)** | The chart already ships dotted-form overlay files; rewriting them would force a flag-day migration of operator runbooks, CI steps, and the helm-docs aggregator config. The user input's dashed form was the user's framing, not a codebase fact. | Renaming to dashed: rejected — Brownfield rule 1, breaks every operator's saved `helm install -f values.prod.yaml` command. Documented in research R3. |
| **Per-DNS-change events go to the audit chain only, NOT to a new Kafka topic** | The downstream consumers of "DNS records changed for tenant X" today are zero — no other BC needs to react. Audit is the only legitimate consumer. Adding a `tenants.dns.records_changed` Kafka topic for hypothetical future consumers would be premature abstraction (general-instructions: "no half-finished implementations / hypothetical future requirements"). | A new Kafka topic: rejected — no consumer; would burn a topic name in the registry; the `tenants.events` envelope already carries the slug + lifecycle context that downstream consumers need. Documented in research R2. |
| **Production status page on Cloudflare Pages, dev kept in-cluster** | Constitution rule 49 demands status-page operational independence for the surface customers and external monitors watch — that's prod, not dev. Operating two Cloudflare Pages projects (one per env) would double the maintenance surface (DNS, tokens, Workers) for marginal value: dev is operator-internal and operators have direct Grafana access during a dev outage. | Cloudflare Pages for dev too: rejected — extra Pages project + extra Cloudflare DNS token in Vault + extra ExternalSecret. Dedicated Hetzner VM for prod: kept as documented fallback in the runbook but not the default — Cloudflare Pages is zero-VM-management and is what most SaaS shops use for public status. Documented in research R6. |
| **CI gates added as steps inside existing jobs, NOT a new `.github/workflows/helm-ci.yml`** | The existing `helm-lint` and `e2e` jobs already do path-filtered work over `deploy/helm/**`; adding a parallel workflow file would duplicate the path-filter, the Helm setup steps, and the kind-cluster setup. The CI surface area is already large (8 workflow files); keeping new gates inside existing jobs reduces per-PR runner-time and CI maintenance burden. | A new workflow file: rejected — duplicate setup, duplicate path-filter, no benefit. Documented in research R7. |

---

*Phase 0 (research) and Phase 1 (data-model + contracts + quickstart) artefacts are emitted as siblings to this file. Phase 2 (tasks.md) is generated by `/speckit-tasks` and is intentionally not produced here.*
