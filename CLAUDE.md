# musematic Development Guidelines

Auto-generated from all feature plans. Last full sync: 2026-04-29. Manually compacted: 2026-05-05 (deduplication of common stacks; per-feature entries now list only deltas).

---

## Common Stacks (assumed by every BC unless noted otherwise)

### Python control plane (`apps/control-plane/src/platform/<bc>/`)
Python 3.12+ · FastAPI 0.115+ · Pydantic v2 · SQLAlchemy 2.x async · Alembic 1.13+ · aiokafka 0.11+ · redis-py 5.x async · httpx 0.27+ · APScheduler 3.x · grpcio 1.65+ · pytest 8.x + pytest-asyncio · ruff 0.7+ · mypy 1.11+ strict.

### Go satellites (`services/<svc>/`)
Go 1.22+ · client-go 0.31+ · google.golang.org/grpc 1.67+ · pgx/v5 · go-redis/v9 · confluent-kafka-go/v2 · aws-sdk-go-v2 · prometheus/promauto · multi-stage distroless image (<100MB; <50MB target for newer satellites).

### Frontend (`apps/web/`)
TypeScript 5.x strict · Next.js 14+ App Router · React 18+ (function components only) · shadcn/ui (ALL UI primitives) · Tailwind CSS 3.4+ utility-only · TanStack Query v5 · TanStack Table v8 · Zustand 5.x · Recharts 2.x · React Hook Form 7.x + Zod 3.x · date-fns 4.x · Lucide React · next-themes · cmdk · Vitest + RTL + Playwright + MSW · pnpm 9+. shadcn `Select` here is the native HTML `<select>`, NOT the Radix composite. Tooltip is a no-op stub rendering `TooltipContent` as `sr-only`.

### Cluster data stores
PostgreSQL 16 (CloudNativePG) · Redis 7 Cluster (AOF, fsync 1s) · Kafka 3.7 KRaft (Strimzi) · MinIO S3-compatible · Qdrant (StatefulSet, no operator) · Neo4j 5.x (StatefulSet, APOC) · ClickHouse 24.3+ (StatefulSet + Keeper) · OpenSearch 2.18 (StatefulSet + Dashboards + ICU). Generic-S3 client per Principle XVI (`S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_USE_PATH_STYLE`).

> **Per-feature entries below list only deltas**: BC path, key behaviors, owned tables/buckets/topics/Redis keys, NEW deps beyond the common stack.

---

## Data Store Foundations (002–008)

- **002 Redis Cache & Hot State** — cluster client (`redis-cluster.platform-data:6379` prod; `REDIS_TEST_MODE=standalone` tests). Lua scripts: `budget_decrement.lua`, `rate_limit_check.lua`, `lock_acquire.lua`, `lock_release.lua`. Key patterns: `session:{user}:{session}` · `budget:{exec}:{step}` · `ratelimit:{res}:{key}` · `lock:{res}:{id}` · `leaderboard:{t}` · `cache:{ctx}:{key}`.
- **003 Kafka Event Backbone** — Strimzi operator; aiokafka (Py) + confluent-kafka-go v2 (Go).
- **004 MinIO Object Storage** — MinIO Operator; aioboto3 (Py).
- **005 Qdrant Vector Search** — qdrant-client[grpc] 1.12+.
- **006 Neo4j Knowledge Graph** — neo4j-python-driver 5.x async, APOC via `NEO4J_PLUGINS`.
- **007 ClickHouse Analytics** — clickhouse-connect 0.8+ HTTP; backup: altinity/clickhouse-backup.
- **008 OpenSearch Full-Text** — opensearch-py 2.x async; ISM lifecycle + SM snapshots → MinIO.

---

## Go Satellites (009–012)

