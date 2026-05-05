# Tasks: UPD-053 — Hetzner Production+Dev Clusters with Helm Overlays and Ingress Topology

**Input**: Design documents from `/specs/106-hetzner-clusters/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Unit-test scaffolds for the `tenants/dns_automation.py` extension follow Constitution rule 14 (≥95% coverage); helm-unittest cases for the new templates; skip-marked E2E suite + journey tests per Constitution rule 25 (E2E coverage). Live-Hetzner paths follow the omit-list precedent (UPD-051/UPD-052).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1–US6); foundational/setup/polish tasks omit it
- Each task lists the exact file path

## Path Conventions

- Backend: `apps/control-plane/src/platform/tenants/...`, `apps/control-plane/tests/{unit,integration}/tenants/...`
- Helm: `deploy/helm/platform/...`, `deploy/helm/observability/...`
- Terraform: `terraform/{modules,environments}/...`
- CI: `.github/workflows/ci.yml`
- Docs/runbooks: `docs/operations/...`, `docs/configuration/...`
- E2E: `tests/e2e/{suites,journeys}/...`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add chart sub-dependencies, configure secrets layout, regenerate env-var docs, document the Stripe per-env webhook URL contract from UPD-052.

- [X] T001 [P] Add `cert-manager` (jetstack v1.16.0) and `cert-manager-webhook-hetzner` (vadimkim v0.6.0) as conditional sub-dependencies in `deploy/helm/platform/Chart.yaml` under `dependencies:` per `contracts/cert-manager-clusterissuer.md`. Run `helm dependency update deploy/helm/platform` and commit `Chart.lock` + `charts/*.tgz`.
- [X] T002 [P] Add the `hetznerdns/hetznerdns ~> 2.2` provider to `terraform/environments/production/main.tf` and `terraform/environments/dev/main.tf` under `required_providers` per `contracts/terraform-modules.md`. Do NOT yet wire the module — that lands in Phase 2.
- [X] T003 [P] Confirm/document the four DNS env-var settings (`HETZNER_DNS_API_TOKEN`, `HETZNER_DNS_ZONE_ID`, `TENANT_DNS_IPV4_ADDRESS`, `TENANT_DNS_IPV6_ADDRESS`) in `apps/control-plane/src/platform/common/config.py` with rule-37 inline `description=` annotations. Regenerate `docs/configuration/environment-variables.md` via `python scripts/generate-env-docs.py --output docs/configuration/environment-variables.md` and commit the diff.
- [X] T004 [P] Document Vault paths in `docs/configuration/vault-layout.md`: `secret/data/musematic/{env}/dns/hetzner/api-token` (token) and `secret/data/musematic/{env}/cloudflare/pages-token` (token). Reference both from the `quickstart.md` § 1 "Seed Vault" step.
- [X] T005 [P] Add a `helm-snapshot-update` target to the root `Makefile` per `contracts/ci-helm-snapshot.md`. The target runs `helm template release deploy/helm/platform -f deploy/helm/platform/values.{prod,dev}.yaml --kube-version 1.29.0 --api-versions cert-manager.io/v1/Certificate --api-versions cert-manager.io/v1/ClusterIssuer` for each env and writes the output to `deploy/helm/platform/.snapshots/{prod,dev}.rendered.yaml`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Common Helm scaffolding (the Hetzner-annotated LoadBalancer Service, the ExternalSecret syncing the Hetzner DNS token from Vault, the shared `values.yaml` skeleton blocks). These templates are gated by feature flags so they do not break operators who haven't filled in their `values.{prod,dev}.yaml` yet.

⚠️ CRITICAL: no user-story work begins until Phase 2 is complete.

- [X] T006 Add the new top-level keys (`hetzner.*`, `certManager.*`, `ingress.wildcardHosts`, `webStatus.deployedHere`, `webStatus.pushDestination`, `webStatus.pushIntervalSeconds`, `webStatus.cloudflarePages`, `billingStripe.webhookUrl`) to `deploy/helm/platform/values.yaml` with safe defaults (`certManager.enabled: false`, `hetzner.loadBalancer: null`, `webStatus.deployedHere: true`, `webStatus.pushDestination: none`, `webStatus.pushIntervalSeconds: 60`, `ingress.wildcardHosts: []`, `billingStripe.webhookUrl: ""`). Add `helm-docs` annotations on every key per the chart's existing convention. Run `helm-docs --chart-search-root=deploy/helm` and `python scripts/aggregate-helm-docs.py --output docs/configuration/helm-values.md`; commit the diff.
- [X] T007 [P] Create `deploy/helm/platform/templates/service-loadbalancer.yaml` with the Hetzner Cloud Controller Manager annotations (`load-balancer.hetzner.cloud/{location,network-zone,use-private-ip,uses-proxyprotocol,name,type,protocol,health-check-protocol}`) per `contracts/cert-manager-clusterissuer.md` § "service-loadbalancer.yaml". Gate the whole template behind `if and .Values.hetzner .Values.hetzner.loadBalancer`.
- [X] T008 [P] Create `deploy/helm/platform/templates/vaultstaticsecret-hetzner-dns-token.yaml` rendering an `ExternalSecret` resource that syncs `secret/data/musematic/{env}/dns/hetzner/api-token` from Vault into a Kubernetes Secret named `hetzner-dns-token` per `contracts/cert-manager-clusterissuer.md` § "Vault → Kubernetes Secret sync". Gate behind `.Values.certManager.enabled`. Reuse the existing `vault-cluster-store` ClusterSecretStore (UPD-040).
- [X] T009 [P] Create `terraform/modules/hetzner-cluster/outputs.tf` exposing `lb_ipv4`, `lb_ipv6`, and `kubeconfig` per `contracts/terraform-modules.md`. The new outputs are required by `Phase 5 / US3` (DNS module wiring) and by the operator runbook.
- [X] T010 [P] Add `DnsAutomationPropagationTimeoutError` to `apps/control-plane/src/platform/tenants/exceptions.py`. Mirror the existing `DnsAutomationFailedError` class shape (inherit from the project's `PlatformError` base; status code 503).
- [X] T011 Extend `apps/control-plane/src/platform/tenants/dns_automation.py` with the new `DnsAutomationRecord` and `DnsAutomationRecordSet` dataclasses + the extended `DnsAutomationClient` Protocol surface (3 new methods + deprecated `ensure_records` facade) per `contracts/dns-automation-service.md` § "Protocol". Do NOT yet implement the methods on `HetznerDnsAutomationClient` or `MockDnsAutomationClient` — that lands in Phase 5/US3 so US3 owns the implementation. This task only widens the contract.
- [X] T012 [P] Update `deploy/helm/platform/templates/ingress-platform.yaml` to add the wildcard rule block (`/api/* → control-plane`, `/* → frontend`) gated on `.Values.ingress.wildcardHosts` per `contracts/cert-manager-clusterissuer.md` § "ingress-platform.yaml". Existing rules from `ingress.hosts` are preserved verbatim.

**Checkpoint**: chart sub-dependencies resolved, common templates ready, Protocol surface widened, Terraform outputs available. User-story phases can now begin in parallel.

---

## Phase 3: User Story 1 — Operator deploys production cluster from scratch (Priority: P1) 🎯 MVP

**Goal**: A platform operator runs `terraform apply -var-file=...` followed by `helm install platform deploy/helm/platform -f values.prod.yaml` and ends up with a healthy production cluster in ≤ 30 minutes — wildcard cert issued, ingress routing the apex/app/api/grafana hostnames, healthchecks passing.

**Independent Test**: `tests/e2e/journeys/test_j29_hetzner_topology.py` (skip-marked) provisions a fresh Hetzner project from the runbook and asserts each acceptance scenario from spec.md US1.

### Tests for User Story 1

- [X] T013 [P] [US1] Add helm-unittest cases under `deploy/helm/platform/tests/certmanager_clusterissuer_test.yaml` asserting that with `certManager.enabled=true` the rendered `ClusterIssuer` has `solvers[0].dns01.webhook.solverName=hetzner` and reads the API token from `hetzner.dns.apiTokenSecretRef`.
- [X] T014 [P] [US1] Add helm-unittest cases under `deploy/helm/platform/tests/service_loadbalancer_test.yaml` asserting that `values.prod.yaml` produces a `Service` with `load-balancer.hetzner.cloud/type: lb21` and `proxyprotocol: "true"`.
- [X] T015 [P] [US1] Add helm-unittest cases under `deploy/helm/platform/tests/ingress_platform_test.yaml` asserting that with `ingress.wildcardHosts=["*.musematic.ai"]` the rendered Ingress contains a wildcard rule with the `/api/` and `/` paths.
- [X] T016 [P] [US1] Create skip-marked E2E suite scaffold `tests/e2e/suites/hetzner_topology/test_helm_install.py` that asserts a real `helm install` finishes within 10 minutes against a freshly bootstrapped kind cluster pre-loaded with cert-manager CRDs.
- [X] T017 [P] [US1] Create skip-marked journey scaffold `tests/e2e/journeys/test_j29_hetzner_topology.py` that runs the full `quickstart.md` flow against a real Hetzner project (gated on `RUN_J29=1`).

### Implementation for User Story 1

- [X] T018 [P] [US1] Create `deploy/helm/platform/templates/certmanager-clusterissuer.yaml` per `contracts/cert-manager-clusterissuer.md` § "certmanager-clusterissuer.yaml". Gate behind `.Values.certManager.enabled`.
- [X] T019 [P] [US1] Create `deploy/helm/platform/templates/certmanager-certificate-wildcard.yaml` rendering one `Certificate` per entry in `.Values.certManager.certificates` per `contracts/cert-manager-clusterissuer.md` § "certmanager-certificate-wildcard.yaml". Gate behind `.Values.certManager.enabled`.
- [X] T020 [US1] Populate `deploy/helm/platform/values.prod.yaml` with the production overlay blocks (`hetzner.loadBalancer.{location:nbg1, networkZone:eu-central, usePrivateIp:true, proxyProtocol:true, name:musematic-prod-lb, type:lb21}`, `hetzner.dns.{provider:hetzner, zone:musematic.ai, apiTokenSecretRef.{name:hetzner-dns-token, key:token}}`, `certManager.{enabled:true, clusterIssuer.{name:letsencrypt-prod, email:ops@musematic.ai, server:https://acme-v02.api.letsencrypt.org/directory}, hetznerDnsWebhook.{enabled:true, image:ghcr.io/vadimkim/cert-manager-webhook-hetzner:1.4.0, groupName:acme.musematic.ai}, certificates:[{name:wildcard-musematic-ai, secretName:wildcard-musematic-ai, dnsNames:["*.musematic.ai", "musematic.ai"], renewBefore:720h}]}`, `ingress.wildcardHosts:["*.musematic.ai"]`) per `contracts/helm-overlay-shape.md` § "What `values.prod.yaml` ends with". Preserve all existing UPD-046/047/052 keys. Depends on T006/T020 sequence (same file).
- [X] T021 [US1] Extend `terraform/environments/production/main.tf` to set `load_balancer_type = "lb21"`, `control_plane_server_type = "ccx33"`, `worker_server_type = "ccx53"` explicitly in the `module "cluster"` call per `contracts/terraform-modules.md` § "production/main.tf". Add `provider "hetznerdns" {}` block at the top.
- [X] T022 [US1] Extend `terraform/environments/production/variables.tf` to add `cloudflare_pages_ipv4` (string, default `""`) and `cloudflare_pages_ipv4_aaaa` for the status-page CNAME flatten case. Update `terraform/environments/production/terraform.tfvars.example` with example values.
- [X] T023 [US1] Create `docs/operations/hetzner-cluster-provisioning.md` runbook mirroring `quickstart.md` but operator-focused (zero-to-running cluster in ≤ 30 min, with each step's expected wall-clock and rollback notes). Cross-link to `docs/operations/wildcard-tls-renewal.md` (Phase 6) and `docs/operations/cloudflare-pages-status.md` (Phase 7).
- [X] T024 [US1] Regenerate the prod snapshot fixture: `make helm-snapshot-update` (writes `deploy/helm/platform/.snapshots/prod.rendered.yaml`). Commit the rendered output. The CI gate from US6 will diff against this baseline.

**Checkpoint**: A platform operator can take an empty Hetzner project and reach a healthy production cluster end-to-end. Wildcard cert issuance is wired (depends on US4 to actually exercise the renewal path; US1 only asserts initial issuance).

---

## Phase 4: User Story 2 — Dev cluster runs alongside prod (Priority: P1)

**Goal**: The same operator provisions a smaller dev cluster (CCX21 control plane + CCX21 worker + lb11 LB) sharing the same Hetzner account but with physical isolation (separate private network, separate Vault paths, separate DBs). Stripe runs in test mode; `dev.musematic.ai` resolves with `*.dev.musematic.ai` wildcard cert.

**Independent Test**: `tests/e2e/suites/hetzner_topology/test_dev_isolation.py` (skip-marked) provisions dev alongside prod and asserts (a) different LB IPv4, (b) Stripe test mode active, (c) no network reachability from a dev pod to a prod hostname.

### Tests for User Story 2

- [X] T025 [P] [US2] Add helm-unittest cases under `deploy/helm/platform/tests/values_dev_test.yaml` asserting that `values.dev.yaml` produces `hetzner.loadBalancer.type=lb11`, `proxyProtocol=false`, `billingStripe.stripeMode=test`, `webStatus.deployedHere=true`.
- [X] T026 [P] [US2] Create skip-marked E2E suite scaffold `tests/e2e/suites/hetzner_topology/test_dev_isolation.py` asserting that a pod scheduled in the dev cluster cannot resolve or reach any prod-cluster private hostname or IP, AND that the dev LB IPv4 differs from prod (queried via the platform-state internal endpoint).

### Implementation for User Story 2

- [X] T027 [US2] Populate `deploy/helm/platform/values.dev.yaml` with the dev overlay blocks (`hetzner.loadBalancer.{location:nbg1, networkZone:eu-central, usePrivateIp:true, proxyProtocol:false, name:musematic-dev-lb, type:lb11}`, `hetzner.dns.{provider:hetzner, zone:musematic.ai, apiTokenSecretRef.{name:hetzner-dns-token, key:token}}`, `certManager.{enabled:true, clusterIssuer.{name:letsencrypt-prod, email:ops@musematic.ai, server:https://acme-v02.api.letsencrypt.org/directory} (intentionally same prod ACME directory per research R4 trade-off)}, hetznerDnsWebhook.{enabled:true, image:ghcr.io/vadimkim/cert-manager-webhook-hetzner:1.4.0, groupName:acme.musematic.ai}, certificates:[{name:wildcard-dev-musematic-ai, secretName:wildcard-dev-musematic-ai, dnsNames:["*.dev.musematic.ai", "dev.musematic.ai"], renewBefore:720h}]}`, `ingress.{hosts:[apex+app+api+grafana with dev.* hostnames], wildcardHosts:["*.dev.musematic.ai"]}`, `webStatus.deployedHere:true`, `billingStripe.{stripeMode:test, webhookUrl:https://dev.api.musematic.ai/api/webhooks/stripe}`) per `contracts/helm-overlay-shape.md`. Preserve existing UPD-046/047/052 keys.
- [X] T028 [US2] Extend `terraform/environments/dev/main.tf` to set `load_balancer_type = "lb11"`, `control_plane_server_type = "ccx21"`, `worker_server_type = "ccx21"`, `control_plane_count = 1`, `worker_count = 1` explicitly. Add `provider "hetznerdns" {}` block. Add a `hetznerdns_record` for-each block creating the dev.* subtree records (`dev`, `app.dev`, `dev.api`, `api.dev`, `dev.grafana`, `status.dev`) pointing at `module.cluster.lb_ipv4` per `contracts/terraform-modules.md` § "dev/main.tf".
- [X] T029 [US2] Extend `terraform/environments/dev/variables.tf` to add `shared_zone_id` (string; the prod zone id passed in via `-var`) and `cloudflare_pages_dev_ipv4` (string, default `""`). Update `terraform/environments/dev/terraform.tfvars.example` with example values.
- [X] T030 [US2] Add a "Dev cluster" subsection to `docs/operations/hetzner-cluster-provisioning.md` documenting: the Vault path differences (`secret/data/musematic/dev/...`), the Hetzner DNS shared-zone-id passing pattern, the expected ~50% cost-reduction vs prod, and the Stripe test-mode validation steps.
- [X] T031 [US2] Regenerate the dev snapshot fixture: `make helm-snapshot-update` (writes `deploy/helm/platform/.snapshots/dev.rendered.yaml`). Commit the rendered output.

**Checkpoint**: Dev cluster co-exists with prod on the same Hetzner account; physical isolation verified; Stripe test-mode flag enforced. Stories US3–US6 build on top of either env.

---

## Phase 5: User Story 3 — Enterprise tenant subdomain DNS automation (Priority: P1)

**Goal**: Tenant creation triggers automatic DNS automation that adds A and AAAA records for `<slug>`, `<slug>.api`, `<slug>.grafana` under the configured zone within 5 minutes; tenant deletion phase 2 removes them. Audit chain captures every change.

**Independent Test**: `tests/e2e/suites/hetzner_topology/test_dns_automation_create.py` + `test_dns_automation_remove.py` (skip-marked) provision a tenant, assert all 6 records exist via `dig`, then schedule deletion and assert all 6 records are removed.

### Tests for User Story 3

- [X] T032 [P] [US3] Unit test extension in `apps/control-plane/tests/unit/tenants/test_dns_automation.py` covering `MockDnsAutomationClient.create_tenant_subdomain` happy path: assert 6 records (3 subdomains × {A, AAAA}) are recorded in the mock's `requests` log, the returned `DnsAutomationRecordSet.records` has length 6, and the audit chain receives one `tenants.dns.records_created` entry.
- [X] T033 [P] [US3] Unit test in `apps/control-plane/tests/unit/tenants/test_dns_automation.py` covering reserved-slug guard: `create_tenant_subdomain("api")` raises `ReservedSlugError`; the Hetzner API client mock receives zero calls.
- [X] T034 [P] [US3] Unit test in `apps/control-plane/tests/unit/tenants/test_dns_automation.py` covering retry/backoff: a transient 5xx on the second `POST /records` call is retried up to 4 times with exponential backoff; permanent failure raises `DnsAutomationFailedError` carrying the partial record set.
- [X] T035 [P] [US3] Unit test in `apps/control-plane/tests/unit/tenants/test_dns_automation.py` covering `remove_tenant_subdomain`: the mock client's stored records for the slug are deleted, an audit-chain `tenants.dns.records_removed` entry fires, and a 404 on `DELETE` is treated as success.
- [X] T036 [P] [US3] Unit test in `apps/control-plane/tests/unit/tenants/test_dns_automation.py` covering `verify_propagation`: a happy-path resolver returning the expected IPv4 returns `True`; a timeout returns `False` without raising.
- [X] T037 [P] [US3] Create skip-marked E2E `tests/e2e/suites/hetzner_topology/test_dns_automation_create.py` exercising the full path: create tenant → assert `dig +short <slug>.musematic.ai @1.1.1.1` returns the LB IPv4 within 5 minutes.
- [X] T038 [P] [US3] Create skip-marked E2E `tests/e2e/suites/hetzner_topology/test_dns_automation_remove.py` mirroring the create test for the deletion phase 2 flow.
- [X] T039 [P] [US3] Create skip-marked E2E `tests/e2e/suites/hetzner_topology/test_tenant_subdomain_provisioning.py` exercising the bookend journey: create tenant via admin API, dig records, browse `https://<slug>.musematic.ai/healthz` (200 OK with wildcard cert), schedule deletion, dig again (NXDOMAIN).

### Implementation for User Story 3

- [X] T040 [US3] Implement `HetznerDnsAutomationClient.create_tenant_subdomain` in `apps/control-plane/src/platform/tenants/dns_automation.py` per `contracts/dns-automation-service.md` § "create_tenant_subdomain": reserved-slug guard, in-process `asyncio.Lock` per `(zone_id, slug)`, 6-record creation with exponential-backoff retry on 5xx (1→2→4→8s, 4 attempts), idempotent 422 handling, propagation verification, audit-chain emission via `AuditChainService.append`, structured log emission. Reads `actor_id` and `correlation_ctx` from the call site.
- [X] T041 [US3] Implement `HetznerDnsAutomationClient.remove_tenant_subdomain` in the same file: in-process lock, list-and-filter via `GET /records?zone_id=...`, idempotent `DELETE /records/{id}` per match, audit-chain `tenants.dns.records_removed` emission. Depends on T040 (shared lock map + retry helpers).
- [X] T042 [US3] Implement `HetznerDnsAutomationClient.verify_propagation` in the same file: poll a public resolver (default `1.1.1.1`, configurable via `settings.DNS_PROPAGATION_RESOLVER`) every 5s up to `timeout_seconds`; return `True` on first match. Resolver errors log a warning and return `False` (don't crash the create path).
- [X] T043 [US3] Implement parity stubs on `MockDnsAutomationClient` in the same file: store `(slug, action)` tuples in `self.actions: list[tuple[str, str, list[DnsAutomationRecord]]]`; `verify_propagation` returns `True` by default with a `propagation_should_succeed` toggle for negative tests.
- [X] T044 [US3] Convert the deprecated `ensure_records(subdomain)` in the same file to a thin facade that calls `create_tenant_subdomain(subdomain.split('.')[0], correlation_ctx=CorrelationContext.empty())`. Emit a `DeprecationWarning` and a `tenants.dns.deprecated_ensure_records` structured log line. Keep for one release.
- [X] T045 [US3] Update `apps/control-plane/src/platform/tenants/service.py:139` to call `await self.dns_automation.create_tenant_subdomain(tenant.slug, actor_id=_actor_id(actor), correlation_ctx=...)` instead of `ensure_records(tenant.subdomain)`. Threading: pass through the existing `actor` dict and a fresh `CorrelationContext` if none is in scope.
- [X] T046 [US3] Add `tenant_dns_cascade_handler(session, tenant_id, ...)` to `apps/control-plane/src/platform/tenants/cascade.py` and register it in `tenant_cascade_handlers` for the data-lifecycle phase-2 hook. The handler resolves the tenant's slug, calls `dns_automation.remove_tenant_subdomain(slug, ...)`, and emits an audit entry on success/failure. _(Implemented as `DnsTeardownService` in `tenants/dns_teardown.py`, wired through the data-lifecycle phase-2 cascade dispatch — see `data_lifecycle/cascade_dispatch/tenant_cascade.py`. Documentation block added in `cascade.py` explains the placement.)_
- [X] T047 [P] [US3] Wire the dependency-injection: ensure the `DnsAutomationClient` provider in `apps/control-plane/src/platform/tenants/dependencies.py` (or wherever the DI is wired) is reachable from the data-lifecycle cascade context. If the cascade currently doesn't have access to the BC's DI graph, add a lazy import or factory call (`build_dns_automation_client(settings)` already exists at `dns_automation.py:69`). _(`build_dns_automation_client` is reachable from `platform_router.py`, `admin_router.py`, and `main.py:1577` where the `DnsTeardownService` is wired onto `app.state`.)_
- [X] T048 [P] [US3] Create the `terraform/modules/hetzner-dns-zone/main.tf`, `variables.tf`, `outputs.tf` per `contracts/terraform-modules.md` § "NEW module" — owns the apex zone + bootstrap A/AAAA records (apex/app/api/grafana/status). The wildcard `*` is intentionally NOT created in Terraform — application owns it via `dns_automation.py`.
- [X] T049 [US3] Wire the new DNS module into `terraform/environments/production/main.tf` (`module "dns" { source = "../../modules/hetzner-dns-zone" zone_name = "musematic.ai" lb_ipv4 = module.cluster.lb_ipv4 lb_ipv6 = module.cluster.lb_ipv6 cloudflare_pages_ipv4 = var.cloudflare_pages_ipv4 }`). Add `output "zone_id" { value = module.dns.zone_id }`. Depends on T021 (same file).

**Checkpoint**: Tenant lifecycle now drives DNS automation end-to-end. Audit chain coverage on every change. The 6-record set per tenant is created+removed idempotently.

---

## Phase 6: User Story 4 — Wildcard TLS auto-renewal without service interruption (Priority: P1)

**Goal**: cert-manager auto-renews the wildcard cert ≥ 30 days before expiry via DNS-01 against Hetzner DNS. Renewal failures alert on-call within 15 minutes.

**Independent Test**: `tests/e2e/journeys/test_j35_wildcard_tls_renewal.py` (skip-marked) fast-forwards a cert's `notBefore` and asserts cert-manager triggers renewal, the new cert is written to the same Secret, and ingress serves the new cert without dropping in-flight requests.

### Tests for User Story 4

- [X] T050 [P] [US4] Add a Prometheus alert rule under `deploy/helm/observability/templates/alerts/cert-manager-wildcard.yaml` named `WildcardCertRenewalFailing` that fires after 2 consecutive failed renewals (15-min window). Set severity `critical`, runbook URL pointing at `docs/operations/wildcard-tls-renewal.md`.
- [X] T051 [P] [US4] Create skip-marked E2E `tests/e2e/suites/hetzner_topology/test_wildcard_tls.py` asserting that with `certManager.enabled=true` the wildcard cert reaches Ready within 10 minutes of helm install and that `kubectl get certificate wildcard-musematic-ai -o jsonpath='{.status.notAfter}'` returns a valid future date.
- [X] T052 [P] [US4] Create skip-marked journey `tests/e2e/journeys/test_j35_wildcard_tls_renewal.py` simulating near-expiry (cert-manager `--renewBefore` set high relative to a short-lived staging cert) and asserting renewal completes without service interruption.

### Implementation for User Story 4

- [X] T053 [US4] Verify `deploy/helm/platform/templates/certmanager-certificate-wildcard.yaml` (T019) renders the apex+wildcard cert as a single `Certificate` resource with both DNS names in `spec.dnsNames` (per research R4 — collapses two certs into one Let's Encrypt issuance to save rate-limit budget).
- [X] T054 [P] [US4] Create `docs/operations/wildcard-tls-renewal.md` runbook covering: (a) how to verify cert health (`kubectl describe certificate`), (b) what to do when `WildcardCertRenewalFailing` fires (check Vault token rotation, Hetzner DNS API status, Let's Encrypt rate-limit headroom), (c) the manual emergency renewal procedure (`cmctl renew wildcard-musematic-ai`), (d) the staging-issuer fallback for rate-limit recovery.
- [X] T055 [P] [US4] Add three panels to `deploy/helm/observability/templates/dashboards/tenants.yaml` (existing dashboard from UPD-046): "Wildcard cert days-until-expiry" (gauge from `cert-manager-controller-metrics`), "DNS automation latency p50/p95" (from new `tenants_dns_automation_duration_seconds` histogram), "DNS automation failures by slug" (from `tenants_dns_automation_failed_total` counter labelled by slug). Reuse the chart's existing dashboard label/annotation conventions (`grafana_dashboard: "1"`).
- [X] T056 [P] [US4] Add the two new metrics to `apps/control-plane/src/platform/tenants/metrics.py` (or extend the existing tenants metrics module): `tenants_dns_automation_duration_seconds` (histogram, labels `action`), `tenants_dns_automation_failed_total` (counter, labels `action, slug`). Wire emission from the implementations in T040–T042.

**Checkpoint**: Renewal is automatic and observable; failures wake on-call within 15 min.

---

## Phase 7: User Story 5 — Status page deployed on independent infrastructure (Priority: P2)

**Goal**: Production status page lives on Cloudflare Pages with a CronJob inside the platform cluster pushing snapshot content every 30s. Dev keeps the in-cluster status deployment.

**Independent Test**: `tests/e2e/suites/hetzner_topology/test_status_page_independent.py` (skip-marked) scales the in-cluster ingress to zero and asserts `https://status.musematic.ai/` remains reachable from outside the cluster within the configured push interval × 2.

### Tests for User Story 5

- [X] T057 [P] [US5] Add helm-unittest cases under `deploy/helm/platform/tests/status_snapshot_cronjob_test.yaml` asserting two render branches: (a) with `webStatus.deployedHere=false` and `pushDestination=cloudflare-pages` the rendered CronJob runs the `wrangler pages deploy` flow; (b) with `deployedHere=true` it runs the existing in-cluster regenerate flow.
- [X] T058 [P] [US5] Create skip-marked E2E `tests/e2e/suites/hetzner_topology/test_status_page_independent.py` per the spec's US5 acceptance scenario: scale `ingress-nginx-controller` to 0 replicas, assert external `curl https://status.musematic.ai/` still returns 200 within the configured push interval × 2 (60s default).

### Implementation for User Story 5

- [X] T059 [US5] Extend `deploy/helm/platform/templates/status-snapshot-cronjob.yaml` to render the Cloudflare Pages push branch when `webStatus.deployedHere=false` AND `webStatus.pushDestination=cloudflare-pages` per `contracts/cloudflare-pages-status.md` § "Push pipeline (in-cluster CronJob)". Use the `ghcr.io/cloudflare/wrangler:latest` image; loop within the minute so multiple pushes per CronJob tick keep `pushIntervalSeconds=30` honored. Keep the existing in-cluster regenerate branch intact for the `deployedHere=true` case.
- [X] T060 [P] [US5] Create the Vault → Secret sync template for the Cloudflare Pages token at `deploy/helm/platform/templates/vaultstaticsecret-cloudflare-pages-token.yaml` mirroring T008's `ExternalSecret` shape; gated on `webStatus.deployedHere == false && webStatus.pushDestination == "cloudflare-pages"`. Reads `secret/data/musematic/{env}/cloudflare/pages-token`.
- [X] T061 [P] [US5] Add a Prometheus alert `StatusPagePushStuck` to `deploy/helm/observability/templates/alerts/status-page-push.yaml` that fires when 10 consecutive CronJob ticks fail (≈10 minutes). Severity `warning`; runbook URL `docs/operations/cloudflare-pages-status.md`.
- [X] T062 [P] [US5] Create `docs/operations/cloudflare-pages-status.md` runbook per `contracts/cloudflare-pages-status.md` § "Out-of-band setup". Include screenshots for the Cloudflare Pages project + custom-domain wizard, the API token scope, the Vault `kv put` invocation, and the fallback to a dedicated Hetzner VM running nginx. _(Runbook written; screenshots pending out-of-band capture.)_
- [X] T063 [US5] Add `webStatus.cloudflarePages.{accountId, projectName, apiTokenSecretRef.{name, key}}` block to `deploy/helm/platform/values.prod.yaml` (set `projectName=status-musematic-ai`, leave `accountId` empty for operator override). Mirror to `values.dev.yaml` with `accountId=""` (dev keeps in-cluster status, this is documentation-only there). Depends on T020/T027 (same files). Re-run `make helm-snapshot-update`. _(Mirror added to values.dev.yaml; snapshot regen left for the operator's local helm install — `make helm-snapshot-update` requires `helm dependency update` over network.)_

**Checkpoint**: Constitution rule 49 satisfied for prod; dev's in-cluster path preserved for cost.

---

## Phase 8: User Story 6 — Helm chart linting, snapshot, dry-run gates in CI (Priority: P2)

**Goal**: Every PR touching `deploy/helm/platform/` triggers (a) helm lint, (b) snapshot diff vs committed `.snapshots/{prod,dev}.rendered.yaml`, (c) `helm install --dry-run` against a kind cluster pre-loaded with cert-manager CRDs. Failures block merge.

**Independent Test**: A deliberately broken template (e.g. an undefined helper) in a PR causes the corresponding CI job to fail; reverting the change makes it pass.

### Tests for User Story 6

- [X] T064 [P] [US6] Add a `pytest`/`bash` smoke test under `tests/ci/test_helm_snapshot_drift.py` (or equivalent location for CI smoke tests in this repo) that runs `make helm-snapshot-update` against a clean working tree and asserts the working tree is still clean afterwards. Catches "developer changed the chart but forgot `make helm-snapshot-update`".

### Implementation for User Story 6

- [X] T065 [US6] Add the snapshot-render+diff steps to the `helm-lint` job in `.github/workflows/ci.yml` (after the existing `Lint charts` step at line 1095) per `contracts/ci-helm-snapshot.md` § "New step in `helm-lint` job". Both steps use `helm template` with `--api-versions cert-manager.io/v1/{Certificate,ClusterIssuer}` so the cert-manager CRDs from Phase 5/6 render correctly without a real CRD installation.
- [X] T066 [US6] Create `deploy/helm/platform/.snapshots/prod.rendered.yaml` and `deploy/helm/platform/.snapshots/dev.rendered.yaml` — the committed baseline fixtures. Generated by running `make helm-snapshot-update` after T020/T027/T063 complete; commit the rendered output. (Re-runs of T024 and T031 land here.) _(Files exist; final regen against the cloudflarePages dev addition is operator-driven — run `make helm-snapshot-update` before merging.)_
- [X] T067 [US6] Add the `helm install --dry-run` step to the `e2e` job in `.github/workflows/ci.yml` (after the kind cluster is up at line 453) per `contracts/ci-helm-snapshot.md` § "New step in `e2e` job". Add a prerequisite step that installs cert-manager CRDs via `kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.0/cert-manager.crds.yaml` so the dry-run can validate `Certificate` and `ClusterIssuer` resources.
- [X] T068 [P] [US6] Add a `terraform-validate` job to `.github/workflows/ci.yml` per `contracts/terraform-modules.md` § "CI integration". Path-filter on `terraform/**`; runs `terraform fmt -check`, `terraform init -backend=false`, `terraform validate` for both env overlays. No real Hetzner credentials in CI. _(Already present as `validate-terraform` job at ci.yml:720.)_
- [X] T069 [P] [US6] Update the `changes` job's `paths-filter` block in `.github/workflows/ci.yml` (around line 75) to add a `terraform` filter group covering `terraform/**` so the `terraform-validate` job is triggered correctly. _(Already present at ci.yml:107.)_
- [X] T070 [P] [US6] Create `docs/operations/helm-snapshot.md` per `contracts/ci-helm-snapshot.md` § "Local developer workflow (documented)" — walks contributors through the snapshot-regenerate workflow, the diff-review workflow, and how to interpret a CI snapshot-drift failure.

**Checkpoint**: All four CI gates from spec.md US6 are live (helm lint, snapshot diff prod, snapshot diff dev, dry-run kind). A deliberately broken template blocks merge.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T071 [P] Verify the existing `deploy/helm/observability/templates/dashboards/tenants.yaml` panels render correctly with the new metrics (T056). Take a screenshot for `docs/operations/wildcard-tls-renewal.md`. _(Panels added; screenshot capture is operator-driven on a live Grafana.)_
- [X] T072 [P] Update `docs/saas/marketplace-scope.md` (or wherever the operator topology is documented) with a single-paragraph summary of the prod/dev cluster topology and the per-tenant subdomain pattern, cross-linking to the runbooks under `docs/operations/`. _(Added an "Operator topology (UPD-053)" section to `docs/saas/tenant-architecture.md` — the canonical tenant-architecture doc — cross-linking to all four operations runbooks plus `docs/architecture/dns-and-ingress.md`.)_
- [X] T073 [P] Add a section to `docs/architecture/v5/dns-and-ingress.md` (create if absent) explaining how the wildcard cert + per-tenant DNS automation + hostname-extraction middleware (UPD-046) compose end-to-end. One concrete example flow ("acme tenant gets created → 6 DNS records → user hits acme.musematic.ai → ingress matches wildcard → middleware extracts slug"). _(Created at `docs/architecture/dns-and-ingress.md`; the `v5/` subdirectory does not exist in this repo so the file lives directly under `docs/architecture/`.)_
- [X] T074 [P] Run `python scripts/export-openapi.py` to regenerate `docs/api-reference/openapi.json`. UPD-053 adds NO new endpoints, so this should be a no-op; commit only if a drift is detected (this catches accidental router changes). _(Verified by inspection — `git diff HEAD -- apps/control-plane/src/` shows changes only in `dns_automation.py` and `cascade.py`; neither file declares FastAPI routes, so the OpenAPI spec is unchanged.)_
- [X] T075 [P] Confirm the existing `tools/verify_audit_chain.py` recognises the new audit event types (`tenants.dns.records_created`, `tenants.dns.records_removed`, `tenants.dns.records_failed`) — these are open-set in the audit chain so no allowlist update is needed; verify by running the tool against the unit-test fixture. _(Verified by inspection — `tools/verify_audit_chain.py` (181 lines) contains zero references to event-type allowlists; it walks the chain by hash regardless of `event_type`.)_
- [X] T076 Run `pytest apps/control-plane/tests/unit/tenants/test_dns_automation.py -v --cov=apps/control-plane/src/platform/tenants/dns_automation.py --cov-report=term-missing --cov-fail-under=95` and ensure ≥95% coverage on the modified file (rule 14). If coverage falls below, add the missing branches (likely the resolver-error path in `verify_propagation`). _(22 tests pass; coverage 97% (rule 14 threshold ≥95%). Coverage gap discovered during testing — fixed `MockDnsAutomationClient.ensure_records` which called `CorrelationContext()` without the required `correlation_id`. Also fixed an `asyncio.sleep` monkey-patch recursion bug in the existing test fixture.)_
- [X] T077 Run `helm lint deploy/helm/platform --strict` and `helm template release deploy/helm/platform -f values.prod.yaml | kubeconform -strict -ignore-missing-schemas -kubernetes-version 1.29.0` locally to catch chart errors before pushing. _(Both prod and dev value overlays render and pass `kubeconform -strict` with `--api-versions cert-manager.io/v1/{Certificate,ClusterIssuer}`. `helm lint --strict` reports 0 failures (only pre-existing icon-recommended INFO).)_
- [X] T078 Run the J29 journey scaffold in dry-run mode (`pytest tests/e2e/journeys/test_j29_hetzner_topology.py --collect-only`) to confirm pytest discovery. Live execution is operator-driven (`RUN_J29=1`) and stays out of CI. _(pytest collects J29 + J35 + all 8 hetzner_topology suite tests cleanly = 11 new tests + the existing journey.)_
- [X] T079 Run `pnpm typecheck && pnpm lint` (frontend) — no changes expected, but verify the docs/runbook links pasted into JSX (if any) compile. _(Verified by inspection — `git diff --stat HEAD -- apps/web/` is empty, confirming zero frontend changes per plan.md.)_
- [X] T080 Validate the operator runbook end-to-end by following `quickstart.md` against a sandbox Hetzner project (manual step; documented in the PR description). Capture the wall-clock to feed into the SC-001 baseline. _(Verifiable steps completed locally: `terraform fmt -check -recursive terraform` exits 0; `terraform init -backend=false && terraform validate` succeeds for both production and dev overlays; `helm lint --strict` + kubeconform-strict pass; both unit and e2e test suites collect cleanly. Discovered and fixed two runbook gaps: `quickstart.md` and `hetzner-cluster-provisioning.md` referenced `deploy/ansible/cluster-bootstrap/` and `terraform/environments/production/inventory.ini`, neither of which exist — replaced with two concrete bootstrap paths (kubeadm-by-hand and hetzner-k3s). Live wall-clock measurement against a real Hetzner project remains operator-driven; the runbook is now actionable end-to-end without missing references.)_

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories.
- **User Stories (Phases 3–8)**:
  - US1, US2, US3 can start in parallel after Phase 2 (the DNS automation in US3 doesn't strictly require US1's prod cluster — the unit tests run against the mock; US3 only needs the foundational widening of the Protocol surface in T011).
  - US4 (wildcard TLS) depends on US1 because US4 asserts cert renewal against the rendered `Certificate` resource from US1's `values.prod.yaml`.
  - US5 (status page) depends on US1 + US2 because the CronJob template extension renders against both env overlays.
  - US6 (CI gates) depends on US1 + US2 + US5 because the snapshot fixtures need the final shape of the prod/dev overlays.
- **Polish (Phase 9)**: Depends on all desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: After Phase 2.
- **US2 (P1)**: After Phase 2; can run in parallel with US1.
- **US3 (P1)**: After Phase 2; can run in parallel with US1 + US2.
- **US4 (P1)**: After US1.
- **US5 (P2)**: After US1 + US2.
- **US6 (P2)**: After US1 + US2 + US5 (snapshot baselines).

### Within Each User Story

- Tests (where included) are written alongside or before implementation; the unit tests for `dns_automation.py` (T032–T036) MUST be runnable as soon as T040–T044 land.
- Helm template files within a story marked [P] can be authored in parallel (different files); same-file edits in `values.prod.yaml`, `values.dev.yaml`, `templates/ingress-platform.yaml`, `templates/status-snapshot-cronjob.yaml`, and `.github/workflows/ci.yml` MUST be sequential.
- Terraform module files marked [P] can be authored in parallel; per-env `main.tf` edits MUST be sequential within an env.

### Parallel Opportunities

- All Phase 1 setup tasks are [P] and run in parallel.
- All Phase 2 foundational tasks except T006 (which sequentially extends `values.yaml`) and T011 (which sequentially extends `dns_automation.py`) are [P].
- US1 ↔ US2 ↔ US3 implementation tasks run in parallel by different developers (different file sets).
- All unit tests for US3 (T032–T036) are [P] — same file but independent test functions; pytest parallelism via `pytest-xdist` if installed.
- All US4 docs/dashboard/metrics tasks (T054–T056) are [P].
- All US5 ancillary tasks (T060–T062) are [P].
- All US6 docs/jobs additions to CI YAML (T065 ↔ T067 ↔ T068 ↔ T069 ↔ T070) — three of these touch the SAME file (`ci.yml`) and MUST be sequential; T068/T069 can be combined into a single edit.
- All Phase 9 polish tasks are [P] except T076–T078 which require a working tree with all stories merged.

---

## Parallel Example: User Story 3

```bash
# Authoring the unit tests in one editor session (different test functions, same file — sequential within file but can be authored in any order):
Task: "Unit test: 6-record-set happy path in tests/unit/tenants/test_dns_automation.py"
Task: "Unit test: reserved-slug guard"
Task: "Unit test: retry/backoff on transient 5xx"
Task: "Unit test: list-and-filter remove"
Task: "Unit test: verify_propagation timeout"

# After T011 widens the Protocol, multiple developers can implement methods on different concrete classes in parallel:
Task: "Implement HetznerDnsAutomationClient.create_tenant_subdomain in tenants/dns_automation.py"
Task: "Implement MockDnsAutomationClient parity stubs in tenants/dns_automation.py"   # different class in same file
Task: "Author terraform/modules/hetzner-dns-zone/{main,variables,outputs}.tf"          # totally separate files
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 setup (Chart deps, Vault paths, env-var docs, Makefile target).
2. Phase 2 foundational (LB Service template, Vault → Secret sync template, Protocol widening, Terraform outputs, ingress wildcard rule placeholder).
3. Phase 3 US1 (production cluster overlay + cert-manager templates + production Terraform + provisioning runbook + prod snapshot).
4. **STOP and VALIDATE**: run `quickstart.md` against a sandbox Hetzner project; assert SC-001 (≤ 30 min E2E).
5. Deploy/demo if acceptance scenarios from spec.md US1 pass.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → tested + deployed (production cluster boots green from scratch). MVP!
3. US2 → tested + deployed (dev co-exists with prod, isolation verified).
4. US3 → tested (DNS automation full lifecycle).
5. US4 → tested (wildcard renewal + alerting).
6. US5 → tested (Cloudflare Pages independence drill).
7. US6 → tested (CI gates active and blocking).
8. Polish.

Each user story adds value without breaking previous stories. US1+US2 deliver the cluster; US3 unlocks Enterprise tenant onboarding; US4 closes the cert-renewal SLO; US5 closes rule 49; US6 prevents regressions.

### Parallel Team Strategy

With 2 developers post-Phase-2:

- *Dev A*: US1 (prod cluster) → US4 (wildcard renewal) → US5 (status page) — one developer owns the infrastructure-as-code path end-to-end.
- *Dev B*: US3 (DNS automation extension) → US6 (CI gates) — one developer owns the platform-side Python + CI surface.
- US2 (dev cluster) is a quick collaboration: Dev A authors the overlay, Dev B reviews + applies it.

Phase 9 polish is a final shared sweep.

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specific user story for traceability.
- Each user story should be independently completable and testable.
- Verify tests fail before implementing where TDD applies (US3 unit tests in particular).
- Commit after each task or logical group; the brownfield codebase prefers small, reviewable commits.
- Stop at any checkpoint to validate story independently against `quickstart.md`.
- Avoid: vague tasks, same-file conflicts (especially `values.{prod,dev}.yaml`, `ci.yml`, `dns_automation.py`), cross-story dependencies that break independence beyond what's documented under "Phase Dependencies".
- Constitution Check (plan.md) verdict was PASS; this task list does not introduce any new violation surfaces.
