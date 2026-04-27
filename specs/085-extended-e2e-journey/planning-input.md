# Planning Input — UPD-035 Extended E2E Journey Tests and Observability Helm Bundle

> **Captured verbatim from the user's `/speckit.specify` invocation on 2026-04-27.** This file is the immutable record of the brownfield context that authored spec.md. Edits MUST NOT be made here; if a correction is needed, edit spec.md and append a note to the corrections list at the top of this file.

## Corrections Applied During Spec Authoring

1. **"Seven new user journey E2E tests" → eight.** The brownfield input's "Seven new" wording (mirroring FR-519's identical slip) does not match the eight personas it enumerates (Privacy Officer, Security Officer, Finance Owner, SRE, Model Steward, Accessibility User, Compliance Auditor, Dashboard Consumer). FR-521 through FR-528 = 8 FRs = 8 journeys. The spec uses 8.
2. **"9 existing journeys (J01-J09)"** does not match the on-disk inventory under `tests/e2e/journeys/` which currently has J01-J04 plus a `test_j10_multi_channel_notifications.py`. The plan phase reconciles file numbering against feature 072's authority; the spec describes the WHAT in persona terms regardless.
3. **`helm/observability/` vs `deploy/helm/observability/`.** On-disk path is `deploy/helm/observability/`; canonical.
4. **Brownfield input cites `tests/e2e/chaos/`** but no such directory currently exists on disk. The plan phase verifies whether feature 071's chaos work places them elsewhere; if so, FR-532 paths are reconciled.

---

# UPD-035 — Extended E2E Journey Tests and Observability Helm Bundle

## Brownfield Context

**Extends:**
- UPD-021 (kind-based E2E test infrastructure — bounded-context suites, chaos, performance)
- UPD-022 (9 user journey tests — J01 Admin, J02 Creator, J03 Consumer, J04 Workspace Goal, J05 Trust Officer, J06 Operator, J07 Evaluator, J08 External Integrator, J09 Research Scientist)
- UPD-034 (Log aggregation, 14 new Grafana dashboards, 5 Loki alerts)
- All audit-pass features (UPD-023 through UPD-033)
- Feature 047-observability-stack (existing 7 dashboards, Prometheus, Grafana, Jaeger, Alertmanager, OTEL Collector)

**Adds:**
1. **Unified observability Helm bundle** — single `deploy/helm/observability/` umbrella chart installing the complete observability stack in one command (Prometheus + Grafana + Jaeger + Loki + Promtail + Alertmanager + OTEL Collector).
2. **Seven new user journey E2E tests** for personas introduced or expanded by the audit pass: Privacy Officer, Security Officer, Finance Owner, SRE, Model Steward, Accessibility User, Compliance Auditor, Dashboard Consumer.
3. **Extensions to the nine existing journeys** to exercise audit-pass and observability capabilities.
4. **Six new bounded-context E2E suites** covering the new bounded contexts (privacy_compliance, security_compliance, cost_governance, multi_region_ops, model_catalog, localization).
5. **Expanded chaos scenario catalog** covering the new failure modes.
6. **E2E-stack provisioning** that includes the observability Helm chart, so journey tests run against a live Grafana/Loki/Prometheus and assert on real dashboard data.

**FRs:** FR-513 through FR-545 (new, across sections 106, 107, and 108).

---

## Summary

Without UPD-035 the test pyramid has three gaps:

- Eight new bounded contexts (from audit pass) have no user-journey-level coverage; only per-BC unit tests exist.
- The observability Helm bundle was fragmented across sub-charts and ad-hoc install scripts; there is no single reproducible install command for the full stack.
- The existing 9 user journeys predate the audit pass and do not exercise privacy rights, budgets, model fallback, accessibility, or log-metric-trace correlation.

UPD-035 closes all three with:

- **One Helm chart to install all observability components** (`helm install observability ./deploy/helm/observability/`).
- **Extended journey test harness** with 16 total journeys (9 existing + 7 new).
- **Tests run against a real observability stack** — no mocking of Loki/Prometheus/Grafana.