- **009 Runtime Controller** (`services/runtime-controller/`) — gRPC RuntimeControlService (7 RPCs); reconciliation 30s; Redis heartbeat scanner (TTL 60s); warm pool (in-mem + PG); TaskPlanRecord (PG + MinIO); secrets via K8s projected volumes.
- **010 Sandbox Manager** (`services/sandbox-manager/`) — gRPC SandboxService (5 RPCs); pod exec via remotecommand; 4 templates (python3.12/node20/go1.22/code-as-reasoning); hardening (UID 65534, drop ALL caps, RO rootfs, deny-all NetworkPolicy); orphan scanner.
- **011 Reasoning Engine** (`services/reasoning-engine/`, port 50052) — gRPC ReasoningEngineService (9 RPCs); Redis Lua (EVALSHA) atomic budgets; goroutine pool + bounded semaphore for ToT branches; client-streaming gRPC for CoT traces; rule-based mode selector (6 modes); two-sample convergence; fan-out registry for budget event streaming.
- **012 Simulation Controller** (`services/simulation-controller/`, port 50055) — gRPC SimulationControlService (6 RPCs); pods in `platform-simulation` namespace with deny-all production-egress NetworkPolicy; remotecommand tar artifact collection; Kafka topic `simulation.events`; ATE with ConfigMap-injected scenarios; orphan scanner; bucket `simulation-artifacts`.

---

## Control Plane Foundation (013–020)

- **013 FastAPI App Scaffold** (`platform/common/`) — app factory + lifespan; PlatformSettings; canonical EventEnvelope + event-type registry + DLQ; correlation-ID + JWT (RS256) middleware; 10 client wrappers (8 stores + 4 gRPC satellites); PlatformError hierarchy; cursor/offset pagination; 8 runtime profile entrypoints. Dep: PyJWT 2.x, opentelemetry-sdk 1.27+.
- **014 Auth BC** (`platform/auth/`) — Argon2id (OWASP params, argon2-cffi 23+); RS256 JWT pair (15min/7d); Redis sessions `session:{user_id}:{session_id}`; TOTP MFA (pyotp 2.x; Fernet-encrypted secrets) + recovery codes; lockout `auth:lockout:{user_id}`/`auth:locked:{user_id}`; RBAC engine (10 roles, workspace-scoped); purpose-bound agent authz; service-account API keys (`msk_` prefix, Argon2id-hashed); 7 REST endpoints; topic `auth.events` (6 event types).
- **015 Next.js App Scaffold** (`apps/web/`) — route groups `(main)` + `(auth)`; CSS-custom-property dark mode (no FOIT); `lib/api.ts` (JWT injection + 401-refresh-retry + 3× exp backoff + ApiError); `lib/ws.ts` (topic subs, exp-backoff reconnect 1s→30s); Zustand stores (auth: persists only refreshToken; workspace: invalidates TanStack Query on switch); `lib/hooks/use-api.ts` factory hooks; sidebar RBAC filter via `requiredRoles: RoleType[]`; cmdk Cmd+K palette; 11 shared components (DataTable/StatusBadge/MetricCard/ScoreGauge/EmptyState/ConfirmDialog/CodeBlock/JsonViewer/Timeline/SearchInput/FilterBar). Dep: highlight.js (lazy).
- **016 Accounts BC** (`platform/accounts/`) — self-registration with anti-enumeration (always 202); SHA-256 hashed email-verify (24h) + invite (7d) tokens; signup modes open/invite_only/admin_approval; state machine pending_verification→pending_approval→active↔suspended→blocked→archived; admin approval queue; 8 lifecycle actions (suspend/reactivate/block/unblock/archive/reset-mfa/reset-password/unlock); resend rate limit `resend_verify:{user_id}`; in-process auth-service calls (credential creation + session invalidation); 17 REST endpoints; topic `accounts.events` (15 event types).
- **017 Login UI** (`apps/web/app/(auth)/`, `components/features/auth/`) — RHF+Zod login; two-step MFA (TOTP + recovery via shadcn InputOTP, auto-submit at 6); lockout countdown via `useEffect`+`setInterval` (no polling); forgot/reset flows with anti-enumeration; password rules match feature 016 (12-char + upper + lower + digit + special); MFA enrollment dialog (qrcode.react SVG + text fallback + recovery-code mandatory ack); `?redirectTo` deep link (relative-only); 6 useMutation hooks in `lib/hooks/use-auth-mutations.ts`; login flow state as local discriminated union (NOT Zustand).
- **018 Workspaces BC** (`platform/workspaces/`) — workspace CRUD + membership (owner/admin/member/viewer scoped); default workspace via Kafka consumer on `accounts.user.activated` (idempotent); workspace goals as first-class GID dimension (state open→in_progress→completed|cancelled); workspace-wide visibility grants (FQN arrays, union with per-agent zero-trust); workspace settings (super-context subs: agents/fleets/policies/connectors); per-user limits via in-process accounts service; 20 REST + 2 internal interfaces; topic `workspaces.events` (11 event types).
- **019 WebSocket Real-Time Gateway** (`platform/ws_hub/`, `ws-hub` runtime profile) — JWT auth on upgrade; in-memory ConnectionRegistry + SubscriptionRegistry; 11 channels (execution/interaction/conversation/workspace/fleet/reasoning/correction/simulation/testing/alerts/attention); per-instance Kafka group `ws-hub-{hostname}-{pid}`; dynamic topic subs (KafkaFanout starts/stops on refcount 0↔1); asyncio.Queue backpressure + `events_dropped` notification; workspace-scoped visibility filtering; attention channel auto-subscribed (filters `interaction.attention` by target_id); RFC 6455 ping/pong; SIGTERM → broadcast close 1001 → stop consumers. No SQLAlchemy.
- **020 Analytics & Cost Intelligence** (`platform/analytics/`) — Kafka→ClickHouse pipeline (batch 100 events or 5s, from `workflow.runtime`+`evaluation.events`); ClickHouse AggregatingMergeTree views (hourly/daily/monthly); cost-per-quality (LEFT JOIN usage × quality by execution_id); rule-based optimization recs (4 rules); linear-regression budget forecasting (7/30/90d, CI, volatility flag); 4 REST GET + 1 internal cost-summary; PG table `analytics_cost_models`; topic `analytics.events`.

