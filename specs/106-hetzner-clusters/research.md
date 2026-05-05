# UPD-053 — Phase 0 Research

> Eight research items resolving the unknowns from the user-supplied implementation plan against the brownfield reality of the repo. Each item: **Decision** → **Rationale** → **Alternatives considered**. Pre-existing implementations are called out so the implementation phase extends rather than replaces.

---

## R1 — DNS automation is an *extension*, not a new BC

**Decision**: Extend the existing `apps/control-plane/src/platform/tenants/dns_automation.py` (`HetznerDnsAutomationClient`, `MockDnsAutomationClient`, `DnsAutomationClient` Protocol) rather than creating a new `dns_automation/` bounded context. Add three new operations: `create_tenant_subdomain(slug)` (replaces the single-subdomain `ensure_records`), `remove_tenant_subdomain(slug)`, and a propagation verifier. Wire `create_tenant_subdomain` from `TenantsService.provision_enterprise_tenant` (already calls `ensure_records` at `tenants/service.py:139`) and `remove_tenant_subdomain` from `data_lifecycle/` cascade phase 2 (UPD-051).

**Rationale**: The brownfield code already expresses DNS automation as a Protocol-shaped seam inside `tenants/`. Spawning a dedicated BC for what is fundamentally one additional operation (`remove_*`) plus a richer record set (3 subdomains × 2 record types) would duplicate scaffolding (`models.py`, `repository.py`, `events.py`, `__init__.py`) for no behavioural payoff and would force a migration to update `TenantsService`'s constructor signature. Constitution Principle I (modular monolith — extend existing BCs).

**Alternatives considered**:
- *New `dns_automation/` BC*: rejected — adds module bloat without new ownership boundary; the records are tenant-scoped and the only writers are `tenants/` (create) and `data_lifecycle/` (delete).
- *In-place rewrite of `ensure_records` to take 3 subdomains*: rejected — would break the existing Protocol contract used by tests; safer to add the new method and deprecate `ensure_records` after a release.

---

## R2 — DNS record IDs are not persisted; removal is by zone-list-and-filter

**Decision**: `remove_tenant_subdomain(slug)` lists records under the zone via the Hetzner DNS API `GET /records?zone_id=...`, filters in-process by `name in {<slug>, <slug>.api, <slug>.grafana}`, and issues a `DELETE /records/{id}` for each match. No new PostgreSQL table for `tenant_dns_records`.

**Rationale**: The Hetzner DNS API is the source of truth; persisting record ids in PostgreSQL would create a divergence trap (record manually deleted via Hetzner UI → stale row → idempotent removal fails). The list-and-filter pattern is what the user input's reference `HetznerDnsClient._delete_records_by_name` already shows, and it survives manual operator interventions. Audit chain captures the record ids returned by the API at create time and the ids deleted at remove time, so the chain remains complete.

