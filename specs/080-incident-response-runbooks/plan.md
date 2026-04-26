# Implementation Plan: Incident Response and Runbooks

**Branch**: `080-incident-response-runbooks` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/080-incident-response-runbooks/spec.md`

## Summary

Stand up the `incident_response/` bounded context that the constitution already names as the owner of UPD-031 (Constitution § "New Bounded Contexts" line 495), backing the already-reserved REST prefixes `/api/v1/incidents/*` and `/api/v1/runbooks/*` and the already-declared Kafka topics `incident.triggered` / `incident.resolved`. The brownfield input nominated `analytics/services/alert_rules.py` as the upstream — that file does not exist today (`apps/control-plane/src/platform/analytics/` has no `services/` subfolder; threshold firing today is in-process inside `analytics/service.py:226 AnalyticsService.check_budget_thresholds`). Rather than retrofit a misnamed module, this plan introduces a small **`IncidentTriggerInterface`** in the incident_response BC that any signal source (analytics threshold firings, certification failures, security events, chaos-test detectors) calls in-process. The interface keeps the upstream additive and reverses the brownfield ambiguity into an explicit contract. Timeline reconstruction stitches three sources: the audit-chain-anchored audit-source records each BC emits (the chain itself stores hashes only — `audit/repository.py:52 get_by_sequence_range`), the execution journal (`execution/service.py:289 get_journal`), and Kafka events replayed with a new `_offset_for_timestamp` helper around `aiokafka.AIOKafkaConsumer.offsets_for_times()` (no offset-by-timestamp helper exists today). Provider clients (PagerDuty Events API v2, OpsGenie Alert API, VictorOps REST endpoint) live behind a single `PagingProviderClient` Protocol with one adapter per provider. Credentials resolve through the constitutional `SecretProvider` (`common/clients/model_router.py:43`); never the database, code, or logs (rule 39, rule 23, rule 31). All administrative writes (integration CRUD, runbook edit, post-mortem create/distribute) emit audit-chain entries via `AuditChainService.append` (`audit/service.py:48`) — never directly. Frontend ships an Incidents tab under the existing operator route (`apps/web/app/(main)/operator/page.tsx`) — no new application. Ten initial runbooks are seeded via Alembic data migration so a fresh deployment satisfies SC-004 with no separate operator action.

## Technical Context

**Language/Version**: Python 3.12+ (control plane). No Go changes.
**Primary Dependencies** (already present): FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+ (consumer with `offsets_for_times` for timeline replay), redis-py 5.x async (dedup + delivery-retry coordination), httpx 0.27+ (PagerDuty / OpsGenie / VictorOps REST clients), APScheduler 3.x (delivery-retry scanner, runbook-staleness scanner). No new top-level dependency.
**Storage**: PostgreSQL — 4 new tables (`incident_integrations`, `incidents`, `runbooks`, `post_mortems`) via Alembic migration `063_incident_response.py`, plus a fifth supporting table `incident_external_alerts` for the per-(incident, integration) external-reference + delivery-state tracking that the brownfield JSONB sketch would otherwise hide. Redis — 2 new key patterns: `incident:dedup:{condition_fingerprint}` (open-incident lookup, TTL = max-incident-age + grace; FR-505.5) and `incident:delivery:{integration_id}:{external_alert_id}` (retry-state cache, TTL = retry envelope; FR-505.6). MinIO — 1 reserved bucket prefix `incident-response-postmortems` for post-mortem timeline blobs that exceed the PostgreSQL row-size budget; a row points at the blob. No Vault paths owned by this BC — provider credentials are stored at `secret/data/incident-response/integrations/{integration_id}` via the existing `SecretProvider` (`common/clients/model_router.py:43–44`; `RotatableSecretProvider.get_current()` at `security_compliance/providers/rotatable_secret_provider.py:21`).
**Testing**: pytest + pytest-asyncio 8.x. Existing fixtures for `audit/`, `execution/`, `notifications/`, `workspaces/` are reused. New fixtures only for (a) provider-mock HTTP servers (one per provider) and (b) a fixed-clock incident lifecycle harness for deduplication + retry assertions.
**Target Platform**: Linux server (control plane), Kubernetes deployment. Background scanners (delivery retry, runbook staleness flag) run on the existing `scheduler` runtime profile.
**Project Type**: Web service (FastAPI control plane bounded context — new BC + small extensions to `analytics/`, `audit/`, `execution/`, `workspaces/`, `common/config.py`).
**Performance Goals**: Incident creation from an alert-rule firing adds ≤ 50 ms p95 to the upstream call (synchronous PostgreSQL insert + dedup Redis lookup; external paging is dispatched async and does not block). External-alert delivery happens within ≤ 5 s p95 of incident creation under healthy provider conditions. Timeline reconstruction for a one-hour incident window completes in ≤ 10 s p95 against the three sources combined. Runbook viewer renders inline in the Incidents tab in ≤ 200 ms p95.
**Constraints**: Internal incident creation MUST succeed even when every external provider is unreachable (FR-505.6 — no external-side dependency on the local source-of-truth write). Duplicate suppression is keyed on a `condition_fingerprint` derived deterministically from (alert_rule_id, scope_identifier) so the same active condition cannot multiply (FR-505.5). Provider credentials NEVER appear in logs (constitution rule 23, rule 40, rule 31). Audit chain entries are durable — never dropped under backpressure (constitution Critical Reminder 30); the BC's audit-emitting code path uses `AuditChainService.append` and surfaces failures rather than swallowing them. Post-mortem timelines MUST mark unavailable sources rather than silently producing partial results (spec FR-507.6) — the timeline assembler returns a `TimelineSourceCoverage` per source. Two-way provider-side acknowledgement sync is documented as out-of-scope for v1 (spec Out of Scope) — best-effort provider-resolve-on-internal-resolve only (FR-505.7).
**Scale/Scope**: Up to ~50 incidents/day under normal operation × ~365 days = ~18 K incidents/year of warm hot-path; deduplication keeps this from multiplying under alert storms. Runbook library starts at exactly 10 seeded scenarios; expected steady-state ≤ 200 runbooks per operator. Post-mortems ≤ 100/year. Timeline window typical ≤ 6 hours, hard cap configurable (default 24h) so reconstruction stays bounded.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Source | Status | Notes |
|---|---|---|---|
| Brownfield rule 1 — never rewrite | Constitution § Brownfield | ✅ Pass | New BC `incident_response/`. Modifies `analytics/service.py`, `audit/repository.py` (additive read helper), `execution/repository.py` (additive read helper), `workspaces/service.py` (archival hook), `common/config.py` additively; no file rewritten. |
| Brownfield rule 2 — Alembic only | Constitution § Brownfield | ✅ Pass | Single migration `063_incident_response.py` adds 5 tables + seeds 10 runbooks via a data migration in the same revision. No raw DDL. |
| Brownfield rule 3 — preserve tests | Constitution § Brownfield | ✅ Pass | All existing `analytics/`, `audit/`, `execution/`, `workspaces/` tests stay green. Existing services keep their public signatures; new methods are additive. |
| Brownfield rule 4 — use existing patterns | Constitution § Brownfield | ✅ Pass | New BC follows the standard layout (`models.py`, `schemas.py`, `service.py`, services subfolder, `repository.py`, `router.py`, `events.py`, `exceptions.py`, `dependencies.py`). Event registration follows the `analytics/events.py` pattern. Migration filename uses the next free 3-digit prefix (`063_*` per the existing chain). |
| Brownfield rule 5 — cite exact files | Constitution § Brownfield | ✅ Pass | Project Structure below names every file; integration seams cite file:line for the call sites. |
| Brownfield rule 6 — additive enums | Constitution § Brownfield | ✅ Pass | New enums (`IncidentSeverity`, `IncidentStatus`, `PagingProvider`, `RunbookStatus`, `PostMortemStatus`) are owned by this BC. No existing enums mutated. |
| Brownfield rule 7 — backwards-compatible APIs | Constitution § Brownfield | ✅ Pass | A workspace with no incident-response configuration sees no behaviour change. New endpoints are additive. The `IncidentTriggerInterface` upstream is opt-in: callers that don't register a producer continue to operate unchanged. |
| Brownfield rule 8 — feature flags | Constitution § Brownfield | ✅ Pass | External paging delivery is gated by per-integration `enabled=true` (FR-505.1); a deployment can opt out by leaving zero integrations enabled. The internal incident path is always-on (additive read surface in the operator dashboard). No new global feature flag is required because the existing constitutional flag set is sufficient. |
| Rule 9 — every PII operation audited | Constitution § Domain | ✅ Pass | This BC does not write user PII. Administrative actions (integration create/edit/disable, runbook CRUD, post-mortem create/distribute) emit audit-chain entries via `AuditChainService.append` (`audit/service.py:48`). Distribution recipients are operator email addresses — handled per existing notifications-bc-PII conventions. |
| Rule 10 — every credential goes through Vault | Constitution § Domain | ✅ Pass | Provider integration keys resolved via `SecretProvider.get_current()` (`common/clients/model_router.py:43`). The PostgreSQL `incident_integrations.integration_key_ref` column stores the secret reference path only — never the value (FR-505.9, rule 43). |
| Rule 17 — outbound webhooks HMAC-signed | Constitution § Domain | ✅ Pass | Outbound alert delivery to PagerDuty/OpsGenie/VictorOps uses provider-native authentication (Routing Key for PagerDuty, GenieKey for OpsGenie, REST API key for VictorOps) per each provider's published spec — webhook-style HMAC is N/A for these provider APIs. The platform's own outbound webhook subsystem (feature 077) is unrelated to this path. |
| Rule 20 — structured JSON logs | Constitution § Domain | ✅ Pass | All new modules use `structlog`. Provider HTTP clients log request/response metadata (status, latency, retry_count) — never request bodies that could carry credentials (rule 23, rule 40). |
| Rule 21 — correlation IDs propagated | Constitution § Domain | ✅ Pass | Incident creation, runbook fetch, and post-mortem read all carry the existing `CorrelationContext`. The `incident.triggered` / `incident.resolved` Kafka envelope includes `correlation_id`, `trace_id`, and (when known) `workspace_id`. |
| Rule 22 — Loki labels low-cardinality only | Constitution § Domain | ✅ Pass | Allowed labels: `service`, `bounded_context=incident_response`, `level`, `provider` (PagerDuty / OpsGenie / VictorOps — bounded set of 3). `incident_id`, `runbook_id`, `external_alert_id` go in the JSON payload, never as Loki labels. |
| Rule 24 — every BC dashboard | Constitution § Domain | ✅ Pass | New `deploy/helm/observability/templates/dashboards/incident-response.yaml` ConfigMap following the `cost-governance.yaml` pattern (verified to exist in `deploy/helm/observability/templates/dashboards/`). Panels: open-incident count by severity, MTTR rolling 7d, external-delivery success rate per provider, runbook lookup count per scenario, post-mortems published per quarter. Label `grafana_dashboard: "1"` applied (rule 27). |
| Rule 25 — every BC gets E2E suite + journey | Constitution § Domain | ✅ Pass | New `tests/e2e/suites/incident_response/` suite. A new operator journey (alert-rule fires → on-call paged → runbook surfaced → resolve → start post-mortem → distribute) is added to the journey tree alongside existing journeys (rule 28 — extend, do not parallel). |
| Rule 26 — journeys against real backends | Constitution § Domain | ✅ Pass | E2E uses the kind cluster + Helm chart. Provider sandboxes are simulated with the same provider-mock HTTP servers used in unit tests, deployed as in-cluster pods (no test-only bypass paths in production code). |
| Rule 30 — admin endpoints segregated | Constitution § Domain | ✅ Pass | Integration CRUD lives under `/api/v1/admin/incidents/integrations/*` per rule 29; runbook authoring lives under `/api/v1/admin/runbooks/*`. Read-side incident detail and runbook viewing live under the constitutionally-reserved `/api/v1/incidents/*` and `/api/v1/runbooks/*` (already declared at constitution § REST Prefix lines 806–807). Each admin method has either `require_admin` or `require_superadmin` (rule 30). |
| Rule 32 — audit chain on config changes | Constitution § Domain | ✅ Pass | Integration create/update/disable, runbook create/update/retire, post-mortem create/mark-blameless/distribute all emit audit-chain entries through `AuditChainService.append`. |
| Rule 35 — email enumeration prohibition | Constitution § Domain | ✅ N/A | This BC has no email-existence reveal surface. |
| Rule 36 — UX-impacting FRs documented | Constitution § Domain | ✅ Pass | New `/operator/incidents/` and `/operator/runbooks/` pages documented in the docs site as part of this PR. |
| Rule 39 — every secret resolves via SecretProvider | Constitution § Domain | ✅ Pass | All provider credentials resolve through `SecretProvider.get_current()`. No `os.getenv` calls for `*_API_KEY` / `*_SECRET` patterns inside this BC. CI static-analysis check (rule 39) covers it. |
| Rule 40 — Vault tokens never in logs | Constitution § Domain | ✅ Pass | Provider clients log request metadata (URL, method, status, duration) only. Authorization headers and request bodies are masked at the structlog processor layer. |
| Rule 41 — Vault failure does not bypass auth | Constitution § Domain | ✅ Pass | If the secret store is unavailable, provider clients fail closed: the internal incident is still created (FR-505.6), but the external delivery is queued for retry; no hardcoded credential fallback exists. |
| Rule 45 — backend has UI | Constitution § Domain | ✅ Pass | New `/operator/incidents/`, `/operator/runbooks/`, `/operator/incidents/[id]/post-mortem/` pages added under the existing operator route (`apps/web/app/(main)/operator/`). |
| Rule 48 — platform state is user-visible | Constitution § Domain | ✅ Pass | This feature surfaces operator-side incidents only. Public status-page communication (rule 49) is handled by the separate public status surface and is explicitly out of scope (spec § Out of Scope). |
| Rule 50 — mock LLM for previews | Constitution § Domain | ✅ N/A | This feature does not invoke an LLM (out-of-scope: timeline auto-summarization, FR-507 § Out of Scope). |
| Principle I — modular monolith | Constitution § Core | ✅ Pass | All work in the Python control plane. New BC `incident_response/` lives under `apps/control-plane/src/platform/`. |
| Principle III — dedicated stores | Constitution § Core | ✅ Pass | PostgreSQL for relational truth (incidents, runbooks, post-mortems, integrations, external-alert tracking). Redis for hot dedup + delivery-retry state. MinIO/S3 for over-size post-mortem timeline blobs (Principle XVI — generic S3 protocol). No vector / FTS / OLAP need. |
| Principle IV — no cross-BC table access | Constitution § Core | ✅ Pass | `incident_response/` calls into `audit/`, `execution/`, `workspaces/`, `notifications/`, `analytics/` ONLY through their public service interfaces. Two small additive read methods are needed on `audit/repository.py` (timestamp-window read) and `execution/repository.py` (timestamp-window read across multiple executions); these are added by their owning BCs and exposed via service-layer methods, not via direct table access. |
| Principle V — append-only journal | Constitution § Core | ✅ Pass | Timeline reconstruction READS the execution journal — never mutates. |
| Principle VI — policy is machine-enforced | Constitution § Core | ✅ Pass | Runbook content is documentation, not enforcement (constitution § Principle VI is explicit on this distinction — "Markdown files … are descriptive documentation. They never constitute the enforcement model"). Runbooks here are advisory operator content; nothing in this feature changes platform behaviour based on runbook text. |
| AD-22 — structured JSON logs only | Constitution § Architecture Decisions | ✅ Pass | Confirmed under rule 20 above. |
| Constitutional Kafka topics — already declared | Constitution § Kafka Registry line 777–778 | ✅ Pass | `incident.triggered` and `incident.resolved` are already in the topic registry. This feature implements their schemas and registers the producer; no topic-registry change. |
| Constitutional REST prefixes — already declared | Constitution § REST Prefix lines 806–807 | ✅ Pass | `/api/v1/incidents/*` and `/api/v1/runbooks/*` are already in the prefix registry. Admin authoring surfaces use the segregated `/api/v1/admin/*` prefix per rule 29. |

## Project Structure

### Documentation (this feature)

```text
specs/080-incident-response-runbooks/
├── plan.md              # This file
├── spec.md              # Feature spec
├── planning-input.md    # Verbatim brownfield input (preserved as planning artifact)
├── research.md          # Phase 0 — provider-API decisions, dedup-fingerprint shape, timeline source matrix
├── data-model.md        # Phase 1 — 5 PG tables + Redis keys + MinIO bucket layout
├── quickstart.md        # Phase 1 — local end-to-end walk: configure provider → fire alert → page → resolve → post-mortem
├── contracts/           # Phase 1
│   ├── incident-trigger-interface.md       # the in-process producer contract that analytics + future BCs call
│   ├── paging-provider-client.md           # PagerDuty/OpsGenie/VictorOps adapter Protocol + per-provider notes
│   ├── incident-service.md                 # create_from_signal, resolve, list, get
│   ├── runbook-service.md                  # CRUD, lookup_by_scenario, freshness-flag
│   ├── post-mortem-service.md              # start, save_section, distribute, link_execution, link_certification
│   ├── timeline-assembler.md               # assemble(window) → Timeline + per-source TimelineSourceCoverage
│   ├── incidents-rest-api.md               # /api/v1/incidents/* + /api/v1/admin/incidents/integrations/*
│   └── runbooks-rest-api.md                # /api/v1/runbooks/* + /api/v1/admin/runbooks/*
├── checklists/
│   └── requirements.md
└── tasks.md             # Created by /speckit.tasks (NOT created here)
```

### Source Code (repository root)

```text
apps/control-plane/
├── migrations/versions/
│   └── 063_incident_response.py                       # NEW — 5 tables + 10-runbook data migration
│                                                       #   (rebase to current head at merge time)
└── src/platform/
    ├── incident_response/                             # NEW BOUNDED CONTEXT (Constitution § New BCs line 495)
    │   ├── __init__.py
    │   ├── models.py                                  # NEW — IncidentIntegration, Incident, Runbook,
    │   │                                              #   PostMortem, IncidentExternalAlert
    │   ├── schemas.py                                 # NEW — request/response Pydantic for /incidents/*
    │   │                                              #   /runbooks/*, post-mortem composer
    │   ├── service.py                                 # NEW — IncidentResponseService facade exposing the
    │   │                                              #   methods external BCs (analytics, certifications,
    │   │                                              #   security_compliance, chaos detectors) call into
    │   ├── services/
    │   │   ├── __init__.py
    │   │   ├── incident_service.py                    # NEW — create_from_signal (dedup via Redis),
    │   │   │                                          #   resolve, list, get; emits incident.triggered /
    │   │   │                                          #   incident.resolved on `incident_response.events`
    │   │   ├── integration_service.py                 # NEW — CRUD for IncidentIntegration; provider
    │   │   │                                          #   credential lookup via SecretProvider
    │   │   ├── runbook_service.py                     # NEW — CRUD; lookup_by_scenario; freshness-flag
    │   │   │                                          #   evaluator (driven by APScheduler)
    │   │   ├── post_mortem_service.py                 # NEW — start, save_section, mark_blameless,
    │   │   │                                          #   distribute; calls timeline_assembler
    │   │   ├── timeline_assembler.py                  # NEW — assemble(window) → Timeline; queries
    │   │   │                                          #   audit + execution + Kafka and returns per-source
    │   │   │                                          #   coverage flags (FR-507.6)
    │   │   ├── kafka_replay.py                        # NEW — _offset_for_timestamp(topic, partition, ts)
    │   │   │                                          #   helper around aiokafka.AIOKafkaConsumer.
    │   │   │                                          #   offsets_for_times(); bounded read window
    │   │   └── providers/
    │   │       ├── __init__.py
    │   │       ├── base.py                            # NEW — PagingProviderClient Protocol:
    │   │       │                                      #   async def create_alert(self, ...) → ProviderRef
    │   │       │                                      #   async def resolve_alert(self, provider_ref)
    │   │       ├── pagerduty.py                       # NEW — PagerDuty Events API v2 adapter
    │   │       ├── opsgenie.py                        # NEW — OpsGenie Alert API v2 adapter
    │   │       └── victorops.py                       # NEW — Splunk On-Call (VictorOps) REST adapter
    │   ├── repository.py                              # NEW — PostgreSQL queries for the 5 tables;
    │   │                                              #   includes condition-fingerprint indexed lookup
    │   ├── router.py                                  # NEW — FastAPI routers: read at /api/v1/incidents/*
    │   │                                              #   and /api/v1/runbooks/*; admin at
    │   │                                              #   /api/v1/admin/incidents/integrations/* and
    │   │                                              #   /api/v1/admin/runbooks/* (rule 29)
    │   ├── events.py                                  # NEW — register incident.triggered,
    │   │                                              #   incident.resolved (constitutional topic names);
    │   │                                              #   topic = `incident_response.events`
    │   ├── exceptions.py                              # NEW — IntegrationNotFoundError,
    │   │                                              #   ProviderUnreachableError (does NOT propagate to
    │   │                                              #   caller — recorded on the incident),
    │   │                                              #   StaleConcurrentEditError (runbook concurrent edit),
    │   │                                              #   PostMortemOnOpenIncidentError (FR-507.1 guard)
    │   ├── dependencies.py                            # NEW — FastAPI deps; SecretProvider injection
    │   ├── trigger_interface.py                       # NEW — IncidentTriggerInterface Protocol that
    │   │                                              #   analytics, certifications, security_compliance,
    │   │                                              #   chaos detectors call to fire an incident.
    │   │                                              #   Single-method Protocol:
    │   │                                              #   async def fire(signal: IncidentSignal) → IncidentRef
    │   │                                              #   IncidentSignal carries (alert_rule_class, severity,
    │   │                                              #   title, description, related_executions,
    │   │                                              #   related_event_ids, condition_fingerprint).
    │   ├── seeds/
    │   │   ├── __init__.py
    │   │   └── runbooks_v1.py                         # NEW — the 10 seeded runbooks as Python literals;
    │   │                                              #   imported by 063_incident_response.py data migration
    │   └── jobs/
    │       ├── __init__.py
    │       ├── delivery_retry_scanner.py              # NEW — APScheduler hook; finds queued external
    │       │                                          #   alerts whose retry-window is due and re-attempts
    │       │                                          #   (FR-505.6)
    │       └── runbook_freshness_scanner.py           # NEW — APScheduler hook; flags stale runbooks
    │                                                  #   (FR-506.6)
    │
    ├── analytics/
    │   └── service.py                                 # MODIFIED — at the existing
    │                                                  #   AnalyticsService.check_budget_thresholds
    │                                                  #   (line 226) and any new threshold-firing helpers,
    │                                                  #   add a single in-process call into the registered
    │                                                  #   IncidentTriggerInterface when the configured
    │                                                  #   incident-trigger flag is set on the alert rule.
    │                                                  #   Default registration is a no-op producer so
    │                                                  #   existing callers remain unaffected. The brownfield
    │                                                  #   input named `analytics/services/alert_rules.py`
    │                                                  #   — that file does not exist; we keep the change
    │                                                  #   inside the existing `analytics/service.py` and
    │                                                  #   document the deviation here (this plan)
    │                                                  #   rather than introduce a wrongly-named module.
    │
    ├── audit/
    │   └── repository.py                              # MODIFIED — add list_audit_sources_in_window(
    │                                                  #     start_ts, end_ts, sources: list[str]
    │                                                  #   ) -> list[AuditChainEntry]
    │                                                  #   The audit chain stores hashes only, so the
    │                                                  #   `timeline_assembler` joins each chain entry with
    │                                                  #   its originating BC's audit-source record by
    │                                                  #   (audit_event_source, audit_event_id) read through
    │                                                  #   that BC's public service. This new helper is the
    │                                                  #   anchor query.
    │
    ├── execution/
    │   └── repository.py                              # MODIFIED — add list_journal_in_window(
    │                                                  #     execution_ids: list[UUID],
    │                                                  #     start_ts, end_ts
    │                                                  #   ) -> list[ExecutionEvent]
    │                                                  #   Existing `get_events(execution_id, since_seq, …)`
    │                                                  #   at repo.py:166 is sequence-only; the new method
    │                                                  #   serves the timeline assembler's window query
    │                                                  #   without breaking the sequence-based contract.
    │                                                  #   Service-layer method `get_journal_in_window` added
    │                                                  #   to `execution/service.py` to expose it across the
    │                                                  #   BC boundary (Principle IV).
    │
    ├── workspaces/
    │   └── service.py                                 # MODIFIED — on workspace archival, call into
    │                                                  #   IncidentResponseService.handle_workspace_archived()
    │                                                  #   so historical incident, runbook, and post-mortem
    │                                                  #   records are preserved (spec FR-CC-4).
    │
    └── common/
        └── config.py                                  # MODIFIED — add IncidentResponseSettings sub-model:
                                                        #   delivery_retry_initial_seconds (default 30),
                                                        #   delivery_retry_max_attempts (default 6),
                                                        #   delivery_retry_max_window_seconds (default 86400),
                                                        #   runbook_freshness_window_days (default 90),
                                                        #   timeline_max_window_hours (default 24),
                                                        #   dedup_fingerprint_ttl_seconds (default 86400 * 30).

deploy/helm/observability/templates/dashboards/
└── incident-response.yaml                              # NEW — Grafana dashboard ConfigMap (rule 24)
                                                        #   following the cost-governance.yaml pattern.

apps/web/
├── app/(main)/operator/                                # EXTENDED — operator route already exists
│   ├── incidents/
│   │   ├── page.tsx                                    # NEW — Incidents tab (open + resolved tables,
│   │   │                                               #   severity filter, alert-storm visibility)
│   │   └── [incidentId]/
│   │       ├── page.tsx                                # NEW — incident detail + inline runbook +
│   │       │                                           #   external-delivery status per integration
│   │       └── post-mortem/
│   │           └── page.tsx                            # NEW — post-mortem composer with auto-generated
│   │                                                   #   timeline, impact / root-cause / action-items
│   │                                                   #   editors, distribution dialog
│   └── runbooks/
│       ├── page.tsx                                    # NEW — runbook library with scenario search and
│       │                                               #   stale-runbook badges
│       └── [runbookId]/
│           └── page.tsx                                # NEW — runbook viewer + (admin-gated) editor
└── components/features/incident-response/              # NEW — IncidentTable, IncidentDetail,
                                                        #   ExternalDeliveryStatus, RunbookViewer,
                                                        #   RunbookEditor, RunbookStaleBadge,
                                                        #   PostMortemComposer, TimelineDisplay,
                                                        #   TimelineSourceCoverage,
                                                        #   IntegrationConfigForm

tests/control-plane/unit/incident_response/
├── test_incident_service.py                            # NEW — dedup by fingerprint, severity mapping,
│                                                       #   integration-disabled path
├── test_integration_service.py                         # NEW — secret reference flow, audit-chain emission,
│                                                       #   admin-only RBAC
├── test_runbook_service.py                             # NEW — CRUD, freshness flag, concurrent-edit guard
├── test_post_mortem_service.py                         # NEW — start guard (open incident), section save,
│                                                       #   distribute, link to execution / certification
├── test_timeline_assembler.py                          # NEW — three-source merge order, source-coverage
│                                                       #   flag, missing-source signalling (FR-507.6)
├── test_provider_pagerduty.py                          # NEW — request shape, severity mapping, error paths
├── test_provider_opsgenie.py                           # NEW — request shape, severity mapping, error paths
├── test_provider_victorops.py                          # NEW — request shape, severity mapping, error paths
└── test_seeded_runbooks_present.py                     # NEW — SC-004 — exactly the 10 scenarios with all
                                                        #   four required fields populated

tests/control-plane/integration/incident_response/
├── test_alert_rule_fires_incident.py                   # NEW — analytics threshold → IncidentTrigger →
│                                                       #   incident row + external-alert row + Kafka event
├── test_dedup_under_alert_storm.py                     # NEW — SC-002 — sustained synthetic firings produce
│                                                       #   exactly one incident + one external page
├── test_provider_unreachable_retry.py                  # NEW — SC-003 — provider goes down, internal
│                                                       #   incident still created, retry succeeds on recovery
├── test_runbook_inline_from_incident.py                # NEW — SC-005 — incident view links to runbook in
│                                                       #   one hop
├── test_post_mortem_timeline_combines_sources.py       # NEW — SC-007 — three-source timeline ordered
│                                                       #   correctly, missing-source flag set
├── test_post_mortem_bidirectional_links.py             # NEW — SC-008 — discoverable from incident,
│                                                       #   execution, certification
├── test_admin_audit_chain_emission.py                  # NEW — SC-009 — every admin write produces an
│                                                       #   audit-chain entry
└── test_workspace_archival_preserves_records.py        # NEW — FR-CC-4

tests/e2e/suites/incident_response/
├── test_alert_rule_pages_oncall.py                     # NEW — provider mock receives the alert
├── test_runbook_one_click_from_incident.py             # NEW — UI assertion matching SC-005
└── test_post_mortem_distribute.py                      # NEW — distribution event produced + recipient
                                                        #   delivery surfaced via notifications BC
```

**Structure Decision**: One new bounded context (`incident_response/`), aligned with the constitution's existing declaration that `incident_response/` owns UPD-031 (Constitution § "New Bounded Contexts" line 495). Five surgical extensions: `analytics/service.py` (the trigger-interface call site at the existing threshold-firing function — no `analytics/services/alert_rules.py` is created because that file did not exist and inventing it would violate brownfield rule 1), `audit/repository.py` + `execution/repository.py` (additive timestamp-window read methods exposed through their service layers — Principle IV preserved), `workspaces/service.py` (archival preservation hook), `common/config.py` (settings sub-model). Frontend extends the existing `apps/web/app/(main)/operator/` route group — the operator dashboard is the constitutional home (constitution implicit in rule 45 + spec § Dependencies) and there is no new application. Dashboard ships in the unified observability Helm bundle per rule 27.

## Complexity Tracking

| Item | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| `IncidentTriggerInterface` Protocol instead of a Kafka-driven upstream | The constitutional `monitor.alerts` topic exists in the registry but has no consumer today. Wiring a new consumer in this PR would couple incident creation to Kafka delivery semantics (at-least-once + retry) for what is fundamentally an in-process invariant — "this BC just observed an alert-rule fire; turn it into an incident." The Protocol keeps the call in-process, the dedup deterministic, and lets future producers (chaos detectors, certification evaluators) register without a topic-schema change. | Wire `monitor.alerts` consumer in this PR: rejected — extra surface area for a single producer (analytics) today, and dedup becomes harder to reason about across at-least-once delivery. We keep `monitor.alerts` reserved for cross-process operator-broadcast use; that is a different shape. |
| Five PostgreSQL tables (the four from the brownfield input + `incident_external_alerts`) | The brownfield input proposed a JSONB `related_events` and an implicit external-reference column on `incidents`. Splitting external-alert tracking into its own table makes per-(incident, integration) state explicit, gives FR-505.4 a clear write target ("persist the external reference or the failure to obtain one"), and gives the retry scanner a clean query surface. JSONB-blob tracking would force per-row JSON manipulation under contention. | Single JSONB column on `incidents`: rejected — concurrent retry updates would race; queryability for the dashboard's per-provider success rate panel would be poor. |
| Redis dedup key + delivery-retry key | Spec FR-505.5 requires zero-duplicate-incidents under sustained alert-storm; a PostgreSQL "find existing open incident with this fingerprint" query on every fire would contend. Redis hot-path lookup is < 1 ms with the system of record still in PostgreSQL. The retry-state key gives the APScheduler scanner an O(1) workload selector instead of a full table scan. | PostgreSQL on every fire: rejected — slow under storm and creates lock contention with concurrent incident creates. |
| Adding a timestamp-window read helper to `audit/repository.py` and `execution/repository.py` instead of in-process filtering | Both repositories are sequence-only today. Pulling all sequences and filtering in Python would be slow and memory-hungry for a 6-hour timeline window. The additive read methods preserve Principle IV (the helpers are exposed via the BCs' service layers — `incident_response/` does not query their tables) and are useful to future BCs. | In-process post-fetch filtering: rejected — performance and memory; would also block on `execution/` BC for cross-execution joins. |
| `kafka_replay._offset_for_timestamp` helper around `aiokafka.AIOKafkaConsumer.offsets_for_times()` | No existing helper performs offset-by-timestamp lookup; consumers all tail live. Timeline reconstruction needs a bounded historical read. The helper is intentionally tiny (one method) and isolated — it does not change consumer-registration patterns elsewhere. | Replay all from earliest: rejected — unbounded; would page through gigabytes for a 6-hour window. |
| MinIO bucket `incident-response-postmortems` for over-size timeline blobs | Post-mortem timelines for multi-hour windows can exceed PostgreSQL row-size budgets, particularly when execution-journal events are dense. The existing pattern (cost-governance, evaluation) is to keep the row in PostgreSQL with the bulk in S3-protocol storage. | All in PostgreSQL: rejected — row bloat; MinIO/S3 is the constitutional choice (Principle XVI). |
| `incident_external_alerts` per-provider state separate from `incidents` | A single incident can be raised in multiple integrations (e.g., one PagerDuty + one OpsGenie test integration). Each carries its own provider reference, its own delivery state, its own retry counter. | Bake provider state into `incidents`: rejected — multi-integration breaks; retry semantics get conflated. |
| Seed 10 runbooks via a data migration in the same Alembic revision | Spec SC-004 requires a fresh deployment to land with all 10 runbooks already present with all four required fields. A separate seed step (CLI command, post-deploy hook) would create a window where the assertion fails. The data migration is reversible (the down-revision deletes the seed rows by their stable IDs) and idempotent (the migration uses `INSERT … ON CONFLICT DO NOTHING` keyed on the unique `scenario` field). | Separate ops-cli seed command: rejected — race condition with SC-004; ops-cli seed is also a runtime concern, not a database concern. Hardcoded fallback: rejected — would be undocumented. |

## Dependencies

- **`audit/` BC (existing)** — `AuditChainService.append` at `audit/service.py:48` is the canonical write path required by constitution rule 9 + 32 for every administrative action. New read helper `list_audit_sources_in_window` added to `audit/repository.py` for timeline reconstruction. Anchor for FR-507.2.
- **`execution/` BC (existing)** — `ExecutionService.get_journal` at `execution/service.py:289` is the canonical journal read; new `list_journal_in_window` (repo + service) is added for timeline reconstruction. Principle V preserved (READ ONLY).
- **`analytics/` BC (existing)** — `AnalyticsService.check_budget_thresholds` at `analytics/service.py:226` is the first registered producer of `IncidentTriggerInterface`. Future producers (`certifications/`, `security_compliance/`, chaos detectors) register through the same interface in their own PRs.
- **`notifications/` BC (feature 077)** — internal-to-platform notifications about post-mortem distribution route through `AlertService` (`notifications/service.py:167–256`). No new outbound channel inside notifications — external paging providers are owned by THIS BC.
- **`workspaces/` BC (existing)** — archival hook on `workspaces/service.py` for FR-CC-4.
- **`security_compliance/` BC (UPD-024)** — `RotatableSecretProvider.get_current()` at `security_compliance/providers/rotatable_secret_provider.py:21` resolves provider credentials. Audit-chain integrity is enforced through this BC's `AuditChainService` (constitution rule 9, 30, 31 references).
- **`common/clients/clickhouse.py`** — not a dependency; this BC does not write to ClickHouse. Analytics read already exists for the threshold-firing path.
- **`SecretProvider` Protocol (`common/clients/model_router.py:43–44`)** — frozen contract; injected as a FastAPI dependency.
- **Constitution § Kafka Topics Registry (lines 777–778)** — `incident.triggered` and `incident.resolved` are already declared. This feature implements their schemas under the topic name convention `incident_response.events` (consistent with `analytics.events`, `notifications.events`).
- **Constitution § REST Prefix Registry (lines 806–807)** — `/api/v1/incidents/*` and `/api/v1/runbooks/*` already declared; admin authoring uses the segregated `/api/v1/admin/*` prefix per rule 29.
- **Constitution § Feature Flag Inventory (lines 880–894)** — no new global flag added; per-integration `enabled` boolean satisfies the toggle requirement of FR-505.1.
- **APScheduler** — already in the runtime; the delivery-retry and runbook-freshness scanners run on the existing `scheduler` profile.
- **`aiokafka.AIOKafkaConsumer.offsets_for_times()`** — already shipped with the existing aiokafka version (0.11+).
- **Provider APIs** — PagerDuty Events API v2 (https://developer.pagerduty.com), OpsGenie Alert API v2 (https://docs.opsgenie.com), Splunk On-Call (VictorOps) REST endpoint (https://help.victorops.com). Each adapter is small (≤ 200 LOC). No vendor SDKs are added — `httpx` is sufficient and avoids dependency surface.

## Wave Placement

**Wave 8** — placed after the audit chain (UPD-024, established earlier waves), notifications (feature 077, Wave 5), cost governance (feature 079, Wave 7) so post-mortem timeline reconstruction has a stable audit chain to read from and notifications has the routing path the post-mortem distribution feature uses. The constitution's Document References (§ Document References, line 1051) and the constitutional declaration that `incident_response/` is a v1.2.0 audit-pass BC mean this can land independently of UPD-036 onward (the v1.3.0 admin / OAuth / Vault audit-pass extensions). Frontend lands in the same wave because rule 45 binds backend to UI and there is no shipping value in a dashboard tab that is incomplete for one release. Compatible with the merged PR pipeline; does not block any feature in flight.