---

## Domain Bounded Contexts (021–025)

- **021 Agent Registry & Ingest** (`platform/registry/`) — PG (5 tables: `registry_namespaces`, `registry_agent_profiles`, `registry_agent_revisions`, `registry_maturity_records`, `registry_lifecycle_audit`) + OpenSearch index `marketplace-agents` + Qdrant collection `agent_embeddings` + MinIO bucket `agent-packages`.
- **022 Context Engineering Service** (`platform/context_engineering/`) — PG (5 tables: `context_engineering_profiles`, `context_profile_assignments`, `context_assembly_records`, `context_ab_tests`, `context_drift_alerts`) + ClickHouse `context_quality_scores` + MinIO bucket `context-assembly-records`. Dep: optional LLM call for hierarchical compression.
- **023 Memory & Knowledge Subsystem** (`platform/memory/`) — PG (7 tables: `memory_entries`, `evidence_conflicts`, `embedding_jobs`, `trajectory_records`, `pattern_assets`, `knowledge_nodes`, `knowledge_edges`) + Qdrant collection `platform_memory` (1536-dim Cosine) + Neo4j (`MemoryNode`, `MEMORY_REL`); embedding/consolidation/session-cleanup workers; sliding-window rate limit (Redis).
- **024 Interactions & Conversations** (`platform/interactions/`) — PG (8 tables: `conversations`, `interactions`, `interaction_messages`, `interaction_participants`, `workspace_goal_messages`, `conversation_branches`, `branch_merge_records`, `attention_requests`); 3 topics.
- **025 Connector & Plugin Framework** (`platform/connectors/`) — PG (6 tables: `connector_types`, `connector_instances`, `connector_credential_refs`, `connector_routes`, `outbound_deliveries`, `dead_letter_entries`) + Redis (route cache, DLQ depth) + MinIO (DLQ archival). Deps: aioimaplib 1.0+, aiosmtplib 3.0+. Email poll + retry scanner.

---

## Frontend Features (026–027, 035, 041–044, 049–050)