---

## User Scenarios

### User Story 1 — Privacy Officer journey (Priority: P1)

A data subject submits a right-to-be-forgotten request via the self-service portal. The Privacy Officer receives notification, validates the subject's identity, triggers the erasure, and verifies the cascade completed correctly with audit evidence.

**Independent Test:** Submit a DSR for a seeded test user. Verify cascade deletion propagates across PostgreSQL/Qdrant/Neo4j/ClickHouse/OpenSearch/S3, tombstone record is created with cryptographic proof, audit chain entry is appended, subject is notified. 20+ assertion points.

**Acceptance:**
1. DSR submitted via `POST /api/v1/privacy/dsr`.
2. Privacy Officer (test fixture) approves after identity validation.
3. Cascade deletion propagates; Qdrant vectors removed, Neo4j nodes detached, ClickHouse rows hard-deleted, S3 objects purged.
4. Tombstone record exists with cryptographic hash covering the deletion scope.
5. Audit chain entry linked to tombstone; hash chain integrity verified post-operation.
6. Subject receives notification via configured channel.
7. DSR status = `completed` with timestamp and duration metric.

### User Story 2 — Security Officer journey (Priority: P1)

A Security Officer performs a quarterly security compliance cycle: reviews SBOM, triages CVE findings, schedules secret rotation, issues JIT credential, verifies audit chain integrity, exports signed audit log.

**Independent Test:** SBOM published for test release, synthetic vulnerability scan ingested with known CVE, rotation scheduled for database credential, JIT credential issued to on-call fixture, audit chain verified end-to-end, signed export generated. 20+ assertion points.

**Acceptance:**
1. SBOM published and retrievable in both SPDX and CycloneDX formats.
2. Vulnerability scan result visible with severity breakdown.
3. Critical CVE finding triggers ticket creation via incident integration.
4. Secret rotation scheduled with dual-credential window; old credential remains valid during window.
5. JIT credential issued with scope + TTL; operation audit logged on use.
6. Audit chain integrity verification returns ✓ for the test period.
7. Signed audit log exported and external signature verifiable.

### User Story 3 — Finance Owner journey (Priority: P1)

A Finance Owner configures a workspace budget, monitors consumption, and responds to anomalies.

**Independent Test:** Configure monthly budget, trigger executions crossing 50% and 80% soft thresholds, cross hard cap, admin override, trigger cost anomaly via sudden model-cost spike, export chargeback report. 18+ assertion points.

**Acceptance:**
1. Workspace budget configured via `POST /api/v1/costs/budgets`.
2. 50% and 80% alerts fire; notifications received on configured channel.
3. Hard cap blocks new executions; clear error message.
4. Admin override unblocks; audit logged.
5. Cost anomaly (10× spike in 5-minute window) detected and listed in anomaly feed.
6. Chargeback report exportable with correct cost breakdown.
7. Forecast visible for end-of-period spend with confidence interval.

### User Story 4 — SRE (Multi-Region) journey (Priority: P1)

An SRE operator performs a quarterly failover test to the secondary region, verifies no data loss, and fails back.

**Independent Test:** Schedule maintenance window, drain in-flight work, verify replication lag under RPO target, execute failover, verify new executions route to secondary, execute failback, reconcile data. 18+ assertion points.

**Acceptance:**
1. Maintenance window scheduled and visible on operator dashboard.
2. New executions blocked with clear maintenance message; in-flight completes.
3. Replication lag for all stores below RPO threshold prior to failover.
4. Failover executed; DNS/routing switches to secondary.
5. New executions succeed against secondary.
6. Failback restores primary as active.
7. Reconciliation query confirms zero data divergence.

### User Story 5 — Model Steward journey (Priority: P1)

A Model Steward approves a new model entry, configures a fallback policy, verifies fallback behavior, reviews cost impact.

**Independent Test:** Approve model entry with full card, deprecate older entry with grace period, configure fallback policy for agent, simulate primary provider 429 rate-limit, verify fallback used, verify fallback event logged and cost attribution reflects fallback provider. 18+ assertion points.

