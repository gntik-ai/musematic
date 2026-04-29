# Tasks: UPD-035 — Extended E2E Journey Tests and Observability Helm Bundle

**Feature**: 085-extended-e2e-journey
**Branch**: `085-extended-e2e-journey`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

User stories (from spec.md):
- **US1 (P1)** — Operator installs the complete observability stack in one command (the Track A foundational MVP — every other journey depends on the umbrella chart being installable)
- **US2 (P1)** — SRE debugs an outage end-to-end via the observability stack (the canonical observability-ROI flow → J17 Dashboard Consumer)
- **US3 (P1)** — Privacy Officer completes a right-to-be-forgotten cycle end-to-end (J10 Privacy Officer)
- **US4 (P1)** — Security Officer completes a compliance cycle end-to-end (J11 Security Officer)
- **US5 (P1)** — Finance Owner completes a budget and chargeback cycle end-to-end (J12 Finance Owner)
- **US6 (P1)** — SRE completes a quarterly failover test end-to-end (J13 SRE Multi-Region)
- **US7 (P1)** — Model Steward completes a catalog and fallback cycle end-to-end (J14 Model Steward)
- **US8 (P1)** — Accessibility user completes a full workflow keyboard-only with zero AA violations (J15 Accessibility User)
- **US9 (P2)** — Compliance Auditor exports and verifies an audit trail (J16 Compliance Auditor)
- **US10 (P2)** — Maintainer adds and maintains BC-specific E2E suites for the new bounded contexts (6 new suites)
- **US11 (P3)** — Maintainer adds and runs chaos scenarios (6 new scenarios)

Independent-test discipline: every journey US (US2-US9) MUST be runnable in isolation against the kind cluster + umbrella chart preset; the BC suites (US10) MUST be discoverable by `pytest` independently; the chaos scenarios (US11) MUST inject failure → assert degraded behaviour → revert cleanly without side effects on other tests.

**Wave-12 sub-division** (per plan.md §"Wave layout"):
- W12A — Helm bundle (Track A): T001-T020
- W12B — Test extensions (Track B): T021-T079
- W12C — Joint validation: T080-T085
- W12D — Polish: T086-T091

---

## Phase 1: Setup

- [x] T001 Bump `deploy/helm/observability/Chart.yaml` `version:` to `0.2.0` (current: `0.1.0`); preserve all five `dependencies:` entries verbatim (`opentelemetry-collector v0.108.1`, `kube-prometheus-stack v65.8.1`, `jaeger v3.4.1`, `loki v6.16.0`, `promtail v6.16.6`); run `helm dep update` and commit any `Chart.lock` delta. Note: brownfield input claims 7 sub-charts; canonical is 5 (kube-prometheus-stack bundles Prometheus + Grafana + Alertmanager + node-exporter + kube-state-metrics) — see plan.md correction §3.
- [ ] T002 [P] Add `playwright>=1.45` and `axe-playwright-python>=1.0` to `tests/e2e/pyproject.toml` `[project.optional-dependencies] e2e =` extras; run `uv lock` (or pip-compile) and commit the lockfile update; verify Playwright browser bundle download via `playwright install chromium` succeeds in CI on `ubuntu-latest`.
- [x] T003 [P] Inventory the on-disk dashboard ConfigMaps (`deploy/helm/observability/templates/dashboards/`) — write the 22-row enumeration into `specs/085-extended-e2e-journey/contracts/dashboard-inventory.md` (NEW file): one row per dashboard ConfigMap with the dashboard `uid` and the owning feature; flag the 22nd dashboard `trust-content-moderation.yaml` (owned by feature 078, not in the brownfield-input 21-row enumeration — see plan.md correction §1). The README authored at T018 references this contract file.
- [x] T004 [P] Inventory the on-disk journey files (`tests/e2e/journeys/test_j*.py`) — write the actual-vs-FR-461-expected enumeration into `specs/085-extended-e2e-journey/contracts/journey-numbering.md` (NEW file): record that J01-J04 exist, J05-J09 are missing, J10-notifications exists and will be renamed per plan.md correction §2. The file is the cross-feature coordination artifact for the J10-notifications → J10-privacy-officer rename; feature 072's owner sign-off is recorded here.

---

## Phase 2: Foundational Track A — Helm Bundle (blocks US1 + US2 + every journey that needs the chart)

### Sizing-preset value files

- [x] T005 [P] [W12A] Create `deploy/helm/observability/values-minimal.yaml` (preset for kind / dev): Prometheus 1 replica + retention 7d + 2 GB PV; Grafana 1 replica + renderer plugin **DISABLED** (`grafana.plugins: []`); Loki SingleBinary + retention 24h + filesystem backend (`loki.storage.type=filesystem`, NOT S3 — skips the pre-install bucket-creation Job entirely per plan.md research R2); Jaeger allInOne + BadgerDB 1 GB; OTEL Collector 1 replica; total RAM target ≤ 1 GB. Document the capacity envelope at the file head as the canonical YAML anchor.
- [x] T006 [P] [W12A] Create `deploy/helm/observability/values-standard.yaml` (preset for small production): Prometheus HA 2 replicas + retention 30d + 20 GB PV; Grafana HA 2 replicas + renderer plugin **ENABLED** (`grafana.plugins: ["grafana-image-renderer"]`) per plan.md research R5; Loki SingleBinary + retention 14d hot + S3 cold (90d); Jaeger allInOne + BadgerDB 5 GB (matches existing `templates/jaeger-badger-pvc.yaml`); OTEL Collector 2 replicas; total RAM target ~ 4 GB. Documented capacity envelope: 1M metric series, 100 logs/s, 1k traces/s.
- [x] T007 [P] [W12A] Create `deploy/helm/observability/values-enterprise.yaml` (preset for HA production): Prometheus HA 2 replicas + Thanos sidecars (S3 long-term storage) per plan.md research R1; Grafana HA 2 replicas + Postgres backend + renderer plugin ENABLED; Loki **Distributed** mode (`loki.deploymentMode=Distributed` — compactor + ingester + querier separate Deployments), S3 chunks, retention 14d hot + 90d cold; Jaeger collector+query split (operator-supplied Cassandra/Elasticsearch — chart documents the swap); OTEL Collector 3+ replicas + autoscaling; total RAM target ~ 16 GB. Documented capacity envelope: 10M metric series, 10k logs/s, 100k traces/s.
- [x] T008 [P] [W12A] Create `deploy/helm/observability/values-e2e.yaml` (kind-cluster overlay used by `make e2e-up`): Prometheus 1 replica + retention 1h + ephemeral memory storage (no PV); Grafana 1 replica + renderer plugin DISABLED; Loki SingleBinary + retention 1h + filesystem backend (no S3); Jaeger allInOne + memory storage (`jaeger.storage.type=memory`, NOT BadgerDB) — overrides `templates/jaeger-badger-pvc.yaml` to skip; Promtail 128Mi limit; OTEL Collector 1 replica with reduced batch size; total RAM target ≤ 1 GB on a 16 GB kind laptop. Documented purpose: this file is consumed ONLY by the kind / E2E path, NEVER deployed to production clusters.

### Chart templates (NEW)

