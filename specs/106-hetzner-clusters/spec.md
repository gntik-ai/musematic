# Feature Specification: Hetzner Production+Dev Clusters with Helm Overlays and Ingress Topology (UPD-053)

**Feature Branch**: `106-hetzner-clusters`
**Created**: 2026-05-04
**Status**: Draft
**Input**: User description: UPD-053 finalises the production+dev cluster topology on Hetzner Cloud. It ships Helm overlays for two physically separated Kubernetes clusters (`musematic-prod` and `musematic-dev`) with their own Cloud Load Balancers, wildcard TLS via cert-manager + Let's Encrypt + Hetzner DNS-01, per-tenant DNS automation against Hetzner DNS, Terraform scaffolding for both clusters, per-environment Stripe webhook URL configuration, an externally-hosted status page, and Helm chart linting + dry-run install in CI.

## Brownfield Context

UPD-039 introduced the Helm chart at `deploy/helm/platform/` with three deployment modes (kind, k3s, Hetzner LB) and anticipated wildcard TLS for `*.musematic.ai`. The dev environment was conceptual only — no formal Hetzner dev cluster topology was defined and no production overlay existed alongside the kind/k3s overlays. UPD-052 (105) introduced Stripe billing and assumes a per-environment webhook URL but doesn't choose one. UPD-045 (constitution rule 49) requires the status page to live outside the platform cluster so a platform outage cannot take its own status surface down. UPD-046 (096) introduced tenant subdomain routing and reserved slugs.

This feature finalises the production+dev cluster topology, wires wildcard TLS auto-renewal, automates per-tenant DNS, codifies the dev-vs-prod overlays, and ensures the status page is deployed independently. Functional requirements **FR-776 through FR-791** (section 126 of the FR catalog) are owned by this feature.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operator deploys production cluster from scratch (Priority: P1)

A platform operator provisions the production cluster end-to-end. They run `terraform apply -var-file=prod.tfvars` to bring up the Hetzner Cloud Kubernetes infrastructure (1× CCX33 control plane, 3× CCX53 workers, 1× lb21 Cloud Load Balancer, DNS zone bound to `musematic.ai`), pull the kubeconfig, then `helm install platform deploy/helm/platform -f values-prod.yaml`. The cluster comes up, cert-manager issues the wildcard cert, ingress routes apex/app/api/grafana to the right backends, and the operator confirms `https://app.musematic.ai` returns the production frontend with a valid TLS chain. The operator follows a runbook checked into the repository to do all of this; no out-of-band steps are required.

**Why this priority**: Production deployability is the foundational gate for the whole feature — without it the platform cannot accept production traffic. P1.

**Independent Test**: Run the runbook against a freshly created Hetzner project. Assert that `terraform apply -var-file=prod.tfvars` completes without errors, that `helm install` finishes within 10 minutes, that cert-manager reports the wildcard cert as `Ready=True`, that `curl -fsSL https://app.musematic.ai/healthz` returns 200 with a non-self-signed cert chain, that `api.musematic.ai/healthz` and `grafana.musematic.ai/api/health` likewise return 200, and that the runbook reports the cluster healthy within 5 minutes of helm install completion.

**Acceptance Scenarios**:

1. **Given** a fresh Hetzner Cloud project with the API token stored in Vault, **When** the operator runs `terraform apply -var-file=prod.tfvars`, **Then** Terraform creates the control plane, workers, Cloud LB, and DNS zone reproducibly with no manual steps and emits a kubeconfig artifact.
2. **Given** a provisioned cluster, **When** the operator runs `helm install platform deploy/helm/platform -f values-prod.yaml`, **Then** the install succeeds, all platform deployments reach Ready, and the ingress controller acquires the LB's public IPv4/IPv6.
3. **Given** a successful helm install, **When** cert-manager processes the wildcard `*.musematic.ai` Certificate, **Then** the DNS-01 challenge against Hetzner DNS resolves and the cert is issued by Let's Encrypt within 5 minutes.
4. **Given** an issued wildcard cert, **When** an external client requests `https://app.musematic.ai`, `https://api.musematic.ai`, `https://grafana.musematic.ai`, **Then** ingress routes the requests to frontend, control-plane, and Grafana respectively and serves the wildcard cert.
5. **Given** the deployment, **When** healthchecks fire, **Then** every cluster healthcheck passes within 5 minutes of helm install completing and a runbook checked into `docs/runbooks/` walks the operator through the full provisioning sequence.