**Acceptance:**
1. Model entry approved via `POST /api/v1/model-catalog/entries` with complete card.
2. Deprecation set with grace period date; grandfathered executions continue.
3. Fallback policy saved with primary + 2 fallbacks, quality-tier constraints.
4. Synthetic 429 from primary triggers fallback to tier-2 model.
5. Fallback event logged with rationale; visible in Model Catalog dashboard.
6. Cost attribution record shows fallback provider's price.
7. Audit chain entry for model deprecation.

### User Story 6 — Accessibility User journey (Priority: P1)

A user completes a full interaction flow using only keyboard + screen reader, asserting WCAG AA compliance throughout.

**Independent Test:** Automate keyboard-only navigation through login → marketplace → conversation → execution observation → reasoning trace review → logout. Run axe-core on every page; zero AA violations allowed. 15+ assertion points.

**Acceptance:**
1. Every interactive element reachable via Tab / Shift+Tab / arrows.
2. Every status change announced via ARIA live region.
3. Color contrast ratios verified at ≥ 4.5:1 (normal text) and ≥ 3:1 (large text).
4. Focus indicators visible on all interactive elements.
5. Screen reader (axe accessibility tree inspection) announces landmarks, headings, form labels correctly.
6. Zero axe-core AA violations on any visited page.
7. Command palette (Cmd/Ctrl+K) usable via keyboard.

### User Story 7 — Compliance Auditor journey (Priority: P2)

A compliance auditor prepares for a regulatory audit: exports audit trail, verifies hash chain integrity, queries specific event types, reviews compliance evidence.

**Independent Test:** Request audit export for 30-day window, verify signed export, chain integrity verification, query authentication events / DSR / policy violations / JIT grants, review compliance dashboard for SOC2 controls. 16+ assertion points.

**Acceptance:**
1. Audit export generated with cryptographic signature.
2. External signature verification succeeds using the published public key.
3. Hash chain verification returns ✓ end-to-end.
4. Event queries return expected counts and types.
5. Compliance evidence dashboard shows current state of SOC2/ISO27001 controls.
6. Evidence bundle downloadable as single archive.

### User Story 8 — Dashboard Consumer / Observability Correlation journey (Priority: P2)

An SRE uses the observability stack end-to-end to debug a production issue through log-metric-trace correlation.

**Independent Test:** Trigger synthetic error condition (agent fails with correlated upstream API error). Verify alert fires, navigate dashboard → Loki log → Jaeger trace → Prometheus metric. 15+ assertion points exercising all three backends.

**Acceptance:**
1. Synthetic error creates log entry with `trace_id` label within 15s in Loki.
2. `HighErrorLogRate` alert fires and notifies.
3. Cross-Service Error Overview dashboard shows the failing service.
4. Clicking a Loki log entry opens the matching Jaeger trace.
5. Trace includes spans across at least 3 services with correct parent/child relationships.
6. Prometheus metric for the same service shows correlated spike at the same timestamp.
7. After resolution, alert closes within one evaluation cycle.

---

### Edge Cases

- **Loki unreachable during a journey test:** journey must fail with clear message, not silently pass. Asserts on log presence explicitly check Loki reachability.
- **Observability stack not yet started when journey runs:** harness waits up to 60s for Grafana health endpoint before executing.
- **Cascade deletion partially fails:** tombstone not created; DSR marked `failed` with details; journey asserts this failure path in negative test.
- **Failover runbook mid-test pod kill:** secondary region must already be ready; if not, journey fails with capacity error rather than timing out.
- **Accessibility axe-core false positive:** allowlist mechanism per page with justification required; zero silent waivers.

---

## Requirements

### Functional Requirements