- [x] T009 [W12A] Create `deploy/helm/observability/templates/networkpolicy.yaml` per plan.md correction §10: deny-by-default ingress to the `platform-observability` namespace, with explicit `from:` allow rules for: (a) the same namespace (intra-stack traffic — Promtail → Loki, OTEL → Jaeger / Prometheus / Loki); (b) the platform namespaces `platform-control`, `platform-execution`, `platform-simulation`, `platform-data`, `platform-ui` (allowed to scrape `/metrics` and POST traces / logs); (c) ingress controller (allowed to reach Grafana on port 3000). Egress: unrestricted within the cluster, restricted to S3 endpoint outside the cluster. Conditioned on `networkPolicy.enabled` Helm value (default `true` in `standard` / `enterprise`, `false` in `minimal` / `e2e`).
- [x] T010 [W12A] Add the `musematic-observability.dataSourceLabels` macro to `deploy/helm/observability/templates/_helpers.tpl` per plan.md design Track A: returns the standard labels PLUS `grafana_datasource: "1"` (the Grafana sidecar discovery selector). Existing `musematic-observability.dashboardLabels` and `musematic-observability.ruleLabels` macros stay unchanged.
- [x] T011 [P] [W12A] Create `deploy/helm/observability/templates/grafana-datasources/prometheus.yaml`: ConfigMap with `musematic-observability.dataSourceLabels` (T010) carrying the YAML datasource definition (`name: Prometheus`, `type: prometheus`, `url: http://kube-prometheus-stack-prometheus.platform-observability.svc.cluster.local:9090`, `isDefault: true`, `access: proxy`). The Grafana sidecar's `searchNamespace: ALL` (or scoped to `platform-observability`) discovers and loads it.
- [x] T012 [P] [W12A] Create `deploy/helm/observability/templates/grafana-datasources/loki.yaml`: ConfigMap with the Loki datasource (`name: Loki`, `type: loki`, `url: http://loki-gateway.platform-observability.svc.cluster.local:3100`, `isDefault: false`) AND the FR-515 / SC-003 derived-field configuration so that any log entry whose JSON payload contains `trace_id` renders as a clickable link via `datasourceUid: jaeger` (opening the matching Jaeger trace) AND any log entry whose JSON payload contains `correlation_id` renders as a Loki-internal link (filtered Loki query for the same correlation_id). The derived-fields list is documented inline as the canonical FR-515 contract.
- [x] T013 [P] [W12A] Create `deploy/helm/observability/templates/grafana-datasources/jaeger.yaml`: ConfigMap with the Jaeger datasource (`name: Jaeger`, `type: jaeger`, `url: http://musematic-observability-jaeger-query.platform-observability.svc.cluster.local:16686`, `isDefault: false`, `uid: jaeger`). The `uid: jaeger` is referenced by T012's derived-field `datasourceUid` — the two MUST match.
- [x] T014 [W12A] Modify `deploy/helm/observability/values.yaml`: REMOVE the inline `kube-prometheus-stack.grafana.additionalDataSources:` block (replaced by T011-T013 ConfigMaps); ENABLE the Grafana sidecar's data-source discovery via `grafana.sidecar.datasources.enabled: true` and `grafana.sidecar.datasources.label: grafana_datasource` and `grafana.sidecar.datasources.labelValue: "1"` per plan.md research R3. Verify on local kind that exactly one datasource per backend appears in Grafana's `/api/datasources` list (no duplicates from inline-vs-ConfigMap collision).

### `platform-cli observability` sub-app

- [x] T015 [W12A] Create `apps/ops-cli/src/platform_cli/commands/observability.py` per plan.md design Track A: a Typer app `observability_app = typer.Typer(help="Manage the observability stack")` with placeholder docstrings for the four sub-commands (filled in T016-T017). Add the import line `from platform_cli.commands import observability` to `apps/ops-cli/src/platform_cli/main.py:6` (existing imports block) and the registration line `app.add_typer(observability.observability_app, name="observability")` to `apps/ops-cli/src/platform_cli/main.py:67` (after the existing `admin_app` registration, preserving the existing pattern from `:62-66`).
- [x] T016 [W12A] Implement `observability install` and `observability upgrade` Typer commands in `apps/ops-cli/src/platform_cli/commands/observability.py`: `--preset {minimal|standard|enterprise|e2e}` resolves to the corresponding `values-{preset}.yaml` path under `deploy/helm/observability/`; `--namespace` defaults to `platform-observability`; `--values` accepts additional `-f` overlay paths chained AFTER the preset values; `--wait` enables `helm --wait` and follows up with parallel health-endpoint probes (Loki `/ready`, Prom `/-/ready`, Grafana `/api/health`, Jaeger collector port 14269, OTEL `:13133/`) per plan.md research R7. Pre-flight: if preset is `standard` or `enterprise`, verify the `minio-platform-credentials` secret exists in the target namespace (per plan.md research R2) — emit a clear actionable error if missing. Subprocess invocations use `shlex.split` / list args (NEVER string concatenation) for the SC-019 security note. Rich-formatted output: emit a per-component health table on completion with ✓ / ✗ glyphs.
- [x] T017 [W12A] Implement `observability uninstall` and `observability status` commands in the same file: `uninstall --purge-pvcs` lists all PVCs / CRDs / webhooks / ConfigMaps with label `app.kubernetes.io/instance=observability` AND `app.kubernetes.io/managed-by=Helm` (the constitutional Helm-owned discovery selectors); without `--purge-pvcs` it lists them as warnings (DESTRUCTIVE); with the flag and an interactive confirmation prompt (Typer `typer.confirm`), it deletes them; `status` runs the same parallel health-endpoint probes as T016's `--wait` follow-up and emits a Rich table or a JSON object (`--json` flag — matches the existing CLI's `--json` global option pattern at `main.py:31-59`). Exit code is `1` if any health probe fails, `0` otherwise — wired to CI for the `make e2e-up` post-step verification.

### E2E provisioning + Makefile

- [x] T018 [W12A] Author `deploy/helm/observability/README.md` per plan.md correction §12: include (a) one-command install invocation per preset; (b) the per-preset capacity envelope table from research R1; (c) install-time S3 bucket creation rationale (research R2) — both co-install and stand-alone paths; (d) Grafana data-source provisioning + derived-field link verification steps; (e) uninstall semantics + the orphan-resource enumeration the `uninstall` CLI command performs; (f) troubleshooting (PVC pending in `minimal`, S3 bucket creation failure, renderer plugin OOM in `minimal`); (g) cross-link to feature 084's Loki-label lint rule (constitution rule 22 enforcement). Reference the dashboard-inventory contract (T003) and the journey-numbering contract (T004) inline.
- [x] T019 [W12A] Modify `tests/e2e/cluster/install.sh` (per the existing 19.8 KB script) to call `helm install observability ./deploy/helm/observability/ -n platform-observability --create-namespace -f ./deploy/helm/observability/values-e2e.yaml --wait` BEFORE the existing `helm install platform …` step; verify the chart's components are healthy (re-uses the same probe loop the CLI's `status` subcommand will define in T017 — extract the probe logic into a shared bash function in the same file); abort the install on observability-stack failure with a clear diagnostic so the rest of the e2e setup does not silently continue against a half-broken stack.
- [ ] T020 [W12A] Modify `tests/e2e/Makefile` per plan.md design: the existing `e2e-up` target (currently calls `cluster/install.sh`) requires no change other than verifying that the script's modification at T019 took effect (smoke-test the target end-to-end); the existing `e2e-chaos` target's conditional check on `tests/e2e/chaos/` directory presence is the integration point for Phase 14 (T072+); the existing `e2e-journeys` target's `pytest -n $(E2E_JOURNEY_WORKERS)` already runs in parallel — no change. Verify the existing `Makefile` env vars at lines 1-15 are unchanged.

---

## Phase 3: Foundational Track B — Test Harness (blocks every journey US — US2 through US9 — and US10 BC suites and US11 chaos)

### Mock LLM Provider 429 injection

- [x] T021 [W12B] Modify `apps/control-plane/src/platform/common/llm/mock_provider.py` per plan.md research R8: add `async def set_rate_limit_error(self, prompt_pattern: str, count: int = 1) -> None` method that records via Redis key `e2e:mock_llm:rate_limit:{prompt_pattern}` the number of remaining 429-injected calls; modify `async def generate(...)` so that BEFORE consuming from the queue, if the prompt matches a configured `prompt_pattern` and the counter is > 0, decrement the counter and raise `RateLimitError` (a new exception class in `apps/control-plane/src/platform/common/llm/exceptions.py` if not already present — added in the same task); gate the entire injection-check block behind `os.getenv("FEATURE_E2E_MODE") == "true"` so production traffic never hits this path. Add unit test `apps/control-plane/tests/unit/common/llm/test_mock_provider_rate_limit.py` verifying: (a) injected pattern raises after one call when count=1; (b) counter decrements to zero and subsequent calls return normal responses; (c) injection is invisible (raises `KeyError` at injection-time) when `FEATURE_E2E_MODE` is unset.
- [x] T022 [W12B] Verify `apps/control-plane/src/platform/model_catalog/services/fallback_service.py` catches `RateLimitError` (the new exception type from T021) and walks the configured fallback chain. If the existing FallbackService catches a different exception type (e.g., a generic provider error), update it additively to ALSO catch `RateLimitError` — preserve the existing behaviour for other exception types. Add unit test `apps/control-plane/tests/unit/model_catalog/test_fallback_on_rate_limit.py` verifying the FallbackService walks from primary → tier-2 → tier-3 when the Mock LLM Provider injects rate-limit errors at each tier in sequence.

### Observability assertion helpers (5 NEW modules)