- **026 Home Dashboard** (`app/(main)/home/`) — 4× MetricCard, Timeline (top 10), PendingActionCard (urgency-sorted, inline approve/reject + optimistic), 4 Quick Actions (RBAC-disabled for viewers), WS real-time invalidation (execution/interaction/workspace), ConnectionStatusBanner + 30s polling fallback, per-section error boundaries.
- **027 Admin Settings Panel** (`app/(main)/admin/settings/`) — 6-tab shadcn Tabs with `?tab=` routing; layout-level guard (platform_admin only); server-side DataTable (approve/reject/suspend/reactivate, optimistic, self-suspend prevention); RHF+Zod for 5 settings forms (Signup/Quotas/Email/Security); `If-Unmodified-Since`/412 stale detection + StaleDataAlert; per-toggle auto-save Connectors tab; "click to update" credential masking (Email tab).
- **035 Agent Marketplace UI** (`app/(main)/marketplace/`) — 3 pages (landing, `/[namespace]/[name]`, compare); 18 components (MarketplaceSearchBar, FilterSidebar, AgentCard, AgentCardGrid, AgentDetail, TrustSignalsPanel, AgentRevisions, PolicyList, QualityMetrics, ComparisonView, ComparisonFloatingBar, RecommendationCarousel, ReviewsSection, StarRating(+Input), InvokeAgentDialog, CreatorAnalyticsTab, UsageChart/SatisfactionTrendChart); URL-param search; 300ms debounce; mobile Sheet drawer; useComparisonStore (FQN list, max 4, no persist).
- **041 Agent Catalog Workbench** — frontend-only; data from registry (021), composition (038), policy (028). Dep: Monaco Editor 0.50+.
- **042 Fleet Dashboard** — frontend-only; data from fleet management/learning (033), simulation (040), registry (021). Deps: @xyflow/react 12+, dagre (NEW).
- **043 Trust & Certification Workbench** (`app/(main)/trust-workbench/`) — 2 pages (queue, `[certificationId]` w/ 4 tabs); 15 components (CertificationDataTable, CertificationStatusBadge, CertificationDetailView, StatusTimeline, EvidenceList(+ItemCard), ReviewerForm, TrustRadarChart, TrustDimensionTooltip, PolicyAttachmentPanel, PolicyCatalog, PolicyBindingList(+Card), PrivacyImpactPanel, PrivacyDataCategoryRow); 7 hook files; 11 TanStack Query hooks; `usePolicyAttachmentStore` (Zustand); HTML5 native drag-and-drop (NO @dnd-kit); `?tab=` (evidence|trust-radar|policies|privacy); approve→POST activate + evidence ref; reject→POST revoke; 409 concurrent review detection; stale privacy banner. **NO new packages**.
- **044 Operator Dashboard & Diagnostics** — frontend-only; reuses `lib/ws.ts`.
- **049 Analytics & Cost Dashboard** — frontend-only.
- **050 Evaluation/Testing UI** — frontend-only.

---

## Governance, Workflow, Fleet, Evaluation (028–029, 033–034, 038–040)