- **FR-513 / FR-514**: Unified observability Helm chart with lifecycle management CLI (see section 106 in the FR document).
- **FR-515 / FR-516**: Grafana data source auto-provisioning and dashboards/alerts via ConfigMaps.
- **FR-517 / FR-518**: Retention configuration and sizing presets via Helm values.
- **FR-519**: Seven new journeys (Privacy Officer, Security Officer, Finance Owner, SRE, Model Steward, Accessibility User, Compliance Auditor, Dashboard Consumer).
- **FR-520**: Nine existing journeys extended per the mapping in FR-520.
- **FR-521 through FR-528**: Specific journey test definitions (one FR per journey).
- **FR-529**: Journey test narrative reports with dashboard snapshots.
- **FR-530**: Journey tests run against the ephemeral but complete observability stack (no mocks of backends).
- **FR-531**: Six new bounded-context E2E suites for the new bounded contexts.
- **FR-532**: Chaos scenario expansion with six new scenarios.
- **FR-533 through FR-545**: Loki, Promtail, structured logging, dashboards, alerts, low-cardinality labels, log volume observability (see section 108 in the FR document, delivered jointly with UPD-034 — UPD-035 only adds the test and Helm bundle layer; UPD-034 owns the implementation).

---

## Helm Bundle Layout

```
deploy/helm/observability/
├── Chart.yaml                          # umbrella chart metadata
├── values.yaml                         # shared defaults
├── values-minimal.yaml                 # preset: dev/kind
├── values-standard.yaml                # preset: small production
├── values-enterprise.yaml              # preset: HA with Thanos + distributed Loki
├── charts/                             # vendored sub-charts or dependencies list
├── templates/
│   ├── namespace.yaml                  # platform-observability namespace
│   ├── networkpolicy.yaml              # restrict traffic to/from namespace
│   ├── grafana-datasources/
│   │   ├── prometheus.yaml             # auto-provisioned
│   │   ├── loki.yaml                   # auto-provisioned with derived fields
│   │   └── jaeger.yaml                 # auto-provisioned
│   ├── dashboards/                     # 21 dashboards (7 existing + 14 new), each as ConfigMap
│   │   ├── 01-platform-overview.yaml
│   │   ├── 02-workflow-execution.yaml
│   │   ├── 03-reasoning-engine.yaml
│   │   ├── 04-data-stores.yaml
│   │   ├── 05-fleet-health.yaml
│   │   ├── 06-cost-intelligence.yaml
│   │   ├── 07-self-correction.yaml
│   │   ├── 08-control-plane-logs.yaml
│   │   ├── 09-go-services-logs.yaml
│   │   ├── 10-frontend-web-logs.yaml
│   │   ├── 11-audit-event-stream.yaml
│   │   ├── 12-cross-service-errors.yaml
│   │   ├── 13-privacy-compliance.yaml
│   │   ├── 14-security-compliance.yaml
│   │   ├── 15-cost-governance.yaml
│   │   ├── 16-multi-region-ops.yaml
│   │   ├── 17-model-catalog.yaml
│   │   ├── 18-notifications-delivery.yaml
│   │   ├── 19-incident-response.yaml
│   │   ├── 20-goal-lifecycle.yaml
│   │   └── 21-governance-pipeline.yaml
│   ├── alerts/
│   │   ├── prometheus-rules.yaml       # existing metric-based alerts
│   │   └── loki-rules.yaml             # 5 Loki-based alerts from UPD-034
│   └── _helpers.tpl
└── README.md                           # install/upgrade/uninstall operator guide
```

### Install Flow

```bash
# One command, full stack:
helm upgrade --install observability ./deploy/helm/observability/ \
  --namespace platform-observability --create-namespace \
  --values ./deploy/helm/observability/values-standard.yaml

# Or via operator CLI:
platform-cli observability install --preset standard
platform-cli observability status
```

---

## Extended Journey Test Layout