- [x] T023 [P] [W12B] Create `tests/e2e/journeys/helpers/observability_readiness.py` per plan.md research R7: `async def wait_for_observability_stack_ready(timeout_seconds: int = 60) -> None` that probes Loki `/ready`, Prometheus `/-/ready`, Grafana `/api/health`, Jaeger collector `:14269/`, and OTEL Collector `:13133/` in parallel with `httpx.AsyncClient`; on success returns; on timeout raises `RuntimeError` naming each endpoint and its last-seen status. The 60s deadline is overridable via env var `MUSEMATIC_E2E_OBS_READY_TIMEOUT`. Implement `_loki_url()`, `_prom_url()`, `_grafana_url()`, `_jaeger_url()`, `_otel_url()` helpers reading from env vars with sensible kind-cluster defaults (port-forwarded URLs).
- [x] T024 [P] [W12B] Create `tests/e2e/journeys/helpers/assert_log_entry.py` per plan.md design Track B: `async def assert_log_contains(loki_client, labels: dict[str, str], substring: str, within_seconds: int = 30, poll_interval: float = 1.0) -> dict` — uses `httpx` (NOT a typed Loki SDK per research R4) to query `/loki/api/v1/query_range` with the constructed LogQL selector built from `labels`; polls until match or deadline; on match returns the matched log entry as Loki sees it; on timeout raises `AssertionError` naming the labels, substring, and the most-recent log volume seen at those labels. **Reachability check**: BEFORE the first poll, GET Loki's `/ready` — if non-200, raise immediately with a clear "Loki at {url} not ready: {response}" message (the spec edge-case).
- [x] T025 [P] [W12B] Create `tests/e2e/journeys/helpers/assert_metric.py`: `async def assert_metric_value(prom_client, query: str, expected: float, tolerance: float = 0.01, within_seconds: int = 15, poll_interval: float = 1.0) -> float` — queries Prometheus `/api/v1/query` with the PromQL `query`; polls until the result is within `tolerance` of `expected` or deadline; returns the actual value on success; raises with diagnostics (last-seen value, query, time range) on timeout.
- [x] T026 [P] [W12B] Create `tests/e2e/journeys/helpers/assert_trace.py`: `async def assert_trace_exists(jaeger_client, trace_id: str, expected_services: list[str], expected_operations: list[str] | None = None, within_seconds: int = 30) -> dict` — fetches `/api/traces/{trace_id}` from Jaeger; verifies the trace includes every expected service at least once and (if provided) every expected operation; on miss raises with the actual service / operation list seen.
- [x] T027 [P] [W12B] Create `tests/e2e/journeys/helpers/assert_dashboard_snapshot.py`: `async def take_dashboard_snapshot(grafana_client, dashboard_uid: str, time_range: str = "now-1h", width: int = 1920, height: int = 1080, output_dir: Path = Path("reports/snapshots"), journey_id: str = "", step: str = "") -> Path | None` — calls Grafana renderer plugin `/render/d/{uid}/?from=...&to=...&width=...&height=...&kiosk=tv`; saves PNG to `output_dir/{journey_id}/{step}-{dashboard_uid}.png`; on HTTP 404 (renderer not enabled — `minimal` / `e2e` presets per T005, T008) returns None and logs a graceful-degrade INFO line per plan.md research R5 (does NOT fail the test).
- [x] T028 [P] [W12B] Create `tests/e2e/journeys/helpers/axe_runner.py` per plan.md research R6: `async def run_axe_scan(page, allowlist_path: Path, impact: str = "moderate") -> list[dict]` — uses `axe-playwright-python` to inject axe-core into the Playwright `page` object, runs the WCAG 2.1 AA ruleset, loads the allowlist JSON file, filters the violations against the allowlist (any violation whose `rule_id` is in the allowlist for the current page URL is dropped), returns the remaining violations. The caller (J15) is responsible for failing the test if the returned list is non-empty. Logs each filtered-out violation as an INFO line with the allowlist's justification + tracking ID + expiry date so suppression is visible in test output.

### Conftest + narrative-report integration

- [x] T029 [W12B] Modify `tests/e2e/journeys/conftest.py` to add the new fixtures per plan.md design Track B: (a) `observability_stack_ready` (session-scoped, calls `wait_for_observability_stack_ready` from T023); (b) `loki_client`, `prom_client`, `jaeger_client`, `grafana_client` (function-scoped `httpx.AsyncClient` with appropriate `base_url`, depending on `observability_stack_ready`); (c) `axe_runner` (function-scoped Playwright + axe-core harness); (d) the existing `journey_context` fixture is updated to ALSO depend on `observability_stack_ready` so any journey test transitively gets the stack readiness gate. Verify the existing 38.8 KB conftest's other fixtures (admin_client, persona clients, ws_client, etc.) are untouched.
- [x] T030 [W12B] Modify `tests/e2e/journeys/helpers/narrative.py` (existing 2.1 KB module) to embed dashboard snapshot links + LogQL query links + Jaeger trace links in the per-journey HTML narrative report. New helper function `def add_snapshot_to_report(report, snapshot_path, label) -> None` callable from inside any journey test step. Verify the existing report-generation behaviour for non-observability journeys is preserved.
- [x] T031 [W12B] Create `tests/e2e/journeys/fixtures/axe_allowlist.json` per plan.md design Track B: a JSON file with a top-level `pages: {}` mapping URL patterns (regex) to lists of allowlisted violation rule IDs, each with `justification`, `tracking_id`, `expiry_date` (ISO 8601). Initialize empty (no entries — every J15 violation MUST either be fixed or explicitly allowlisted with justification). The file ships with the codebase; J15 (T060) is the consumer; the constitution rule 28 contract requires written justification + remediation tracking + expiry, all enforced by T028's logging.

---

## Phase 4: User Story 1 — Single-Command Observability Install (P1) 🎯 MVP — TRACK A CAPSTONE

**Story goal**: One Helm command (or one CLI subcommand) installs the complete observability stack on a fresh kind cluster within 10 min cold / 3 min warm; every component reports healthy; uninstall leaves the namespace deletable with zero orphan resources; three sizing presets each install on their target cluster size.

**Independent test**: On a fresh kind cluster, run `helm upgrade --install observability ./deploy/helm/observability/ --namespace platform-observability --create-namespace --values ./deploy/helm/observability/values-e2e.yaml` and wait for `--wait` to return; verify all 6 spec acceptance checks (component pods Running + Ready, Grafana health 200, all 3 datasources healthy, all 23 dashboards loaded, all alert rules loaded, status CLI returns ✓); run `helm uninstall observability -n platform-observability` and verify zero residual artifacts.

### Tests

- [x] T032 [P] [US1] [W12A] Add E2E test `tests/e2e/suites/observability/test_chart_install_e2e.py` (SC-001, SC-002, SC-003): on a fresh kind cluster, install the umbrella chart with `values-e2e.yaml`; assert (a) every named component pod is Running + Ready; (b) Grafana `/api/health` returns 200; (c) Grafana `/api/datasources` lists Prometheus + Loki + Jaeger and each `/api/datasources/{N}/health` returns success; (d) Grafana `/api/search?type=dash-db` returns all 23 dashboard UIDs from the dashboard-inventory contract (T003); (e) Prometheus `/api/v1/rules` lists every PrometheusRule from `templates/alerts/`; (f) Loki ruler's `/loki/api/v1/rules` lists every Loki alert from feature 084. Test runs against the actual chart, no mocks.
- [x] T033 [P] [US1] [W12A] Add E2E test `tests/e2e/suites/observability/test_chart_uninstall_clean.py` (SC-004): install then uninstall the umbrella chart; assert zero residual CRDs labelled by this chart, zero residual PVCs labelled by this chart, zero residual webhooks, zero residual ConfigMaps shipped by this chart. If any sub-chart's CRDs survive uninstall by sub-chart contract (kube-prometheus-stack ships several), the test asserts the chart's README documents the manual cleanup AND the documented cleanup commands actually leave zero orphans.
- [x] T034 [P] [US1] [W12A] Add E2E test `tests/e2e/suites/observability/test_chart_upgrade_idempotent.py`: install the umbrella chart; modify a non-destructive value (e.g., bump Loki retention from 1h → 2h via a values overlay); run `helm upgrade`; assert the upgrade applies cleanly with no data loss for in-tier (hot) data and the new value is reflected in the running components.
- [x] T035 [P] [US1] [W12A] Add E2E test `tests/e2e/suites/observability/test_cli_status.py`: install the umbrella chart; run `platform-cli observability status`; assert exit code 0 and every component's row shows ✓; deliberately scale Loki to 0 replicas; re-run `status`; assert exit code 1 and Loki's row shows ✗.
- [x] T036 [P] [US1] [W12A] Add Helm unittest at `deploy/helm/observability/tests/test_chart_render.yaml` per plan.md design Track A: assert (a) all 23 dashboard ConfigMaps render with the `grafana_dashboard: "1"` label (rule 27 contract); (b) all PrometheusRule files render with the `prometheus-rule: "1"` label; (c) the Loki alert rules from feature 084 render under `loki-rules.yaml`; (d) the new Grafana data source ConfigMaps from T011-T013 render with the `grafana_datasource: "1"` label; (e) the NetworkPolicy from T009 renders with the configured deny-by-default + allow rules. Use `helm-unittest` plugin (`helm plugin install https://github.com/helm-unittest/helm-unittest`).

