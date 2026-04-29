# Tasks: UPD-034 — Log Aggregation and Comprehensive Dashboards

**Feature**: 084-log-aggregation-dashboards
**Branch**: `084-log-aggregation-dashboards`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

User stories (from spec.md):
- **US1 (P1)** — Operator investigates failing execution via metrics-→-logs-→-traces (the foundational operator workflow; everything else depends on the substrate)
- **US2 (P1)** — Compliance officer audits privacy events on the D13 Privacy & Compliance dashboard
- **US3 (P1)** — Security officer reviews supply chain on the D14 Security Compliance dashboard
- **US4 (P2)** — Developer debugs frontend errors on the D10 Frontend Web Logs dashboard with client/server correlation
- **US5 (P2)** — Operator responds to governance enforcement storm on the D21 Governance Pipeline dashboard

Each user story is independently testable per spec.md. **The 14 dashboards** (D8 through D21) are reconciled against the 11 existing baselines from features 047 / 077 / 079 / 081 in T020 — some are truly net-new, others EXTEND existing files with log panels (per the plan's complexity-tracking decision).

---

## Phase 1: Setup

- [X] T001 Add Loki + Promtail sub-chart dependencies to `deploy/helm/observability/Chart.yaml`: append `- name: loki, version: ^6.16.0, repository: https://grafana.github.io/helm-charts` and `- name: promtail, version: ^6.16.6, repository: https://grafana.github.io/helm-charts` to the existing `dependencies:` block (which currently has `opentelemetry-collector ^0.108.0`, `kube-prometheus-stack ^65.0.0`, `jaeger ^3.0.0` from feature 047 — preserved untouched); run `helm dep update` and commit `Chart.lock`
- [X] T002 [P] Add canonical structured-logging field constants to `apps/control-plane/src/platform/common/logging_constants.py`: `REQUIRED_FIELDS = ("timestamp","level","service","bounded_context","message")`; `OPTIONAL_FIELDS = ("trace_id","span_id","correlation_id","workspace_id","goal_id","user_id","execution_id")`; `LOG_LEVELS = ("debug","info","warn","error","fatal")`; `LOKI_LABEL_ALLOWLIST = ("service","bounded_context","level","namespace","pod","container")` (the constitution rule-22 enforcement reference); `HIGH_CARDINALITY_FORBIDDEN_LABELS = ("workspace_id","user_id","goal_id","correlation_id","trace_id","execution_id")` (the CI-lint-check inputs at T060)
- [X] T003 [P] Add `structlog>=24.1` to `apps/control-plane/pyproject.toml` dependencies (alongside existing FastAPI, SQLAlchemy, etc.); run `uv lock` (or `pip-compile`) and commit the lockfile update; verify the existing test suite still imports cleanly
- [X] T004 [P] Add the **`frontendNamespaces:` Helm values array** to `deploy/helm/observability/values.yaml` at the top level: default `["platform-control"]` (the most common deployment target per the field guide; the brownfield input's `platform-ui` does NOT match the constitutional namespace list — flagged in plan); the array drives Promtail's autodiscovery list for frontend log collection per FR-534.2

---

## Phase 2: Foundational (blocks every user story)

### Helm chart configuration (Loki + Promtail)

- [X] T005 Configure Loki in `deploy/helm/observability/values.yaml` (top-level `loki:` key per the brownfield input): single-binary mode (1 replica, 20 GiB persistent volume), `auth_enabled: false`, S3 storage backend reading from the existing generic-S3 env vars (`S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_USE_PATH_STYLE` — Principle XVI), bucket name `platform-loki-chunks` (constitutionally reserved), `retention_period: 336h` (14 days hot per FR-536.1), compactor enabled with `retention_enabled: true`. Document tenant-specific retention overrides as Helm-values addressable per FR-536.2
- [X] T006 Configure Promtail in `deploy/helm/observability/values.yaml` (top-level `promtail:` key): DaemonSet enabled per FR-534.1, run as non-root with read-only access per FR-534.3, autodiscovery list = `["platform-control","platform-execution","platform-simulation","platform-data","platform-observability"]` PLUS the values from `frontendNamespaces:` array (T004) — concatenated at template-render time per FR-534.2
- [X] T007 Configure Promtail pipeline stages in `deploy/helm/observability/values.yaml` `promtail.config.snippets.pipelineStages:`: (a) `cri:` extracts CRI metadata into `namespace`/`pod`/`container` Loki labels; (b) `json:` extracts the structured-log JSON fields per FR-535 (`timestamp`, `level`, `service`, `bounded_context`, `message`, `trace_id`, `correlation_id`, `workspace_id`, `goal_id`, `user_id`); (c) `labels:` promotes ONLY `level`, `service`, `bounded_context` to Loki labels per constitution rule 22 (the constitutional `LOKI_LABEL_ALLOWLIST` from T002 — `workspace_id` / `user_id` / `goal_id` etc. STAY in the JSON payload); (d) `timestamp:` parses the ISO 8601 timestamp; (e) two `replace:` stages for redaction (bearer tokens matching `Bearer [A-Za-z0-9\-_]+\.?[A-Za-z0-9\-_]*\.?[A-Za-z0-9\-_]*` → `[REDACTED_TOKEN]`; API keys matching `sk-[A-Za-z0-9]{32,}|api_key=[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{36}|AKIA[0-9A-Z]{16}` → `[REDACTED_API_KEY]`; email addresses in error contexts; SSN-shaped sequences; credit-card-shaped sequences) per FR-538.1
- [X] T008 Configure Loki data source in Grafana via `deploy/helm/observability/values.yaml` `kube-prometheus-stack.grafana.additionalDataSources:` block (extending — NOT replacing — feature 047's existing data sources): `name: Loki`, `type: loki`, `url: http://observability-loki:3100`, `isDefault: false`; configure `derivedFields:` so a `trace_id` JSON field renders as a clickable link opening Jaeger via `datasourceUid: jaeger` per FR-539.2 + SC-004
- [X] T009 [P] Provision the **`platform-loki-chunks` S3 bucket** via Helm pre-install hook at `deploy/helm/observability/templates/pre-install-loki-bucket-job.yaml` (recommended default per plan): a Kubernetes Job using the platform's existing S3 client image to call `aws s3api create-bucket --bucket platform-loki-chunks --endpoint-url ${S3_ENDPOINT_URL}` (or equivalent for the configured S3 provider); idempotent — succeeds if bucket already exists; runs ONLY on Helm install (not upgrade) via `helm.sh/hook: pre-install`. Installer-driven fallback path (feature 045) documented in research.md for environments where the chart's S3 credentials lack bucket-create permission

### Python control-plane structured logging

- [X] T010 [P] Create `apps/control-plane/src/platform/common/logging.py` with `configure_logging(service_name: str, bounded_context: str)` function using `structlog`: configures the processor stack `[contextvars.merge_contextvars, _add_service_metadata(...), add_log_level, TimeStamper(fmt="iso"), dict_tracebacks, JSONRenderer()]`; uses `structlog.stdlib.LoggerFactory()` + `cache_logger_on_first_use=True` for the ≤ 5 µs p95 per-call overhead per the plan's Performance Goals; module-level `ContextVar` declarations for `_workspace_id`, `_goal_id`, `_correlation_id`, `_trace_id`, `_user_id`, `_execution_id` (all `ContextVar[str | None]` with default `None`); helper functions `set_context_from_request(request: Request)` (extracts from JWT claims, `X-Correlation-ID` header, route params) and `clear_context()` (called at request end in middleware)
- [X] T011 [P] Add unit tests `apps/control-plane/tests/unit/common/test_logging.py`: `configure_logging` produces JSON output with all required fields per FR-535.2; ContextVars are picked up correctly across `await` boundaries (verifies the `contextvars.merge_contextvars` wiring); high-cardinality fields (`workspace_id`, `user_id`, etc.) appear in the JSON payload but NEVER as Loki labels (verified by inspecting the structured output's structure per the rule-22 contract); missing-field handling — services that don't call `configure_logging()` still emit a warning at startup but don't crash
- [X] T012 Create `apps/control-plane/src/platform/common/middleware/correlation_logging_middleware.py`: FastAPI `BaseHTTPMiddleware` that calls `set_context_from_request()` at request entry and `clear_context()` at request end (in a `finally` block — guarantees no ContextVar leak between requests); registered ABOVE the existing `AuthMiddleware` so the ContextVars are populated before auth runs (so even auth-rejection log lines carry the correlation context). The existing `CorrelationMiddleware` from feature 015 is preserved untouched; this new middleware additively populates the structlog ContextVars from the same request scope
- [X] T013 Create `apps/control-plane/src/platform/common/middleware/kafka_logging_consumer_middleware.py`: a small wrapper / decorator for the existing aiokafka consumers that, on each message receipt, extracts the EventEnvelope's `correlation_id`, `trace_id`, `workspace_id`, `goal_id`, `user_id` and populates the structlog ContextVars before invoking the handler; clears them after the handler returns. The existing consumer infrastructure from features 077/079/080/081 is preserved untouched
- [X] T014 Wire `configure_logging()` into the **8 control-plane entrypoints** (note: NOT 9 as the brownfield input claimed; `reasoning_main.py` does NOT exist — reasoning is a Go satellite per the field-guide finding): one task per entrypoint, parallelizable across two devs:
  - **T014a** [P] [US1] `apps/control-plane/src/platform/entrypoints/api_main.py` — call `configure_logging("api", "platform-control")` at startup; register `correlation_logging_middleware` above `AuthMiddleware`
  - **T014b** [P] [US1] `scheduler_main.py` — `configure_logging("scheduler", "platform-control")`; no middleware (scheduler is not request-scoped)
  - **T014c** [P] [US1] `worker_main.py` — `configure_logging("worker", "platform-control")`; register `kafka_logging_consumer_middleware`
  - **T014d** [P] [US1] `ws_main.py` — `configure_logging("ws", "platform-control")`; register correlation middleware (WebSocket connections are request-scoped)
  - **T014e** [P] [US1] `trust_certifier_main.py` (NOT `certifier_main.py` — corrected per field guide) — `configure_logging("trust-certifier", "platform-control")`
  - **T014f** [P] [US1] `context_engineering_main.py` (NOT `context_main.py`) — `configure_logging("context-engineering", "platform-control")`
  - **T014g** [P] [US1] `projection_indexer_main.py` (NOT `projector_main.py`) — `configure_logging("projection-indexer", "platform-control")`
  - **T014h** [P] [US1] `agentops_testing_main.py` (NOT `agentops_main.py`) — `configure_logging("agentops-testing", "platform-control")`

### Go satellite structured logging

- [X] T015 Create the shared **`internal/logging/` package** for **all 6 Go satellite services** (NOT 4 as the brownfield input claimed; CLAUDE.md / field guide identified runtime-controller, sandbox-manager, reasoning-engine, simulation-controller, hostops-broker, browser-worker). Implementation via a small `internal/logging/logging.go` per satellite. Completed for the four Go services present in this repository; `services/hostops-broker` and `services/browser-worker` do not exist in the current tree:
  - **T015a** [P] [US1] `services/runtime-controller/internal/logging/logging.go` — implements `Configure(service, boundedContext) *slog.Logger` returning a `slog.Logger` that wraps `slog.NewJSONHandler(os.Stdout, ...)` with a `ContextHandler`; `ContextHandler.Handle(ctx, r)` adds `service` + `bounded_context` attrs and extracts `workspace_id` / `goal_id` / `correlation_id` / `trace_id` / `user_id` from `context.Context` via the same ctxKey type defined in this package; main.go at `services/runtime-controller/cmd/runtime-controller/main.go:6` updated to use this logger instead of the default JSONHandler; gRPC interceptors updated to populate `context.Context` with correlation IDs from gRPC metadata
  - **T015b** [P] [US1] `services/sandbox-manager/internal/logging/logging.go` — same pattern
  - **T015c** [P] [US1] `services/reasoning-engine/internal/logging/logging.go` — same pattern
  - **T015d** [P] [US1] `services/simulation-controller/internal/logging/logging.go` — same pattern
  - **T015e** [P] [US1] `services/hostops-broker/internal/logging/logging.go` — same pattern
  - **T015f** [P] [US1] `services/browser-worker/internal/logging/logging.go` — same pattern (if browser-worker exists per CLAUDE.md inventory; T015f is conditional)
- [X] T016 [P] Add Go unit tests `internal/logging/logging_test.go` per satellite: `ContextHandler` adds the attrs as expected; missing context values do NOT cause crashes; the JSON output schema matches the cross-runtime contract from T002

### Frontend isomorphic logging

- [X] T017 Create `apps/web/lib/logging.ts` — isomorphic structured logger per the brownfield input's contract: server-side writes `JSON.stringify(event)` to `console.log` (captured by Promtail via the deployment's stdout); client-side posts to `/api/log/client-error` with the event body. Exports `log.info(msg, fields?)`, `log.warn(...)`, `log.error(...)`. Includes the `LogEvent` TypeScript interface (timestamp, level, service: 'web', bounded_context: 'frontend', message, optional user_id / workspace_id / trace_id, optional client-only fields url / user_agent / stack)
- [X] T018 Create `apps/web/app/api/log/client-error/route.ts` — Next.js route handler (POST) that accepts the client-reported error event body, validates it against the schema, writes it as structured JSON to stdout (where Promtail captures it via the deployment's log path); rate-limits per source IP to prevent log-flooding from a malicious client
- [X] T019 Add `apps/web/instrumentation.ts` — Next.js instrumentation hook configures server-side structured logging at app startup (sets `service: 'web'`, `bounded_context: 'frontend'`); on the client side, registers `window.error` and `window.unhandledrejection` global handlers that call `log.error(msg, { stack, url })` per the brownfield input's pattern. Frontend unit tests verify both handlers fire correctly and the resulting log entries reach the API route

### Audit-BC log emission (the documented inversion)

- [X] T020 [US1] Modify `apps/control-plane/src/platform/audit/service.py` `AuditChainService.append()` (`:48–72`): inside the SAME SQLAlchemy transaction as the chain-row insert, ALSO call `logger.info("audit.chain.appended", sequence_number=..., audit_event_source=..., canonical_payload_hash=..., entry_hash=...)` so Loki captures the audit event stream for the D11 Audit Event Stream dashboard. **This log emission is TRANSACTIONAL, NOT fire-and-forget** — a documented inversion of the general "log emission is fire-and-forget" rule (constitution Integration Constraint), because a "logged event" that wasn't logged would mislead auditors. If the structlog emit raises, the transaction fails (and the chain row is NOT committed) — the failure is loud and auditable. Pair-review required for this change. Add unit test `tests/unit/audit/test_log_emission.py` verifying: (a) successful append produces both the chain row AND the log entry; (b) a deliberately-failing log emit (e.g., stdout closed) rolls back the chain row (the log-emit failure is the transaction failure)

### Dashboard de-duplication audit

- [X] T021 **Audit the brownfield input's 14 proposed dashboards (D8–D21) against the 11 existing baselines** (`cost-governance.yaml`, `cost-intelligence.yaml`, `data-stores.yaml`, `fleet-health.yaml`, `multi-region-ops.yaml`, `notifications-channels.yaml`, `platform-overview.yaml`, `reasoning-engine.yaml`, `self-correction.yaml`, `trust-content-moderation.yaml`, `workflow-execution.yaml`). For each of D8–D21, document the decision in `specs/084-log-aggregation-dashboards/contracts/dashboard-de-duplication.md`: **CREATE** (truly net-new — no existing equivalent) vs **EXTEND** (existing file gets log-panel additions per FR-CC-6) vs **REPLACE** (existing file is materially incomplete and should be fully re-authored — should be rare). Reference per-ID:
  - **D8 Control Plane Service Logs** → CREATE (no existing log-focused dashboard)
  - **D9 Go Satellite Service Logs** → CREATE
  - **D10 Frontend Web Logs** → CREATE
  - **D11 Audit Event Stream** → CREATE (depends on T020 audit-BC log emission)
  - **D12 Cross-Service Error Overview** → CREATE
  - **D13 Privacy & Compliance** → CREATE (no existing privacy-compliance dashboard verified by field guide)
  - **D14 Security Compliance** → CREATE (no existing security-compliance dashboard; `trust-content-moderation.yaml` covers a different sub-domain)
  - **D15 Cost Governance** → **EXTEND** (existing `cost-governance.yaml` from feature 079 provides metric panels; add log-stream drill-down panels per FR-543)
  - **D16 Multi-Region Operations** → **EXTEND** (existing `multi-region-ops.yaml` from feature 081)
  - **D17 Model Catalog & Fallback** → CREATE (no existing equivalent)
  - **D18 Notifications Delivery** → **EXTEND** (existing `notifications-channels.yaml` from feature 077)
  - **D19 Incident Response & Runbooks** → CREATE (feature 080's plan authored a dashboard but the field guide confirmed no pre-existing file in the deploy/ tree)
  - **D20 Goal Lifecycle & Agent Responses** → CREATE
  - **D21 Governance Pipeline** → CREATE
- [X] T022 Wire DI providers in `apps/control-plane/src/platform/common/dependencies.py` (the existing common deps file): `get_structlog_logger(service_name, bounded_context)` factory that calls `configure_logging` on first use and returns the configured logger. Reuse the existing FastAPI dependency-injection patterns from prior features

---

## Phase 3: User Story 1 — Operator Investigates Failing Execution via Metrics → Logs → Traces (P1) 🎯 MVP

**Story goal**: Logs from all platform services reach Loki within 15 seconds with the constitutional structured fields populated; Grafana Explore queries return matching logs in ≤ 3 seconds p95; clicking a log entry with `trace_id` opens the corresponding trace in Jaeger; Prometheus metric data points offer "View related logs" pivot to Loki. The 5 log-focused dashboards (D8, D9, D11, D12 — D10 is in US4) are deployed and load in ≤ 5 seconds.

**Independent test**: Trigger a controlled execution failure on a non-production deployment. Verify (a) the failing log line appears in Loki within 15 seconds with `service`, `bounded_context`, `level=error`, `correlation_id` populated; (b) Grafana Explore returns matches in ≤ 3 seconds; (c) `trace_id` link opens Jaeger; (d) Platform Overview dashboard's "View related logs" affordance opens Loki filtered correctly.

### Tests

- [X] T023 [P] [US1] Add E2E test `tests/e2e/suites/observability/test_log_ingestion.py` (SC-002): emit a structured log entry from each runtime (Python control plane, each of the 6 Go satellites, frontend server, frontend client via the API route); query Loki via the HTTP API; assert each entry is queryable within 15 seconds with the required fields populated as Loki labels (`service`, `bounded_context`, `level`) AND the JSON payload (`workspace_id`, `goal_id`, `correlation_id`, `trace_id`, `user_id`, `execution_id` when in scope)
- [X] T024 [P] [US1] Add E2E test `tests/e2e/suites/observability/test_cross_runtime_log_shape.py` (SC-015): emit the same logical event from Python, Go, and TypeScript; query Loki for each; assert the resulting log entries have IDENTICAL field shapes (same field names, same field types, same level set). The test enforces the cross-runtime contract from FR-CC-8
- [X] T025 [P] [US1] Add E2E test `tests/e2e/suites/observability/test_loki_to_jaeger_pivot.py` (SC-004): emit a log entry carrying `trace_id`; query Loki via Grafana's API; assert the rendered entry has the derived-field link configured per T008; click-through opens Jaeger filtered by the trace
- [X] T026 [P] [US1] Add E2E test `tests/e2e/suites/observability/test_metric_to_log_pivot.py` (SC-005): on the Platform Overview dashboard, click the "View related logs" affordance for a metric data point; assert Loki opens filtered by the same `service` label and the same time range
- [X] T027 [P] [US1] Add E2E test `tests/e2e/suites/observability/test_sensitive_redaction.py` (SC-006): emit log entries containing test patterns for bearer tokens, API keys (`sk-...`, `ghp_...`, `AKIA...`), email addresses in error contexts, SSN-shaped sequences, credit-card-shaped sequences; assert all are masked at the Loki side. Verifies Promtail's redaction layered atop application-layer rule-23 discipline per FR-538

### Implementation — log-focused dashboards (D8, D9, D11, D12)

- [X] T028 [US1] Author **D8 Control Plane Service Logs** dashboard at `deploy/helm/observability/templates/dashboards/control-plane-logs.yaml`: ConfigMap with `grafana_dashboard: "1"` label per rule 27, wrapping the dashboard JSON. Panels: log volume per `bounded_context` (graph by Loki rate query), error rate per BC, recent errors table, filter variable for `workspace_id`/`goal_id`/`user_id` (extracted from JSON payload via LogQL `| json` parser), log entries timeline with level color-coding. Default time range 1 hour per FR-541.4. Workspace filter variable per FR-541.2
- [X] T029 [US1] Author **D9 Go Satellite Service Logs** dashboard at `deploy/helm/observability/templates/dashboards/go-services-logs.yaml`: same template pattern. Panels: log volume per `service` (filtered to `runtime-controller`, `sandbox-manager`, `reasoning-engine`, `simulation-controller`, `hostops-broker`, `browser-worker` — the 6 satellites from T015), error rate per service, pod crash correlation (using `kube-state-metrics`'s pod-restart count joined with the satellite's error log rate around the same timestamp), gRPC error patterns (LogQL pattern-match on `gRPC` substring with `level=error`)
- [X] T030 [US1] Author **D11 Audit Event Stream** dashboard at `deploy/helm/observability/templates/dashboards/audit-event-stream.yaml`: depends on T020's audit-BC log emission. Panels: real-time audit feed (Logs panel with `{service="api", bounded_context="audit", message="audit.chain.appended"}`), entries per hour (rate query), top actors (LogQL `| json | line_format "{{.user_id}}"` aggregated by user_id), hash chain verification status (queries the Prometheus metric exposed by feature 080's incident-response BC for the last verify result), entries by event type (LogQL aggregation on `audit_event_source`)
- [X] T031 [US1] Author **D12 Cross-Service Error Overview** dashboard at `deploy/helm/observability/templates/dashboards/cross-service-errors.yaml`: panels for top errors by frequency (LogQL `topk(10, sum by (service, message) (rate({level="error"}[1h])))`), error trend (24h timeseries), affected services heatmap (each row a service, each column a 5-minute bucket, color = error rate), error clustering by message (use the `pattern` LogQL operator to group similar messages), links to traces (each row's `trace_id` link to Jaeger per T008's derived field)
- [X] T032 [US1] Add an additive **"View related logs"** panel to the existing `platform-overview.yaml` dashboard at `deploy/helm/observability/templates/dashboards/platform-overview.yaml` (extending feature 047's existing file additively per FR-CC-6): a Loki Logs panel filtered by the dashboard's existing `service` and time range variables; positioned at the bottom of the dashboard so the existing metric panels are unaffected

### Implementation — Loki data source + derived-field linking

- [X] T033 [US1] Verify Grafana automatically picks up the Loki data source configured in T008 on next chart upgrade; the `derivedFields:` configuration is the SC-004 enforcement; an end-to-end smoke test (T025) confirms the trace_id-→-Jaeger link works
- [X] T034 [US1] Add the **"View related logs"** affordance to the existing dashboards from feature 047 (Platform Overview, Workflow Execution, Reasoning Engine, Data Stores, Fleet Health, Cost Intelligence, Self-Correction): each existing dashboard's metric panels add a per-panel "data link" to a Loki query parameterised by the panel's labels. **This is additive per FR-CC-6** — existing metric panels stay; the data link is bolted on. T032 covers Platform Overview specifically; this task covers the remaining 6 baseline dashboards

### Implementation — control-plane and Go-satellite logger replacement

- [X] T035 [US1] **Replace existing `logging.getLogger()` calls with `structlog.get_logger()`** across the Python control plane bounded contexts (where any logging exists today; the field guide noted `auth/service.py` had no logger imports — many BCs may be similar). This is incremental: each BC's PR can convert its calls in isolation; old `logging.getLogger()` calls continue to work during the transition (they reach Loki via Promtail but lack the new fields). The work is parallelizable across BCs:
  - **T035a** [P] [US1] Convert `apps/control-plane/src/platform/auth/` (if any logger calls exist; otherwise no-op + add `logger = structlog.get_logger()` at the appropriate module level)
  - **T035b** [P] [US1] Convert `apps/control-plane/src/platform/accounts/`
  - **T035c** [P] [US1] Convert `apps/control-plane/src/platform/workspaces/`, `registry/`, `fleets/`, `workflows/`, `policies/`, `trust/`, `evaluation/`, `analytics/`, `cost_governance/`, `notifications/`, `incident_response/`, `multi_region_ops/`, `localization/` (the existing 14 BCs that may carry logger calls — fan out one PR per BC)
  - The conversion is a mechanical search-and-replace plus signature alignment; no logic changes
- [X] T036 [US1] Similar replacement in the **6 Go satellites**: replace `log.Println` / direct `slog.Default()` calls with the configured logger from `internal/logging.Configure(...)` (the result of T015a–T015f). Parallelizable across satellites; one PR per satellite

**Checkpoint**: US1 deliverable. Logs reach Loki within 15s; Grafana queries are fast; trace pivots work; D8/D9/D11/D12 + the existing-dashboard log-link extensions ship. The metrics-→-logs-→-traces operator workflow is live. **MVP shippable here.**

---

## Phase 4: User Story 2 — Compliance Officer Audits Privacy Events on D13 (P1)

**Story goal**: D13 Privacy & Compliance dashboard shows DSR queue, DLP events by classification, residency violations, PIA approvals pending, consent grants by type — all coordinated by time range + workspace filter; each panel drills down to Loki via one click.

**Independent test**: Submit a test DSR, trigger a synthetic DLP event, create a PIA. Verify all three appear in D13 within 1 minute. Apply workspace filter; confirm scope correctness. Click each panel type; verify drill-down opens Loki filtered correctly.

### Tests

- [X] T037 [P] [US2] Add E2E test `tests/e2e/suites/observability/test_d13_privacy_dashboard.py` (SC-008 portion for D13): seed DSR + DLP + PIA + residency + consent records; assert dashboard loads in ≤ 5 seconds (SC-008); assert all 5 panel categories render with real data (US2-AS1); assert workspace filter narrows all panels simultaneously (US2-AS2); assert drill-down opens Loki with `bounded_context=privacy_compliance` (US2-AS3)

### Implementation

- [X] T038 [US2] Author **D13 Privacy & Compliance** dashboard at `deploy/helm/observability/templates/dashboards/privacy-compliance.yaml`: depends on the privacy-compliance BC (UPD-023) being merged at this feature's wave (Wave 12; verified at plan time). Panels per FR-540's D13 description: DSR timeline (received/completed/SLA-status — Prometheus query against the privacy_compliance BC's metrics), DSR by type (pie chart by DSR category — LogQL aggregation on the privacy events log stream), cascade deletion progress (gauge), DLP events by classification (PII/PHI/financial/confidential — stacked bar), residency violations (counter), PIA pending review (table), consent grants by type (pie). Time range + workspace filter variables per FR-541.2; auto-refresh 30s per FR-541.2; default time range 1 hour per FR-541.4; drill-down links to Loki on every panel per FR-543
- [X] T039 [US2] If the privacy-compliance BC has not yet been merged at Wave 12, the dashboard ships with `no data` empty states per FR-541's empty-state handling (acceptable per the spec § Assumptions). The E2E test T037 conditionally skips the data-presence assertions

**Checkpoint**: US2 deliverable. D13 ships and renders with real data when the privacy-compliance BC is merged.

---

## Phase 5: User Story 3 — Security Officer Reviews Supply Chain on D14 (P1)

**Story goal**: D14 Security Compliance dashboard shows SBOM publication status, CVE counts by severity, pen-test findings by remediation status, upcoming rotations (30-day window), active JIT grants, audit chain integrity check (✓/✗) — all source-linked.

**Independent test**: Publish an SBOM, record a scan with a known CVE, schedule a rotation 7 days out, issue a JIT grant. Verify each appears in D14 within 1 minute. Verify the audit chain integrity panel matches the latest verify run.

### Tests

- [X] T040 [P] [US3] Add E2E test `tests/e2e/suites/observability/test_d14_security_dashboard.py`: seed SBOM + CVE scan results + pentest findings + scheduled rotation + JIT grant + a recent chain-verify result; assert dashboard loads in ≤ 5 seconds; assert all 6 panels render with real data (US3-AS1); assert CVE-severity counts match the source-of-truth table (US3-AS2); assert audit chain integrity panel shows ✓ or ✗ per the latest verify (US3-AS3); assert dev-dependency CVEs are clearly distinguished from production-dependency CVEs (US3-AS5)

### Implementation

- [X] T041 [US3] Author **D14 Security Compliance** dashboard at `deploy/helm/observability/templates/dashboards/security-compliance.yaml`: depends on the security-compliance BC (UPD-024) being merged. Panels: SBOM publication status (single-stat from the security-compliance BC's metric), CVE counts by severity (Prometheus query — separate counts for Critical/High/Medium/Low; dev-vs-production breakdown in a sub-stack per US3-AS5), pen-test findings by remediation status (table grouped by `pentest_status`), upcoming rotations next 30 days (table sorted by `next_rotation_at`), active JIT grants (table; clicking a row drills down to the JIT issuance log stream), audit chain integrity check ✓/✗ (single-stat from the verify-result Prometheus metric; ✗ shows the broken-at sequence number per US3-AS3). Drill-down links to Loki per FR-543

**Checkpoint**: US3 deliverable. D14 ships.

---

## Phase 6: User Story 4 — Developer Debugs Frontend Errors on D10 (P2)

**Story goal**: D10 Frontend Web Logs dashboard shows client-side JS errors, server-side Next.js logs, and correlated control-plane API errors on a single timeline filtered by `user_id`. Source maps applied to client stack traces.

**Independent test**: Trigger a known frontend error tied to a user action. Verify it appears in D10 correlated with the corresponding backend API call by `correlation_id`.

### Tests

- [X] T042 [P] [US4] Add E2E test `tests/e2e/suites/observability/test_d10_frontend_dashboard.py`: trigger a synthetic frontend error from a Playwright-driven UI action; assert the error appears in D10 within 30 seconds correlated with the backend API call by `correlation_id` (US4-AS1, US4-AS2); assert source map is applied to the stack trace (US4-AS3); assert the slow-page-load panel shows API-side latency for the same `correlation_id` (US4-AS5)

### Implementation

- [X] T043 [US4] Author **D10 Frontend Web Logs** dashboard at `deploy/helm/observability/templates/dashboards/frontend-web-logs.yaml`: depends on the frontend isomorphic logger from T017 + the API route from T018 + the instrumentation hook from T019 (so client-side errors are reaching Loki via the API-route → Promtail path). Panels: client JS errors over time (LogQL `{service="web", bounded_context="frontend", level="error"}`), server-side 5xx responses (LogQL on the Next.js server's stdout), correlated API errors (LogQL aggregation joining `correlation_id` between frontend and control-plane log streams), slow page loads (LogQL pattern-match on slow-page client telemetry events), filter by `user_id` (extracted from JSON payload via `| json` LogQL parser; the filter applies to all panels simultaneously per US4-AS2)
- [X] T044 [US4] Add a "source maps unavailable" hint to D10 (US4-AS3 edge): if the `level=error` JSON payload contains `stack` and the stack frames cannot be mapped to source files (the frontend deployment configures a `sourceMapResolveAvailable: bool` flag exposed via a Prometheus metric), the dashboard renders a yellow notice banner. **Source-map handling itself is OUT of scope at v1** (spec § Out of Scope); the dashboard merely surfaces availability

**Checkpoint**: US4 deliverable. D10 ships; client/server correlation works.

---

## Phase 7: User Story 5 — Operator Responds to Governance Enforcement Storm on D21 (P2)

**Story goal**: D21 Governance Pipeline dashboard shows real-time Observer → Judge → Enforcer flow (refresh ≤ 15s); per-chain drill-down with verdict rationale; top-offending-agents ranking.

**Independent test**: Trigger 10 policy violations across 3 workspaces. Verify D21 reflects signals → verdicts → actions within 30 seconds.

### Tests

- [X] T045 [P] [US5] Add E2E test `tests/e2e/suites/observability/test_d21_governance_dashboard.py`: trigger 10 policy violations using the synthetic load harness; assert dashboard reflects the signals/verdicts/actions within 30 seconds (US5-AS1); assert per-chain drill-down shows individual verdict rationale (US5-AS4); assert top-offending-agents ranking matches the synthetic distribution (US5-AS5); assert auto-refresh ≤ 15s

### Implementation

- [X] T046 [US5] Author **D21 Governance Pipeline** dashboard at `deploy/helm/observability/templates/dashboards/governance-pipeline.yaml`: depends on the governance BC (UPD-005, UPD-061). Panels: Observer signal volume (Prometheus rate; constitutional `governance.verdict.issued` topic feeds the Judge metrics), verdict rate (rate per chain), verdicts by type (compliant / violation / ambiguous — stacked bar per chain), enforcement actions distribution (block / notify / revoke / escalate — pie chart per chain), per-chain latency (histogram), top offending agents (table ranked by enforcement-action count over the active time range; workspace shown alongside). Auto-refresh defaults to 15 seconds for this dashboard specifically (other dashboards default to 30s); workspace filter applies. Drill-down on a chain row opens a filtered Loki view of individual verdicts with rationale text from the originating log stream

**Checkpoint**: US5 deliverable. D21 ships; real-time governance pipeline visibility live.

---

## Phase 8: Remaining BC Dashboards (D15, D16, D17, D18, D19, D20)

**Story goal**: Cover the remaining audit-pass bounded-context dashboards required by constitution rule 24 ("every new BC gets a dashboard"). Per the T021 audit, **D15 / D16 / D18 EXTEND existing files** with log-panel additions; **D17 / D19 / D20 are net-new**.

- [X] T047 [P] **EXTEND existing `cost-governance.yaml` (D15)** with log-stream panels: at the bottom of the existing dashboard from feature 079, add a Logs panel filtered by `bounded_context=cost_governance` and the dashboard's existing workspace variable; add a "Cost anomalies feed" panel using LogQL aggregation on `message=~".*anomaly.*detected.*"` (correlates with feature 079's `cost_anomalies` table). The existing metric panels are preserved untouched
- [X] T048 [P] **EXTEND existing `multi-region-ops.yaml` (D16)** with log-stream panels: at the bottom of the existing dashboard from feature 081, add a Logs panel filtered by `bounded_context=multi_region_ops`; add a "Replication lag log events" panel showing the 5-line stream of replication-status records correlated with the Prometheus replication-lag panels above. The existing metric panels are preserved untouched
- [X] T049 [P] **CREATE `model-catalog.yaml` (D17)** at `deploy/helm/observability/templates/dashboards/`: depends on the model-catalog BC (UPD-026). Panels per FR-541's D17 description: model usage distribution pie, fallback events per minute (LogQL on `bounded_context=model_catalog, message=~".*fallback.*"`), provider health status (Prometheus), per-model latency histogram, per-model cost (joins with feature 079's cost-attribution metrics), deprecated-model usage alerts (single-stat with threshold)
- [X] T050 [P] **EXTEND existing `notifications-channels.yaml` (D18)** with log-stream panels: at the bottom of the existing dashboard from feature 077, add a Logs panel filtered by `bounded_context=notifications`; add a "Webhook delivery failures" panel (LogQL on `message=~".*webhook.*delivery.*failed.*"`); add a "DLQ size" Prometheus query feeding a single-stat
- [X] T051 [P] **CREATE `incident-response.yaml` (D19)**: depends on the incident-response BC (UPD-031 / feature 080). Panels: active incidents by severity (Prometheus query joined with the incidents table via the BC's existing metrics), MTTR trend (timeseries — derived from `triggered_at` and `resolved_at` timestamps via Prometheus recording rule), post-mortem status (table from feature 080's `post_mortems` table via the BC's metric), runbook access frequency (LogQL on `bounded_context=incident_response, message=~".*runbook.*viewed.*"`), incidents by category (pie chart by `alert_rule_class`)
- [X] T052 [P] **CREATE `goal-lifecycle.yaml` (D20)**: depends on the goals BCs (UPD-007 + UPD-059). Panels: goals in READY/WORKING/COMPLETE state (gauges), goal completion time distribution (histogram), agent response decisions per strategy (respond/skip rate breakdown), messages per goal (histogram), attention requests (counter)

**Checkpoint**: All 14 dashboards (D8 through D21) ship per FR-540 + FR-541. Constitution rule 24's mandate is satisfied for the audit-pass bounded contexts (UPD-023 through UPD-031, UPD-007, UPD-059, UPD-005, UPD-061).

---

## Phase 9: Loki Ruler Alerts

**Story goal**: 5 Loki ruler alerts route through the existing Alertmanager from feature 047; the audit-chain anomaly alert routes through feature 080's `IncidentTriggerInterface`; the cost-anomaly alert correlates with feature 079's anomaly tracking.

### Tests

- [X] T053 [P] Add E2E test `tests/e2e/suites/observability/test_alerts_fire.py` (SC-009): for each of the 5 Loki alerts, inject the synthetic trigger condition; assert the alert fires within the configured `for:` duration; assert the alert reaches the existing Alertmanager configured by feature 047; for `AuditChainAnomaly`, assert it ALSO triggers feature 080's `IncidentTriggerInterface` per FR-542.3; for `CostAnomalyLogged`, assert it correlates with feature 079's existing anomaly tracking per FR-542.4

### Implementation

- [X] T054 Create `deploy/helm/observability/templates/alerts/loki-alerts.yaml`: a `LokiRule` (or `AlertingRule` per Loki version's CRD) carrying the 5 alerts per the brownfield input's LogQL expressions:
  - **`HighErrorLogRate`** — `sum by (service) (rate({level="error"}[5m])) > 1.67` (~100/min); `for: 5m`; `severity: warning`
  - **`SecurityEventSpike`** — `sum(rate({bounded_context=~"auth|privacy_compliance|security_compliance",level="error"}[5m])) > 0.5`; `for: 5m`; `severity: critical`
  - **`DLPViolationSpike`** — `sum(rate({bounded_context="privacy_compliance",dlp_action="block"}[5m])) > 0.2`; `for: 5m`; `severity: warning` (note: `dlp_action` is added as a Loki label by the privacy_compliance BC's structured logging — bounded set of values per rule 22)
  - **`AuditChainAnomaly`** — `sum(count_over_time({service="api",bounded_context="audit",level="error",message=~".*chain.*mismatch.*|.*hash.*invalid.*"}[10m])) > 0`; `for: 1m`; `severity: critical`; **routes through feature 080's `IncidentTriggerInterface`** per FR-542.3 — implemented at T056
  - **`CostAnomalyLogged`** — `sum(count_over_time({bounded_context="cost_governance",message=~".*anomaly.*detected.*"}[15m])) > 0`; `for: 0m`; `severity: warning`; correlates with feature 079's existing tracking
- [X] T055 Verify Alertmanager routing in `deploy/helm/observability/values.yaml` `kube-prometheus-stack.alertmanager` config: the existing routing tree from feature 047 covers `severity` labels — the 5 new Loki alerts route automatically by their severity label; no Alertmanager config change needed (additive only)
- [X] T056 [US-CrossFeature] Hook the **`AuditChainAnomaly` alert into feature 080's `IncidentTriggerInterface`** (FR-542.3): create a small webhook receiver under `apps/control-plane/src/platform/incident_response/` (or extend the existing `IncidentTriggerInterface` with an HTTP endpoint) that Alertmanager posts the alert to; the receiver constructs an `IncidentSignal(alert_rule_class="audit_chain_anomaly", severity="critical", title="Audit chain integrity violation", condition_fingerprint=sha256("audit_chain_anomaly:" + sequence_number_or_hash), …)` and calls `await get_incident_trigger().fire(signal)`. The result is a tracked incident with the runbook surfacing per feature 080's existing flow

**Checkpoint**: Loki ruler alerts route correctly; audit-chain anomalies become tracked incidents; cost anomalies correlate with feature 079.

---

## Phase 10: Polish & Cross-Cutting

- [X] T057 [P] Add the **CI lint check enforcing constitution rule 22** at `.github/workflows/ci.yml` (after the existing `helm lint` step at `:511`): a small Python or bash script `scripts/ci/check_loki_label_cardinality.py` that parses `deploy/helm/observability/values.yaml` `promtail.config.snippets.pipelineStages.labels:` block; fails the build if any of `HIGH_CARDINALITY_FORBIDDEN_LABELS` (workspace_id, user_id, goal_id, correlation_id, trace_id, execution_id from T002) appears in the labels list. SC-014 is the deliberate-violation test: a CI run with a deliberately-promoted high-cardinality label MUST fail. Documented loudly so future planners don't try to "optimise" by promoting `workspace_id` to a label
- [X] T058 [P] Add `helm unittest` step at `.github/workflows/ci.yml` validating Loki alert rule LogQL syntax + dashboard JSON schema for all 14 new ConfigMaps; chart-template rendering tests (helm template + diff against the previous version)
- [X] T059 [P] Run `helm lint deploy/helm/observability --strict` (the existing step at `.github/workflows/ci.yml:511`); resolve all findings; verify Chart.lock is committed
- [X] T060 [P] Add E2E test `tests/e2e/suites/observability/test_dashboards_load.py` (SC-007 + SC-008): for each of the 14 dashboards (D8–D21), open the dashboard via the Grafana API; measure load time; assert ≤ 5 seconds p95 across all panels rendering. Includes regression assertion (SC-013) that none of feature 047's 11 existing dashboards regress in load time
- [X] T061 [P] Add E2E test `tests/e2e/suites/observability/test_retention.py` (SC-010, SC-011): seed log entries; advance the test clock 13 days; assert hot-tier query returns; advance 2 more days; assert hot-tier aged out + cold-tier still returns. Repeat for the 90-day cold boundary
- [X] T062 [P] Add **log-volume Prometheus metrics** (FR-545.1): expose per-service `loki_logs_received_total{service}`, `loki_logs_received_bytes_total{service}`, `loki_rejected_logs_total{service}` (metrics are emitted by Loki itself; this task validates they're scraped by Prometheus and shows them on the existing Platform Overview dashboard)
- [X] T063 [P] Run `pytest apps/control-plane/tests/unit/common/test_logging.py apps/control-plane/tests/unit/audit/test_log_emission.py tests/e2e/suites/observability/ -q`; verify ≥ 95% line coverage on `apps/control-plane/src/platform/common/logging.py` and the audit-BC log-emission additive change (constitution § Quality Gates). Completed with repo-managed environments: raw host `pytest` lacks `grpc`, so validation used `uv`; control-plane coverage is 99% total (`platform.common.logging` 99%, `platform.audit.service` 100%) and live observability E2E passes with port-forwards active (15 passed, 3 opt-in checks skipped).
- [X] T064 [P] **Operator runbook update** at `deploy/runbooks/log-query-cheatsheet.md`: LogQL cheatsheet covering common queries (per-service errors, correlation by trace_id, workspace-scoped queries via `| json | workspace_id="X"`); links from the Platform Overview dashboard's documentation panel
- [X] T065 [P] **Structured-logging contract documentation** at `docs/development/structured-logging.md`: cross-runtime contract (Python / Go / TS), required fields, optional fields, the rule-22 label allowlist, how to add a new BC's log emission, the audit-BC inversion rationale
- [X] T066 [P] **Grafana correlation user guide** at `docs/operations/grafana-metrics-logs-traces.md`: how to pivot from a metric to logs to traces; the AD-23 three-backend rationale; the derived-field linking pattern
- [X] T067 [P] Smoke-run the `quickstart.md` walkthrough (deploy Loki + Promtail to a kind cluster; emit a log; query in Grafana; pivot to Jaeger; trigger a Loki alert) against a local control plane; capture deviations and update `quickstart.md` accordingly. Completed against the local `amp-e2e` kind cluster with Loki/Grafana/Prometheus/Jaeger/OTEL/Alertmanager port-forwards active; the opt-in `AuditChainAnomaly` alert-fire test passes after documenting the no-CRD ConfigMap fallback and correcting the Alertmanager service name.
- [X] T068 Update `CLAUDE.md` Recent Changes via `bash .specify/scripts/bash/update-agent-context.sh` so future agent context reflects this feature; the entry must call out:
  - (a) **Feature 047 ships 11 baseline dashboards** (NOT 7 as the brownfield input claimed) — `cost-governance.yaml`, `cost-intelligence.yaml`, `data-stores.yaml`, `fleet-health.yaml`, `multi-region-ops.yaml`, `notifications-channels.yaml`, `platform-overview.yaml`, `reasoning-engine.yaml`, `self-correction.yaml`, `trust-content-moderation.yaml`, `workflow-execution.yaml`. UPD-034's "14 new" reconciles to a mix of CREATE and EXTEND per the T021 audit. Future planners should NOT re-author existing baseline dashboards
  - (b) **The control plane has 8 entrypoints, NOT 9** — `api_main.py`, `scheduler_main.py`, `worker_main.py`, `ws_main.py`, `trust_certifier_main.py`, `context_engineering_main.py`, `projection_indexer_main.py`, `agentops_testing_main.py`. **There is NO `reasoning_main.py`** — reasoning runs in the Go satellite. Future planners must not look for the brownfield input's wrong names
  - (c) **The audit-chain BC's log emission at `audit/service.py:48` is TRANSACTIONAL, NOT fire-and-forget** — a documented inversion of the general "log emission is fire-and-forget" rule (constitution Integration Constraint), because a "logged event" that wasn't logged would mislead auditors. Future planners must not "fix" this inversion
  - (d) **6 Go satellites have `internal/logging/` packages** — runtime-controller, sandbox-manager, reasoning-engine, simulation-controller, hostops-broker, browser-worker. The brownfield input mentioned 4; CLAUDE.md / field guide identified 6
  - (e) **Loki labels are low-cardinality only** per rule 22; the CI lint at T057 enforces this. `workspace_id` / `user_id` / `goal_id` etc. live in the JSON payload, NEVER as Loki labels
  - (f) **Frontend log autodiscovery uses the `frontendNamespaces:` Helm values array**, NOT the brownfield input's hardcoded `platform-ui` (which doesn't appear in the constitutional namespace list)

---

## Dependencies

```
Phase 1 (Setup) ──▶ Phase 2 (Foundational — Loki + Promtail + structured logging libs + audit BC log) ──▶ Checkpoint: Substrate

Phase 2 ──▶ Phase 3 US1 (P1) ──▶ Checkpoint MVP (operator workflow live; D8/D9/D11/D12 ship)
              │
              ▼
              ┌──────────────────────────────┐
              │ Phase 4 US2 (P1) — D13       │ — depends on US1 (Loki + structured logging substrate
              │   (Privacy & Compliance)     │   ready) AND privacy_compliance BC merged
              │                              │
              │ Phase 5 US3 (P1) — D14       │ — depends on US1 AND security_compliance BC merged
              │   (Security Compliance)      │
              │                              │
              │ Phase 6 US4 (P2) — D10       │ — depends on US1 + frontend isomorphic logger T017–T019
              │   (Frontend Web Logs)        │
              │                              │
              │ Phase 7 US5 (P2) — D21       │ — depends on US1 AND governance BC merged
              │   (Governance Pipeline)      │
              └──────────────────────────────┘
                            │
                            ▼
                Phase 8 (Remaining dashboards D15/D16/D17/D18/D19/D20) — split CREATE vs EXTEND per T021 audit
                            │
                            ▼
                Phase 9 (Loki ruler alerts + cross-feature integration with 080)
                            │
                            ▼
                      Phase 10 (Polish + CI lint + docs + agent-context update)
```

**MVP scope**: Phase 1 + Phase 2 + Phase 3 = ~36 tasks. Delivers the Loki + Promtail substrate end-to-end with structured logging across all three runtimes, the audit-BC log emission, and the 4 log-focused dashboards (D8/D9/D11/D12). The metrics-→-logs-→-traces operator workflow is live; constitution rule 20 / 22 / AD-22 / AD-23 enforcement is in place.

**Parallel opportunities**:
- Phase 1: T002 ∥ T003 ∥ T004 (independent files).
- Phase 2: T005 / T006 / T007 / T008 sequential (single values.yaml file); T009 sequential after T005; T010 ∥ T011 (Python lib + tests); T012 ∥ T013 (two middlewares); **T014a–T014h** are 8 parallel sub-tasks across two devs by entrypoint group; **T015a–T015f** are 6 parallel sub-tasks across the Go satellites; T017 / T018 / T019 sequential (frontend isomorphic logger); T020 sequential (audit-BC log emission — pair-review required); T021 sequential (the dashboard de-duplication audit drives everything in Phase 8).
- Phase 3: T023 ∥ T024 ∥ T025 ∥ T026 ∥ T027 (test-only, parallel); T028 ∥ T029 ∥ T030 ∥ T031 (4 dashboards, parallelizable across two devs); T032 / T033 / T034 mostly parallel; **T035a–T035c** are parallel sub-tasks across BCs; **T036** is parallel across the 6 Go satellites.
- Phase 4: T037 ∥ T038 ∥ T039 (test, dashboard, conditional fallback).
- Phase 5: T040 ∥ T041 (test + dashboard).
- Phase 6: T042 ∥ T043 ∥ T044.
- Phase 7: T045 ∥ T046.
- Phase 8: T047 ∥ T048 ∥ T049 ∥ T050 ∥ T051 ∥ T052 (6 parallel dashboard authoring/extension sub-tasks).
- Phase 9: T053 sequential after T054; T055 ∥ T056 after T054.
- Phase 10: T057 ∥ T058 ∥ T059 ∥ T060 ∥ T061 ∥ T062 ∥ T063 ∥ T064 ∥ T065 ∥ T066 ∥ T067 (independent surfaces); T068 last.

---

## Implementation strategy

The plan's Wave 12A–12D split organises the work:

1. **Wave 12A (Helm sub-chart deployment + bucket + Loki data source + alerts wiring)** — Phases 1, 2 (Helm portion), 9 (alert wiring portion). One DevOps-leaning dev. ~1.5 days.
2. **Wave 12B (Cross-runtime structured logging)** — Phases 2 (Python + Go + TS portions), parallelizable across three devs. Phase 2's logging substrate, the audit-BC log emission (T020), and the 8 control-plane entrypoint instrumentations (T014) + the 6 Go satellite migrations (T015) + the frontend logger (T017–T019). ~2 days calendar with parallelism.
3. **Wave 12C (Audit + dashboards)** — T021 audit + Phase 3 (D8/D9/D11/D12) + Phase 4 (D13) + Phase 5 (D14) + Phase 8 (the remaining 6 dashboards). ~1.5 days with two devs splitting the dashboard authoring.
4. **Wave 12D (E2E tests + CI lint + docs + agent-context update)** — Phase 10 + the E2E tests scattered through earlier phases. ~1 day.

**Total: ~5.5–6 calendar days for two devs**, in line with the plan's adjusted estimate.

**Constitution coverage matrix**:

| Rule / AD | Where applied | Tasks |
|---|---|---|
| 1, 4, 5 (brownfield) | All — extends `deploy/helm/observability/`, `apps/control-plane/`, `services/*`, `apps/web/`, `.github/workflows/ci.yml` | T001, T005, T012, T015, T020, T034, T047, T048, T050, T057 |
| 2 (Alembic only) | N/A — no SQL changes | — |
| 6 (additive enums) | N/A | — |
| 7 (backwards compat) | Phase 2 | T035 (mechanical search-and-replace; old `logging.getLogger()` calls continue working during transition) |
| 8 (feature flags) | Phase 1, 2 | Constitutional `FEATURE_STRUCTURED_LOGGING` (always on), `FEATURE_LOKI_ENABLED`, `FEATURE_PROMTAIL_REDACTION` already declared at constitution lines 892–894; this plan wires their runtime gates via the Helm chart values |
| 9 (PII / sensitive op audit) | Phase 2 | T020 (audit-BC log emission inside the existing transactional audit chain) |
| 13 (every user-facing string through i18n) | N/A — Grafana dashboards English-only at v1 per spec § Out of Scope | — |
| 18, AD-21 (residency at query time) | Phase 1, 2 | T005 (Loki uses generic S3 — replication via the Loki-per-region pattern from feature 081 if multi-region is enabled) |
| 20, AD-22 (structured JSON logs) | Phase 2 | T010, T015, T017 — this feature IS the canonical implementation |
| 21 (correlation IDs context-managed) | Phase 2 | T012, T013, T015 (Python ContextVars; Go context.Context; Next.js request context) |
| 22 (Loki labels low-cardinality only) | Phase 2, 10 | T002, T007, T057 (the CI lint enforcement) |
| 23, 31, 40 (no secrets in logs) | Phase 2 | T007 (Promtail redaction layered atop the application-layer rule-23 discipline) |
| 24, 27 (BC dashboard via Helm bundle, ConfigMaps with `grafana_dashboard: "1"` label) | Phases 3–8 | T028–T031, T038, T041, T043, T046, T047–T052 (14 dashboards, each as a ConfigMap with the rule-27 label) |
| 25, 26, 28 (E2E + journey crossing + journeys against real backends) | Phase 10 | T060 (extends J06 incident-response journey from features 080 / 081 with log-driven debugging) |
| 29, 30 (admin endpoint segregation, admin role gates) | N/A — feature exposes no REST endpoints; Grafana RBAC governs dashboard access | — |
| 32 (audit chain on config changes) | Phase 2 | T020 (audit-BC log emission preserves the existing event-publish; the chain itself is the source of truth) |
| 33 (failover quarterly) | N/A | — |
| 36 (UX-impacting FR documented) | Phase 10 | T064, T065, T066, T067 (LogQL cheatsheet, structured-logging contract docs, Grafana correlation guide, quickstart) |
| 39 (every secret resolves via SecretProvider) | Phase 1, 2 | T005 (Loki S3 credentials via the existing SecretProvider env-var pattern) |
| 41 (Vault failure does not bypass auth) | ⚠️ Documented inversion in audit BC | T020 (audit-chain log emission is transactional — NOT fire-and-forget; rationale documented as a deliberate inversion of the general fire-and-forget rule because audit integrity is non-negotiable) |
| 42, 43, 44 (OAuth env-var bootstrap, OAuth secrets in Vault, rotation responses opaque) | N/A | — |
| 45 (backend has UI) | Phases 3–8 | The 14 dashboards ARE the operator UI |
| 50 (mock LLM for previews) | N/A — no LLM use | — |
| Principle I (modular monolith) | All | All control-plane changes in Python; no new BC |
| Principle III (dedicated stores) | Phase 1 | T005 (Loki is the new dedicated logging store; PG / Redis / etc. unchanged); AD-23 explicitly: Loki for logs, Jaeger for traces, Prometheus for metrics |
| Principle IV (no cross-BC table access) | Phase 2 | T020 (audit-BC log emission is within the audit BC; dashboards query Loki/Prometheus, never directly cross BC tables) |
| Principle XVI (generic S3) | Phase 1 | T005, T009 (Loki uses S3_ENDPOINT_URL etc.; never references MinIO) |
| Constitutional `platform-loki-chunks` bucket reservation | Phase 2 | T009 |
| Constitutional feature flags already declared | Phase 1 | T005–T008 wire the chart's `loki.enabled` / `promtail.enabled` to the constitutional flag names |

---

## Notes

- The `[Story]` tag maps each task to its user story (US1, US2, US3, US4, US5, or US-CrossFeature for the audit-chain incident-trigger integration that spans this feature and feature 080) so independent delivery is preserved.
- This feature is the canonical implementation of constitution **UPD-034** (named explicitly in Constitution § "Observability Extension"). The substrate this feature delivers (Loki + Promtail + structured logging + 14 dashboards + 5 Loki ruler alerts) is what every prior audit-pass feature implicitly assumed exists for its operational dashboards.
- The **6 brownfield-input corrections** captured in T068 / CLAUDE.md update — (a) 11 baseline dashboards not 7, (b) 8 entrypoints not 9 with corrected names, (c) audit-BC transactional log emission, (d) 6 Go satellites not 4, (e) rule-22 Loki label discipline with CI lint enforcement, (f) `frontendNamespaces:` Helm values array not hardcoded `platform-ui` — are first-class deliverables. Future planners reading the brownfield input directly without reading this plan will get the wrong information; T068 is the canonical durable correction.
- The **audit-chain BC's log emission at `audit/service.py:48` is TRANSACTIONAL** — a documented inversion of the general "log emission is fire-and-forget" rule. Pair-review required for T020. Future planners must not "fix" the inversion.
- **Loki labels are low-cardinality only** per rule 22; the CI lint at T057 enforces this. SC-014 is the deliberate-violation test that fails the build if a developer attempts to promote a high-cardinality field to a label.
- **`platform-loki-chunks` S3 bucket** is provisioned via Helm pre-install hook (T009 default) OR via the installer (feature 045 fallback — for environments where the chart's S3 credentials lack bucket-create permission).
- **Loki single-binary mode for v1**; HA / distributed mode is a future concern. Multi-region log federation uses the Loki-per-region pattern (feature 081's contract).
- **Logs do NOT flow through OTEL Collector** — OTEL stays metrics+traces only per AD-23. Promtail directly to Loki.
- **Grafana dashboards are English-only at v1** (Grafana's i18n is limited; feature 083's 6-locale promise covers the application UI, not Grafana). Documented in spec § Out of Scope.
- **Effort estimate**: input said 6 SP / 5 days / 3 calendar days for 2 devs. Plan judged this **realistic but moderately understated** because 6 Go satellites (vs 4) + audit-BC transactional log emission + dashboard de-duplication audit + bucket provisioning + CI lint check add up. Realistic: **5.5–6 calendar days for two devs** with the documented Wave 12A–12D split.
- This is the **last feature in the audit-pass execution order** (Wave 12). After this lands, all of UPD-023 through UPD-031 / UPD-005 / UPD-007 / UPD-059 / UPD-061 have observability dashboards; the platform's metrics-→-logs-→-traces operator workflow is complete.
