# Implementation Plan: UPD-035 — Extended E2E Journey Tests and Observability Helm Bundle

**Branch**: `085-extended-e2e-journey` | **Date**: 2026-04-27 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

UPD-035 is the **capstone of the audit pass** (Constitution lines 502-516, audit-pass roster line 476). It is delivered in two parallelizable tracks that converge for end-to-end validation:

- **Track A — Unified observability Helm bundle**: Promote `deploy/helm/observability/` from its current "skeleton + 22 dashboards + 6 alert files" state into a fully-packaged umbrella chart with three sizing presets (`values-minimal.yaml` / `values-standard.yaml` / `values-enterprise.yaml`), one E2E overlay (`values-e2e.yaml`), explicit Grafana data-source ConfigMaps for Prometheus + Loki + Jaeger (with derived-field links so `trace_id` in Loki opens the matching Jaeger trace), explicit NetworkPolicy isolation, the Grafana renderer plugin enabled in `standard`-and-richer presets (so journey reports can embed dashboard snapshots), a README documenting install / upgrade / uninstall semantics, and a `platform-cli observability install|upgrade|uninstall|status` subcommand wrapping the Helm calls and verifying every component's health endpoint.
- **Track B — Extended E2E suite**: Add 8 new journeys (J10-J17) under `tests/e2e/journeys/`, extend each of the 9 historical journeys per FR-520 (the on-disk codebase currently has J01-J04 plus a `test_j10_multi_channel_notifications.py` — the plan reconciles numbering with feature 072), add 6 new bounded-context suites under `tests/e2e/suites/`, add 6 new chaos scenarios under a new `tests/e2e/chaos/` directory (the directory does not currently exist — the existing `Makefile` already invokes it conditionally), add 5 new observability assertion helpers (`assert_log_entry`, `assert_metric`, `assert_trace`, `assert_dashboard_snapshot`, `axe_runner`), add 4 new readiness helpers (Loki / Prometheus / Grafana / Jaeger health gates) wired into `tests/e2e/journeys/conftest.py`, and extend the Mock LLM Provider (`apps/control-plane/src/platform/common/llm/mock_provider.py`) with a synthetic-429 injection knob (used by J14 Model Steward and the `test_model_provider_total_outage.py` chaos scenario).

Both tracks consume — but do NOT re-implement — feature 084's structured-logging contract, dashboards D8-D14, and Loki alert rules. Both tracks run on top of feature 071's kind harness and feature 072's journey scaffold. The CI gate is delivered by extending the existing `.github/workflows/e2e.yml` job (no new workflow file), which already runs `make e2e-test`, `make e2e-journeys`, `make e2e-chaos`, and `make e2e-perf` in sequence.

## Constitutional Anchors

This plan is bounded by the following Constitution articles. Each implementation step below cites the article it serves.

| Anchor | Citation | Implementation tie |
|---|---|---|
| **UPD-035 declared** | Constitution lines 502-516, audit-pass roster line 476 | The whole feature |
| **Rule 22 — Loki labels low-cardinality only** | Constitution rule 22 | UPD-034 owns the lint; T046 in Phase 11 only verifies the lint runs in CI |
| **Rule 24 — every BC has a dashboard** | Constitution rule 24 | All 21 dashboards ship as ConfigMaps in the umbrella chart (T011-T013) |
| **Rule 27 — dashboards as ConfigMaps with `grafana_dashboard: "1"`** | Constitution rule 27 | Already true on disk; T011 audits the label and the corresponding Prometheus rule label `prometheus-rule: "1"` |
| **Rule 28 — axe-core fails CI on AA violations** | Constitution rule 28 | J15 (T029) is the executable gate; the per-page allowlist file (T030) is the documented-exemption mechanism |
| **AD-22 — structured JSON logs only** | Constitution AD-22 | UPD-034 owns the contract; UPD-035 asserts on it via `assert_log_entry` (T021) |
| **AD-23 — Loki / Jaeger / Prometheus three separate backends bound by Grafana** | Constitution AD-23 | The three data-source ConfigMaps (T009) and the Loki → Jaeger derived-field link (T010) ARE this contract |
| **Rule 50 — 16 user journeys, 6 new BC suites, real-stack E2E** | Constitution rule 50 (and FR-519) | Eight new journeys (J10-J17) + nine extended journeys (J01-J09) totals 17, not 16 — see correction §6 below; six new BC suites verbatim (T034-T039) |
| **`platform-cli` extension pattern** | `apps/ops-cli/src/platform_cli/main.py:62-66` (`app.add_typer(install_app, name="install")` …) | T015 follows this pattern with `app.add_typer(observability_app, name="observability")` |
| **Mock LLM Provider 429 injection** | `apps/control-plane/src/platform/common/llm/mock_provider.py:62-258` (no current rate-limit knob) | T020 adds `set_rate_limit_error()` and the corresponding `generate()` short-circuit, gated by the `FEATURE_E2E_MODE` flag |

## Technical Context