- **028 Policy & Governance Engine** (`platform/policies/`) — PG (5 tables: `policy_policies`, `policy_versions`, `policy_attachments`, `policy_blocked_action_records`, `policy_bundle_cache`) + Redis (`policy:bundle:{fingerprint}` TTL 300s, write rate-limit counters). GovernanceCompiler (typed EnforcementBundle + task-scoped shards, SHA-256 fingerprint cache); ToolGatewayService 4-check (permission→purpose→budget→safety, fail-safe deny-all); MemoryWriteGateService (namespace authz + Redis sliding-window + contradiction check); OutputSanitizer (5 pre-compiled regex → `[REDACTED:type]`); visibility-aware registry filter (SQL-level WHERE, zero-trust default); topics `policy.events`, `policy.gate.blocked`. Canonical site for `policies/` logic: `governance/services/judge_service.py:19` (NOT `policies/services/policy_engine.py`).
- **029 Workflow & Execution Engine** (`platform/workflows/` + `platform/execution/`) — PG (10 tables: `workflow_definitions`, `workflow_versions`, `workflow_trigger_definitions`, `executions`, `execution_events`, `execution_checkpoints`, `execution_dispatch_leases`, `execution_task_plan_records`, `execution_approval_waits`, `execution_compensation_records`) + Redis (`exec:lease:{exec}:{step}`, `exec:state:{exec}` TTL 30s) + MinIO `execution-task-plans`. YAML parser + JSON Schema + WorkflowCompiler IR + 7 trigger types; append-only journal + ExecutionProjector + SchedulerService priority queue + replay/resume/rerun + hot change + compensation + approval gates + dynamic re-prioritization; gRPC to RuntimeControl + ReasoningEngine; topics `execution.events`, `workflow.triggers`. Deps: PyYAML 6.x, jsonschema 4.x.
- **033 Fleet Management & Learning** (`platform/fleet/`) — PG (12 tables) + Redis (`fleet:health:{id}` JSON TTL 90s, `fleet:member:avail:{fleet_id}:{fqn}` TTL 120s) + ClickHouse (read `execution_metrics` from 020) + MinIO bucket `fleet-patterns`.
- **034 Evaluation & Semantic Testing** (`platform/evaluation/`) — PG (13 tables) + Qdrant collection `evaluation_embeddings` + ClickHouse table `testing_drift_metrics` + MinIO buckets `evaluation-ate-evidence`, `evaluation-generated-suites`. LLM-as-Judge + adversarial gen via httpx; APScheduler drift scanner; gRPC to Simulation + Reasoning.
- **038 AI Agent Composition** (`platform/composition/`) — PG (5 tables). LLM API calls via httpx.
- **039 Scientific Discovery Orchestration** (`platform/discovery/`) — PG (8 tables) + Redis sorted sets `leaderboard:{session_id}` + Neo4j (provenance graph) + Qdrant collection `discovery_hypotheses` (1536-dim Cosine). Deps: scipy ≥ 1.13 (clustering), numpy ≥ 1.26.
- **040 Simulation & Digital Twins** (`platform/simulation/`) — PG (5 tables) + Redis `sim:status:{run_id}` + ClickHouse read-only (`execution_metrics_daily` from 020). Deps: scipy ≥ 1.13 (regression + t-test), numpy ≥ 1.26.

---

## Operations & Infra (045–048)

- **045 Installer & Operations CLI** — Python CLI (Typer 0.12+, Rich, Jinja2 for Helm values, PyYAML, asyncpg, cryptography for RSA keys, aioboto3, PyInstaller for binary). Files-only state (checkpoints + manifests).
- **046 CI/CD Pipeline** — GitHub Actions: dorny/paths-filter@v3, golangci-lint-action@v6, bufbuild/buf-action@v1, gitleaks-action@v2, trivy-action, anchore/sbom-action@v0, softprops/action-gh-release@v2, docker/build-push-action@v6. Images → ghcr.io; SBOMs → GitHub Release assets.
- **047 Observability Stack** — Helm umbrellas: opentelemetry-collector, kube-prometheus-stack, jaegertracing/jaeger. Python: opentelemetry SDK already in control plane; Go: go.opentelemetry.io/otel. Storage: BadgerDB PVC (5 GiB, Jaeger traces 7d), Prometheus PVC (20 GiB, metrics 15d).
- **048 Backup & Restore** — Typer CLI; APScheduler; aiokafka; aioboto3 (optional S3 upload). JSON manifests on local FS or MinIO bucket.

---

## Cross-Cutting (052–056)