### Implementation (already covered by Phase 2 Track A)

The chart bundle, presets, NetworkPolicy, datasources, CLI, README, and Makefile changes from T001-T020 are the implementation for US1. The tests above (T032-T036) are the verification.

---

## Phase 5: User Story 2 — Dashboard Consumer / Log-Metric-Trace Correlation (P1) — J17

**Story goal**: An SRE responding to an alert follows a single linear navigation alert → dashboard panel → Loki log → Jaeger trace → Prometheus metric → resolution without leaving Grafana, without manually re-typing queries, and without copy-pasting IDs between tools. The alert closes within one Loki ruler evaluation cycle on resolution.

**Independent test**: With the umbrella chart + platform chart installed and seed data loaded, trigger a controlled synthetic failure; verify all 7 hop assertions (Loki log within 15s, alert fires + propagates, dashboard shows failing service, Loki → Jaeger derived-field link works, trace spans 3+ services with correct parent/child, Prometheus metric correlates, alert closes on resolution).

### Tests

- [x] T037 [P] [US2] [W12B] Add a small `_e2e` synthetic-failure injector endpoint at `apps/control-plane/src/platform/_e2e/router.py` (or extend an existing one): `POST /api/v1/_e2e/inject-failure` accepts `{"correlation_id": ..., "service": ..., "error_message": ..., "trace_id": ...}` and emits a structured-log error from the named service (cross-runtime — control plane can dispatch to a Go satellite via a gRPC method that has its own logger). Gated by `FEATURE_E2E_MODE`. The endpoint is the dependency for J17 — without it, J17 cannot deterministically trigger a synthetic outage.
- [x] T038 [US2] [W12B] Author `tests/e2e/journeys/test_j17_dashboard_consumer.py` per plan.md design Track B: 7 acceptance points (15+ assertion points minimum per FR-528):
  - Inject the synthetic failure via T037's endpoint.
  - Assert `assert_log_contains(loki_client, {"service": ..., "level": "error"}, error_message, within_seconds=15)` — captures hop 1 (Loki log presence).
  - Assert the `HighErrorLogRate` Loki ruler alert fires (poll Alertmanager API for the active alert with the matching service label).
  - Assert the alert is delivered to the configured notification channel (in-process Mock channel from feature 077).
  - Take a dashboard snapshot of D12 Cross-Service Errors via T027.
  - Assert the Loki entry's `trace_id` derived field link → Jaeger via T026 `assert_trace_exists` with at least 3 expected services.
  - Assert `assert_metric_value(prom_client, "rate({service=...}[5m])", expected_spike, tolerance=0.5, within_seconds=15)` — captures hop 5 (metric correlation).
  - Mark the synthetic failure resolved via the inverse `_e2e` endpoint.
  - Poll Alertmanager until the alert closes, assert `within_seconds <= ruler_evaluation_interval + 5s`.
  - Use `narrative.add_snapshot_to_report(...)` to embed the dashboard snapshot in the journey HTML report.
- [x] T039 [P] [US2] [W12B] Add a deterministic-mode helper to `tests/e2e/journeys/test_j17_dashboard_consumer.py`: scope the synthetic failure injection by per-test `correlation_id` so concurrent J17 runs do not contaminate each other (uses `journey_context.correlation_id` from the existing fixture). The journey is the existence-proof for `pytest -n 4` parallel execution against the same kind cluster.

---

## Phase 6: User Story 3 — Privacy Officer DSR Cycle (P1) — J10

**Story goal**: Right-to-be-forgotten lifecycle end-to-end: identity validation → cascade erasure → tombstone + cryptographic proof → audit chain entry → subject notification. 20+ assertion points across 6 stores (PostgreSQL / Qdrant / Neo4j / ClickHouse / OpenSearch / S3).

### Tests