**Alternatives considered**:
- *`tenant_dns_records` table* (id, tenant_id, slug, hetzner_record_id, record_type, created_at): rejected — extra DDL with no behavioural benefit; the zone is small (≤ ~5 records per tenant × low-thousands of tenants ≪ Hetzner's per-zone limit).
- *Store in a Redis hash with a TTL*: rejected — cache eviction would lose the record ids needed for cleanup.

---

## R3 — Helm overlay file naming preserves dotted convention

**Decision**: This feature uses the chart's existing dotted-overlay naming: `values.prod.yaml`, `values.dev.yaml` (NOT the `values-prod.yaml` / `values-dev.yaml` style from the user input). The files already exist at `deploy/helm/platform/values.prod.yaml` and `deploy/helm/platform/values.dev.yaml`. We extend them in place.

**Rationale**: Brownfield rule 1 (never rewrite). The dotted form is what `helm-docs` already aggregates and what the deploy pipeline already references. Renaming would force changes in `.github/workflows/ci.yml`, `Makefile`, contributor docs, and operator runbooks for cosmetic gain.

**Alternatives considered**:
- *Add new `values-prod.yaml` / `values-dev.yaml` files alongside the existing dotted variants*: rejected — two parallel overlays would diverge and confuse operators.
- *Rename existing files to the dashed form*: rejected — breaks every operator's saved `helm install` command and creates a flag-day migration.

---

## R4 — cert-manager + Hetzner DNS-01 webhook is a chart subdependency, not a manual install

**Decision**: Add `cert-manager` and `cert-manager-webhook-hetzner` as Helm dependencies in `deploy/helm/platform/Chart.yaml` (gated by `certManager.enabled`, which the chart already references). Render new templates `templates/certmanager-clusterissuer.yaml`, `templates/certmanager-certificate-wildcard.yaml`, and `templates/certmanager-certificate-apex.yaml`. The Hetzner DNS API token sync from Vault to a Kubernetes Secret reuses the existing `vault/` chart's `VaultStaticSecret` pattern.

**Rationale**: The chart already annotates ingresses with `cert-manager.io/cluster-issuer: letsencrypt-prod` (`web-status-ingress.yaml:16`, `values.yaml:827`) but doesn't actually deploy cert-manager or any ClusterIssuer — which means today the annotation is decorative and certs only exist if an operator pre-installed cert-manager out-of-band. UPD-053 closes this gap by making the install reproducible. The Hetzner DNS-01 webhook (`ghcr.io/vadimkim/cert-manager-webhook-hetzner:1.4.0` per the user input) is a community webhook with stable releases.

**Alternatives considered**:
- *Document a manual cert-manager install in the runbook*: rejected — defeats US1's "single helm install" acceptance criterion and leaves the cert path non-reproducible.
- *Use Let's Encrypt's HTTP-01 instead of DNS-01*: rejected — HTTP-01 cannot issue wildcards (`*.musematic.ai`), so per-tenant subdomains would each need their own cert and would burn Let's Encrypt rate-limit budget.
- *Use a different DNS provider (Cloudflare, Route53)*: rejected — `tenants/dns_automation.py` already uses Hetzner DNS, and the apex zone `musematic.ai` is registered there per the user input.

---

## R5 — Stripe webhook URL is in `values.{env}.yaml`, signing secret in Vault

**Decision**: The Stripe webhook URL is rendered from `values.prod.yaml` / `values.dev.yaml` into the control-plane Deployment's environment as `BILLING_STRIPE_WEBHOOK_URL` (already set on `values.prod.yaml:32` from UPD-052). The webhook signing secret stays at `secret/data/musematic/{env}/billing/stripe/webhook-secret` in Vault — environment-specific path, NOT a Helm value. Cross-environment delivery is rejected because the prod webhook handler verifies against the prod secret only.

**Rationale**: UPD-052 already established the Vault path family. UPD-053's job is to expose the URL difference via the per-env overlays so the control plane can register the right webhook with Stripe (`/api/webhooks/stripe` on `api.musematic.ai` for prod, on `dev.api.musematic.ai` for dev). Constitution rules 11/39 (secrets in Vault, never in Helm values).

**Alternatives considered**:
- *Single shared webhook URL with multiplexed signing secrets*: rejected — would require the control plane to introspect the Stripe event payload to select a secret, and a misrouted prod event would have a path to dev infrastructure.
- *Configure the URL via Stripe Dashboard only (no Helm value)*: rejected — operators need a single source of truth; the value is non-secret and belongs in the chart.

---

## R6 — Status page operational independence: Cloudflare Pages first, in-cluster fallback for dev only

**Decision**: Production status page is Cloudflare Pages with a CronJob in the platform cluster pushing snapshot content via the Cloudflare Pages Direct Upload API every 30s (live data) and at least daily (static). The existing `deploy/helm/platform/templates/status-snapshot-cronjob.yaml` is **extended** to add a push-to-external-host code path gated by `webStatus.deployedHere=false` and `webStatus.pushDestination=cloudflare-pages`. Dev cluster keeps the in-cluster `web-status-deployment.yaml` for cost and to avoid maintaining a second Cloudflare Pages project for dev. Constitution rule 49 (status independence) is satisfied for prod, which is the surface that customers and external monitors actually watch.

**Rationale**: A platform outage that takes down `app.musematic.ai` ALSO takes down the in-cluster `web-status-deployment.yaml` (same ingress, same LB, same nginx). Cloudflare Pages is independent infra (different cloud, different DNS path post-CNAME). Dev's in-cluster status page is acceptable because dev is not a customer-facing surface — operators monitoring dev have direct Grafana access. The user input's "Cloudflare Pages or VM" alternative is preserved as a documented fallback in the runbook (FR-789).

**Alternatives considered**:
- *Cloudflare Pages for both prod and dev*: rejected — dev would need its own Pages project + DNS + push pipeline maintenance for marginal value.
- *Dedicated Hetzner VM running nginx for prod*: kept as a fallback in the runbook but not the default — Cloudflare Pages requires no VM management, no patching, no LB.
- *Keep status page in-cluster for prod*: rejected — direct rule 49 violation.

---

## R7 — CI adds snapshot diff + kind-cluster dry-run on top of existing helm-lint

**Decision**: The existing `helm-lint` job in `.github/workflows/ci.yml:1061` runs `helm lint --strict` plus `kubeconform` against every chart and `helm unittest` against the observability chart. UPD-053 adds:
- A new `helm-snapshot-diff` step under the `helm-lint` job that runs `helm template release deploy/helm/platform -f values.prod.yaml > /tmp/prod.rendered.yaml` (and the dev variant) and diffs against committed snapshots at `deploy/helm/platform/.snapshots/{prod,dev}.rendered.yaml` (via `git diff --no-index`).
- A new `helm-dry-run` step under the existing `e2e` job (which already provisions a kind cluster via `helm/kind-action@v1`) that runs `helm install platform deploy/helm/platform -f values.dev.yaml --dry-run --debug --kube-version=1.29.0`.
- Contributor docs at `docs/operations/helm-snapshot.md` explaining how to regenerate snapshots after intentional template changes (`make helm-snapshot-update`).

**Rationale**: The user input's "snapshot diff + helm install --dry-run against kind" is already 80% present via `helm-unittest` + `kubeconform`. The remaining gap is (a) a deterministic full-render snapshot (template-level regression catch) and (b) actual API-server schema validation against a real kind cluster (which `kubeconform` does statically but a real `--dry-run` exercises mutation webhooks too). Adding the steps as new ones inside existing jobs avoids a new workflow file (CI surface area is already large).

**Alternatives considered**:
- *New standalone `.github/workflows/helm-ci.yml`*: rejected — splits Helm CI from the path-filter pattern that gates every other job.
- *Replace helm-unittest with snapshot diff*: rejected — they catch different classes of regression (helm-unittest = assertions on rendered values; snapshot diff = full-output regression).
- *Use `helm-diff` plugin with a deployed release*: rejected — requires a stateful target, doesn't fit ephemeral PR CI.

---

## R8 — Terraform: Hetzner DNS provider added; per-env LB type defaulted

**Decision**: Extend `terraform/modules/hetzner-cluster/main.tf` to:
- Set `var.load_balancer_type` defaults: `lb21` for the prod environment (`terraform/environments/production/`), `lb11` for dev (`terraform/environments/dev/`). Currently no default; tfvars must set it.
- Add the Hetzner DNS provider (`hetznerdns/hetznerdns ~> 2.2`) as an optional sub-module `terraform/modules/hetzner-dns-zone/` that owns the apex zone (created once) and the per-env subtree records (apex/app/api/grafana/status/`*` wildcard).
- Output the Cloud LB's `ipv4_address` and `ipv6_address` so the apex/app/api/grafana A/AAAA records can be wired automatically rather than manually copied.

**Rationale**: The brownfield Terraform under `terraform/modules/hetzner-cluster/` already provisions the LB but stops short of DNS — operators today wire DNS records through the Hetzner web UI. Adding the DNS module closes the loop so `terraform apply` produces a fully resolvable cluster. Per-env LB defaults reduce tfvars boilerplate and prevent accidental prod-sized LB on dev (which is a constitution principle of "smaller dev footprint" per the spec's SC-002).

**Alternatives considered**:
- *Manage DNS entirely via the application-side `DnsAutomationService`*: rejected — bootstrap chicken-and-egg (the apex `musematic.ai` and `app.musematic.ai` records must exist BEFORE the application can run; only the per-tenant `<slug>` records are application-managed).
- *External tool (octodns, dnscontrol) for DNS-as-code*: rejected — additional tooling not justified when the team already uses Terraform for everything else under `terraform/`.
- *Different LB types per env via tfvars only (no module default)*: rejected — operator can still override but the default-value approach catches "operator forgot to set lb_type" by sizing for the env.