- **052 GID Correlation Envelope** — Starlette middleware. Tables: ClickHouse (`usage_events`, `usage_hourly_v2`); OpenSearch (`audit-events`, `connector-payloads` index templates). PG unaffected.
- **053 Zero-Trust Visibility** — feature flag (pydantic-settings). No new DDL; uses existing `workspaces_visibility_grants` + `registry_agent_profiles`.
- **054 Safety Pre-Screener & Sanitization** — opentelemetry-sdk 1.27+, PyYAML 6.x. PG enum value addition (Alembic 042).
- **055 Runtime Warm Pool** — Go (runtime-controller) + Python control plane. PG table `runtime_warm_pool_targets` (additive).
- **056 IBOR Integration & related rollups** — multi-feature umbrella spanning IBOR connector, model-router/audit-chain rollups, OpenSpec scaffolding. NEW dep: `ldap3 2.9+` (LDAP adapter). Deps already present: PyJWT 2.x, cryptography (JWKS RSA). PG tables added across this umbrella: `ibor_connectors`, `ibor_sync_runs`, plus 4 added columns and 1 new enum value on `registry_lifecycle_status`. Redis: 3 new key patterns (state + JWKS cache + rate limit). E2E harness uses `tests/e2e/` (kind ≥ 0.23, kubectl ≥ 1.28, helm ≥ 3.14, Docker ≥ 24); pytest 8 + pytest-asyncio + pytest-html + pytest-timeout + httpx + websockets + aiokafka + asyncpg + python-on-whales (optional). Existing Helm chart at `deploy/helm/platform/` — **do NOT fork**. Journey extension adds `pytest-xdist` (parallel for SC-005).

---

## Recent Quality / SaaS Features (075–089, 099)