- [x] T040 [US3] [W12B] Author `tests/e2e/journeys/test_j10_privacy_officer.py` happy-path test per FR-521: 10 cascade-completion assertion families, ≥ 20 distinct assertion points:
  - Submit DSR via `POST /api/v1/privacy/dsr` (the privacy_compliance router from feature 076).
  - Privacy Officer fixture approves; poll for DSR status `approved`.
  - Wait for cascade completion (poll DSR status until `completed`).
  - Per-store assertions: PostgreSQL row tombstoned (direct DB query via `db` fixture); Qdrant vectors removed (Qdrant client via fixture); Neo4j nodes detached (Neo4j async session); ClickHouse rows hard-deleted (clickhouse-connect HTTP query); OpenSearch documents deleted (opensearch-py async); S3 objects purged (aioboto3 list_objects).
  - Tombstone record exists with cryptographic hash (PostgreSQL query against the privacy_compliance tombstone table per feature 076).
  - Audit chain entry exists, links to tombstone (PostgreSQL query against `audit/` BC's chain table per feature 074).
  - Subject receives notification (poll the notifications BC's outbound delivery table).
  - DSR `completed` with timestamp + duration metric (assert via `assert_metric_value(prom_client, ...)`).
  - Use `assert_log_contains(loki_client, {"bounded_context": "privacy_compliance"}, "dsr.cascade.completed", within_seconds=15)` for cross-runtime log assertion.
- [x] T041 [P] [US3] [W12B] Author the J10 negative-test variant — partial cascade failure: deliberately scale down Qdrant to 0 replicas before cascade, submit DSR, wait for retries to exhaust; assert (a) DSR status is `failed`, NOT `completed`; (b) NO tombstone record was created; (c) the audit chain has a `dsr.cascade.partial_failure` entry, NOT a `dsr.cascade.completed` entry. Restore Qdrant after the test (cleanup fixture). The test is the executable proof that the cascade is atomic from the audit perspective.
- [x] T042 [US3] [W12B] Author the J10 chain-integrity post-condition: after the happy-path J10 test (T040) completes, call `POST /api/v1/audit/verify` for the test period; assert the response shows `chain_intact: true`, `verified_entries_count: > 0`, and the time range includes the DSR's audit entry. The verification step is the SC-012 success criterion's audit-chain integrity assertion.

---

## Phase 7: User Story 4 — Security Officer Compliance Cycle (P1) — J11

**Story goal**: Security cycle end-to-end: SBOM publication → vulnerability triage → secret rotation with dual-credential window → JIT credential issue + use → audit chain integrity verify → signed audit log export. 20+ assertion points.

### Tests

- [x] T043 [US4] [W12B] Author `tests/e2e/journeys/test_j11_security_officer.py` per FR-522: 7 cycle stages, ≥ 20 assertion points:
  - Publish SBOM via `POST /api/v1/security/sbom/publish` (feature 074 / UPD-024); assert retrievability in BOTH SPDX and CycloneDX formats.
  - Ingest vulnerability scan with a known critical CVE via `POST /api/v1/security/scans/`; assert severity breakdown is visible.
  - Assert the critical CVE triggers an incident-integration ticket creation (Kafka `incident.triggered` topic — consume via `kafka_consumer` fixture; the topic is owned by feature 080 per the constitutional Kafka registry).
  - Schedule database-credential rotation via `POST /api/v1/security/rotations/` with a 7-day dual-credential window; assert old credentials remain valid through the window (test by issuing a connection request with the old credential within the window).
  - Issue JIT credential via `POST /api/v1/security/jit/grant`; assert the credential's TTL + scope; use the credential and assert audit-log entry is created.
  - Verify audit chain integrity via `POST /api/v1/audit/verify`; assert `chain_intact: true` for the test period.
  - Export signed audit log via `POST /api/v1/audit/attestations/`; assert the signature is verifiable using the public key from `GET /api/v1/audit/public-key`.
- [x] T044 [P] [US4] [W12B] Author the J11 dev-vs-production-CVE variant: ingest a critical CVE in a dev dependency (matched by the `dependency_type: "dev"` tag); assert it does NOT block the platform release (constitution Integration Constraint) AND it IS distinguished from production CVEs in the response payload. The variant is the spec edge-case for FR-522.
- [x] T045 [P] [US4] [W12B] Author the J11 JIT-credential-expiry variant: issue a JIT credential with a short TTL; wait for expiry; attempt to use the credential; assert the operation is refused with a clear "JIT credential expired" error AND the audit log records the refusal.
- [x] T046 [US4] [W12B] J11 chain-integrity post-condition: same pattern as T042; verifies the entire cycle's chain entries are valid.

---

## Phase 8: User Story 5 — Finance Owner Budget and Chargeback (P1) — J12

**Story goal**: Budget cycle end-to-end: configure → soft-threshold alerts → hard cap → admin override → cost anomaly → chargeback report → forecast. 18+ assertion points.

### Tests

- [x] T047 [US5] [W12B] Author `tests/e2e/journeys/test_j12_finance_owner.py` per FR-523: 7 stages, ≥ 18 assertion points:
  - Configure workspace budget via `POST /api/v1/costs/budgets` (feature 079 / UPD-027) with soft thresholds 50% / 80% and a hard cap.
  - Trigger executions to cross 50% threshold; assert the `cost.budget.threshold.reached` Kafka event fires AND the configured notification is delivered.
  - Continue to cross 80% threshold; assert the second alert.
  - Continue to cross hard cap; assert the next execution is REFUSED with a clear cost-cap-blocked error message (assertion includes the exact error message text).
  - Apply admin override via `POST /api/v1/costs/budgets/{id}/override`; assert the override is logged in the audit chain AND the next execution succeeds.
  - Inject a 10× cost spike via the Mock LLM Provider's per-prompt cost-injection knob (extension to the existing mock provider — analogous to T021's rate-limit injection but for cost; if the knob does not exist, T047 includes the small extension); assert the `cost.anomaly.detected` Kafka event fires.
  - Export chargeback report via `POST /api/v1/costs/chargeback/export`; assert the totals match the analytics rollups exactly (zero arithmetic discrepancy per SC-014).
  - Query end-of-period forecast via `GET /api/v1/costs/forecasts/{workspace_id}`; assert the response includes a documented confidence interval.
- [x] T048 [P] [US5] [W12B] Author the J12 admin-override-audit assertion: after the override step, query the audit chain (`GET /api/v1/audit/...`) and assert the override entry references both the original-budget snapshot and the override-grant scope.
- [x] T049 [P] [US5] [W12B] Author the J12 forecast-confidence-interval assertion: poll the forecast endpoint for at least 10 minutes of seeded execution data; assert the forecast response shape includes `point_estimate`, `lower_bound`, `upper_bound`, and `confidence_level` (the documented schema from feature 079).
- [x] T050 [P] [US5] [W12B] J12 cost-attribution Loki log assertion: use `assert_log_contains(loki_client, {"bounded_context": "cost_governance"}, "cost.execution.attributed", within_seconds=15)` to verify the per-execution cost-attribution log line reaches Loki within the FR-535 budget.

---

## Phase 9: User Story 6 — SRE Multi-Region Failover (P1) — J13

**Story goal**: Failover cycle end-to-end: maintenance window → drain → replication-lag check → failover → route check → failback → reconciliation. 18+ assertion points.

### Tests

- [x] T051 [US6] [W12B] Author `tests/e2e/journeys/test_j13_sre_multi_region.py` per FR-524: 7 stages, ≥ 18 assertion points:
  - Schedule maintenance window via `POST /api/v1/regions/maintenance` (feature 081 / UPD-025).
  - Assert in-flight executions complete; new executions return the maintenance-mode error from the `MaintenanceGateMiddleware` (registered ABOVE auth per feature 081's design).
  - Assert replication lag is below RPO across all stores (query the `region.replication.lag` Kafka topic via `kafka_consumer` fixture).
  - Execute failover via `POST /api/v1/regions/failover/execute`; assert `region.failover.initiated` then `region.failover.completed` events.
  - Assert new executions succeed against secondary (test by issuing an execution and verifying it ran on the secondary's runtime-controller).
  - Execute failback via `POST /api/v1/regions/failback/execute`.
  - Run reconciliation query via `POST /api/v1/regions/reconcile`; assert zero data divergence.
- [x] T052 [P] [US6] [W12B] Author the J13 secondary-not-ready negative variant: deliberately simulate the secondary region not ready (test fixture); attempt failover; assert the operation is refused with a clear capacity-error diagnostic AND the journey fails fast (NOT a stuck failover that times out).
- [x] T053 [P] [US6] [W12B] Author the J13 maintenance-gate fail-OPEN-on-Redis-miss variant: deliberately scale down Redis OR delete the maintenance-window key during the test; assert the gate middleware honours the documented fail-OPEN behaviour (feature 081 plan correction §plan-04: stuck Redis state does NOT block the cluster). The variant is the executable proof that the documented inversion of constitution rule 41 is honoured.
- [x] T054 [US6] [W12B] J13 RPO/RTO metric assertion: after failback, query `GET /api/v1/regions/metrics/rpo-rto` and assert the recorded values for the test event are within the documented thresholds.

---

## Phase 10: User Story 7 — Model Steward Catalog and Fallback (P1) — J14

**Story goal**: Catalog cycle end-to-end: approval with full card → deprecation with grace period → fallback policy → 429 injection → fallback verification → cost attribution to fallback. 18+ assertion points.

### Tests

- [x] T055 [US7] [W12B] Author `tests/e2e/journeys/test_j14_model_steward.py` per FR-525: 7 stages, ≥ 18 assertion points:
  - Approve model entry via `POST /api/v1/model-catalog/entries` with a full model card (capabilities, limitations, training cutoff, safety assessments).
  - Assert the model card is retrievable in full via `GET /api/v1/model-catalog/entries/{model_id}/card`.
  - Deprecate an existing model via `POST /api/v1/model-catalog/entries/{model_id}/deprecate` with a grace-period date.
  - Assert grandfathered executions on the deprecated model continue (test by triggering an execution on the deprecated model within the grace period).
  - Configure fallback policy on a seeded agent (primary + 2 fallbacks with quality-tier constraints).
  - Inject synthetic 429 from the primary via the Mock LLM Provider knob (T021): `await mock_llm.set_rate_limit_error(prompt_pattern, count=1)`.
  - Trigger an agent execution; assert the fallback to tier-2 is used.
  - Assert the `model.fallback.triggered` Kafka event fires (consume via `kafka_consumer` fixture).
  - Assert the cost attribution record (queried from `cost_attributions` table per feature 079) reflects the fallback provider's price, NOT the primary's.
  - Assert the audit chain entry for the model deprecation step.
- [x] T056 [P] [US7] [W12B] Author the J14 fallback-cascade-exhaustion variant: inject 429 from primary AND tier-2 AND tier-3; assert the agent's execution fails with a clear "model unavailable, all fallbacks exhausted" error AND the `cost.execution.attributed` event is NOT emitted (no execution → no cost). The variant overlaps with the chaos scenario `test_model_provider_total_outage.py` (T075).
- [x] T057 [P] [US7] [W12B] Author the J14 grace-period-elapsed variant: deprecate a model; advance the test clock past the grace-period date (or use a short test grace period); attempt to invoke an agent grandfathered on the deprecated model; assert the agent rebinds to its fallback OR fails with a clear "model deprecated, grace period elapsed" error.
- [x] T058 [US7] [W12B] J14 dashboard-snapshot post-condition: take a snapshot of D17 Model Catalog dashboard via T027; embed in the J14 HTML narrative report at the "fallback triggered" step.

---

## Phase 11: User Story 8 — Accessibility User Keyboard-Only with Zero AA Violations (P1) — J15

**Story goal**: Full keyboard-only walkthrough of login → marketplace → conversation → execution observation → reasoning trace → logout with zero axe-core AA violations on every visited page. 15+ assertion points.

### Tests

- [x] T059 [US8] [W12B] Author `tests/e2e/journeys/test_j15_accessibility_user.py` per FR-526 — uses Playwright (browser automation) + axe-playwright-python (T028 helper):
  - Setup: launch Playwright with `headless=True`, `viewport={"width": 1920, "height": 1080}`, navigate to the platform's web UI URL (port-forwarded from kind via the existing `tests/e2e/cluster/install.sh` exposes `http://localhost:8080`).
  - At each page transition (login form → marketplace → agent detail → conversation → execution view → reasoning trace → logout), call `run_axe_scan(page, allowlist_path=tests/e2e/journeys/fixtures/axe_allowlist.json, impact="moderate")` from T028; assert the returned violations list is EMPTY (zero AA violations not in allowlist).
  - At each page transition, verify keyboard reachability: every interactive element MUST be reachable via Tab / Shift+Tab / arrows; no element MUST require mouse hover to reveal interactivity.
  - Verify ARIA live region announcements during async operations (status changes, execution progress updates) — use Playwright's `page.locator('[role="status"]')` to verify the announcement text.
  - Verify color contrast ratios at ≥ 4.5:1 (normal) / 3:1 (large) — the axe-core ruleset already enforces this; the assertion is part of T028's allowlist filter.
  - Verify focus indicators are visible on every interactive element (use Playwright's `page.locator(':focus')`'s computed style for `outline` or `box-shadow`).
  - Verify the command palette (Cmd/Ctrl+K) is fully keyboard-usable.
- [x] T060 [P] [US8] [W12B] Author the J15 allowlist-empty regression test: assert `tests/e2e/journeys/fixtures/axe_allowlist.json` is empty (or contains only entries whose `expiry_date` is in the future); fail loudly if a stale or unjustified allowlist entry exists. The test runs as part of the J15 setup so any new violation forces either a fix or an explicit allowlist entry with justification.
- [x] T061 [P] [US8] [W12B] Author a J15 source-map regression test: when the frontend reports a JavaScript error (Track B test fixture deliberately triggers one), assert the resulting log entry's stack trace points at the original TypeScript source line, NOT the minified bundle (the FR-CC-7 contract from feature 084 — UPD-035 verifies the gate works end-to-end).
- [x] T062 [US8] [W12B] J15 CI-gate wiring: verify `.github/workflows/e2e.yml`'s `make e2e-journeys` step fails CI on any J15 axe-core violation. The `pytest --html` report MUST capture each violation with the offending DOM selector and the WCAG criterion violated for triage.

---

## Phase 12: User Story 9 — Compliance Auditor Audit Export (P2) — J16

**Story goal**: Audit-export cycle end-to-end: 30-day export → signature verify → chain integrity verify → event-type queries → compliance evidence dashboard → bundle export. 16+ assertion points.

### Tests

- [x] T063 [US9] [W12B] Author `tests/e2e/journeys/test_j16_compliance_auditor.py` per FR-527: 6 stages, ≥ 16 assertion points:
  - Request audit export via `POST /api/v1/audit/attestations/` for a 30-day window.
  - Assert the export's cryptographic signature is verifiable using `GET /api/v1/audit/public-key` (use the `cryptography` library to verify externally — the test fixture is the "external auditor").
  - Verify hash chain integrity end-to-end via `POST /api/v1/audit/verify` with the same time range; assert `chain_intact: true`, `verified_entries_count > 0`, no broken links.
  - Query specific event types: authentication events, DSR events, policy violations, JIT grants — assert each query returns expected counts and types from the seed data.
  - Take a snapshot of the compliance evidence dashboard (D14 Security Compliance + D13 Privacy Compliance) for SOC2/ISO27001 controls visibility.
  - Export evidence bundle via `POST /api/v1/audit/evidence/export`; assert the bundle is downloadable as a single archive AND its manifest is internally consistent (every artifact referenced by hash, manifest signed by the same key).
- [x] T064 [P] [US9] [W12B] Author the J16 broken-chain negative variant: deliberately corrupt a row in the audit chain (test-only direct DB write); run `POST /api/v1/audit/verify`; assert the response returns `chain_intact: false` AND names the broken sequence number. The variant is the executable proof that chain verification is not a no-op.
- [x] T065 [US9] [W12B] J16 evidence-bundle-manifest-consistency assertion: for each artifact in the exported bundle, recompute the SHA-256 hash; assert it matches the manifest's recorded hash; the test is the SC-017 success criterion's manifest-internally-consistent assertion.

---

## Phase 13: User Story 10 — Bounded-Context E2E Suites (P2)

**Story goal**: Six new BC suites under `tests/e2e/suites/` (privacy_compliance, security_compliance, cost_governance — completed, multi_region_ops, model_catalog, localization), each discoverable by pytest, runnable in parallel, integrated with the Mock LLM Provider and the dev-only `_e2e` endpoints.

### Tests (each suite is one task — sub-tests per FR-531 inside each task)

- [x] T066 [P] [US10] [W12B] Create `tests/e2e/suites/privacy_compliance/` per FR-531: 5 tests — `test_dsr_access.py` (GET-style DSR), `test_dsr_erasure_cascade.py` (the cascade flow that J10 also exercises end-to-end, but here scoped to per-store assertions), `test_residency_enforcement.py` (region-bound query rejection per feature 076), `test_dlp_pipeline.py` (DLP event detection + Kafka `privacy.dlp.event` topic), `test_pia_workflow.py` (PIA approval lifecycle).
- [x] T067 [P] [US10] [W12B] Create `tests/e2e/suites/security_compliance/` per FR-531: 5 tests — `test_sbom_generation.py`, `test_vuln_scan_gating.py`, `test_secret_rotation_dual_window.py` (the dual-credential window contract from feature 074 — old credentials valid during window), `test_jit_credential_lifecycle.py`, `test_audit_chain_integrity.py`.
- [x] T068 [P] [US10] [W12B] Modify `tests/e2e/suites/cost_governance/` per plan.md correction §7: `git mv test_anomaly_alert_routes_to_admin.py test_anomaly_detection.py`; `git mv test_attribution_visible_during_run.py test_attribution.py`; `git mv test_hard_cap_blocks_then_override.py test_budget_enforcement.py`; CREATE `test_forecast.py` (the 4th test per FR-531 — exercises `GET /api/v1/costs/forecasts/{workspace_id}` and asserts the forecast schema). The renames preserve git history.
- [x] T069 [P] [US10] [W12B] Create `tests/e2e/suites/multi_region_ops/` per FR-531: 3 tests — `test_region_config.py` (region config CRUD), `test_replication_monitoring.py` (replication-lag observation per feature 081), `test_maintenance_mode.py` (maintenance-window scheduling and gate-middleware behaviour, including the fail-OPEN-on-Redis-miss variant from T053).
- [x] T070 [P] [US10] [W12B] Create `tests/e2e/suites/model_catalog/` per FR-531: 3 tests — `test_catalog_crud.py`, `test_fallback_on_rate_limit.py` (uses Mock LLM 429 injection from T021 — overlaps with J14 but here scoped to BC-level), `test_model_card.py` (model card publication + retrieval).
- [x] T071 [P] [US10] [W12B] Create `tests/e2e/suites/localization/` per FR-531: 2 tests — `test_user_preferences.py` (`PUT /api/v1/me/preferences` with locale + theme; persistence + retrieval), `test_locale_files.py` (locale catalog file integrity per feature 083 — every supported locale has a complete catalog; this is the runtime side of constitution rule 38).
- [x] T072 [US10] [W12B] Verify the 6 new suites integrate with the existing `tests/e2e/Makefile`'s `e2e-test` target (no Makefile change needed — pytest discovers them); verify parallel execution does not contaminate seed data per FR-456 isolation contract; the per-suite-isolation pattern established by feature 071 is reused.

---

## Phase 14: User Story 11 — Chaos Scenarios (P3)

**Story goal**: Six new chaos scenarios under `tests/e2e/chaos/` (newly created directory) covering Loki ingestion outage, Prometheus scrape failure, model provider total outage, residency misconfiguration, budget hard cap mid-execution, audit chain storage failure.

### Setup

- [x] T073 [US11] [W12B] Create `tests/e2e/chaos/__init__.py` (empty file) per plan.md correction §4 — the directory does not exist on disk; the existing `Makefile` `e2e-chaos` target conditionally runs pytest against it. With the directory in place, the conditional fires and the suite runs in CI.
- [x] T074 [US11] [W12B] Add `tests/e2e/chaos/conftest.py` with chaos-specific fixtures: `failure_injector` (a context manager that scales a target Deployment to 0 replicas for the test scope and restores afterward), `chaos_correlation_id` (per-test correlation ID for log scoping). Reuse the existing `tests/e2e/journeys/conftest.py`'s patterns where applicable.

### Scenarios (each is an independent task)

- [x] T075 [P] [US11] [W12B] Create `tests/e2e/chaos/test_loki_ingestion_outage.py` per FR-532: scale Loki to 0 replicas mid-test; assert (a) the platform's request-handling latency is unaffected per AD-22 fire-and-forget contract — emit a high-volume of structured-log lines from the control plane and measure p95 request latency; (b) on Loki recovery, log emission resumes (assert log presence after Loki is scaled back). The test is the executable proof that Loki unreachability does NOT cause application failures.
- [x] T076 [P] [US11] [W12B] Create `tests/e2e/chaos/test_prometheus_scrape_failure.py`: scale Prometheus to 0 replicas; trigger metric-emitting traffic; on Prometheus recovery, assert metrics gap is visible (no false continuous data) AND assert the platform itself does not fail — metric emission is best-effort.
- [x] T077 [P] [US11] [W12B] Create `tests/e2e/chaos/test_model_provider_total_outage.py` per FR-532 + plan.md research R8: use Mock LLM Provider 429 injection (T021) at every fallback tier; trigger an agent execution; assert (a) all configured fallbacks are walked in order; (b) when all are exhausted, the execution fails with the documented "all fallbacks exhausted" error; (c) the failure does NOT corrupt the agent's state (assert state is recoverable on next invocation when at least one tier becomes available). Overlaps with J14 fallback-cascade-exhaustion variant (T056) but at chaos-scope (longer-duration, more tiers).
- [x] T078 [P] [US11] [W12B] Create `tests/e2e/chaos/test_residency_misconfig.py` per FR-532: deliberately misconfigure a workspace's residency policy (test-only direct DB write to set a region the cluster is not in); attempt a query against that workspace; assert the query is REFUSED with a clear residency-violation error AND the audit log records the refusal. The scenario is the residency-enforcement BC's fail-closed contract from feature 076.
- [x] T079 [P] [US11] [W12B] Create `tests/e2e/chaos/test_budget_hard_cap_midexec.py` per FR-532: configure a budget with a hard cap that the in-flight execution will cross mid-step; assert the execution is gracefully terminated (NOT killed) — the partial-progress is checkpointed per feature 029's contract; assert the budget-cap audit entry references the partial-progress hash.
- [x] T080 [P] [US11] [W12B] Create `tests/e2e/chaos/test_audit_chain_storage_failure.py` per FR-532: deliberately make the audit-chain storage path fail (test-only — e.g., point the audit BC at a non-existent S3 bucket); attempt operations that would create chain entries; assert the operations are REFUSED with a clear "audit chain unavailable, cannot proceed" error (the FAIL-CLOSED contract); on storage recovery, assert subsequent operations succeed AND the chain has NO unverifiable entries (continuity preserved). The scenario is the executable proof that the audit chain fails-closed (the documented constitution contract).

---

## Phase 15: FR-520 — Existing Journey Extensions (J01-J09)

**Story goal**: Extend each of the 9 existing journeys per FR-520 to exercise audit-pass + observability capabilities. Note: J05-J09 do not currently exist on disk per plan.md correction §2 — those tasks AUTHOR them per feature 072's spec AND extend them per FR-520 in the same task.

### Per-journey tasks (parallel — all 9 independent)

- [x] T081 [P] [W12B] Modify `tests/e2e/journeys/test_j01_admin_bootstrap.py` per FR-520 Administrator: add steps to (a) configure DLP rules via the privacy_compliance API; (b) set a workspace budget via the cost_governance API; (c) seed the approved model catalog with at least one entry per provider via the model_catalog API; (d) verify the observability stack is reachable (uses `observability_stack_ready` fixture from T029); (e) verify all 23 dashboards load via the Grafana API. +5 assertion points.
- [x] T082 [P] [W12B] Modify `tests/e2e/journeys/test_j02_creator_to_publication.py` per FR-520 Creator: when the agent declares sensitive data categories during creation, assert a PIA workflow is automatically triggered (via privacy_compliance API); assert the model binding is validated against the approved catalog (rejected if not on catalog). +2 assertion points.
- [x] T083 [P] [W12B] Modify `tests/e2e/journeys/test_j03_consumer_discovery_execution.py` per FR-520 Consumer: after execution, verify a cost attribution record exists; verify a content moderation pass event is logged; verify the corresponding log entry reaches Loki within 15s with the correct `user_id` field via `assert_log_contains(...)`. +3 assertion points.
- [x] T084 [P] [W12B] Modify `tests/e2e/journeys/test_j04_workspace_goal_collaboration.py` per FR-520 Workspace Goal: label the goal with tags via the common/tagging substrate (feature 082); verify a tag-based policy expression is evaluated correctly; verify the goal appears in the Goal Lifecycle dashboard (D20). +2 assertion points.
- [x] T085 [W12B] Author `tests/e2e/journeys/test_j05_trust_governance_pipeline.py` (NEW per plan.md correction §2 — J05 does not exist on disk) per feature 072's spec AND with FR-520 extensions: trust review → governance pipeline → fairness evaluation run → result persistence; verify the Governance Pipeline dashboard (D21) reflects the verdict. ≥ 15 assertion points (FR-462 minimum).
- [x] T086 [W12B] Author `tests/e2e/journeys/test_j06_operator_incident_response.py` (NEW) per feature 072's spec AND FR-520: incident triggered (mock PagerDuty webhook from feature 080); operator consults runbook inline; post-mortem timeline reconstruction; verify the Incident Response dashboard (D19) reflects the active incident. ≥ 15 assertion points.
- [x] T087 [W12B] Author `tests/e2e/journeys/test_j07_evaluator_improvement_loop.py` (NEW) per feature 072's spec AND FR-520: evaluator improvement loop with fairness scorer (feature 078); verify LLM-as-Judge uses a catalog-approved model; verify model fallback triggers when the primary returns rate-limit (uses Mock LLM Provider 429 from T021). ≥ 15 assertion points.
- [x] T088 [W12B] Author `tests/e2e/journeys/test_j08_external_a2a_mcp.py` (NEW) per feature 072's spec AND FR-520: external integrator via A2A and MCP protocols; verify webhook is HMAC-signed (feature 077); verify rate-limit headers are present on API responses; verify OpenAPI schema is served at `/api/openapi.json`. ≥ 15 assertion points.
- [x] T089 [W12B] Author `tests/e2e/journeys/test_j09_scientific_discovery.py` (NEW) per feature 072's spec AND FR-520: scientific discovery flow (feature 039); when demographic data is involved, verify a fairness check runs; verify evaluation results are cost-attributed. ≥ 15 assertion points.
- [ ] T090 [W12B] Rename `tests/e2e/journeys/test_j10_multi_channel_notifications.py` → `test_j10_privacy_officer.py` per plan.md correction §2 — `git mv` (preserves history); the existing notifications-coverage logic is extracted into FR-520 extensions of T081 (J01 — notifications channel config) and T038 (J17 — notification correlation). PENDING feature 072 owner sign-off recorded in `specs/085-extended-e2e-journey/contracts/journey-numbering.md` (T004). The renamed file's contents are then completely rewritten by T040 (the J10 Privacy Officer authoring task) — the rename is the directory-discipline step; the content rewrite is T040.

---

## Phase 16: Joint Validation (W12C)

- [ ] T091 [W12C] Run the full E2E suite end-to-end: `make e2e-up && make e2e-test && make e2e-journeys && make e2e-chaos && make e2e-down`; verify all suites pass; verify the per-test HTML reports are generated under `tests/e2e/reports/`; verify dashboard snapshots (where renderer is enabled in `values-e2e.yaml` — DISABLED by T008, so snapshots are gracefully skipped) do NOT fail the test.
- [ ] T092 [W12C] Run the full E2E suite 3 times consecutively in a controlled environment; assert ≥ 99% pass rate per SC-006 (no flakiness). For any test that fails ≥ 1 time, file a flake-tracking ticket and document a deterministic-mode fix; flake suppression via retry IS NOT acceptable.
- [ ] T093 [W12C] Smoke-test the umbrella chart on a second Kubernetes distribution: install on a k3s cluster (or an alternative — Microk8s, etc.) with the `standard` preset; verify all 6 SC-001 acceptance checks pass. Document the test target + steps in `deploy/helm/observability/README.md` (T018) under a "Tested distributions" section.
- [x] T094 [W12C] Periodic-CI managed-cluster gate: author `.github/workflows/observability-managed-cluster.yml` that triggers weekly (`schedule: ['0 6 * * 1']`) and installs the umbrella chart on a single managed cluster (GKE/EKS/AKS — environment variable selected); verifies all SC-001 checks; uninstalls cleanly. The workflow is the FR-514 managed-cluster verification path; failures alert the platform-ops team via the configured notification channel. PENDING feature 046 owner sign-off (plan.md open question Q5).
- [ ] T095 [W12C] CI duration tuning: measure the wall-clock duration of the full e2e workflow run; if it exceeds the existing 45-minute timeout in `.github/workflows/e2e.yml:21`, parallelize via pytest-xdist `--workers` configuration (existing `E2E_JOURNEY_WORKERS=4` in the Makefile); if still exceeds, split journeys + BC suites + chaos into separate jobs per the existing `.github/workflows/e2e.yml` job structure.
- [x] T096 [W12C] Verify CI artifact upload retains the new `tests/e2e/reports/snapshots/` directory: inspect `.github/workflows/e2e.yml`'s `actions/upload-artifact@v4` step (existing line ~78); confirm the path glob includes `snapshots/`; if not, patch the step (additive — preserves the existing 30-day retention).

---

## Phase 17: Polish (W12D)

- [x] T097 [P] [W12D] Author `specs/085-extended-e2e-journey/quickstart.md` — operator's "first 30 minutes" guide: install the umbrella chart with `values-e2e.yaml`, install the platform chart, verify all 23 dashboards load, run J01 admin journey, observe the result, run a chaos scenario, observe the alert. Reuses the existing speckit `quickstart.md` convention from features 071 and 072.
- [x] T098 [P] [W12D] Author `specs/085-extended-e2e-journey/contracts/observability-helpers.md` — the canonical contract for the 5 helper modules (T024-T028) including signatures, expected behaviour, and the negative-test matrix. Cross-link from each helper module's docstring to this contract.
- [x] T099 [P] [W12D] Update `apps/ops-cli/README.md` (or create if absent) — document the new `platform-cli observability` sub-app with examples for each preset; cross-link to `deploy/helm/observability/README.md` (T018) for the chart-side details.
- [x] T100 [P] [W12D] Add `helm-unittest` invocations to `.github/workflows/ci.yml`'s `helm-lint` job: run `helm unittest deploy/helm/observability/` in addition to the existing `helm lint` step. The unittest gate from T036 verifies the chart renders correctly on every PR (regression prevention for the `grafana_dashboard: "1"` / `prometheus-rule: "1"` / `grafana_datasource: "1"` label discipline).
- [x] T101 [P] [W12D] Update `CLAUDE.md` (the project root agent context file) per the speckit convention: append to the "Active Technologies" section with feature 085's stack identifiers; append to the "Recent Changes" section with a 1-2 line summary of UPD-035's contributions; record the 12 brownfield-input corrections from plan.md correction list as future-planner reference. Keep the file under the 200-line rule.
- [x] T102 [W12D] Run the `tests/e2e/journeys/fixtures/axe_allowlist.json` expiry-check job once: assert all entries (initially zero) have an `expiry_date` ≤ 90 days in the future; document the cadence in CLAUDE.md. The check runs nightly via the existing `cron-cleanup` workflow if present, or as a per-PR check on PRs that modify the allowlist file.
- [ ] T103 [W12D] Cross-feature coordination follow-up: confirm with feature 072's owner that the J10-notifications → J10-privacy-officer rename (T090) is approved; record the sign-off in `specs/085-extended-e2e-journey/contracts/journey-numbering.md` (T004). If the rename is rejected, fall back to the J18 alternative path enumerated in plan.md research R9.

---

## Task Count Summary

| Phase | Range | Count | Wave | Parallelizable |
|---|---|---|---|---|
| Phase 1 — Setup | T001-T004 | 4 | W12A.0 | yes (T002-T004) |
| Phase 2 — Foundational Track A | T005-T020 | 16 | W12A.1-W12A.3 | mostly yes |
| Phase 3 — Foundational Track B | T021-T031 | 11 | W12B.1 | mostly yes |
| Phase 4 — US1 P1 single-command install | T032-T036 | 5 | W12A.3 | yes (T032-T035) |
| Phase 5 — US2 P1 J17 dashboard consumer | T037-T039 | 3 | W12B.4 | partially |
| Phase 6 — US3 P1 J10 Privacy Officer | T040-T042 | 3 | W12B.4 | partially |
| Phase 7 — US4 P1 J11 Security Officer | T043-T046 | 4 | W12B.4 | partially |
| Phase 8 — US5 P1 J12 Finance Owner | T047-T050 | 4 | W12B.4 | partially |
| Phase 9 — US6 P1 J13 SRE Multi-Region | T051-T054 | 4 | W12B.4 | partially |
| Phase 10 — US7 P1 J14 Model Steward | T055-T058 | 4 | W12B.4 | partially |
| Phase 11 — US8 P1 J15 Accessibility | T059-T062 | 4 | W12B.4 | partially |
| Phase 12 — US9 P2 J16 Compliance Auditor | T063-T065 | 3 | W12B.4 | partially |
| Phase 13 — US10 P2 BC suites | T066-T072 | 7 | W12B.2 | yes (six independent suites) |
| Phase 14 — US11 P3 Chaos | T073-T080 | 8 | W12B.5 | yes (six independent scenarios) |
| Phase 15 — FR-520 J01-J09 extensions | T081-T090 | 10 | W12B.3 | yes (nine independent journeys) |
| Phase 16 — Joint validation | T091-T096 | 6 | W12C | sequential |
| Phase 17 — Polish | T097-T103 | 7 | W12D | yes |
| **Total** | | **103** | | |

## MVP Definition

**The MVP is US1 (Phase 4 — single-command install with all 23 dashboards loaded and CLI status returning ✓ on a fresh kind cluster).** Everything else (US2 through US11) is built on top of this MVP. After the MVP lands, US2 (J17 dashboard consumer) provides the canonical observability-ROI proof. After US2, the remaining P1 journeys (US3-US8) and P2 / P3 work can land in any order, parallelized across two devs (one per track per the plan).

## Dependency Notes

- **T001-T020 (Track A) → T032-T036 (US1 tests)**: Track A foundational MUST be complete before US1 tests can run.
- **T021-T031 (Track B foundational) → every journey US (US2-US9), every BC suite (US10), every chaos scenario (US11)**: Track B foundational helpers + fixtures + Mock LLM extension are upstream of every test.
- **T020 (Makefile + `e2e-up` integration) → all of W12B**: the umbrella chart MUST install in the e2e flow before the new tests can run against it.
- **All UPD-023 through UPD-034 features → W12B**: every audit-pass feature MUST have landed before its corresponding journey can be authored. UPD-035 is the audit-pass capstone — it lands LAST.
- **T090 (J10 rename) ← feature 072 sign-off**: this is the only cross-feature blocker; T103 records the sign-off.

## Constitutional Audit Matrix

| Constitution rule | Verified by | Phase |
|---|---|---|
| Rule 22 — Loki labels low-cardinality only | Owned by feature 084's lint; UPD-035 only consumes labels via T024 helpers | (delegated) |
| Rule 24 — every BC has a dashboard | T003 dashboard inventory; chart ships 23 dashboards | Phase 1 |
| Rule 27 — dashboards as ConfigMaps with `grafana_dashboard: "1"` | T036 helm-unittest assertion | Phase 4 |
| Rule 28 — axe-core fails CI on AA violations | T059 J15 test; T062 CI gate wiring; T060 allowlist regression | Phase 11 |
| Rule 41 — Vault failure does not bypass auth | T053 J13 fail-OPEN-on-Redis-miss variant (documented inversion) | Phase 9 |
| Rule 50 — 16 journeys + 6 new BC suites + real-stack | 17 journeys (corrected), 6 new BC suites; T066-T072 | Phase 13 |
| AD-22 — structured JSON logs | Owned by feature 084; UPD-035 consumes via T024 | (delegated) |
| AD-23 — Loki / Jaeger / Prometheus three separate backends | T011-T013 datasource ConfigMaps | Phase 2 |
| Principle XVI — generic S3 storage | T005-T008 preset configs reference generic-S3 env vars | Phase 2 |
| Wave 12 capstone | All tasks tagged W12A / W12B / W12C / W12D | All |