| Item | Value |
|---|---|
| **Languages** | Python 3.12+ (control plane and CLI), TypeScript 5.x (frontend, only via Playwright assertions in J15), YAML (Helm chart + GitHub Actions). No Go in this feature. |
| **Primary Dependencies (existing)** | Helm 3.x with the umbrella chart's existing deps: `opentelemetry-collector` v0.108.1, `kube-prometheus-stack` v65.8.1 (Prometheus + Grafana + Alertmanager + node-exporter + kube-state-metrics — bundled), `jaeger` v3.4.1 (allInOne mode with BadgerDB), `loki` v6.16.0 (SingleBinary in `standard`, distributed in `enterprise`), `promtail` v6.16.6. CLI: `typer 0.12+`. E2E: `pytest 8.x`, `pytest-asyncio`, `pytest-html`, `pytest-xdist`, `pytest-timeout`, `httpx 0.27+`, `websockets`, `aiokafka 0.11+`, `asyncpg`, `playwright` (added in this feature for J15), `axe-playwright-python` or equivalent (added in this feature for J15). |
| **Primary Dependencies (NEW in 085)** | `playwright` ≥ 1.45 + `axe-playwright-python` ≥ 1.0.x for J15 (Track B Phase 8); `pytest-html` snapshot embedding (already in feature 071's `tests/e2e/pyproject.toml`); Grafana renderer plugin (server-side dashboard PNG render) — added via the umbrella chart's Grafana `image.tag` and `plugins:` values, NOT a separate sub-chart. |
| **Storage** | None. UPD-035 owns no PostgreSQL tables, no Redis keys, no Kafka topics. The umbrella chart's `pre-install-loki-bucket-job.yaml` (already present at `deploy/helm/observability/templates/pre-install-loki-bucket-job.yaml`) creates the `platform-loki-chunks` bucket via the platform's `minio-platform-credentials` secret; this is unchanged. |
| **Testing** | pytest 8.x for journey + BC suites + chaos; pytest-html for narrative reports; pytest-xdist for parallel journey execution (already wired in `tests/e2e/Makefile` with `E2E_JOURNEY_WORKERS=4` default); pytest-timeout for per-test deadlines; Playwright for J15 keyboard-only browser automation; Helm unittest for chart correctness gates (T013, T044). |
| **Target Platform** | kind (the everyday CI target — `tests/e2e/cluster/kind-config.yaml` is the canonical config), k3s (smoke target — verified in T058), one managed cluster (GKE/EKS/AKS — verified periodically per FR-514). |
| **Project Type** | Operations / testing / packaging. No application code is added to the control plane other than the Mock LLM Provider 429 injection knob (T020) and the new `observability` sub-app on the existing `platform-cli` (T015). |
| **Performance Goals** | Single-command install: ≤ 10 min cold, ≤ 3 min warm cache (SC-001). Journey suite parallel run with 4 workers: ≤ 30 min wall-clock for J01-J17 + the 6 BC suites + the 6 chaos scenarios on the kind cluster's `e2e` preset, matching the existing CI 45-minute timeout in `.github/workflows/e2e.yml:21`. |
| **Constraints** | Constitution rule 22 (Loki labels low-cardinality); constitution rule 27 (`grafana_dashboard: "1"` and `prometheus-rule: "1"` labels); constitution rule 28 (axe-core CI gate, zero AA tolerance); SC-005 ±15 % preset capacity envelope; FR-530 no-mocks-of-observability-backends (every journey assertion that names Loki / Prometheus / Jaeger MUST query the real backend, not a stub). |
| **Scale / Scope** | Track A: 1 umbrella chart, 5 sub-chart deps (already locked), 22 dashboards (already on disk; one extra over the FR-516 21 — see correction §1), 6 alert files (already on disk), 3 sizing presets (NEW), 1 E2E overlay (NEW), 1 NetworkPolicy template (NEW), 3 data-source ConfigMaps (NEW — currently provisioned implicitly via kube-prometheus-stack), 1 README (NEW), 1 CLI subcommand with 4 verbs. Track B: 8 new journey files, 9 extended journey files, 6 new BC suite directories, 6 new chaos scenario files, 5 new helper modules, 4 new readiness fixtures, 1 mock-LLM extension. |

## Constitution Check

> **GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.**

| Check | Verdict | Rationale |
|---|---|---|
| Brownfield rule — modifications respect existing BC boundaries | ✅ Pass | UPD-035 modifies only the umbrella chart at `deploy/helm/observability/` and the test harness at `tests/e2e/` and the CLI at `apps/ops-cli/src/platform_cli/`. No new BC is created; no existing BC's service.py is altered except the Mock LLM Provider's 429 knob (T020), which is a test-mode-only extension gated by `FEATURE_E2E_MODE`. |
| Rule 22 — Loki labels low-cardinality only | ✅ Pass (delegated) | UPD-034 owns the lint and the contract. UPD-035 asserts on Loki labels via `assert_log_entry` but does NOT define labels. |
| Rule 24 — every BC has a dashboard | ✅ Pass | The umbrella chart already ships 22 dashboards (one extra over the FR-516 21 — `trust-content-moderation.yaml` — see correction §1). UPD-035 packages, does not author. |
| Rule 27 — dashboards as ConfigMaps with `grafana_dashboard: "1"` | ✅ Pass (audited) | T011 verifies every dashboard ConfigMap carries the label. The chart's `_helpers.tpl` already provides `musematic-observability.dashboardLabels` macro. |
| Rule 28 — axe-core CI gate | ✅ Pass | J15 (T029) is the executable gate. T046 verifies the gate is wired into `.github/workflows/e2e.yml`. |
| Rule 41 — Vault failure does not bypass auth | ✅ N/A | Feature does not touch auth or Vault paths. |
| Rule 50 — 16 journeys + 6 new BC suites + real-stack | ⚠️ Variance flagged | Constitution says "16 journeys (9 existing + 7 new)" but UPD-035 spec ships **17** (J01-J09 extended + J10-J17 new = 9 + 8). The "+ 7" wording in rule 50 mirrors the FR-519 "Seven new" copy-edit slip; UPD-035 corrects to 8 to match FR-521 through FR-528 (one FR per journey). The variance is documented in spec §"Brownfield-input reconciliations §1" and inherits from the spec. |
| AD-22 — structured JSON logs | ✅ Pass (delegated) | UPD-034 owns. |
| AD-23 — three observability backends | ✅ Pass | The umbrella chart's existing sub-chart layout already enforces three backends. T009 packages the data-source provisioning. |
| Principle XVI — generic S3 storage, MinIO not in code | ✅ Pass | The chart's `pre-install-loki-bucket-job.yaml` uses `minio-platform-credentials` secret naming for compatibility but the bucket access is via S3 SDK (boto3-equivalent). UPD-035 does not change this. |

**Verdict: gate passes with one declared variance (rule 50 wording — eight new journeys, not seven). The variance is corrected in the spec and is the intended behaviour per FR-519's enumeration. No further constitutional action required.**

## Project Structure

### Documentation (this feature)

```text
specs/085-extended-e2e-journey/
├── plan.md                # this file
├── spec.md
├── planning-input.md
└── tasks.md               # produced by /speckit.tasks (next phase)
```

### Source Code (repository root) — files this feature creates or modifies

```text
deploy/helm/observability/
├── Chart.yaml                                # MODIFY (bump version, no new deps)
├── Chart.lock                                # COMMIT (already on disk)
├── values.yaml                               # MODIFY (add Grafana renderer plugin enable, NetworkPolicy toggle)
├── values-minimal.yaml                       # NEW (preset: dev/kind, ≤ 1 GB RAM total stack)
├── values-standard.yaml                      # NEW (preset: small production, HA Prometheus, single-binary Loki, renderer ENABLED)
├── values-enterprise.yaml                    # NEW (preset: Prometheus HA, distributed Loki, Grafana HA, renderer ENABLED)
├── values-e2e.yaml                           # NEW (preset: kind E2E, retention 1h, memory budget; renderer DISABLED to fit kind)
├── README.md                                 # NEW (operator install/upgrade/uninstall guide + preset capacity table)
├── charts/                                   # already on disk (sub-chart tarballs)
└── templates/
    ├── _helpers.tpl                          # MODIFY (add `musematic-observability.dataSourceLabels` macro)
    ├── namespace.yaml                        # already on disk
    ├── networkpolicy.yaml                    # NEW (deny-by-default + allow lists for cluster-internal traffic)
    ├── otel-collector-servicemonitor.yaml    # already on disk
    ├── pre-install-loki-bucket-job.yaml      # already on disk
    ├── jaeger-badger-pvc.yaml                # already on disk
    ├── grafana-datasources/
    │   ├── prometheus.yaml                   # NEW (datasource ConfigMap with Grafana sidecar label)
    │   ├── loki.yaml                         # NEW (datasource ConfigMap + derived-field links: trace_id → Jaeger, correlation_id → filtered Loki)
    │   └── jaeger.yaml                       # NEW (datasource ConfigMap)
    ├── dashboards/                           # already on disk (22 dashboards — see correction §1)
    └── alerts/                               # already on disk (6 alert files)

apps/ops-cli/src/platform_cli/
├── main.py                                   # MODIFY (register `observability_app` sub-typer at line ~66)
└── commands/
    └── observability.py                      # NEW (4 commands: install / upgrade / uninstall / status)

apps/control-plane/src/platform/common/llm/
└── mock_provider.py                          # MODIFY (add `set_rate_limit_error()` method + `generate()` 429 short-circuit, gated by FEATURE_E2E_MODE)

tests/e2e/
├── Makefile                                  # MODIFY (e2e-up installs observability chart; verify e2e-chaos directory exists)
├── pyproject.toml                            # MODIFY (add playwright + axe-playwright-python optional dep)
├── cluster/
│   └── install.sh                            # MODIFY (call helm install for observability chart with values-e2e.yaml before platform install)
├── journeys/
│   ├── conftest.py                           # MODIFY (add loki_client / prom_client / jaeger_client / grafana_client / axe_runner fixtures + observability stack readiness gate)
│   ├── helpers/
│   │   ├── __init__.py                       # already on disk
│   │   ├── agents.py                         # already on disk
│   │   ├── api_waits.py                      # already on disk
│   │   ├── executions.py                     # already on disk
│   │   ├── governance.py                     # already on disk
│   │   ├── narrative.py                      # MODIFY (embed dashboard snapshot links in HTML report)
│   │   ├── oauth.py                          # already on disk
│   │   ├── websockets.py                     # already on disk
│   │   ├── assert_log_entry.py               # NEW
│   │   ├── assert_metric.py                  # NEW
│   │   ├── assert_trace.py                   # NEW
│   │   ├── assert_dashboard_snapshot.py      # NEW
│   │   ├── axe_runner.py                     # NEW
│   │   └── observability_readiness.py        # NEW (Loki + Prometheus + Grafana + Jaeger health-endpoint gate)
│   ├── plugins/                              # already on disk (narrative_report)
│   ├── test_j01_admin_bootstrap.py           # MODIFY (FR-520 extensions: DLP rules + budget + model catalog seed + observability check)
│   ├── test_j02_creator_to_publication.py    # MODIFY (FR-520: PIA trigger + model binding validation)
│   ├── test_j03_consumer_discovery_execution.py  # MODIFY (FR-520: cost attribution + content moderation + Loki log)
│   ├── test_j04_workspace_goal_collaboration.py  # MODIFY (FR-520: tag-based policy expression + Goal Lifecycle dashboard)
│   ├── test_j05_trust_governance_pipeline.py # NEW (J05 — currently missing on disk; spec §"Brownfield-input reconciliations §2")
│   ├── test_j06_operator_incident_response.py # NEW (J06 — missing on disk)
│   ├── test_j07_evaluator_improvement_loop.py # NEW (J07 — missing on disk)
│   ├── test_j08_external_a2a_mcp.py          # NEW (J08 — missing on disk)
│   ├── test_j09_scientific_discovery.py      # NEW (J09 — missing on disk)
│   ├── test_j10_multi_channel_notifications.py # already on disk; RENAME or RENUMBER per feature 072 reconciliation (see correction §2)
│   ├── test_j10_privacy_officer.py           # NEW (J10 in canonical sequence)
│   ├── test_j11_security_officer.py          # NEW
│   ├── test_j12_finance_owner.py             # NEW
│   ├── test_j13_sre_multi_region.py          # NEW
│   ├── test_j14_model_steward.py             # NEW
│   ├── test_j15_accessibility_user.py        # NEW (Playwright + axe-core)
│   ├── test_j16_compliance_auditor.py        # NEW
│   └── test_j17_dashboard_consumer.py        # NEW
├── suites/
│   ├── cost_governance/                      # MODIFY (rename existing 3 tests to canonical FR-531 names; add `test_forecast.py`)
│   │   ├── test_attribution.py               # already on disk as `test_attribution_visible_during_run.py` — RENAME
│   │   ├── test_budget_enforcement.py        # already on disk as `test_hard_cap_blocks_then_override.py` — RENAME
│   │   ├── test_anomaly_detection.py         # already on disk as `test_anomaly_alert_routes_to_admin.py` — RENAME
│   │   └── test_forecast.py                  # NEW (4th test per FR-531)
│   ├── privacy_compliance/                   # NEW (5 tests: dsr_access, dsr_erasure_cascade, residency, dlp, pia)
│   ├── security_compliance/                  # NEW (5 tests: sbom, vuln_scan, rotation, jit, audit_chain)
│   ├── multi_region_ops/                     # NEW (3 tests: region_config, replication, maintenance)
│   ├── model_catalog/                        # NEW (3 tests: catalog_crud, fallback, model_card)
│   └── localization/                         # NEW (2 tests: user_preferences, locale_files)
└── chaos/                                    # NEW DIRECTORY (Makefile already conditions on existence)
    ├── __init__.py                           # NEW
    ├── test_loki_ingestion_outage.py         # NEW
    ├── test_prometheus_scrape_failure.py     # NEW
    ├── test_model_provider_total_outage.py   # NEW (uses Mock LLM Provider 429 knob from T020)
    ├── test_residency_misconfig.py           # NEW
    ├── test_budget_hard_cap_midexec.py       # NEW
    └── test_audit_chain_storage_failure.py   # NEW

.github/workflows/
└── e2e.yml                                   # MODIFY (no structural change — `make e2e-chaos` already in the workflow at line ~50; only adjust artifact retention if needed)
```

**Structure Decision**: Reuse the established layout. Track A's surface lives entirely under `deploy/helm/observability/`. Track B's surface lives entirely under `tests/e2e/`. CLI surface is one new file under `apps/ops-cli/src/platform_cli/commands/observability.py` plus one register-line in `main.py`. The Mock LLM Provider extension is one method addition (gated by `FEATURE_E2E_MODE`) — no new files. No new BC, no new database table, no new Kafka topic, no new REST prefix.

## Brownfield-Input Reconciliations

These are corrections from spec to plan. Each is an artifact-level discrepancy between the brownfield input and the on-disk codebase.

1. **Dashboard count: 22 on disk vs. 21 in FR-516 / brownfield input.** The umbrella chart's `templates/dashboards/` already contains 22 ConfigMaps. The 22nd is `trust-content-moderation.yaml`, which is the dashboard owned by feature 078 (content_safety_fairness — UPD-029). The brownfield input's 21-row enumeration omits it. **Resolution:** the chart ships 22 dashboards; UPD-035's success criteria SC-002 is updated to "all dashboards ship as ConfigMaps and load on first install" with the actual count being 22, not 21 — both texts (spec and FR-516) are correct counts of authored-by-roadmap dashboards but the on-disk chart includes a 22nd from feature 078. The plan adopts the **on-disk count**, not the brownfield count, and the chart's README enumerates 22.

2. **Existing-journey inventory: brownfield input cites J01-J09; on-disk has J01-J04 + a J10-notifications.** Feature 072's plan is the canonical authority for journey numbering; J05-J09 were planned but not yet implemented. UPD-035 completes them as part of the J01-J09 extension scope (Phase 9 / T031-T033), so that FR-520 ("9 existing journeys extended") describes a real on-disk surface after this feature lands. **Resolution:** UPD-035 takes ownership of authoring J05, J06, J07, J08, J09 from scratch (their FR-461 contracts are described in feature 072's spec) AND extending them per FR-520. The existing `test_j10_multi_channel_notifications.py` is the FR-520 "Notifications" extension target, not a separate journey; it is renamed to `test_j10_privacy_officer.py` (the feature-072 J10 slot) and the existing notifications work is folded into the FR-520 extensions of J01 (Administrator — notifications channel config) and the new J17 (Dashboard Consumer — notification correlation), per agreement with feature 072's authority. **Cross-feature coordination required**: this rename is a breaking change for any in-flight 072 PRs and must be sequenced after 072 lands.