- **075 Model Catalog & Fallback** — Python control plane only. (No further deltas tracked here.)
- **076 Privacy Compliance** — Python control plane only.
- **077 Multi-Channel Notifications** — PG: 3 new tables (`notification_channel_configs`, `outbound_webhooks`, `webhook_deliveries`) + 3 additive `DeliveryMethod` enum values (`slack`, `teams`, `sms`). Redis: 3 namespaces (`notifications:webhook_lease:{id}`, `notifications:webhook_dlq_depth`, `notifications:channel_verify:{token}`). Vault: `secret/data/notifications/webhook-secrets/{webhook_id}`, `secret/data/notifications/sms-providers/{deployment}`.
- **078 Content Safety & Fairness** — PG: 3 new tables (`content_moderation_policies`, `content_moderation_events`, `fairness_evaluations`). Vault: `secret/data/trust/moderation-providers/{provider}/{deployment}`. Cost-cap and threshold-cooldown counters reuse existing notifications counters.
- **079 Cost Governance & Chargeback** — PG: 5 new tables (`cost_attributions`, `workspace_budgets`, `budget_alerts`, `cost_forecasts`, `cost_anomalies`) via Alembic `062_cost_governance.py`. ClickHouse: 1 new table `cost_events` (TTL ≥ 2y) added in `cost_governance/clickhouse_setup.py` mirroring `analytics/clickhouse_setup.py`. Redis: `cost:budget:{ws}:{period_type}:{period_start}` (TTL = period+1d), `cost:override:{ws}:{nonce}` (single-shot, TTL ≤ 5min). No Vault.
- **080 Incident Response & Runbooks** — PG: 4 new tables (`incident_integrations`, `incidents`, `runbooks`, `post_mortems`) + supporting `incident_external_alerts` for per-(incident, integration) external-ref + delivery-state tracking. Alembic `063_incident_response.py`. Redis: `incident:dedup:{condition_fingerprint}` (TTL = max-incident-age + grace; FR-505.5), `incident:delivery:{integration_id}:{external_alert_id}` (FR-505.6). MinIO bucket prefix `incident-response-postmortems`. Provider creds at `secret/data/incident-response/integrations/{integration_id}` via existing `SecretProvider` (`common/clients/model_router.py:43–44`; `RotatableSecretProvider.get_current()` at `security_compliance/providers/rotatable_secret_provider.py:21`).
- **081 Multi-Region HA** — PG: 5 new tables (`region_configs`, `replication_statuses`, `failover_plans`, `failover_plan_runs`, `maintenance_windows`) via Alembic `064_multi_region_ops.py`. (Brownfield input proposed 4; the 5th splits run-history off the plan row for FR-478.10 audit.) Redis: `multi_region:active_window` (TTL = window duration; primed on enable; HOT-path), `multi_region:failover_lock:{from_region}:{to_region}` (TTL = max-plan-duration + grace; FR-478.12). Runbooks → `deploy/runbooks/` (Principle XVI separation).
- **082 Tags, Labels & Saved Views** — PG: 3 new tables (`entity_tags`, `entity_labels`, `saved_views`) via Alembic `065_tags_labels_saved_views.py`. Redis: `tags:label_expression_ast:{policy_id}:{version}` (TTL = `policy_cache_ttl_seconds`; invalidated on policy save). `common/tagging/` is a SHARED SUBSTRATE, not a BC — do NOT create rule-24/25 per-BC dashboard/E2E work for it. Canonical sites: `governance/services/judge_service.py:19`, `registry/service.py:371`. Seventh entity is `evaluation_runs` (NOT `evaluation_suites`). Cascade-on-delete is application-layer (per-BC delete path), not FK cascade.
- **083 Accessibility & i18n** — PG: 2 new tables (`user_preferences`, `locale_files`) via Alembic `066_localization.py`. No new Redis keys (locale files in per-process LRU; cache key `(locale_code, version)`). User-pref storage owned by `localization/` BC (NOT `auth/` or `accounts`); use `LocalizationService.get_for_user()` / `get_user_language()`. Rule 13 enforcement: `apps/web/eslint/no-hardcoded-jsx-strings.js`. Rule 28: `pnpm test:a11y`. Rule 38: `localization-drift-check` CI. Frontend root is `apps/web/`, NOT `apps/ui/`. `next-themes` + `cmdk` already wired pre-feature; this added High-Contrast, per-route command registration, `?` help overlay.
- **084 Log Aggregation & Dashboards** — Helm + Python structlog config (additive) + Go ContextHandler + TS isomorphic logger. **No SQL changes** (BC owns no relational tables). MinIO bucket `platform-loki-chunks` (constitutionally reserved). 1 in-cluster PVC (20 GiB default, configurable) for Loki hot tier. **OTEL Collector unchanged** — logs go via Promtail directly, NOT through OTEL Collector. Existing OTEL metrics→Prometheus and traces→Jaeger pipelines from 047 stay.
- **085 Extended E2E Journey (UPD-035)** — Python harness + Helm umbrella + Typer CLI + Playwright/axe helpers. Current chart dashboard inventory is **23** (not 22) — feature 083 added `localization.yaml`. Axe allowlist entries must expire within 90 days. J10 notifications rename remains gated on feature 072 owner sign-off.
- **086 Administrator Workbench & Composition** — headless super-admin bootstrap; `/api/v1/admin/*` composition; admin workbench route group `(admin)` (clean cut from `(main)`); 2PA/impersonation/read-only/config import-export primitives; topic `admin.events`. Filenames: `two_person_auth_*`. Bootstrap Job env-var mapping confirmed.
- **087 Public Signup Flow** — PG enum migration ONLY: `accounts_user_status` adds `pending_profile_completion`. No new tables, Redis keys, Kafka topics, Vault paths, or buckets. Frontend additions in Next.js auth UI.
- **088 Multilingual Repository README (UPD-038)** — Markdown + Python 3.12 stdlib + YAML only. **6 README files total**. Root `LICENSE`/`CONTRIBUTING.md`/`SECURITY.md` absent → out of scope. `docs/assets/` created here. `make dev-up` verified (cold-cache may exceed 5min). GitHub repo `gntik-ai/musematic`. `ci.yml` owns per-PR README filter. `gh` uses `GITHUB_TOKEN`/`GH_TOKEN`. CI installs `pandoc`. Feature 083 vendor reuse unconfirmed. Native-speaker reviews are an external gate.
- **089 Comprehensive Documentation Site (FR-605)** — MkDocs Material (NOT Docusaurus); FR v6 + architecture v5; reorganize existing `docs/` tree with redirects; create missing Terraform modules (Hetzner skeleton); add root `SECURITY.md`; FR-620 locales = `en`, `es`, `de`, `fr`, `it`, `zh`/zh-CN (NOT `ja`); GitHub Pages initial host; reuse `docs/assets/architecture-overview.svg`; Material search; `generate-env-docs.py`; `helm-docs` as CI tool; canonical app/API/Grafana URLs only; OpenAPI from FastAPI; preserve `site_url` and version with `mike`; mirror root `CHANGELOG.md` into release notes.
- **099 Marketplace Scope (UPD-049)** — marketplace scope dimension (`workspace`/`tenant`/`public_default_tenant`) on `registry_agent_profiles`. Platform-staff review queue at `/api/v1/admin/marketplace-review/*`. `POST /api/v1/registry/agents/{id}/fork`. Per-Enterprise-tenant `consume_public_marketplace` feature flag. Migration **108** (single Alembic file): 6 columns, 2 partial indexes, 3 CHECK constraints (incl. three-layer Enterprise refusal); replaces `tenant_isolation` policy with `agents_visibility`. Cross-tenant visibility uses 2 GUCs (`app.tenant_kind`, `app.consume_public_marketplace`) bound by existing `before_cursor_execute` listener. Frontend additions: `apps/web/components/features/marketplace/{publish,review}/` and `apps/web/lib/marketplace/`. Brownfield corrections: spec dir is `099-marketplace-scope` while git branch is `100-upd-049-marketplace` (intentional — spec dir tracks UPD-N numbering); admin pages live under `apps/web/app/(admin)/admin/`, **NOT** `(main)/admin/`; `docs/registry.md` and `docs/tenants.md` don't exist — canonical doc is `docs/saas/marketplace-scope.md`. T020 RLS visibility cross-product, T023–T030 + T048–T049 + T054–T056 + T060 + T064–T069 integration tests committed as scaffolds with skip markers pending live-DB+Kafka fixture; service-layer behaviour fully covered by smoke tests in `tests/unit/marketplace/`.

