# Implementation Plan: UPD-034 — Log Aggregation and Comprehensive Dashboards

**Branch**: `084-log-aggregation-dashboards` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

Extend feature 047's existing umbrella Helm chart at `deploy/helm/observability/` with two new sub-chart dependencies (Grafana Loki + Promtail), add structured-logging discipline across the Python control plane (via `structlog`), the Go satellites (extending the stdlib `log/slog` already in use with a small `internal/logging/` ContextHandler), and the Next.js frontend (via a new isomorphic `apps/web/lib/logging.ts`), and provision the dashboard ConfigMaps + Loki ruler alerts that close the gap feature 047 explicitly left open. The constitution names this **UPD-034** in § "Observability Extension" and reserves the `platform-loki-chunks` S3 bucket; this plan is the canonical implementation. **Three corrections to the brownfield input are flagged loudly** (each becomes a CLAUDE.md update in T064 below): (1) Feature 047 ships **11 baseline dashboards**, not 7 — `cost-governance.yaml`, `cost-intelligence.yaml`, `data-stores.yaml`, `fleet-health.yaml`, `multi-region-ops.yaml`, `notifications-channels.yaml`, `platform-overview.yaml`, `reasoning-engine.yaml`, `self-correction.yaml`, `trust-content-moderation.yaml`, `workflow-execution.yaml` — meaning four of the brownfield input's "new" dashboards (D15 Cost Governance, D16 Multi-Region, D18 Notifications Delivery, possibly D14 Security Compliance / D17 Model Catalog) **may already exist** from features 077 / 079 / 081 and should be EXTENDED with log panels rather than re-authored; the plan task list audits each of the 14 against the existing inventory before authoring. (2) The brownfield input's entrypoint list has wrong names — actual entrypoints under `apps/control-plane/src/platform/entrypoints/` are 8, not 9: `api_main.py`, `scheduler_main.py`, `worker_main.py`, `ws_main.py`, `trust_certifier_main.py` (not `certifier_main.py`), `context_engineering_main.py` (not `context_main.py`), `projection_indexer_main.py` (not `projector_main.py`), `agentops_testing_main.py` (not `agentops_main.py`); **there is NO `reasoning_main.py`** because reasoning runs in the Go satellite, not a Python entrypoint. (3) The audit-chain BC at `apps/control-plane/src/platform/audit/service.py` does NOT currently emit log entries — events go to PostgreSQL and Kafka only. For the **D11 Audit Event Stream** dashboard to be useful, this feature must add structured-log emission alongside the existing event publish so Loki captures the audit event stream as a queryable log; this is a small additive change to the audit BC's `append()` method. **Frontend deployment namespace** is install-time parameterised via `{{ .Release.Namespace }}` (NOT the brownfield input's hardcoded `platform-ui`); Promtail's autodiscovery list MUST be a Helm values array so deployments can specify their actual frontend namespace. **`platform-loki-chunks` bucket** is greenfield — created either by the Helm chart (pre-install hook) or by the installer (feature 045). **OTEL Collector is metrics-+-traces-only today**; logs flow directly via Promtail (NOT through OTEL); this plan does NOT add a logs pipeline to the collector.

## Technical Context

**Language/Version**: YAML (Helm chart values + dashboard ConfigMaps + alert rules) + Python 3.12+ (control plane structlog config + audit-chain log-emission additive change) + Go 1.22+ (Go satellite ContextHandler) + TypeScript 5.x (frontend isomorphic logger). No SQL changes (this feature owns no relational tables).
**Primary Dependencies**:
- *Helm sub-charts* — **NEW**: Grafana Loki sub-chart (`grafana/loki` ^6.16.0) and Promtail sub-chart (`grafana/promtail` ^6.16.6) added to `deploy/helm/observability/Chart.yaml` alongside the existing `opentelemetry-collector ^0.108.0`, `kube-prometheus-stack ^65.0.0`, `jaeger ^3.0.0` from feature 047.
- *Python control plane* — **NEW** dependency: `structlog>=24.1` added to `apps/control-plane/pyproject.toml`. No other new Python deps; the existing `opentelemetry-sdk` already provides the `trace_id` / `span_id` propagation that flows through into the structlog ContextVars.
- *Go satellites* — `log/slog` (stdlib) is already used by `services/runtime-controller/cmd/runtime-controller/main.go` (verified at `:6`); this feature adds a small `internal/logging/` package with a ContextHandler wrapper. **No new Go dependencies.**
- *Frontend* — no new dependencies; the isomorphic logger uses `console.log` server-side and `fetch` client-side, both already present.
**Storage**: S3-compatible object storage for Loki chunk storage via the existing generic-S3 client (`S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_USE_PATH_STYLE` env vars per Principle XVI). Bucket name: `platform-loki-chunks` (constitutionally reserved). One in-cluster persistent volume claim (20 GiB default; configurable per Helm values) for Loki's hot tier write path. No PostgreSQL / Redis / Qdrant / Neo4j changes. **OTEL Collector is unchanged** — its existing metrics-→-Prometheus and traces-→-Jaeger pipelines from feature 047 stay; logs do NOT route through the collector (they go via Promtail directly).
**Testing**: pytest + pytest-asyncio for the audit-chain log-emission additive change and the Python `structlog` config; Go testing + testify for the Go ContextHandler; Vitest + Playwright for the frontend isomorphic logger. **New** Helm chart unit-test step using `helm unittest` (already in the chart's CI surface per feature 047). **New** end-to-end suite under `tests/e2e/suites/observability/` extending the kind-cluster harness from feature 071: log-ingestion latency assertion, dashboard load assertion, alert-firing assertion, sensitive-data redaction assertion.
**Target Platform**: Linux server (control plane), Kubernetes deployment. **Loki single-binary** in v1 per the brownfield input's Helm config — HA mode is a future concern. **Promtail DaemonSet** runs on every node. The control plane's `scheduler` and `api` runtime profiles do not gain any new responsibility (no APScheduler jobs in this feature).
**Performance Goals**: Log entries reach Loki within ≤ 15 seconds of emission p95 (FR-535 / SC-002). Grafana Explore queries against `{service=<X>, level="error"}` over a 1-hour window return in ≤ 3 seconds p95 (SC-003). All 14 new dashboards load and render initial panels in ≤ 5 seconds p95 on seeded demo data (SC-007 + SC-008). Promtail's per-line redaction overhead is ≤ 100 µs p95 (deferred-pattern-matching with pre-compiled regex per Promtail's standard pipeline). The structured-logging contract adds ≤ 5 µs p95 per log call in Python (`structlog`'s overhead at `cache_logger_on_first_use=True`); Go's `slog` has comparable overhead. **No regression in feature 047's existing dashboards** is the SC-013 invariant.
**Constraints**: **Loki labels are low-cardinality only** per constitution rule 22 — `service`, `bounded_context`, `level` (plus the bounded `namespace`, `pod`, `container` set by Promtail from CRI metadata). `workspace_id`, `user_id`, `goal_id`, `correlation_id`, `trace_id` MUST live in the JSON payload, never as labels. The CI lint check that enforces this is delivered as part of T060 (a small grep against the Promtail pipeline_stages config that fails the build if any high-cardinality field is promoted to `labels:`). **Log emission is fire-and-forget** per constitution Integration Constraint — Loki unreachability MUST NOT cause application failures. The Python `structlog.JSONRenderer` writes to stdout; OS pipe pressure is the only backpressure mechanism, which is acceptable since Promtail consumes from stdout asynchronously. **Promtail redaction is best-effort** — application-layer secret-discipline (rule 23) is the authoritative defence; redaction is layered. **Multi-region log federation** is per-region Loki + Grafana federates via the `region` label (feature 081's contract); no cross-region replication of log chunks. **Audit-chain log emission** must be inside the same SQLAlchemy transaction as the chain append so failure-to-log fails-the-append visibly (a "logged event" that wasn't logged would mislead auditors); for the audit BC specifically, log emission is NOT fire-and-forget but transactional. This is a documented inversion of the general "log-emission is fire-and-forget" rule, recorded in Complexity Tracking.
**Scale/Scope**: 14 days hot retention × ~15 platform services × ~hundreds of MB/day per service = ~10–50 GB/day hot, ~150–700 GB total hot footprint at steady state. Cold archive on S3 is essentially unbounded (operator retention policy applies). Dashboard count after this feature: **11 existing + (≤ 14 net-new after de-duplication against the existing 11)** = up to 25 total dashboards. Alert count: **5 existing PrometheusRule files** (`execution-alerts`, `fleet-alerts`, `kafka-alerts`, `reasoning-alerts`, `service-alerts`) **+ 1 new file** (`loki-alerts.yaml` or equivalent) carrying the 5 new Loki ruler rules per FR-542.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Source | Status | Notes |
|---|---|---|---|
| Brownfield rule 1 — never rewrite | Constitution § Brownfield | ✅ Pass | All changes are additive: extending the existing Helm chart, adding sub-charts, adding new dashboard ConfigMaps, adding `structlog` config, adding `internal/logging/` package per Go satellite, adding `apps/web/lib/logging.ts`, adding log emission to the audit-chain BC's existing `append()` (without modifying its current event-publish path). The 11 existing dashboards from feature 047 + features 077/079/081's contributions are preserved; new log-panel additions (FR-CC-6) are bolt-ons. |
| Brownfield rule 2 — Alembic only | Constitution § Brownfield | ✅ N/A | This feature owns no relational tables; no Alembic migration. |
| Brownfield rule 3 — preserve tests | Constitution § Brownfield | ✅ Pass | Existing observability tests stay green. The new structured-logging contract is additive; existing Python `logging.getLogger()` calls (where they exist) continue to function — they just lack the new fields. |
| Brownfield rule 4 — use existing patterns | Constitution § Brownfield | ✅ Pass | Sub-chart additions follow the existing `Chart.yaml dependencies:` shape from feature 047. Dashboard ConfigMaps use the existing `grafana_dashboard: "1"` label and live in `templates/dashboards/`. New alert rules live alongside the existing 5 PrometheusRule files in `templates/alerts/`. The Python `structlog` configuration follows the standard library convention. The Go ContextHandler follows the stdlib `slog.Handler` interface contract. |
| Brownfield rule 5 — cite exact files | Constitution § Brownfield | ✅ Pass | Project Structure below names every file; integration seams cite file:line for the call sites. |
| Brownfield rule 6 — additive enums | Constitution § Brownfield | ✅ N/A | No SQL enums touched. |
| Brownfield rule 7 — backwards-compatible APIs | Constitution § Brownfield | ✅ Pass | The audit-chain BC's `append()` keeps its existing signature; log emission is added inside the implementation. Python services that don't call `configure_logging()` still log via the existing path; the new contract is opt-in per-service-startup. The Go ContextHandler is added inside `Configure()`; existing slog calls work either way. |
| Brownfield rule 8 — feature flags | Constitution § Brownfield | ✅ Pass | `FEATURE_STRUCTURED_LOGGING` (always on per constitution line 892), `FEATURE_LOKI_ENABLED` (line 893, default true, superadmin-toggleable), `FEATURE_PROMTAIL_REDACTION` (line 894, default true, superadmin-toggleable) are constitutional names; this plan wires their runtime gates. The Helm chart's `loki.enabled` / `promtail.enabled` values map to the corresponding constitutional flags. |
| Rule 9 — every PII operation audited | Constitution § Domain | ✅ Pass | This feature does not write user PII directly; it observes logs that may contain PII fragments. Promtail's redaction (FR-538) is the defence-in-depth layer; rule 23 ("secrets never reach logs") is the authoritative application-layer discipline. |
| Rule 13 (every user-facing string through i18n) | Constitution § Domain | ✅ N/A | Grafana dashboards are operator-facing surfaces and English-only at v1 per spec § Out of Scope (Grafana's i18n is limited; feature 083's 6-locale promise covers the application UI, not Grafana). |
| Rule 18, AD-21 (residency at query time) | Constitution § Domain | ✅ Pass | Logs replicate per the Loki-per-region pattern (feature 081's contract); cross-region transfers are governed by existing residency configuration, not by this feature. |
| Rule 20, AD-22 (structured JSON logs) | Constitution § Domain | ✅ Pass | This feature IS the canonical implementation. T015 (Python structlog config), T021 (Go ContextHandler), T026 (Next.js logger) deliver the cross-runtime contract. |
| Rule 21 (correlation IDs context-managed) | Constitution § Domain | ✅ Pass | Python `ContextVars` (control plane), Go `context.Context` (satellites), Next.js request context (frontend server). FastAPI middleware at HTTP ingress and Kafka consumer middleware populate the ContextVars; Go gRPC interceptors populate the context. Manual passing is forbidden by the contract. |
| Rule 22 (Loki labels low-cardinality only) | Constitution § Domain | ✅ Pass | T013 documents the label allowlist (`service`, `bounded_context`, `level`, `namespace`, `pod`, `container`); T060 delivers the CI lint that enforces it (a deliberate-violation test fails the build if a developer attempts to promote a high-cardinality field to a label per FR-535.6 + SC-014). |
| Rule 23, 31, 40 (no secrets in logs) | Constitution § Domain | ✅ Pass | Application-layer discipline is the authoritative mandate; Promtail's redaction (T012, T016) is layered defence. Vault tokens / OAuth client secrets / AppRole SecretIDs are forbidden at the application logger level (rule 23 is a code-review blocker — verified by an additional lint rule that flags `logger.info(...secret...)` patterns). |
| Rule 24, 27 (every BC dashboard via unified Helm bundle, ConfigMaps with `grafana_dashboard: "1"` label) | Constitution § Domain | ✅ Pass | T028–T041 deliver dashboards as ConfigMaps following the existing pattern. T027 reconciles the brownfield input's "14 net-new" against the existing 11 to identify true new vs. extend (the audit shows D15 Cost Governance, D16 Multi-Region, D18 Notifications Delivery already exist from features 079 / 081 / 077; these get log-panel extensions rather than re-authoring). |
| Rule 25, 26, 28 (E2E suite + journey crossing + journey runs against real backends) | Constitution § Domain | ✅ Pass | T053 extends the existing operator incident-response journey J06 from features 080 / 081 with log-driven debugging steps; runs against real Loki/Grafana on the kind cluster per rule 26. |
| Rule 29, 30 (admin endpoint segregation, admin role gates) | Constitution § Domain | ✅ N/A | This feature exposes no REST endpoints. Grafana's existing RBAC governs dashboard access. |
| Rule 32 (audit chain on config changes) | Constitution § Domain | ✅ Pass | The audit chain BC's existing audit emission for chain append is preserved; this feature ADDS a structured-log entry alongside the existing event-publish so Loki captures the stream — the audit chain's own state machine remains the source of truth. |
| Rule 36 (UX-impacting FR documented) | Constitution § Domain | ✅ Pass | T056–T058 update operator runbooks (LogQL cheatsheet), the structured-logging contract documentation for new BC authors, and the Grafana metric/log/trace correlation user guide. |
| Rule 39 (every secret resolves via SecretProvider) | Constitution § Domain | ✅ Pass | Loki's S3 credentials are env-var-driven (`S3_ACCESS_KEY` / `S3_SECRET_KEY`); these resolve through the existing `SecretProvider` (`common/clients/model_router.py:43`) at chart-install time per the existing UPD-040 (Vault) pattern from feature 047. |
| Rule 50 (mock LLM for previews) | Constitution § Domain | ✅ N/A | This feature does not invoke an LLM. |
| Principle I (modular monolith) | Constitution § Core | ✅ Pass | All control-plane changes within the existing Python monolith; no new bounded context. |
| Principle III (dedicated stores) | Constitution § Core | ✅ Pass | Loki is a new dedicated logging store; PG / Redis / Qdrant / Neo4j / ClickHouse / OpenSearch / Kafka stay in their existing roles. AD-23 explicitly: "Loki for logs; Jaeger for traces; Prometheus for metrics" — this feature implements the Loki side. |
| Principle IV (no cross-BC table access) | Constitution § Core | ✅ Pass | Dashboards query Loki and Prometheus; no direct PostgreSQL access from dashboards (the existing pattern). The Python `structlog` config and the audit-BC log-emission addition are within their respective BCs. |
| Principle V (append-only journal) | Constitution § Core | ✅ N/A | Loki's append-only semantics are intrinsic; the platform's execution journal is unrelated. |
| Principle XVI (generic S3) | Constitution § Core | ✅ Pass | Loki uses the generic S3 protocol via `S3_ENDPOINT_URL` env var; never references MinIO directly. |
| Constitutional `platform-loki-chunks` bucket reservation | Constitution § Observability Extension | ✅ Pass | T011 provisions the bucket either via Helm pre-install hook or installer (feature 045) handoff. |
| Constitutional feature flags already declared | Constitution § Feature Flag Inventory lines 892–894 | ✅ Pass | `FEATURE_STRUCTURED_LOGGING`, `FEATURE_LOKI_ENABLED`, `FEATURE_PROMTAIL_REDACTION` already declared; this plan wires them. |

## Project Structure

### Documentation (this feature)

```text
specs/084-log-aggregation-dashboards/
├── plan.md                  # This file
├── spec.md                  # Feature spec
├── planning-input.md        # Verbatim brownfield input (preserved as planning artifact —
│                            #   contains the full Helm/Python/Go/Next.js/LogQL detail
│                            #   that informs but doesn't constrain this plan)
├── research.md              # Phase 0 — dashboard de-duplication audit (the 14 brownfield-input
│                            #   dashboards reconciled against the 11 existing); structlog
│                            #   processor stack decision; Go ContextHandler design; isomorphic
│                            #   frontend logger pattern; bucket-provisioning ownership
│                            #   (Helm pre-install vs feature-045 installer); audit-BC log
│                            #   emission contract (transactional vs fire-and-forget rationale)
├── data-model.md            # Phase 1 — Loki label schema + JSON payload field schema; the
│                            #   structured-logging contract shared across Python / Go / TS
├── quickstart.md            # Phase 1 — local end-to-end walk: deploy Loki + Promtail to a
│                            #   kind cluster; emit a log; query it in Grafana; pivot to Jaeger;
│                            #   trigger a Loki alert
├── contracts/               # Phase 1
│   ├── structured-log-schema.md            # The cross-runtime field schema
│   ├── loki-label-allowlist.md             # The constitution-rule-22-derived label set
│   ├── promtail-pipeline-stages.md         # Pipeline stage shape (CRI → JSON → labels →
│   │                                       #   timestamp → redact)
│   ├── audit-bc-log-contract.md            # The transactional log-emission addition to the
│   │                                       #   audit BC's append()
│   ├── dashboard-de-duplication.md         # The audit of brownfield-input dashboards vs. the
│   │                                       #   existing 11; identifies extend-vs-create per ID
│   ├── loki-alert-rules.md                 # The 5 LogQL expressions and their thresholds
│   └── frontend-isomorphic-logger.md       # The apps/web/lib/logging.ts contract
├── checklists/
│   └── requirements.md
└── tasks.md                 # Created by /speckit.tasks (NOT created here)
```

### Source Code (repository root)

```text
deploy/helm/observability/
├── Chart.yaml                                          # MODIFIED — append two new dependencies:
│                                                       #     - name: loki, version: ^6.16.0,
│                                                       #       repository: https://grafana.github.io/helm-charts
│                                                       #     - name: promtail, version: ^6.16.6,
│                                                       #       repository: https://grafana.github.io/helm-charts
│                                                       #   The 3 existing dependencies
│                                                       #   (opentelemetry-collector, kube-prometheus-
│                                                       #   stack, jaeger) are preserved untouched
├── Chart.lock                                          # AUTO-REGENERATED — `helm dep update`
├── values.yaml                                         # MODIFIED — append top-level keys
│                                                       #   `loki:` and `promtail:` per the
│                                                       #   brownfield input; extend the existing
│                                                       #   `grafana:` block (under
│                                                       #   `kube-prometheus-stack.grafana`) with
│                                                       #   the Loki data source + derived-field
│                                                       #   linking. Add a top-level
│                                                       #   `frontendNamespaces:` array (default
│                                                       #   `["platform-control"]` — flagged as
│                                                       #   install-time-confirm; the brownfield
│                                                       #   input's `platform-ui` does NOT match
│                                                       #   constitution's namespace list)
└── templates/
    ├── _helpers.tpl                                    # MODIFIED — add a small helper
    │                                                   #   `musematic-observability.lokiLabels`
    │                                                   #   that emits the constitutional label
    │                                                   #   allowlist for any future ConfigMap
    │                                                   #   needing it
    ├── namespace.yaml                                  # UNCHANGED
    ├── jaeger-badger-pvc.yaml                          # UNCHANGED
    ├── otel-collector-servicemonitor.yaml              # UNCHANGED — OTEL stays metrics+traces only
    ├── pre-install-loki-bucket-job.yaml                # NEW (alternative to installer-driven
    │                                                   #   bucket creation) — Helm pre-install
    │                                                   #   Job that uses `aws s3api create-bucket`
    │                                                   #   against `S3_ENDPOINT_URL` to create
    │                                                   #   `platform-loki-chunks` if not present;
    │                                                   #   idempotent. Decision in research.md
    │                                                   #   between this and the installer path
    ├── alerts/
    │   ├── execution-alerts.yaml                       # UNCHANGED
    │   ├── fleet-alerts.yaml                           # UNCHANGED
    │   ├── kafka-alerts.yaml                           # UNCHANGED
    │   ├── reasoning-alerts.yaml                       # UNCHANGED
    │   ├── service-alerts.yaml                         # UNCHANGED
    │   └── loki-alerts.yaml                            # NEW — LokiRule / AlertingRule (chart's
    │                                                   #   chosen CRD per Loki version) carrying
    │                                                   #   the 5 LogQL rules: HighErrorLogRate,
    │                                                   #   SecurityEventSpike, DLPViolationSpike,
    │                                                   #   AuditChainAnomaly, CostAnomalyLogged.
    │                                                   #   Routes via the existing Alertmanager
    │                                                   #   from feature 047
    └── dashboards/
        ├── (11 existing ConfigMaps preserved untouched)  # cost-governance.yaml, cost-intelligence.yaml,
        │                                                  #   data-stores.yaml, fleet-health.yaml,
        │                                                  #   multi-region-ops.yaml,
        │                                                  #   notifications-channels.yaml,
        │                                                  #   platform-overview.yaml,
        │                                                  #   reasoning-engine.yaml, self-correction.yaml,
        │                                                  #   trust-content-moderation.yaml,
        │                                                  #   workflow-execution.yaml
        ├── control-plane-logs.yaml                     # NEW — D8
        ├── go-services-logs.yaml                       # NEW — D9
        ├── frontend-web-logs.yaml                      # NEW — D10
        ├── audit-event-stream.yaml                     # NEW — D11 (depends on T020 audit-BC
        │                                                #   log emission)
        ├── cross-service-errors.yaml                   # NEW — D12
        ├── privacy-compliance.yaml                     # NEW — D13 (no existing equivalent)
        ├── security-compliance.yaml                    # NEW — D14 (no existing equivalent;
        │                                                #   `trust-content-moderation.yaml` exists
        │                                                #   but covers a different sub-domain)
        ├── cost-governance-extended.yaml               # ⚠ EXTENDS existing — the existing
        │                                                #   `cost-governance.yaml` (likely from
        │                                                #   feature 079) provides the metric
        │                                                #   panels for D15; this new ConfigMap
        │                                                #   adds the log-stream drill-down panels
        │                                                #   referenced by FR-543 (or, after the
        │                                                #   T027 audit, may be merged into the
        │                                                #   existing file as additive panels —
        │                                                #   plan defers the merge-vs-add decision
        │                                                #   to T030)
        ├── multi-region-ops-extended.yaml              # ⚠ EXTENDS existing — same logic for D16
        ├── model-catalog.yaml                          # NEW — D17 (no existing equivalent)
        ├── notifications-delivery-extended.yaml        # ⚠ EXTENDS existing
        │                                                #   `notifications-channels.yaml` for D18
        │                                                #   per the same merge-vs-add decision
        ├── incident-response.yaml                      # NEW — D19 (no existing equivalent;
        │                                                #   feature 080 spec authored a dashboard
        │                                                #   but field guide confirmed no pre-
        │                                                #   existing file)
        ├── goal-lifecycle.yaml                         # NEW — D20
        └── governance-pipeline.yaml                    # NEW — D21

apps/control-plane/
├── pyproject.toml                                      # MODIFIED — add `structlog>=24.1` to
│                                                       #   dependencies (alongside existing
│                                                       #   FastAPI, SQLAlchemy, etc.)
└── src/platform/
    ├── common/
    │   └── logging.py                                  # NEW — structured JSON logger using
    │                                                   #   structlog; carries ContextVars for
    │                                                   #   workspace_id, goal_id, correlation_id,
    │                                                   #   trace_id, user_id, execution_id;
    │                                                   #   exposes `configure_logging(service,
    │                                                   #   bounded_context)` and
    │                                                   #   `set_context_from_request()` /
    │                                                   #   `clear_context()` helpers
    ├── common/middleware/
    │   ├── correlation_logging_middleware.py           # NEW — FastAPI middleware that populates
    │                                                   #   the ContextVars from JWT claims,
    │                                                   #   X-Correlation-ID header, route params;
    │                                                   #   the existing CorrelationMiddleware
    │                                                   #   (per CLAUDE.md / prior features) may
    │                                                   #   need extension rather than parallel —
    │                                                   #   T017 handles this
    │   └── kafka_logging_consumer_middleware.py        # NEW — wraps existing Kafka consumers
    │                                                   #   to populate ContextVars from the
    │                                                   #   EventEnvelope before the handler runs
    ├── audit/
    │   └── service.py                                  # MODIFIED — at AuditChainService.append()
    │                                                   #   (audit/service.py:48–72), inside the
    │                                                   #   same SQLAlchemy transaction as the
    │                                                   #   chain-row insert, ALSO call
    │                                                   #   logger.info("audit.chain.appended",
    │                                                   #   sequence_number=..., audit_event_source=...,
    │                                                   #   canonical_payload_hash=...,
    │                                                   #   entry_hash=...) so Loki captures the
    │                                                   #   stream for the D11 dashboard. Note:
    │                                                   #   for the audit BC SPECIFICALLY this
    │                                                   #   log emission is NOT fire-and-forget —
    │                                                   #   it's transactional; if the log emit
    │                                                   #   raises, the transaction fails (a
    │                                                   #   "logged event" that wasn't logged
    │                                                   #   would mislead auditors). Documented
    │                                                   #   inversion of the general "log emission
    │                                                   #   is fire-and-forget" rule
    └── entrypoints/
        ├── api_main.py                                 # MODIFIED — call configure_logging("api",
        │                                                #   "platform-control") at startup
        ├── scheduler_main.py                           # MODIFIED
        ├── worker_main.py                              # MODIFIED
        ├── ws_main.py                                  # MODIFIED
        ├── trust_certifier_main.py                    # MODIFIED — note actual filename
        │                                                #   (NOT certifier_main.py per
        │                                                #   brownfield input's mistake)
        ├── context_engineering_main.py                 # MODIFIED — note actual filename
        ├── projection_indexer_main.py                  # MODIFIED — note actual filename
        ├── agentops_testing_main.py                    # MODIFIED — note actual filename
        # Note: there is NO reasoning_main.py because reasoning runs in the Go satellite,
        # not as a Python entrypoint (brownfield input was wrong)

services/
├── runtime-controller/
│   ├── cmd/runtime-controller/main.go                  # MODIFIED — at :6 the existing slog
│   │                                                   #   import is preserved; replace the
│   │                                                   #   default JSONHandler with the new
│   │                                                   #   ContextHandler
│   └── internal/logging/
│       ├── logging.go                                  # NEW — the ContextHandler wrapping
│       │                                               #   slog.NewJSONHandler with service +
│       │                                               #   bounded_context attrs and ContextVar-
│       │                                               #   equivalent (context.Context value
│       │                                               #   extraction)
│       └── logging_test.go                             # NEW — unit tests for the handler
├── sandbox-manager/internal/logging/                   # SAME PATTERN
│   └── logging.go                                      # NEW
├── reasoning-engine/internal/logging/                  # SAME PATTERN
│   └── logging.go                                      # NEW
├── simulation-controller/internal/logging/             # SAME PATTERN
│   └── logging.go                                      # NEW
├── hostops-broker/internal/logging/                    # SAME PATTERN
│   └── logging.go                                      # NEW
└── browser-worker/internal/logging/                    # SAME PATTERN (if browser-worker exists
                                                        #   as a Go satellite per CLAUDE.md
                                                        #   inventory; T021 confirms)
        # Each Go satellite's main.go is also modified to call logging.Configure() at startup
        # and update gRPC interceptors to populate context.Context with correlation IDs from
        # gRPC metadata

apps/web/
├── lib/
│   └── logging.ts                                      # NEW — isomorphic structured logger;
│                                                       #   server-side writes JSON to stdout;
│                                                       #   client-side posts to /api/log/client-error
├── app/
│   ├── api/log/client-error/
│   │   └── route.ts                                    # NEW — Next.js route handler that
│   │                                                   #   accepts client-reported error events
│   │                                                   #   and writes them as structured JSON
│   │                                                   #   to stdout (where Promtail captures
│   │                                                   #   them via the deployment's log path)
│   └── instrumentation.ts                              # NEW — Next.js instrumentation hook
│                                                       #   configures server-side structured
│                                                       #   logging at app startup. Also wires
│                                                       #   the global error / unhandledrejection
│                                                       #   handlers on the client side
└── components/                                         # SOME MODIFIED — instrument critical
                                                        #   user actions (login, workspace switch,
                                                        #   goal creation, execution launch) with
                                                        #   `log.info()` calls so Loki captures
                                                        #   the user-action stream

deploy/installers/                                      # MAY MODIFY — feature 045's installer
└── (existing files)                                    #   provisions the platform-loki-chunks
                                                        #   bucket on first install. Decision in
                                                        #   research.md: Helm pre-install hook vs
                                                        #   installer task. Default: Helm pre-
                                                        #   install hook for self-contained chart
                                                        #   delivery; installer fallback for
                                                        #   environments where the chart's S3
                                                        #   credentials lack bucket-create
                                                        #   permission

.github/workflows/
└── ci.yml                                              # MODIFIED — at :511 the existing
                                                        #   `helm lint "$chart" --strict` step
                                                        #   already validates Chart.yaml /
                                                        #   templates; T058 adds two new steps:
                                                        #   (a) `helm unittest` for Loki alert
                                                        #   rule LogQL syntax + dashboard JSON
                                                        #   schema validation, (b) the rule-22
                                                        #   lint check (a small grep against the
                                                        #   Promtail pipeline_stages config that
                                                        #   fails the build if any high-cardinality
                                                        #   field is promoted to `labels:`)

tests/
└── e2e/suites/observability/
    ├── test_log_ingestion.py                           # NEW — log entries reach Loki within
    │                                                   #   15s of emission (SC-002)
    ├── test_dashboards_load.py                         # NEW — all 14 net-new dashboards load
    │                                                   #   in ≤ 5s (SC-007 + SC-008)
    ├── test_alerts_fire.py                             # NEW — synthetic conditions trigger the
    │                                                   #   5 Loki ruler alerts (SC-009)
    ├── test_sensitive_redaction.py                     # NEW — bearer tokens / API keys / SSNs
    │                                                   #   redacted at Promtail before reaching
    │                                                   #   Loki (SC-006)
    ├── test_cross_runtime_log_shape.py                 # NEW — same logical event from Python /
    │                                                   #   Go / TS produces identical Loki entry
    │                                                   #   shape (SC-015)
    ├── test_metric_to_log_pivot.py                     # NEW — the "View related logs" link from
    │                                                   #   a metric data point opens Loki with
    │                                                   #   the same label set (SC-005)
    └── test_loki_to_jaeger_pivot.py                    # NEW — derived-field link from a Loki
                                                        #   trace_id opens Jaeger (SC-004)
```

**Structure Decision**: This feature is **infrastructure + cross-cutting code** — no new bounded context, no new database tables. The existing Helm chart at `deploy/helm/observability/` is extended with two sub-chart dependencies (Loki + Promtail) and a small batch of new ConfigMaps; the existing 11 dashboards + 5 alert files from features 047 / 077 / 079 / 081 are preserved untouched. The structured-logging substrate is delivered across three runtimes (Python via `structlog`, Go via stdlib `slog` + a small ContextHandler wrapper, TypeScript via a hand-rolled isomorphic logger). The audit-chain BC at `audit/service.py:48` gets a small additive log emission inside its existing `append()` method (transactional log emission, NOT fire-and-forget — documented inversion in Complexity Tracking). The brownfield input's frontend namespace `platform-ui` is replaced with a Helm values array `frontendNamespaces:` so deployments can specify the actual namespace where the frontend deploys (which is `{{ .Release.Namespace }}` per the field-guide finding).

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Loki + Promtail as Helm sub-chart dependencies (NOT a fork or in-repo template) | The Grafana Loki + Promtail sub-charts are well-maintained upstream and follow the same kube-prometheus-stack / opentelemetry-collector pattern feature 047 already uses. Forking would lock the platform out of upstream security fixes; in-repo templates would re-implement what the upstream chart provides for free. | Fork the charts: rejected — upgrade path becomes manual. Hand-rolled ConfigMaps + Deployments: rejected — re-implements upstream value for no gain. |
| Loki single-binary mode for v1 (NOT distributed mode) | Platform's log volume estimate at steady state (~10–50 GB/day) fits comfortably in single-binary's capacity. Distributed mode adds operational complexity (separate ingester / querier / compactor / distributor pods) for capacity headroom we don't need today. | Distributed mode from day 1: rejected — premature optimisation. HA mode: rejected — single-binary's fault tolerance is sufficient given the fire-and-forget log-emission contract. Both can be migrated to in a future feature. |
| Logs flow via Promtail (NOT via OTEL Collector's logs pipeline) | OTEL Collector is metrics+traces only today (verified at `deploy/helm/observability/values.yaml:43–93`). Adding a logs pipeline would route container stdout through OTEL twice (Promtail still needs file-system access for CRI extraction). Direct Promtail → Loki is cleaner and preserves the existing OTEL-Collector responsibility. | Route logs through OTEL Collector: rejected — adds a hop, conflates two concerns; Promtail's pipeline_stages give finer control over redaction and JSON parsing than OTEL's logs receiver. |
| Audit-BC log emission is transactional (NOT fire-and-forget — inversion of general rule) | The audit chain is the platform's authoritative integrity record. A "logged event that wasn't logged" would mislead auditors who read the D11 dashboard expecting it to mirror the chain. By emitting the log inside the same SQLAlchemy transaction as the chain row insert, log-emit failure rolls back the chain insert visibly — auditors see chain.append failures, not silent log gaps. This is a deliberate inversion of the general "log emission is fire-and-forget" rule (constitution Integration Constraint), recorded loudly so future planners don't try to "fix" it. | Fire-and-forget log emission for the audit BC: rejected — silent log gaps mislead auditors. No log emission at all (D11 reads directly from the chain via Loki's API): rejected — the chain is in PostgreSQL, not Loki; D11 needs a Loki-queryable stream to leverage Grafana Explore. |
| Promtail redaction + application-layer secret discipline (BOTH layers, not just one) | Constitution rule 23 says secrets never reach logs in the first place — this is the application-layer mandate. Promtail's redaction is the defence-in-depth layer for the case where a developer accidentally violates rule 23. Both are needed: the application-layer discipline is the authoritative protection; Promtail catches mistakes. | Application-layer only: rejected — rule 23 is a code-review blocker but humans miss things; Promtail catches the slip. Promtail-only: rejected — constitution rule 23 is non-negotiable and Promtail is best-effort (could be misconfigured or have pattern gaps). |
| Loki labels low-cardinality only — `workspace_id` / `user_id` / `goal_id` in JSON payload, NOT labels | Constitution rule 22 explicitly. High-cardinality labels would explode Loki's index and degrade query performance to the point of unusability. The CI lint check (T060) is the build-time enforcement; the Promtail pipeline_stages config (T012) is the design-time reflection. | Promote `workspace_id` to a label "for query convenience": rejected — Loki's label-based index is not a database secondary index; it scales linearly with cardinality. |
| 14 net-new dashboards reconciled against 11 existing (de-duplicate via T027 audit, NOT re-author) | Field-guide research found the brownfield input's "7 baseline dashboards from feature 047" claim was wrong — there are actually 11, including `cost-governance.yaml`, `multi-region-ops.yaml`, `notifications-channels.yaml`, `trust-content-moderation.yaml` that overlap with the brownfield input's "new" D15 / D16 / D18 / (possibly) D14. The plan's T027 audit identifies the overlap per-ID; the result is some dashboards EXTEND the existing file with log panels (saving authoring effort and avoiding two-source-of-truth dashboards), others are truly net-new. | Re-author all 14 from scratch: rejected — duplicates effort + creates two-source-of-truth dashboards (the existing one from feature 079/081/077 stays + the new one — operators will have two cost-governance dashboards). Skip the dashboards that already exist: rejected — they may not have the log-panel additions FR-540 / FR-541 require. |
| Frontend `frontendNamespaces:` Helm values array (NOT hardcoded `platform-ui`) | The constitution's canonical Kubernetes namespace list does NOT include `platform-ui` (verified). The frontend chart deploys via `{{ .Release.Namespace }}` which is install-time. Hardcoding `platform-ui` in Promtail's autodiscovery would break for any deployment that uses a different namespace. The values array lets deployments declare their actual frontend namespaces. | Hardcode `platform-ui`: rejected — wrong for most deployments. Don't autodiscover frontend at all: rejected — frontend logs (D10) are valuable and would be missed. |
| Bucket provisioning via Helm pre-install hook (NOT via the installer feature 045) — recommended default | The Helm pre-install hook keeps the chart self-contained — installing the observability chart provisions everything it needs. The installer (feature 045) path is a fallback for environments where the chart's S3 credentials lack bucket-create permission (e.g., production AWS where the IAM role for chart installation is read-only). Decision documented in research.md so the right path is clear. | Installer-only: rejected — couples the observability chart to the installer's own life cycle; chart can't be installed standalone for testing. Both: works — the Helm hook is idempotent (creates only if absent), the installer is a no-op if the bucket already exists. |
| Eight Python entrypoints to migrate, NOT nine — and the names are corrected | Field-guide research found the brownfield input's 9-entrypoint list contained four wrong filenames (`certifier_main` not `trust_certifier_main`, etc.) and one phantom (`reasoning_main` doesn't exist — reasoning is a Go satellite). The plan corrects each so future planners don't look for the wrong files. | Migrate all 9 names from the brownfield input: rejected — `reasoning_main.py` doesn't exist; following the wrong list creates broken PRs. |

## Dependencies

- **Feature 047 — Observability Stack** (existing): provides Grafana, Prometheus, Alertmanager, OTEL Collector, Jaeger. The Helm chart at `deploy/helm/observability/Chart.yaml` and `values.yaml` is extended additively. The 11 existing dashboards + 5 PrometheusRule alerts are preserved untouched.
- **Feature 071 / 072 (E2E kind harness)**: the new E2E suite under `tests/e2e/suites/observability/` runs against the existing kind cluster + the same Helm chart used in production per constitution rule 26.
- **Feature 079 (cost-governance)**: existing `cost-governance.yaml` dashboard exists; T030 audit decides whether to extend it with log panels or add a sibling `cost-governance-extended.yaml`. Cost-anomaly log alert (FR-542.4) correlates with feature 079's `cost_anomalies` table.
- **Feature 080 (incident-response)**: the `IncidentTriggerInterface` at `incident_response/trigger_interface.py:8–48` is the route the `AuditChainAnomaly` Loki alert fires through (FR-542.3). D19 dashboard reads from feature 080's `incidents` and `post_mortems` tables (no existing equivalent — verified greenfield by field guide).
- **Feature 081 (multi-region-ops)**: existing `multi-region-ops.yaml` dashboard exists; T030 audit decides extend vs add. Multi-region log federation uses the `region` label per feature 081's contract.
- **Feature 077 (notifications)**: existing `notifications-channels.yaml` dashboard exists; T030 audit decides extend vs add. Loki ruler alerts route through the existing Alertmanager configuration from feature 047.
- **Feature 045 (installer)**: alternative provisioning path for the `platform-loki-chunks` bucket (the Helm pre-install hook is the recommended default).
- **Feature 046 (CI/CD pipeline)**: hosts the new lint check enforcing rule 22 (Loki label cardinality discipline).
- **Audit chain BC** (`apps/control-plane/src/platform/audit/service.py:48–72`): the `append()` method is modified to additively emit a structured log entry inside the existing transaction (T020).
- **Constitution § "Observability Extension (UPD-034 and UPD-035)"** — names this feature and reserves the `platform-loki-chunks` bucket. The constitutional 14-dashboard target is the canonical brief.
- **Constitutional feature flags** (`FEATURE_STRUCTURED_LOGGING`, `FEATURE_LOKI_ENABLED`, `FEATURE_PROMTAIL_REDACTION`) — already declared at constitution lines 892–894; this plan wires them.
- **Constitutional rule 22** — Loki label allowlist; T060 delivers the CI lint that enforces it.
- **Constitutional rule 26** — journeys against real backends; T053 extends the existing operator J06 incident-response journey.
- **Constitutional rule 27** — dashboards as ConfigMaps with the `grafana_dashboard: "1"` label; the existing `_helpers.tpl` provides the label helper.
- **Generic S3 client (Principle XVI)** — Loki uses `S3_ENDPOINT_URL` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` env vars (provided by the existing `SecretProvider` at chart-install time).
- **OTEL Collector existing configuration** at `deploy/helm/observability/values.yaml:43–93` — UNCHANGED. Logs do NOT flow through the collector; they go via Promtail directly.

## Wave Placement

**Wave 12** — last in the audit-pass execution order, after notifications (077, Wave 5), cost governance (079, Wave 7), incident response (080, Wave 8), multi-region (081, Wave 9), tags/labels/saved-views (082, Wave 10), and accessibility/i18n (083, Wave 11). The brownfield input's plan said Wave 9, but Wave 9 is feature 081's slot in the established cadence; this feature must come AFTER all the audit-pass BCs whose dashboards it visualises so the dashboards have real data to render. Without that ordering, the dashboards ship with empty panels and SC-007 / SC-008 cannot be verified at the wave's close.

**Note on the input's effort estimate** — the planning input estimated 6 story points / ~5 days (with two devs ~3 calendar days). The plan as designed is **realistic but moderately understated**:

- 11 baseline dashboards already exist (NOT 7 as input claimed) — meaning the dashboard authoring is materially LESS work than the input estimated for some IDs (D15 / D16 / D18 / D14 may extend existing files). This **reduces** the effort.
- 8 control-plane entrypoints (NOT 9) to instrument with `configure_logging()` — small but each one is a careful thread-of-execution review. Roughly the same as input estimated.
- 6 Go satellites get the new `internal/logging/` package (the brownfield input mentioned 4 satellites; the field guide identified 6 — runtime-controller, sandbox-manager, reasoning-engine, simulation-controller, hostops-broker, browser-worker per CLAUDE.md). **Increases** the effort by ~50%.
- The audit-BC transactional log emission is a small but careful change (the documented inversion of the fire-and-forget rule needs explicit pair-review). Adds ~half-day.
- The bucket provisioning (Helm pre-install hook OR installer task) is half-day.
- The CI lint check for rule 22 enforcement is half-day.
- 7 new E2E test files in `tests/e2e/suites/observability/` is a real day of work.

Net: the planning input's **5-day, 2-dev (3 calendar days)** estimate is workable but tight for the dashboard de-duplication audit + the 6 Go satellites + the transactional audit-log emission. Recommend **6–7 calendar days for two devs** with a buffer for the dashboard audit + the audit-BC pair review. The plan flags this rather than rejecting the input estimate outright — for a feature this heavily pre-designed, the input estimate is closer to reality than prior features in this session.

**Wave-internal split** (similar to prior features' A/B/C suggestions):
- **Wave 12A**: Loki + Promtail Helm dependencies + bucket provisioning + Loki data source + alert rules wiring (~1.5 days; Phases 1–2 + Phase 6 of the input).
- **Wave 12B**: Cross-runtime structured logging (Python `structlog` + Go ContextHandler + Next.js isomorphic logger) — parallelizable across three devs (~1 day each, ~2 days calendar with parallelism).
- **Wave 12C**: Audit-BC transactional log emission + the dashboard de-duplication audit (T027) + dashboard authoring (~1.5 days).
- **Wave 12D**: E2E suite + CI lint check + documentation + agent-context update (~1.5 days).

Total: **~5.5 calendar days for two devs**, in line with the input's 3-day estimate when parallelism + de-duplication savings net out.