---

### User Story 2 - Dev cluster runs alongside prod with smaller footprint (Priority: P1)

The same operator provisions the dev cluster on the same Hetzner Cloud account but in a physically separate cluster. They run `terraform apply -var-file=dev.tfvars` (smaller infra: 1× CCX21 control plane, 1× CCX21 worker, 1× lb11 LB), then `helm install platform deploy/helm/platform -f values-dev.yaml`. The dev cluster has its own LB IPs (no overlap with prod), runs Stripe in test mode, exposes `dev.musematic.ai` with a `*.dev.musematic.ai` wildcard cert, and cannot reach prod resources (separate Hetzner private networks, separate Vault paths, separate Kafka/PostgreSQL clusters).

**Why this priority**: Dev cluster is the environment where every change lands before promotion to prod, so without it the team has no way to integration-test changes safely. P1.

**Independent Test**: Provision dev alongside an already-running prod cluster. Assert that the dev LB IPv4 differs from prod, that Stripe webhook deliveries to `https://dev.api.musematic.ai/api/webhooks/stripe` use the test-mode signing secret, that `https://dev.musematic.ai` resolves and serves a `*.dev.musematic.ai` cert, that the dev cluster's monthly Hetzner cost is approximately 50% of prod's (for the same duration), and that a pod in the dev cluster cannot reach the prod PostgreSQL endpoint (network reachability test fails).

**Acceptance Scenarios**:

1. **Given** an existing prod cluster, **When** the operator provisions the dev cluster, **Then** the dev infrastructure is physically separate (own control plane, own workers, own LB, own DNS records under `dev.musematic.ai`) and shares no Hetzner Cloud resources with prod.
2. **Given** the dev `values-dev.yaml`, **When** helm renders the chart, **Then** resource requests and replica counts produce a smaller footprint targeting roughly 50% of the prod monthly Hetzner spend.
3. **Given** the dev cluster, **When** a workspace is upgraded to Pro, **Then** Stripe runs in test mode (test publishable key, test webhook signing secret) and no live charges occur.
4. **Given** the dev cluster, **When** a client requests `https://dev.musematic.ai`, **Then** the ingress serves the `*.dev.musematic.ai` wildcard cert issued by the same cert-manager + Hetzner DNS-01 path as prod.
5. **Given** the dev cluster, **When** a workload attempts to reach a prod hostname or private IP, **Then** the request fails (no shared private network, separate Vault paths, separate database clusters).

---

### User Story 3 - Enterprise tenant subdomain DNS automation (Priority: P1)

A super admin provisions the Acme Enterprise tenant. Tenant creation emits an event the DNS automation service consumes; the service calls the Hetzner DNS API to create A and AAAA records for `acme.musematic.ai`, `acme.api.musematic.ai`, and `acme.grafana.musematic.ai` pointing at the prod LB's IPv4 and IPv6. Within 5 minutes those records resolve via public DNS, the wildcard cert covers them automatically (no per-tenant cert issuance), and the Acme admin can sign in at `https://acme.musematic.ai`. When the tenant later enters deletion phase 2, the same service removes the records.

**Why this priority**: Enterprise tenant provisioning is the contractual surface for the highest-revenue customer tier, and per-tenant subdomains are required for the Enterprise sales motion. P1.

**Independent Test**: Trigger tenant creation for slug `acme`, assert the Hetzner DNS API receives 6 record creation calls (3 A + 3 AAAA), assert that within 5 minutes `dig +short acme.musematic.ai @1.1.1.1` returns the prod LB IPv4, that `https://acme.musematic.ai/healthz` returns 200 with the wildcard cert, that an audit-chain entry is appended for each DNS change, and that calling the deletion phase 2 path removes all 6 records.