```
tests/e2e/journeys/
├── conftest.py                         # shared fixtures
├── helpers/                            # reusable helpers
│   ├── oauth_login.py
│   ├── register_agent.py
│   ├── certify_agent.py
│   ├── wait_for_execution.py
│   ├── subscribe_ws.py
│   ├── assert_log_entry.py             # NEW: assert Loki contains expected log
│   ├── assert_metric.py                # NEW: assert Prometheus value
│   ├── assert_trace.py                 # NEW: assert Jaeger trace structure
│   ├── assert_dashboard_snapshot.py    # NEW: headless render dashboard, attach to report
│   └── axe_runner.py                   # NEW: axe-core automation
│
├── test_j01_admin_bootstrap.py         # EXTENDED: DLP rules, budget, model catalog, observability check
├── test_j02_creator_to_publication.py  # EXTENDED: PIA triggered, model binding validated
├── test_j03_consumer_discovery_execution.py  # EXTENDED: cost attribution, content moderation, Loki log
├── test_j04_workspace_goal_collaboration.py  # EXTENDED: tags, policy expression, dashboard
├── test_j05_trust_governance_pipeline.py     # EXTENDED: fairness eval, governance dashboard
├── test_j06_operator_incident_response.py    # EXTENDED: PagerDuty webhook mock, runbook, post-mortem
├── test_j07_evaluator_improvement_loop.py    # EXTENDED: fairness scorer, model fallback triggered
├── test_j08_external_a2a_mcp.py              # EXTENDED: webhook HMAC, rate limit headers, OpenAPI
├── test_j09_scientific_discovery.py          # EXTENDED: fairness on demographic hypotheses, cost attribution
│
├── test_j10_privacy_officer.py               # NEW: DSR lifecycle
├── test_j11_security_officer.py              # NEW: SBOM/CVE/rotation/JIT/audit
├── test_j12_finance_owner.py                 # NEW: budget/anomaly/chargeback
├── test_j13_sre_multi_region.py              # NEW: failover/maintenance
├── test_j14_model_steward.py                 # NEW: catalog approval/fallback
├── test_j15_accessibility_user.py            # NEW: keyboard/screen reader/axe
├── test_j16_compliance_auditor.py            # NEW: audit export/chain verify
└── test_j17_dashboard_consumer.py            # NEW: log-metric-trace correlation
```

### New Bounded-Context Suite Layout

```
tests/e2e/suites/
├── ... existing suites from UPD-021 ...
├── privacy_compliance/                 # NEW
│   ├── test_dsr_access.py
│   ├── test_dsr_erasure_cascade.py
│   ├── test_residency_enforcement.py
│   ├── test_dlp_pipeline.py
│   └── test_pia_workflow.py
├── security_compliance/                # NEW
│   ├── test_sbom_generation.py
│   ├── test_vuln_scan_gating.py
│   ├── test_secret_rotation_dual_window.py
│   ├── test_jit_credential_lifecycle.py
│   └── test_audit_chain_integrity.py
├── cost_governance/                    # NEW
│   ├── test_attribution.py
│   ├── test_budget_enforcement.py
│   ├── test_forecast.py
│   └── test_anomaly_detection.py
├── multi_region_ops/                   # NEW
│   ├── test_region_config.py
│   ├── test_replication_monitoring.py
│   └── test_maintenance_mode.py
├── model_catalog/                      # NEW
│   ├── test_catalog_crud.py
│   ├── test_fallback_on_rate_limit.py
│   └── test_model_card.py
└── localization/                       # NEW
    ├── test_user_preferences.py
    └── test_locale_files.py
```

### Expanded Chaos Catalog

```
tests/e2e/chaos/
├── ... 6 existing scenarios from UPD-021 ...
├── test_loki_ingestion_outage.py       # NEW
├── test_prometheus_scrape_failure.py   # NEW
├── test_model_provider_total_outage.py # NEW — fallback exhaustion
├── test_residency_misconfig.py         # NEW — query rejection behavior
├── test_budget_hard_cap_midexec.py     # NEW — graceful termination
└── test_audit_chain_storage_failure.py # NEW — fail-closed
```

---

## Test Harness Enhancements

### Observability helpers