---

## Project Structure

```text
src/
tests/
```

## Commands

`cd src && pytest && ruff check .`

### Database & migrations
`make migrate` · `make migrate-rollback` · `make migrate-create NAME=add_feature` · `make migrate-check`

App traffic → `musematic-pooler:5432` (production). Migrations & admin ops → `musematic-postgres-rw:5432` (direct).

## Code Style

Python 3.12+ (application), PostgreSQL 16 (database): standard conventions.

SQLAlchemy model order: `Base` first, then behavior mixins (`UUIDMixin`, `TimestampMixin`, `SoftDeleteMixin`, `AuditMixin`, `WorkspaceScopedMixin`, `EventSourcedMixin`), then concrete columns.

---

## Standing Conventions (manual additions, do not auto-overwrite)

- **Repo:** `gntik-ai/musematic`. Frontend root: `apps/web/` (not `apps/ui/`).
- **Admin UI:** lives under `(admin)` route group, **not** `(main)/admin/`.
- **shadcn quirks here:** `Select` is native HTML `<select>`; `Tooltip` is a `sr-only` no-op stub.
- **Storage abstraction:** generic-S3 client per Principle XVI (`S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_USE_PATH_STYLE`).
- **Architecture decisions:** AD-14 (A2A external-only), AD-15 (MCP through tool gateway), AD-16 (generic S3, MinIO optional).
- **Canonical service sites:** `governance/services/judge_service.py:19` and `registry/service.py:371` (NOT `policies/services/policy_engine.py` or `registry/services/registry_query_service.py` — those don't exist).
- **OpenSpec migration:** capability-by-capability (12 capabilities), NOT feature-by-feature. CI workflows: `openspec-audit.yml`, `openspec-plan-drift.yml`, `tdd-enforcer.yml`.
- **Cascade-on-delete:** application-layer (per-BC delete path), not FK cascade.
- **`common/tagging/`** is a shared substrate, not a BC — no per-BC dashboard/E2E work.

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at `specs/106-hetzner-clusters/plan.md`.
<!-- SPECKIT END -->