**Acceptance Scenarios**:

1. **Given** the Hetzner DNS API token in Vault, **When** the platform starts up, **Then** the DNS automation service loads the token via the existing SecretProvider with no token in environment variables or Helm values.
2. **Given** a tenant creation request for slug `acme`, **When** the DNS automation service handles it, **Then** the service creates A and AAAA records for `acme`, `acme.api`, and `acme.grafana` under the configured zone with TTL 300 and pointing at the prod LB's IPv4/IPv6.
3. **Given** the records are created, **When** the service notifies the admin that the tenant is ready, **Then** it has first verified DNS propagation (e.g. via a public resolver) so the user is not pointed at a not-yet-resolving hostname.
4. **Given** a tenant entering deletion phase 2, **When** the service handles the deletion event, **Then** it removes all records previously created for that slug and appends an audit-chain entry for the removal.
5. **Given** a wildcard cert covering `*.musematic.ai`, **When** new tenant subdomains are created, **Then** no per-subdomain cert issuance is required and the cluster does not hit Let's Encrypt rate limits per tenant.
6. **Given** any DNS change, **When** the service completes the API call, **Then** an audit-chain entry captures actor, change type, slug, record set, and Hetzner DNS record ids.

---

### User Story 4 - Wildcard TLS auto-renewal without service interruption (Priority: P1)