```python
# helpers/assert_log_entry.py
async def assert_log_contains(
    loki_client: LokiClient,
    labels: dict[str, str],
    substring: str,
    within_seconds: int = 30,
) -> LogEntry:
    """
    Poll Loki until a log entry matching labels and containing substring is found.
    Raise AssertionError with diagnostics if not found within the deadline.
    """
    ...

# helpers/assert_metric.py
async def assert_metric_value(
    prom_client: PromClient,
    query: str,
    expected: float,
    tolerance: float = 0.01,
    within_seconds: int = 15,
) -> None:
    """
    Poll Prometheus until metric value matches expected within tolerance.
    """
    ...

# helpers/assert_trace.py
async def assert_trace_exists(
    jaeger_client: JaegerClient,
    trace_id: str,
    expected_services: list[str],
    expected_operations: list[str],
) -> Trace:
    """
    Fetch trace by ID, assert it includes expected services and operations.
    """
    ...

# helpers/assert_dashboard_snapshot.py
async def take_dashboard_snapshot(
    grafana_client: GrafanaClient,
    dashboard_uid: str,
    time_range: str = "now-1h",
    path: str = "reports/snapshots/",
) -> str:
    """
    Render dashboard to PNG via Grafana renderer plugin, save to path, return filename.
    Used in journey test reports.
    """
    ...

# helpers/axe_runner.py
async def run_axe_scan(
    browser_page: PlaywrightPage,
    rules: list[str] | None = None,
) -> list[AxeViolation]:
    """
    Run axe-core on the current page, return violations.
    Fail the test if any violation at AA level is present.
    """
    ...
```

### Kind cluster extension

The kind cluster provisioning (from UPD-021) is extended to install the observability Helm chart automatically:

```yaml
# deploy/helm/observability/values-e2e.yaml (new overlay)
prometheus:
  prometheusSpec:
    retention: 1h              # Short for tests
    resources:
      limits: { memory: 512Mi }
grafana:
  resources:
    limits: { memory: 256Mi }
loki:
  singleBinary:
    resources:
      limits: { memory: 512Mi }
  loki:
    limits_config:
      retention_period: 1h     # Short for tests
promtail:
  resources:
    limits: { memory: 128Mi }
jaeger:
  storage:
    type: memory               # No persistent storage in E2E
```

```bash
# Makefile update for UPD-035
.PHONY: e2e-up
e2e-up:
  kind create cluster --config tests/e2e/cluster/kind-config.yaml
  helm install observability ./deploy/helm/observability/ \
    -n platform-observability --create-namespace \
    -f ./deploy/helm/observability/values-e2e.yaml --wait
  helm install platform ./deploy/helm/platform/ \
    -n platform-control --create-namespace \
    -f tests/e2e/cluster/values-e2e.yaml --wait
  python -m seeders.base --all
```

---

## Acceptance Criteria

- [ ] `deploy/helm/observability/` umbrella chart exists with sub-chart dependencies (Prometheus, Grafana, Jaeger, Loki, Promtail, Alertmanager, OTEL Collector)
- [ ] Three sizing presets (`minimal`, `standard`, `enterprise`) tested and documented
- [ ] `platform-cli observability install|upgrade|uninstall|status` works end-to-end on kind, k3s, and a managed cluster (GKE/EKS/AKS documented paths)
- [ ] All 21 dashboards auto-provisioned on install
- [ ] All alert rules (Prometheus + Loki) auto-provisioned on install
- [ ] Grafana data sources auto-provisioned with derived field links
- [ ] 7 new journey tests (J10-J17) pass on kind with the observability stack installed
- [ ] 9 existing journeys extended and passing with new assertions
- [ ] 6 new bounded-context suites pass
- [ ] 6 new chaos scenarios pass
- [ ] Journey HTML reports include dashboard snapshots at key moments
- [ ] axe-core reports zero AA violations for accessibility journey (J15)
- [ ] Dashboard Consumer journey (J17) successfully correlates a synthetic issue across Loki + Jaeger + Prometheus
- [ ] Helm uninstall leaves the cluster clean (no lingering CRDs, PVCs with labels, webhooks)