3. **Sub-chart count: brownfield input cites 7 (Prometheus, Grafana, Jaeger, Loki, Promtail, Alertmanager, OTEL Collector); on-disk has 5.** The 5 sub-chart deps are: `kube-prometheus-stack` (which bundles Prometheus + Grafana + Alertmanager + node-exporter + kube-state-metrics — three of the brownfield's seven inside one chart), `jaeger`, `loki`, `promtail`, `opentelemetry-collector`. **Resolution:** the chart's actual topology is 5 sub-charts encapsulating 7 logical components; the README documents this clearly so operators don't expect to see 7 separate `dependencies:` lines.

4. **`tests/e2e/chaos/` directory does not exist on disk.** The `tests/e2e/Makefile` `e2e-chaos` target conditionally invokes pytest against the directory and silently skips if missing — i.e., the harness was authored anticipating chaos scenarios but feature 071 did NOT ship them. **Resolution:** UPD-035 creates the directory and the 6 scenarios (Phase 10 / T040-T045). No Makefile change is required.

5. **`tests/e2e/performance/` directory does not exist on disk either.** Same pattern as §4. **Out of scope for UPD-035** — performance tests are owned by feature 071's follow-up scope; UPD-035 does not author them. The Makefile's existing `e2e-perf` target stays unchanged.

6. **CLI command names: brownfield input cites `platform-cli observability install --preset standard`.** The on-disk CLI's `install` sub-app (`apps/ops-cli/src/platform_cli/commands/install.py`) does not have an `observability` sub-app; the convention is one sub-app per top-level domain (`install_app`, `diagnose_app`, `backup_app`, `upgrade_app`, `admin_app`). **Resolution:** UPD-035 adds a new `observability_app` (T015) with four sub-commands `install`, `upgrade`, `uninstall`, `status`. The brownfield input's `--preset standard` is implemented as a Typer option `--preset` accepting `minimal|standard|enterprise|e2e` and resolving to the corresponding `values-{preset}.yaml`.

7. **BC suite naming: cost_governance/ has 3 tests on disk with non-FR-531-canonical names.** Existing files: `test_anomaly_alert_routes_to_admin.py`, `test_attribution_visible_during_run.py`, `test_hard_cap_blocks_then_override.py`. FR-531-canonical names: `test_attribution.py`, `test_budget_enforcement.py`, `test_forecast.py`, `test_anomaly_detection.py`. **Resolution:** UPD-035 RENAMES the three on-disk files to their canonical names and ADDS the missing `test_forecast.py` (Phase 7 / T034 sub-tasks). The renames preserve git history via `git mv`.

8. **Mock LLM Provider 429 injection: brownfield input assumes it exists; on-disk it does not.** `apps/control-plane/src/platform/common/llm/mock_provider.py` is a Redis-backed queue for synthetic responses with no rate-limit-error injection. **Resolution:** UPD-035 adds an `async set_rate_limit_error(prompt_pattern, count)` method and a `generate()` short-circuit that raises a `RateLimitError` exception type the model_catalog FallbackService already handles. The change is gated by the `FEATURE_E2E_MODE` flag so production traffic is unaffected. Implementation in T020.

9. **Sizing-preset value files are missing.** The chart's `values.yaml` is a single 351-line file with all configuration; there are no `values-minimal.yaml`, `values-standard.yaml`, `values-enterprise.yaml`, or `values-e2e.yaml` overlays. **Resolution:** UPD-035 creates the four overlay files with documented capacity envelopes (T005-T008).

10. **NetworkPolicy template missing.** Brownfield input layout includes `templates/networkpolicy.yaml` but the on-disk chart does not have it. **Resolution:** UPD-035 creates the template (T014) implementing deny-by-default ingress with explicit allow rules for the platform namespaces (`platform-control`, `platform-execution`, `platform-simulation`, `platform-data`, `platform-ui`) per FR-513 isolation requirement.

11. **Grafana data-source ConfigMaps are not separate templates.** On-disk, data sources are configured implicitly inside the kube-prometheus-stack values block (Prometheus + Loki — Loki is added via a values override). Jaeger is not currently a configured Grafana data source. **Resolution:** UPD-035 extracts data-source provisioning into three separate ConfigMaps (`templates/grafana-datasources/prometheus.yaml`, `loki.yaml`, `jaeger.yaml`) so each has explicit derived-field configuration and the FR-515 contract is verifiable per data source. T009-T010 cover this.

12. **README.md missing.** The chart has no operator README. **Resolution:** UPD-035 authors `deploy/helm/observability/README.md` (T016) with install/upgrade/uninstall examples, preset capacity table, troubleshooting (most common: PVC pending in `minimal` preset, S3 bucket creation failure on first install, Grafana renderer plugin OOM in `minimal`).

## Phase 0 — Research and Design Decisions

### R1. Helm umbrella-chart preset patterns

The kube-prometheus-stack and Loki sub-charts each ship multiple deployment topologies via values: `prometheus.prometheusSpec.replicas`, `loki.deploymentMode` (SingleBinary | SimpleScalable | Distributed). UPD-035's three presets compose these:

| Preset | Prometheus | Grafana | Loki | Jaeger | OTEL Collector | Renderer plugin | Total RAM (target) |
|---|---|---|---|---|---|---|---|
| `minimal` | 1 replica, retention 7d, 2 GB PV | 1 replica, no renderer | SingleBinary, retention 24h, in-cluster filesystem (no S3) | allInOne, BadgerDB 1 GB | 1 replica | DISABLED | ≤ 1 GB |
| `standard` | HA 2 replicas, retention 30d, 20 GB PV | HA 2 replicas, renderer ENABLED | SingleBinary, retention 14d hot + S3 cold, 20 GB PV | allInOne, BadgerDB 5 GB (existing PVC) | 2 replicas (existing values.yaml) | ENABLED | ~ 4 GB |
| `enterprise` | HA 2 replicas + Thanos sidecars, S3 long-term | HA 2 replicas + Postgres backend, renderer ENABLED | Distributed (compactor + ingester + querier), S3 chunks, 14d hot + 90d cold | Production: collector+query split, Cassandra/Elasticsearch backend (operator-supplied — chart documents the swap) | 3+ replicas, autoscaling | ENABLED | ~ 16 GB |
| `e2e` | 1 replica, retention 1h, ephemeral memory only | 1 replica, no renderer | SingleBinary, retention 1h, ephemeral filesystem (no S3) | allInOne, memory storage | 1 replica | DISABLED | ≤ 1 GB |

**Decision**: Implement presets as **value-file overlays** (not as Helm sub-conditions or `--set` chains). Each preset file is committed to the repo, version-controlled with the chart, and selectable via `helm install … -f values-{preset}.yaml`. The CLI's `--preset` flag resolves to the file path internally (T015).

**Why**: Value files are reproducible (no shell-quoting bugs in `--set`), visible in source control (preset drift is a PR review item), and overrideable per tenant via `-f values-{preset}.yaml -f values-tenant.yaml` chaining.

### R2. Loki S3 bucket creation timing

The chart's existing `pre-install-loki-bucket-job.yaml` (Helm hook weight `-5`) creates the `platform-loki-chunks` bucket via the platform's `minio-platform-credentials` secret. This means **the platform Helm chart must be installed first** (or the secret pre-created) for the Loki bucket-creation hook to succeed.

**Decision**: The umbrella chart's README documents two install paths:
1. **Co-install path (production)**: `helm install platform …` first, which provisions the secret, then `helm install observability …` which provisions Loki and runs the bucket-creation hook.
2. **Stand-alone path (dev / kind)**: `helm install observability … --set loki.storage.type=filesystem` (the `minimal` and `e2e` presets default to filesystem, skipping the hook entirely).

The CLI's `observability install` subcommand checks for the secret and emits a clear error if it is missing in `standard` / `enterprise` presets.

### R3. Grafana data source provisioning vs. Grafana sidecar discovery

Two competing patterns:
1. **Inline values**: Set `grafana.additionalDataSources:` in `values.yaml` — the kube-prometheus-stack chart renders these into the Grafana provisioning ConfigMap.
2. **Separate ConfigMap with sidecar label**: Author a ConfigMap with the `grafana_datasource: "1"` label; the Grafana sidecar discovers and loads it.

The on-disk chart uses #1 implicitly. UPD-035 switches to #2 because:
- Each data source is a separate ConfigMap with explicit derived-field configuration (FR-515 — `trace_id` Loki field links to Jaeger, `correlation_id` Loki field links to filtered Loki query).
- Data-source PRs become small and reviewable in isolation.
- The sidecar discovery is the same mechanism already used by the dashboard ConfigMaps (rule 27), keeping the operational pattern consistent.

**Decision**: Implement #2 (T009-T010) and remove the equivalent inline values. The kube-prometheus-stack Grafana sub-chart's `sidecar.datasources.searchNamespace: ALL` (or scoped to `platform-observability`) MUST be enabled in `values.yaml` so the sidecar finds them.

### R4. Loki / Prometheus / Jaeger client selection for Track B helpers

Three options per backend:

| Backend | HTTP-only client | Typed SDK | Decision |
|---|---|---|---|
| Loki | `httpx` against `/loki/api/v1/query_range` | `python-logql` (3rd party, sparse maintenance) | **`httpx`**: small surface, no extra dep, full LogQL flexibility |
| Prometheus | `httpx` against `/api/v1/query` | `prometheus-api-client` 0.5.x | **`httpx`**: same reasoning + Prometheus's API is stable |
| Jaeger | `httpx` against `/api/traces/{trace_id}` | None mature | **`httpx`** |

**Decision**: All three helpers use `httpx.AsyncClient`. The fixtures wire each client to the in-cluster service URL (e.g., `http://loki-gateway.platform-observability.svc.cluster.local:3100` from a test running inside the cluster, or via a port-forward URL when running outside). The helpers expose async functions `assert_log_contains()`, `assert_metric_value()`, `assert_trace_exists()` matching the brownfield input signatures verbatim.

### R5. Grafana dashboard snapshot rendering

Grafana 10+ ships with the renderer plugin (or `grafana-image-renderer` deployment). It exposes `GET /render/d/{uid}/{name}?from={ts}&to={ts}&width=…&height=…` returning a PNG.

**Decision**: The `assert_dashboard_snapshot.py` helper hits the renderer endpoint via the in-cluster Grafana service, saves PNGs under `tests/e2e/reports/snapshots/{journey}/{step}-{dashboard_uid}.png`, and the narrative-report plugin (already in `tests/e2e/journeys/plugins/`) embeds them in the HTML report (T046).

The renderer is ENABLED in `standard` / `enterprise` and DISABLED in `minimal` / `e2e`. This means **journey tests requiring snapshots run on `standard` or richer**; the `e2e` preset (kind CI) runs the journey **without** snapshots — the helper degrades gracefully (it logs `INFO: snapshot skipped (renderer not enabled)` and proceeds; it does NOT fail the test).

### R6. axe-core / Playwright wiring for J15

Two integration paths:
1. **Playwright with `axe-playwright-python`**: A Python wrapper that injects axe-core into a Playwright page and parses violations. No JavaScript glue needed.
2. **`pytest-playwright` + manual axe injection**: Lower-level; more control but more boilerplate.

**Decision**: Path #1. Add `playwright>=1.45` and `axe-playwright-python>=1.0` to `tests/e2e/pyproject.toml` (T002). The `axe_runner.py` helper exposes `async run_axe_scan(page, rules=…)` returning a list of violations matching the brownfield-input signature. J15 fails on any AA violation that is not in the per-page allowlist file (T030 creates the allowlist scaffold at `tests/e2e/journeys/fixtures/axe_allowlist.json`).

### R7. Stack readiness gate timing

Brownfield input edge case: "Observability stack not yet started when journey runs: harness waits up to 60s for Grafana health endpoint before executing." This is the canonical gate in the `journeys/conftest.py` session-scoped fixture (T022).

**Decision**: A new `observability_stack_ready` session-scoped fixture polls Loki `/ready`, Prometheus `/-/ready`, Grafana `/api/health`, and Jaeger `/` (collector port 14269 admin endpoint) in parallel with `httpx`, with a 60s deadline (overridable via `MUSEMATIC_E2E_OBS_READY_TIMEOUT`). On timeout, the entire journey session aborts with a clear stack-not-ready diagnostic naming which endpoints did not return success. Every journey test depends on this fixture transitively via `journey_context`.

### R8. Mock LLM 429 injection — exception type and FallbackService integration

The model_catalog `FallbackService` (`apps/control-plane/src/platform/model_catalog/services/fallback_service.py`) handles primary-provider failure by walking the configured fallback chain. UPD-035's J14 + chaos test_model_provider_total_outage assert that 429 from primary triggers fallback to tier-2.

**Decision**: The Mock LLM Provider's `set_rate_limit_error(prompt_pattern, count)` method records that the next `count` calls matching `prompt_pattern` MUST raise `RateLimitError` (a new exception in `apps/control-plane/src/platform/common/llm/exceptions.py` if not already present). The FallbackService catches this exception type and walks the fallback chain. The chaos test sets `count` to a large number to simulate "all retries exhausted"; J14 sets `count=1` to verify a single fallback hop.

The mock provider's existing `e2e:mock_llm:calls` Redis counter tracks the failed-then-fallback sequence; assertions inspect this counter.

### R9. Numbering reconciliation with feature 072

Feature 072's spec is the canonical journey numbering authority. The on-disk J10-notifications file precedes UPD-035 and was produced by feature 077 (notifications). Two reconciliation options:

1. **Renumber the existing notifications journey** to a different slot (e.g., J18) and use J10 for Privacy Officer.
2. **Fold notifications coverage into J01 + J17 extensions** and rename the existing `test_j10_multi_channel_notifications.py` → `test_j10_privacy_officer.py`.

Option #2 is cleaner because notifications coverage is naturally cross-cutting (every governance journey uses notifications), so promoting it to its own journey is over-engineering. **Decision**: option #2 — fold notifications coverage into FR-520 extensions of J01 (Administrator: notifications channel config) and J17 (Dashboard Consumer: notification correlation). The plan's T031 (J01 extension) and T028 (J17 authoring) carry the notifications-coverage work.

### R10. CI workflow placement

`.github/workflows/e2e.yml` already runs `make e2e-chaos` (line ~50 per inventory). UPD-035 does NOT modify the workflow's structure; it only relies on the conditional that already detects `tests/e2e/chaos/` and runs pytest against it.

**Decision**: No new CI workflow file. UPD-035's only CI-touching change is to verify the artifact upload in `.github/workflows/e2e.yml:upload-artifact` step retains the new `tests/e2e/reports/snapshots/` directory; if it does not, T046 patches the workflow's path glob.

## Phase 1 — Design

### Track A — Observability Helm Bundle Architecture

```
                  ┌────────────────────────────────────────────┐
                  │   helm install observability …             │
                  │   (or `platform-cli observability install`)│
                  └─────────┬──────────────────────────────────┘
                            │
                   selects values-{preset}.yaml
                            │
            ┌───────────────┴───────────────────────────┐
            │       umbrella chart (Chart.yaml v0.2.0)   │
            │                                            │
            │   sub-chart deps (locked):                 │
            │     • kube-prometheus-stack v65.8.1        │ → Prometheus + Grafana + Alertmanager + ksm + node-exporter
            │     • jaeger v3.4.1                        │ → all-in-one (BadgerDB) | distributed
            │     • loki v6.16.0                         │ → SingleBinary | Distributed
            │     • promtail v6.16.6                     │ → DaemonSet collector
            │     • opentelemetry-collector v0.108.1     │ → metrics + traces fan-out
            │                                            │
            │   templates/                               │
            │     • namespace.yaml             (existing)│ → platform-observability
            │     • networkpolicy.yaml         (NEW)     │ → deny-by-default
            │     • pre-install-loki-bucket-job.yaml     │ → S3 bucket bootstrap
            │     • jaeger-badger-pvc.yaml     (existing)│ → Jaeger trace storage
            │     • otel-collector-servicemonitor.yaml   │ → Prom scrape OTEL
            │     • grafana-datasources/                 │
            │         - prometheus.yaml         (NEW)    │
            │         - loki.yaml              (NEW)     │ → derived fields trace_id → Jaeger, correlation_id → filtered Loki
            │         - jaeger.yaml            (NEW)     │
            │     • dashboards/                (existing)│ → 22 ConfigMaps with grafana_dashboard: "1"
            │     • alerts/                    (existing)│ → 6 PrometheusRule + 1 LokiRule files
            └────────────────────────────────────────────┘
                            │
                            ▼
                   namespace platform-observability
```

**Key macro changes** (`templates/_helpers.tpl`):

```yaml
{{/* musematic-observability.dataSourceLabels — used by NEW datasource ConfigMaps */}}
{{- define "musematic-observability.dataSourceLabels" -}}
{{ include "musematic-observability.labels" . }}
grafana_datasource: "1"
{{- end -}}
```

The `grafana_datasource: "1"` label is the Grafana sidecar's discovery selector (configured in `values.yaml` under `grafana.sidecar.datasources.label: grafana_datasource` / `grafana.sidecar.datasources.labelValue: "1"`).

### Track A — `platform-cli observability` Surface

```python
# apps/ops-cli/src/platform_cli/commands/observability.py (NEW)

import typer

observability_app = typer.Typer(help="Manage the observability stack")

@observability_app.command("install")
def install(
    preset: str = typer.Option("standard", "--preset", "-p",
        help="One of: minimal | standard | enterprise | e2e"),
    namespace: str = typer.Option("platform-observability", "--namespace", "-n"),
    values: list[Path] | None = typer.Option(None, "--values", "-f"),
    wait: bool = typer.Option(True, "--wait/--no-wait"),
) -> None:
    """Install or upgrade the observability stack via Helm."""
    # 1. Validate preset
    # 2. Compose helm command: chart path + values-{preset}.yaml + extra -f
    # 3. Pre-flight: if preset in {standard, enterprise}, verify minio-platform-credentials secret exists
    # 4. Invoke helm via subprocess (NOT shelling-out to a string — use shlex/list args)
    # 5. On --wait, also poll component health endpoints (Loki /ready, Prom /-/ready, Grafana /api/health, Jaeger /)
    # 6. Emit Rich-formatted table of component health on completion
    ...

@observability_app.command("upgrade")
def upgrade(...) -> None: ...

@observability_app.command("uninstall")
def uninstall(
    namespace: str = typer.Option("platform-observability", "--namespace"),
    purge_pvcs: bool = typer.Option(False, "--purge-pvcs",
        help="Also delete labelled PVCs (DESTRUCTIVE — confirms via prompt)"),
) -> None:
    """Uninstall the observability stack and report orphan resources."""
    # 1. helm uninstall
    # 2. List CRDs/PVCs/webhooks/ConfigMaps with label app.kubernetes.io/managed-by=Helm AND app.kubernetes.io/instance=observability
    # 3. If --purge-pvcs, delete; else, list and warn
    ...

@observability_app.command("status")
def status(
    namespace: str = typer.Option("platform-observability", "--namespace"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify component health endpoints; return non-zero if any fail."""
    # 1. Resolve service URLs via kubectl get svc / port-forward
    # 2. Probe each: Loki /ready, Prom /-/ready, Grafana /api/health, Jaeger /, OTEL :13133/
    # 3. Render Rich table or JSON; exit 1 on any failure
    ...
```

Registered in `main.py`:

```python
# apps/ops-cli/src/platform_cli/main.py:62-67 — modify
from platform_cli.commands import observability  # NEW import

app.add_typer(install_app,        name="install")
app.add_typer(diagnose_app,       name="diagnose")
app.add_typer(backup_app,         name="backup")
app.add_typer(upgrade_app,        name="upgrade")
app.add_typer(admin_app,          name="admin")
app.add_typer(observability.observability_app, name="observability")  # NEW
```

### Track B — Helper Module Signatures

```python
# tests/e2e/journeys/helpers/assert_log_entry.py
async def assert_log_contains(
    loki_client: httpx.AsyncClient,           # injected via conftest fixture
    labels: dict[str, str],                    # e.g., {"service": "control-plane", "level": "error"}
    substring: str,                            # required substring inside the log line
    within_seconds: int = 30,                  # poll deadline
    poll_interval: float = 1.0,
) -> dict:                                     # returns the matched log entry as Loki sees it
    """
    Poll Loki's /loki/api/v1/query_range until a log entry matching `labels` and
    containing `substring` is found, or `within_seconds` elapses.

    Loki reachability is verified BEFORE the first poll — if /ready returns non-200,
    raise a clear AssertionError naming the Loki URL and the response.
    """
```

```python
# tests/e2e/journeys/helpers/assert_metric.py
async def assert_metric_value(
    prom_client: httpx.AsyncClient,
    query: str,                                 # PromQL query
    expected: float,
    tolerance: float = 0.01,
    within_seconds: int = 15,
    poll_interval: float = 1.0,
) -> float:                                     # returns the actual value
    """
    Poll Prometheus's /api/v1/query until the result matches `expected` within `tolerance`,
    or `within_seconds` elapses. Raises with diagnostics on timeout.
    """
```

```python
# tests/e2e/journeys/helpers/assert_trace.py
async def assert_trace_exists(
    jaeger_client: httpx.AsyncClient,
    trace_id: str,
    expected_services: list[str],               # e.g., ["control-plane", "reasoning-engine", "sandbox-manager"]
    expected_operations: list[str] | None = None,
    within_seconds: int = 30,
) -> dict:                                      # returns the trace as Jaeger reports it
    """
    Fetch the trace by ID, verify it includes all expected services, and (if provided)
    that each expected operation appears at least once. Raise with diagnostics on miss.
    """
```

```python
# tests/e2e/journeys/helpers/assert_dashboard_snapshot.py
async def take_dashboard_snapshot(
    grafana_client: httpx.AsyncClient,
    dashboard_uid: str,
    time_range: str = "now-1h",
    width: int = 1920, height: int = 1080,
    output_dir: Path = Path("reports/snapshots"),
    journey_id: str = "",
    step: str = "",
) -> Path | None:                               # None if renderer is disabled (graceful degrade)
    """
    Render the dashboard via Grafana renderer plugin; save PNG; return path.
    On HTTP 404 from the renderer endpoint, return None (renderer not enabled in this preset).
    """
```

```python
# tests/e2e/journeys/helpers/axe_runner.py
async def run_axe_scan(
    page: "playwright.async_api.Page",
    allowlist_path: Path = Path("tests/e2e/journeys/fixtures/axe_allowlist.json"),
    impact: str = "moderate",                   # axe impact level: minor | moderate | serious | critical
) -> list[dict]:                                # returns AA violations NOT in allowlist
    """
    Inject axe-core into the page (via axe-playwright-python), run the AA ruleset,
    filter against the per-page allowlist, return remaining violations.
    Caller is responsible for failing the test if the list is non-empty.
    """
```

### Track B — `journeys/conftest.py` New Fixtures

```python
# additions to tests/e2e/journeys/conftest.py

@pytest.fixture(scope="session")
async def observability_stack_ready() -> None:
    """Block journey session until Loki/Prom/Grafana/Jaeger are all ready."""
    deadline = time.monotonic() + int(os.getenv("MUSEMATIC_E2E_OBS_READY_TIMEOUT", "60"))
    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            results = await asyncio.gather(
                _probe(client, _loki_url() + "/ready"),
                _probe(client, _prom_url() + "/-/ready"),
                _probe(client, _grafana_url() + "/api/health"),
                _probe(client, _jaeger_url() + "/"),
                return_exceptions=True,
            )
            if all(r is True for r in results): return
            await asyncio.sleep(2)
    raise RuntimeError(f"observability stack not ready within budget: {results}")

@pytest.fixture
async def loki_client(observability_stack_ready) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=_loki_url(), timeout=10.0) as c:
        yield c

@pytest.fixture
async def prom_client(observability_stack_ready) -> AsyncIterator[httpx.AsyncClient]: ...

@pytest.fixture
async def jaeger_client(observability_stack_ready) -> AsyncIterator[httpx.AsyncClient]: ...

@pytest.fixture
async def grafana_client(observability_stack_ready, admin_client) -> AsyncIterator[httpx.AsyncClient]: ...

@pytest.fixture
async def axe_runner(): ...   # Playwright + axe-playwright-python harness
```

### Track B — Journey Test Skeleton

Every J10-J17 file follows the same skeleton (chosen so the per-test scaffolding is consistent and the FR-mandated assertion-point counts are checkable):

```python
# tests/e2e/journeys/test_jXX_<persona>.py
import pytest
from .helpers.assert_log_entry import assert_log_contains
from .helpers.assert_metric import assert_metric_value
from .helpers.assert_trace import assert_trace_exists
from .helpers.assert_dashboard_snapshot import take_dashboard_snapshot
# …

pytestmark = [
    pytest.mark.journey,
    pytest.mark.jXX_<persona>,                   # filtering: pytest -m jXX_<persona>
]

@pytest.mark.asyncio
async def test_jXX_<persona>_main_flow(
    journey_context,
    admin_client, <persona>_client, …,
    loki_client, prom_client, jaeger_client, grafana_client,
):
    # PHASE 1 — setup (seeded fixtures + journey-scoped resources)
    # PHASE 2 — execute the canonical persona flow (8-12 steps)
    # PHASE 3 — observability assertions:
    #    — assert_log_contains(...) per persona's log expectations
    #    — assert_metric_value(...) per persona's metric expectations
    #    — assert_trace_exists(...) per persona's trace expectations
    #    — take_dashboard_snapshot(...) at key moments → narrative report
    # PHASE 4 — audit chain integrity verify (where applicable: J10, J11, J16)
    # PHASE 5 — cleanup (handled by journey_context teardown)
    assert <count> >= <FR-mandated minimum>, "assertion-point shortfall"
```

The pytest marker `jXX_<persona>` mirrors the existing pattern at `tests/e2e/Makefile:e2e-j01` … `e2e-j09`.

## Phase 2 — Implementation Order

| Phase | Goal | Tasks (T-numbers indicative; final list in tasks.md) | Wave | Parallelizable |
|---|---|---|---|---|
| **0. Setup** | Sub-chart audit + dependency pinning verification | T001-T004 | W12A.1 | yes |
| **1. Track A foundational** | Sizing presets + NetworkPolicy + datasources + helpers macro | T005-T014 | W12A.1 | yes |
| **2. Track A CLI + README** | `platform-cli observability` + chart README | T015-T016 | W12A.2 | yes (with #1) |
| **3. Track A E2E overlay + Makefile** | `values-e2e.yaml` + Makefile change + cluster/install.sh | T017-T019 | W12A.3 | sequential after #1 |
| **4. Track B foundational** | Mock LLM 429 + readiness fixture + helper modules | T020-T026 | W12B.1 | sequential within phase |
| **5. Track B BC suites** | 6 new BC suites (T027-T039) | T027-T039 | W12B.2 | yes — six independent suites |
| **6. Track B journey extensions (J01-J09)** | Author J05-J09 + extend J01-J09 per FR-520 | T031-T033 (sub-tasks per journey) | W12B.3 | yes — nine independent journeys |
| **7. Track B new journeys (J10-J17)** | Eight new journeys | T040-T047 (one per journey) | W12B.4 | yes — eight independent journeys |
| **8. Track B chaos** | Six new chaos scenarios | T048-T053 | W12B.5 | yes — six independent scenarios |
| **9. Joint validation** | Full E2E run + flake check (3 consecutive runs) + k3s smoke + reports | T054-T060 | W12C | sequential |
| **10. Polish + docs** | Helm unittest + chart README polish + CI artifact verification + CLAUDE.md update | T061-T068 | W12D | yes |

### Wave layout

UPD-035 lands in **Wave 12** (the audit-pass capstone), broken into four sub-waves:

- **Wave 12A — Helm bundle (Track A)**: T001-T019; ~3 dev-days; dependency on UPD-034 dashboards being on disk (already satisfied — 22 dashboards present).
- **Wave 12B — Test extensions (Track B)**: T020-T053; ~8.5 dev-days; dependencies on UPD-023 through UPD-033 + UPD-034 ALL having landed (audit-pass capstone — by definition runs last).
- **Wave 12C — Joint validation**: T054-T060; ~1 dev-day; both tracks must be merged.
- **Wave 12D — Polish**: T061-T068; ~0.5 dev-days; can overlap with Wave 12C.

**Total: ~13 dev-days.** With two devs in parallel (one per track), wall-clock is **~6 days**, plus the audit-pass-completion gate.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `helm install` for the umbrella chart times out on kind in `e2e` preset (sub-charts pull large images) | Medium | High — entire test pyramid blocks on this | T017's `values-e2e.yaml` uses upstream-published images on Docker Hub or quay; the kind config's image-load step (T019) pre-loads the most critical (Loki, Prometheus, Grafana, Jaeger) so install does not pull. |
| Grafana renderer plugin OOMs on `minimal` / `e2e` presets | High | Low (snapshots disabled gracefully) | T011's `values-minimal.yaml` and T017's `values-e2e.yaml` both DISABLE the renderer; the `assert_dashboard_snapshot.py` helper degrades gracefully (returns None, logs a notice). |
| Mock LLM Provider 429 injection breaks production traffic | Low | High | T020 gates the new `set_rate_limit_error()` method behind the `FEATURE_E2E_MODE` flag — production deployments do not have this flag set. The lint job in CI (existing rule from feature 071) verifies no test-mode endpoints are reachable when the flag is unset. |
| Journey numbering collision with feature 072 in-flight PRs | Medium | Medium | The plan flags the J10-notifications rename in correction §2; sequencing requires UPD-035 to land after feature 072's branch is closed. The plan's T031 (J01 extension) and T028 (J17 authoring) absorb the notifications coverage to avoid losing test surface. |
| axe-core flakes from third-party widgets shipped in the frontend | Medium | Medium | T030 ships an allowlist file (`tests/e2e/journeys/fixtures/axe_allowlist.json`) with explicit per-page exemptions; each entry has a justification + tracking ID + expiry date (constitution rule 28's intent). |
| Loki ingestion lag in `e2e` preset (1-second poll vs. real cluster's sub-second) | Medium | Low | All `assert_log_contains()` polls have a documented `within_seconds=30` deadline by default; tests asserting on log presence MUST use ≥ 15-second deadlines per FR-535's 15-second arrival contract from feature 084. |
| The `grafana_datasource: "1"` discovery label conflicts with the kube-prometheus-stack chart's existing data-source provisioning | Low | Medium | T009-T010 verifies the inline values are removed in the same PR that adds the ConfigMap-based data sources; helm-unittest in T044 catches double-provisioning. |
| The `tests/e2e/chaos/` directory has not been created — Makefile silently skips | High (already true on disk) | Medium | T040 explicitly creates `tests/e2e/chaos/__init__.py` first so pytest discovery proceeds; the Makefile's existing conditional then runs the suite. |
| Cross-feature secret naming (`minio-platform-credentials`) drifts | Low | High | T044 adds a helm-unittest assertion that the `pre-install-loki-bucket-job.yaml` references the canonical secret name; if feature 048 (backup-restore) renames it, the test breaks loudly. |

## Open Questions

These do NOT block the plan but should be tracked:

- **Q1**: Should the Grafana renderer plugin be a separate sub-chart deployment, or is the inline plugin install (`grafana.plugins:` values list) sufficient? **Working assumption**: inline plugin install is sufficient for `standard`; `enterprise` may benefit from a dedicated `grafana-image-renderer` Deployment for HA — defer to operator judgement, document both paths in the README.
- **Q2**: Does feature 072's authority accept the J10-notifications → J10-privacy-officer rename, or should UPD-035 add a J18 slot for notifications and leave J10 coverage to its current notifications occupant? **Pending**: feature 072 owner sign-off; default is rename per correction §2.
- **Q3**: Should axe-core run as a separate "accessibility" pytest marker in CI (allowing it to be skipped on draft PRs to save runtime), or always run as part of J15? **Working assumption**: always run as part of J15; the cost is small (axe-core scan is ~5s per page) and the constitutional rule 28 gate is non-negotiable.
- **Q4**: Should the chaos scenarios run on every PR, nightly, or weekly? **Working assumption**: nightly + on `chaos:` label PRs (a label-gated CI pattern feature 046 already supports); never on every PR (chaos suite is the longest-running of all E2E surfaces).
- **Q5**: Is there a managed-cluster CI job for the umbrella chart's `standard` and `enterprise` presets? **Pending**: feature 046 owner sign-off on a periodic-trigger workflow.

## Cross-Feature Coordination

| Feature | What we need from them | Owner action | Blocking? |
|---|---|---|---|
| **084 (UPD-034)** | Loki/Promtail config, structured-logging contract, dashboards D8-D14, 5 Loki alert rules | Already on disk | No |
| **072 (initial 9 journeys)** | J05-J09 file authority + agreement on J10 rename | UPD-035 authors J05-J09 in correction §2; rename pending sign-off | Yes (Q2) |
| **071 (kind E2E infra)** | `chaos/` dir convention + Mock LLM Provider extension API | UPD-035 follows the existing convention; the 429 extension is additive | No |
| **045 (installer-operations CLI)** | Sub-app registration pattern | UPD-035 follows `app.add_typer()` pattern at `apps/ops-cli/src/platform_cli/main.py:62-66` | No |
| **046 (CI/CD pipeline)** | `make e2e-chaos` already in `.github/workflows/e2e.yml` | No action — UPD-035 just creates the directory the workflow already invokes | No |
| **047 (existing observability)** | 7 baseline dashboards as ConfigMaps | Already on disk + 14 from 084 + 1 from 078 = 22 (correction §1) | No |
| **074-083 (audit-pass BCs)** | All BCs implemented + their REST endpoints active | Per audit-pass wave layout — UPD-035 is the capstone, lands after | Yes (definitionally) |

## Phase Gate

**Plan ready for `/speckit.tasks` when**:
- ✅ Constitutional anchors enumerated and gate verdicts recorded
- ✅ Brownfield-input reconciliations enumerated (12 items)
- ✅ Research decisions R1-R10 documented
- ✅ Wave placement (12A/12B/12C/12D) confirmed
- ✅ Cross-feature coordination matrix populated
- ✅ Risk register populated with mitigations
- ✅ Open questions enumerated (none blocking)

The plan is ready. The next phase (`/speckit.tasks`) breaks the 10-phase implementation order above into ordered, dependency-annotated tasks (T001-T068, indicative).

## Complexity Tracking

> **Filled when Constitution Check has violations that must be justified.**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Rule 50 wording — "16 journeys (9 + 7)" vs. spec's "17 journeys (9 + 8)" | FR-521 through FR-528 = 8 distinct FRs = 8 journeys; the "+ 7" is a copy-edit slip in FR-519 + rule 50 | Reducing to 7 would drop one of the 8 FR-mandated personas, breaking FR-519's enumeration. The variance is in the constitution's wording, not the design — the design follows the 8 FRs. |
| 22 dashboards on disk vs. 21 in FR-516 | Dashboard `trust-content-moderation.yaml` is owned by feature 078 (UPD-029) and was added to the chart out-of-roster | Removing the 22nd dashboard would lose feature 078's BC-dashboard coverage (rule 24 violation). Adding it to FR-516's enumeration is a documentation update, not a design change. |
| Mock LLM 429 injection in control-plane code (test-only) | J14 + chaos scenario `test_model_provider_total_outage.py` need a deterministic 429 trigger; production paths cannot have such a knob | Mocking the LLM provider at the HTTP layer (e.g., httpx mock) would not exercise the FallbackService's exception-handling path; the test would pass without verifying the real fallback chain. The `FEATURE_E2E_MODE`-gated extension is the minimal-surface alternative. |