Thirty days before the wildcard cert expires, cert-manager initiates a renewal via the DNS-01 challenge against Hetzner DNS. The new cert is issued, written to the same `wildcard-musematic-ai` Secret, and the ingress controller picks it up automatically. No request fails, no operator action is required. If the renewal fails (Hetzner DNS unreachable, Let's Encrypt rate limited, etc.), an alert reaches the on-call channel within 15 minutes so the operator can intervene before the cert actually expires.

**Why this priority**: An expired wildcard cert breaks every public hostname simultaneously, including the Stripe webhook receiver — instant complete outage. Auto-renewal without service interruption is P1.

**Independent Test**: In a staging cluster, fast-forward the cert's notBefore so cert-manager treats it as 25 days from expiry, assert renewal triggers, assert the new cert is written to the Secret, assert the ingress controller reloads to use it, assert no in-flight requests fail. Then break the Hetzner DNS API token and assert the renewal-failure alert fires within 15 minutes.

**Acceptance Scenarios**:

1. **Given** a cert with 30 days remaining, **When** cert-manager runs its renewal scan, **Then** it initiates renewal via the DNS-01 webhook against Hetzner DNS without operator action.
2. **Given** a successful renewal, **When** the new cert is issued, **Then** the ingress controller picks up the new Secret and serves it on the next TLS handshake; no in-flight request fails.
3. **Given** a renewal failure (token rotated, API outage, rate limit), **When** the failure persists past one retry cycle, **Then** an alert is delivered to the on-call channel within 15 minutes of the first failed attempt and the runbook for cert-renewal failures is referenced in the alert payload.
4. **Given** the certificate stack, **When** an operator inspects it, **Then** dedicated `Certificate` resources exist for both `*.musematic.ai` and the apex `musematic.ai` (and the dev counterparts in dev), and a `ClusterIssuer` named `letsencrypt-prod` is configured with the Hetzner DNS-01 webhook.
5. **Given** the existing E2E suite, **When** the J35 wildcard-TLS-renewal journey runs, **Then** it covers the near-expiry simulation and asserts renewal completes without service interruption.

---

### User Story 5 - Status page deployed on independent infrastructure (Priority: P2)

Per UPD-045 / constitution rule 49, the status page is NOT deployed inside the platform cluster — a platform outage must never take down its own status reporting. The status page is hosted on Cloudflare Pages (or, if Cloudflare is unavailable, a tiny dedicated Hetzner VM running nginx with static files). A CronJob inside each platform cluster pushes regenerated status content to the host on a fast cadence for live data and a daily cadence for static content. Prod uses `status.musematic.ai`; dev uses `status.dev.musematic.ai`.

**Why this priority**: Independence from the platform cluster is the whole point of this user story, but the platform can still deploy without it (operators see status via Grafana directly during the gap), so P2.

**Independent Test**: Bring down the platform cluster's ingress controller (e.g. scale the deployment to zero) and verify that `https://status.musematic.ai` continues to load and shows the most recent push (within the configured push interval). Then re-enable the cluster and confirm pushes resume.

**Acceptance Scenarios**:

1. **Given** the topology, **When** the operator inspects what runs where, **Then** the status page host is independent of the platform cluster (Cloudflare Pages or a dedicated VM with no shared infrastructure).
2. **Given** the platform cluster, **When** a CronJob in the cluster runs, **Then** it pushes regenerated content to the status page host every 30 seconds for live data and at least daily for static content.
3. **Given** a platform-cluster outage (ingress down, control plane down), **When** an external user opens `https://status.musematic.ai` (or the dev equivalent), **Then** the page loads from the independent host and reflects the last successful push.
4. **Given** prod and dev clusters, **When** they each push status content, **Then** prod publishes to `status.musematic.ai` and dev publishes to `status.dev.musematic.ai` without colliding.

---

### User Story 6 - Helm chart changes pass linting, dry-run, and snapshot diff in CI (Priority: P2)

A developer modifies a Helm template (e.g. adds a new ingress rule, tweaks the cert-manager Certificate). Their PR triggers CI to run `helm lint`, `helm template` against `values-prod.yaml` and `values-dev.yaml`, a snapshot diff that flags unintended template changes, and `helm install --dry-run` against an ephemeral kind cluster. Any failure blocks merge. Contributor docs explain how to update the snapshot when the change is intentional.

**Why this priority**: Catches breakage before merge but the platform can still ship without it (manual testing fills the gap), so P2.

**Independent Test**: Open a PR that intentionally breaks the chart (e.g. an undefined Helm helper). Assert the CI job fails on `helm lint`. Open a second PR that intentionally changes a template's rendered output without updating the snapshot, and assert the snapshot-diff CI job fails until the snapshot is refreshed.

**Acceptance Scenarios**:

1. **Given** a PR that modifies any file under `deploy/helm/platform/`, **When** CI runs, **Then** it executes `helm lint`, `helm template -f values-prod.yaml`, `helm template -f values-dev.yaml`, snapshot diff, and `helm install --dry-run` against kind, all four producing pass/fail signals.
2. **Given** an intentional template change, **When** the developer regenerates the snapshot per the documented procedure and commits it, **Then** snapshot diff passes and merge is unblocked.
3. **Given** an unintentional template change, **When** CI runs, **Then** snapshot diff fails with a clear diff that points the developer at the templates that changed.
4. **Given** the contributor docs, **When** a developer reads them, **Then** they find instructions for updating the snapshot, running the suite locally, and interpreting failures.

---

### Edge Cases

- **Hetzner DNS API outage during tenant provisioning**: tenant creation queues the DNS update, retries with exponential backoff up to a bounded ceiling, and surfaces a degraded-DNS warning to the super admin. The tenant record is not flipped to `active` until DNS resolves.
- **Concurrent tenant provisioning**: super admin provisions two tenants simultaneously and both call the Hetzner DNS API. The DNS automation service serializes per-zone changes via a queue / lease so concurrent calls do not conflict, and each change is retried up to a bounded ceiling on transient API errors.
- **Hetzner DNS propagation slower than the cert-manager DNS-01 timeout**: cert-manager handles propagation polling itself; the platform sets the TTL conservatively (300s) and configures cert-manager's propagation check to use a public resolver so it cannot be fooled by Hetzner's authoritative caches.
- **Cloud LB failure**: a single Hetzner Cloud LB per cluster is the documented topology; failure is mitigated by alerting + a runbook for LB recreation. Multi-LB topology is out of scope for this pass.
- **Custom domains for Enterprise tenants** (e.g. `console.acme.com` instead of `acme.musematic.ai`): out of scope per constitution rule 15; documented as a future feature on the roadmap.
- **Stripe webhook URL drift between environments**: prod registers its webhook against `https://api.musematic.ai/api/webhooks/stripe`, dev against `https://dev.api.musematic.ai/api/webhooks/stripe`. The webhook signing secret is environment-specific in Vault; cross-environment delivery would fail signature verification and is rejected.
- **Wildcard cert renewal hits Let's Encrypt rate limit**: cert-manager's exponential backoff and the staging-issuer fallback path handle the rate-limit case; a runbook for rate-limit recovery is referenced from the renewal-failure alert.
- **Status page push from cluster fails**: the CronJob retries on its next tick; if pushes have failed for more than 1 hour, an alert reaches on-call. Stale-content surfaces a "last updated" timestamp on the page so external readers can see the freshness.
- **Reserved subdomain collision**: tenant slugs like `api`, `grafana`, `status`, `admin`, `www`, `webhooks` are reserved by UPD-046 and must remain unallocatable; DNS automation MUST refuse to create records for any reserved slug even if a buggy upstream attempts it.

## Requirements *(mandatory)*

### Functional Requirements

#### Cluster topology and Helm overlays

- **FR-776**: The Helm chart at `deploy/helm/platform/` MUST ship a `values-prod.yaml` overlay and a `values-dev.yaml` overlay alongside the existing `values.yaml`, `values-kind.yaml`, and `values-k3s.yaml`. The overlays MUST be sufficient (combined with `values.yaml`) to produce a complete production or development render with no mandatory operator-side template editing.
- **FR-777**: The Service of type `LoadBalancer` for the ingress controller MUST emit Hetzner Cloud Controller Manager annotations (`load-balancer.hetzner.cloud/location`, `network-zone`, `use-private-ip`, `uses-proxyprotocol`, `name`, `type`, `protocol`, `health-check-protocol`) parameterised by `.Values.hetzner.loadBalancer`, so prod (lb21) and dev (lb11) provision distinct Cloud LBs in distinct namespaces of the same Hetzner project.
- **FR-778**: Terraform scaffolding MUST exist under `terraform/` (or equivalent) covering both clusters end-to-end (control plane node, workers, Cloud LB, private network, DNS zone), parameterised by `prod.tfvars` and `dev.tfvars` so a freshly cloned operator workstation can run `terraform apply -var-file=<env>.tfvars` without further manual editing.

#### Wildcard TLS via cert-manager + Hetzner DNS-01

- **FR-779**: When `certManager.enabled` is true, the chart MUST render a `ClusterIssuer` named `letsencrypt-prod` that uses the Hetzner DNS-01 webhook solver, reading the Hetzner DNS API token from a Kubernetes Secret rendered from Vault, and pointing at `https://acme-v02.api.letsencrypt.org/directory`.
- **FR-780**: The chart MUST render `Certificate` resources for the wildcard plus apex pair per environment (`*.musematic.ai` + `musematic.ai` in prod; `*.dev.musematic.ai` + `dev.musematic.ai` in dev) and ingress resources MUST consume the resulting Secrets via the `cert-manager.io/cluster-issuer` annotation.
- **FR-781**: Cert renewal MUST be automatic (cert-manager default policy, ≥30-day pre-expiry trigger), MUST not require operator action under normal conditions, and MUST emit an alert to the on-call channel within 15 minutes when renewal fails twice in a row.

#### Ingress and tenant routing

- **FR-782**: The platform ingress MUST route the apex/app/api/grafana hostnames per environment (`musematic.ai` redirect to `app.musematic.ai`, `app` → frontend, `api` → control plane, `grafana` → Grafana in prod; the `dev.*` and alternate `*.dev.*` forms in dev) and MUST include a wildcard rule that matches any tenant subdomain and routes `/api/*` to the control plane and `/*` to the frontend, with the platform's hostname middleware (UPD-046) extracting the tenant slug from the request host.
- **FR-783**: A separate ingress MUST exist for status (`status.musematic.ai`, `status.dev.musematic.ai`) that points at the externally-hosted page; the chart MUST not deploy the status page inside the cluster (constitution rule 49).

#### Per-tenant DNS automation

- **FR-784**: A `DnsAutomationService` MUST expose `create_tenant_subdomain(slug)` and `remove_tenant_subdomain(slug)` operations that respectively add and remove the three A and three AAAA records (`<slug>`, `<slug>.api`, `<slug>.grafana`) under the configured zone, using the Hetzner DNS API and reading the API token from Vault via the existing SecretProvider.
- **FR-785**: `create_tenant_subdomain` MUST verify DNS propagation (e.g. via at least one public resolver) before returning success, so callers can rely on the subdomain being resolvable. Failures MUST retry with exponential backoff up to a bounded ceiling and emit an admin-visible alert when the bound is exceeded.
- **FR-786**: The DNS automation service MUST refuse to act on slugs that appear in the platform's reserved-slug list (UPD-046) and MUST emit an audit-chain entry on every successful or failed DNS change capturing actor, slug, record set, Hetzner record ids, and outcome.
- **FR-787**: Per-tenant subdomains MUST be covered by the cluster's wildcard cert; no per-subdomain cert issuance is required and tenant onboarding MUST not consume Let's Encrypt rate-limit budget.

#### Per-environment Stripe webhook URL

- **FR-788**: The Stripe webhook URL configured in the active provider settings MUST be derived from the active environment so that `values-prod.yaml` produces `https://api.musematic.ai/api/webhooks/stripe` and `values-dev.yaml` produces `https://dev.api.musematic.ai/api/webhooks/stripe`. Webhook signing secrets MUST be environment-specific Vault paths.

#### Status page independence

- **FR-789**: The status page MUST be deployed outside the platform cluster (Cloudflare Pages by default, or a dedicated nginx VM as fallback) and a CronJob inside each cluster MUST push regenerated content to the host every 30 seconds (live data) and at least daily (static content). The status page MUST surface a "last updated" timestamp so external readers can detect stale content.

#### CI gates

- **FR-790**: Every PR that touches files under `deploy/helm/platform/` MUST trigger CI jobs that run `helm lint`, `helm template -f values-prod.yaml`, `helm template -f values-dev.yaml`, snapshot diff against checked-in expected output, and `helm install --dry-run` against a freshly created kind cluster. Any of those failing MUST block merge.
- **FR-791**: Contributor documentation under `docs/` MUST include instructions for running the Helm CI suite locally, regenerating the snapshot when a template change is intentional, and provisioning prod and dev clusters from scratch (the runbook referenced from US1).

#### Cross-cutting

- **FR-A1**: All sensitive material (Hetzner Cloud API token, Hetzner DNS API token, Stripe API key, Stripe webhook signing secrets) MUST be stored in Vault at canonical paths and MUST never appear in Helm values, environment variables, or container images.
- **FR-A2**: Prod and dev MUST run on physically separate Hetzner Cloud Kubernetes clusters with separate Cloud LBs, separate private networks, separate Vault paths, and separate database/Kafka/Redis stacks; cross-environment reachability MUST be impossible by default.
- **FR-A3**: Every DNS change made by the DNS automation service MUST emit an audit-chain entry verifiable via the existing `tools/verify_audit_chain.py`.

### Key Entities

- **HetznerLoadBalancer** — the Hetzner Cloud LB created per cluster; identified by name (`musematic-prod-lb`, `musematic-dev-lb`), type (lb21 / lb11), location, network zone, and the IPv4/IPv6 it advertises. Annotated by the ingress controller's Service spec.
- **HetznerDnsZone** — the `musematic.ai` zone managed via the Hetzner DNS API; the dev cluster shares the zone but operates on the `dev.*` subtree. Records are A/AAAA only for this feature.
- **WildcardCertificate** — the cert-manager Certificate resource backing the `wildcard-musematic-ai` (prod) and `wildcard-dev-musematic-ai` (dev) Secrets; renewed automatically via DNS-01 against Hetzner DNS.
- **DnsAutomationRecordSet** — logical grouping of the 6 records (3× A + 3× AAAA) created/removed by `create_tenant_subdomain` / `remove_tenant_subdomain` for one tenant slug.
- **HelmOverlay** — `values-prod.yaml` / `values-dev.yaml`; reads `values.yaml` defaults and overrides resource sizing, ingress hosts, cert-manager certificates, Stripe mode, status-page push interval, observability retention, and HA toggles.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A platform operator can take an empty Hetzner Cloud project from `terraform apply` to a fully healthy production cluster (helm install succeeded, all pods Ready, wildcard cert issued, ingress serving) in under 30 minutes following only the runbook.
- **SC-002**: Dev cluster monthly Hetzner Cloud spend is no more than approximately 50% of prod's monthly spend for the same uptime, given the documented `values-dev.yaml` sizing.
- **SC-003**: Tenant subdomain provisioning publishes resolvable DNS for `<slug>`, `<slug>.api`, `<slug>.grafana` within 5 minutes of the create call returning, verified via at least one public resolver before the user is notified.
- **SC-004**: Wildcard cert auto-renewal succeeds without operator action ≥ 95% of the time across a calendar year; renewal failures are alerted to the on-call channel within 15 minutes of the second consecutive failed attempt.
- **SC-005**: During a deliberately induced platform-cluster outage (ingress controller scaled to zero), `https://status.musematic.ai` remains reachable and serves content no older than the configured push interval × 2 (i.e. 60 seconds for live data).
- **SC-006**: PRs that touch `deploy/helm/platform/` trigger the four CI jobs (lint, prod template, dev template, snapshot, dry-run) on every push, and a deliberately broken template causes the corresponding job to fail and block merge in 100% of cases sampled.
- **SC-007**: Concurrent provisioning of 5 tenants emits exactly 30 audit-chain entries (5 × 6 records) and the Hetzner DNS API is not subjected to more than the configured rate limit, verified via the audit log and Hetzner API metrics.
- **SC-008**: A pod scheduled in the dev cluster cannot resolve or connect to any prod-cluster private hostname or IP, verified via a network-reachability negative test in the J36 cluster-isolation journey.
- **SC-009**: The Stripe webhook receiver in prod processes events signed with the prod webhook signing secret only; an event signed with the dev secret is rejected with 401 and a security event is emitted.
- **SC-010**: Every DNS change emitted by the DNS automation service is verifiable via `tools/verify_audit_chain.py` after a journey run, with zero missing or duplicate entries.

## Assumptions

- The platform already runs on Hetzner Cloud Kubernetes (UPD-039 introduced the Hetzner LB deployment mode and the Helm chart) and the Hetzner Cloud Controller Manager is installed in-cluster as a chart dependency.
- Both prod and dev share the same Hetzner Cloud account and the same `musematic.ai` DNS zone, with dev operating exclusively on the `dev.*` subtree. Splitting accounts or zones is out of scope.
- Cloudflare Pages is the default status-page host. If Cloudflare is unavailable for any reason, a tiny dedicated Hetzner Cloud VM (or other provider) running nginx with static files is the documented fallback. Either path satisfies the independence requirement.
- The Stripe API version, plan ids, and webhook event subscriptions are configured outside this feature (UPD-052 owns those); this feature only chooses the URL and the signing-secret Vault paths per environment.
- The wildcard cert covers all per-tenant subdomains under `*.musematic.ai`; custom Enterprise domains (e.g. `console.acme.com`) are deferred per constitution rule 15.
- cert-manager and the Hetzner DNS-01 webhook are deployed inside the platform cluster (they are not part of the externally-hosted status-page topology); this is acceptable because cert renewal is not on the request-serving critical path and a temporary cert-manager outage does not break served traffic.
- The dev cluster is permitted to use the Let's Encrypt **prod** ACME directory (rather than the staging directory) to keep the cert-issuing path identical between environments. Rate-limit risk is accepted because subdomain provisioning relies on the wildcard, so issuance frequency is low.
- The DNS automation service is owned by an existing bounded context (`tenants/` or a new `dns_automation/` BC under the control plane); the choice of host BC is a design-time decision and does not affect the spec.
- Status-page push uses an existing platform-side renderer (e.g. the operator dashboard from UPD-044) to produce the static HTML; the implementation may reuse or fork that renderer.
- The Helm chart's existing kind / k3s overlays remain valid (UPD-039 deliverable); this feature does not modify them.
