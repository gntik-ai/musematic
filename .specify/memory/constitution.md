<!--
  Sync Impact Report
  ==================
  Version change: 1.2.0 → 1.3.0
  Bump rationale: MINOR — audit-driven completeness pass expanded
    to 23 features by adding UPD-036 (Administrator Workbench and
    Super Admin Bootstrap), UPD-037 (Public Signup + OAuth UI
    completion), UPD-038 (Multilingual README), UPD-039
    (Comprehensive Documentation and Installation Guides), UPD-040
    (HashiCorp Vault Integration), UPD-041 (OAuth Provider Env-Var
    Bootstrap), and four user-surface completion features UPD-042
    (User-Facing Notification Center + Self-Service Security),
    UPD-043 (Workspace Owner Workbench + Connector Self-Service),
    UPD-044 (Creator-Side UIs — Context Engineering and Agent
    Contracts), and UPD-045 (Public Status Page, Maintenance
    Banner, and Remaining Workbench UIs). Adds 22 new
    domain-specific rules (29–50). No new bounded contexts,
    Kafka topics, REST endpoint prefixes, or feature flags versus
    v1.2.0 — the additions are in the rules surface and the
    feature catalogue. No existing principles removed or
    redefined.
  Modified principles:
    - None renamed or removed
    - Core Principles I–XVI preserved verbatim
  Added sections:
    - Brownfield Rules § "Domain-Specific Rules (Audit Pass)"
      extended with rules 29–50 (admin endpoint segregation,
      admin role gates, super-admin bootstrap secret handling,
      bootstrap idempotence, 2PA enforcement, impersonation
      double-audit, email-enumeration prohibition, documentation
      coupling, auto-documentation, multi-language parity,
      SecretProvider-only secret resolution, Vault token logging
      ban, Vault failure-closed critical path, OAuth env-var
      idempotence, OAuth-secrets-in-Vault-only, rotation response
      opacity, backend-to-UI coverage, self-service scoping,
      workspace-vs-platform scope distinction, user-visible
      platform state, status-page independence, mock LLM for
      creator previews)
  Removed sections: None
  New Kafka topics: 0 (UPD-036–UPD-045 reuse existing topics plus
    per-feature audit chain entries)
  Templates requiring updates:
    - .specify/templates/plan-template.md ✅ compatible
      (Constitution Check section is principle-number-agnostic)
    - .specify/templates/spec-template.md ✅ compatible
    - .specify/templates/tasks-template.md ✅ compatible
  Follow-up TODOs: None
-->

# Agentic Mesh Platform Constitution

> This file is the constitution of the project. It governs how all AI
> agents, workflows, and human developers interact with the codebase.
> Every implementation decision MUST be consistent with this document.
> When in doubt, this file wins over any other context.

## Project Identity

- **Name:** Agentic Mesh Platform
- **Type:** Multi-tenant agent orchestration platform
- **Domain:** Enterprise AI agent lifecycle management, workflow
  execution, fleet coordination, trust governance
- **Scope:** 391 functional requirements + 375 technical requirements
  = 766 total requirements
- **Architecture style:** Modular monolith (Python control plane) + Go
  satellite services + React frontend
- **Deployment target:** Kubernetes (primary), Docker, Docker Swarm,
  Incus, local native

## Brownfield Rules

> These rules govern the UPDATE pass aligning the platform with
> "Agentic Design Patterns" (Gulli, Springer 2025) and "Agentic Mesh"
> (Broda & Broda, O'Reilly 2026). The original codebase is already
> implemented from the initial backlog (52 features, Waves 1-12).

1. **Never rewrite existing code.** Extend, add, or modify — never
   replace a file wholesale.
2. **Every change is an Alembic migration.** No raw DDL. Every new
   column, table, index, or enum value goes through a numbered
   migration.
3. **Preserve all existing tests.** New code MUST include tests.
   Existing tests MUST keep passing.
4. **Use existing patterns.** Follow the conventions already
   established in the codebase: service layer classes, Pydantic
   schemas, FastAPI router structure, SQLAlchemy model mixins, Kafka
   event envelope format.
5. **Reference existing files.** Every spec and plan MUST cite the
   exact files and functions being modified.
6. **Additive enum values.** When adding enum values (e.g.,
   agent_status, role_type), add to the existing enum — never
   recreate it.
7. **Backward-compatible APIs.** New fields are optional with
   defaults. Existing endpoints keep working without changes from
   callers.
8. **Feature flags.** New behaviors that change defaults (e.g.,
   zero-trust visibility) MUST be behind a feature flag for gradual
   rollout.

### Domain-Specific Rules (Audit Pass — UPD-023 through UPD-045)

> The audit-driven completeness pass introduces 42 domain-specific
> rules across v1.2.0 and v1.3.0. They apply to features UPD-023
> through UPD-045 only. Rules 1–8 continue to apply to all
> brownfield work.
>
> - Rules 9–28 govern the original 13-feature scope (UPD-023
>   through UPD-035): privacy, security, cost, model routing,
>   i18n, tagging, logging, observability, accessibility.
> - Rules 29–50 govern the 10 additions (UPD-036 through UPD-045):
>   admin endpoint segregation, super-admin bootstrap,
>   2PA + impersonation, documentation coupling,
>   SecretProvider + Vault lifecycle, OAuth env-var bootstrap,
>   backend-to-UI coverage, self-service scoping,
>   workspace-vs-platform scope, platform state visibility,
>   status-page independence, mock LLM for creator previews.

9. **Every PII operation emits an audit chain entry.** The audit
   chain is append-only with hash linkage; tampering MUST be
   detectable. Use
   `security_compliance/services/audit_chain_service.py` — never
   write audit entries directly.
10. **Every credential goes through vault.** No plaintext secrets
    in code, config, database, or logs. Use
    `security_compliance/services/secret_rotation_service.py` for
    rotation-capable credentials.
11. **Every LLM call goes through the model router.** Model
    bindings MUST be validated against the approved catalog and
    fallback policies respected. Use
    `common/clients/model_router.py` — never call provider SDKs
    directly from business logic.
12. **Every cost-incurring action records an attribution.** Use
    `cost_governance/services/attribution_service.py` after every
    execution step. Budget enforcement happens at the tool gateway.
13. **Every user-facing string goes through i18n.** Hardcoded
    strings in JSX/TSX are a code-review blocker. Use the `t()`
    function everywhere.
14. **Every new entity supports tags and labels.** Add the
    polymorphic `entity_tags` / `entity_labels` relations when
    introducing new entity types; never reinvent tagging per
    context.
15. **Every data deletion cascades.** Right-to-be-forgotten MUST
    propagate across PostgreSQL, Qdrant, Neo4j, ClickHouse,
    OpenSearch, and S3. Use
    `privacy_compliance/services/cascade_deletion.py`.
16. **Every DSR request produces a tombstone.** Tombstones carry a
    cryptographic hash proving deletion completion and are
    themselves immutable audit records.
17. **Outbound webhooks are HMAC-signed.** SHA-256 with per-webhook
    secret. At-least-once delivery with idempotency keys. 3 retries
    over 24h, then dead-letter.
18. **Regional queries enforce data residency.** Cross-region
    transfers blocked when `data_residency_configs` restricts them.
    Enforcement at query time, not at install time.
19. **Maintenance mode respects in-flight work.** When enabled,
    block new writes but let in-flight executions complete.
    Read-only operations remain available.
20. **Every log line is structured JSON.** No `print()`, no
    `fmt.Println()` for operator-visible output. Use `structlog`
    (Python), `slog` with ContextHandler (Go), or the `log` helper
    (TypeScript). Required fields: `timestamp`, `level`, `service`,
    `bounded_context`, `message`.
21. **Correlation IDs propagate through ContextVars /
    context.Context.** `workspace_id`, `goal_id`,
    `correlation_id`, `trace_id`, `user_id` are set by middleware
    at request ingress and Kafka consumption — never passed
    manually.
22. **Loki labels are low-cardinality only.** Allowed: `service`,
    `bounded_context`, `level`, `namespace`, `pod`, `container`.
    High-cardinality values (`workspace_id`, `user_id`, `goal_id`)
    go in the JSON payload, NOT as labels.
23. **Secrets never reach logs.** Even with Promtail redaction,
    secrets MUST never be logged in the first place. Audit logger
    calls in security-sensitive paths (auth, OAuth, secret
    rotation, JIT issuance).
24. **Every new bounded context gets a dashboard.** A Grafana
    dashboard JSON MUST be authored and added to
    `deploy/helm/observability/templates/dashboards/`.
25. **Every new bounded context gets an E2E suite and a journey
    crossing point.** New BC suites live under
    `tests/e2e/suites/<bc_name>/`. At least one user journey MUST
    exercise the new BC at a boundary crossing.
26. **Journey tests run against real observability backends.** No
    mocking of Loki/Prometheus/Jaeger — the kind cluster hosts the
    full stack via the same Helm chart used in production.
27. **All dashboards ship via the unified Helm bundle.** Every
    dashboard MUST be a ConfigMap in
    `deploy/helm/observability/templates/dashboards/` with the
    `grafana_dashboard: "1"` label.
28. **Accessibility is tested, not promised.** The Accessibility
    User journey (J15) runs axe-core in headless browser
    automation and fails the build on any WCAG AA violation.
29. **Admin endpoints are segregated.** All admin-only REST
    endpoints live under `/api/v1/admin/*`, are tagged separately
    in OpenAPI, and have their own rate-limit group. Mixing
    admin and non-admin behaviour on a single endpoint is a
    constitution violation.
30. **Every admin endpoint declares a role gate.** Every method
    in every `admin_router.py` module MUST depend on either
    `require_admin` or `require_superadmin`. A CI static-analysis
    check shall fail the build if any method is missing the
    gate.
31. **Super-admin bootstrap never logs secrets.** Code paths for
    `PLATFORM_SUPERADMIN_PASSWORD` /
    `PLATFORM_SUPERADMIN_PASSWORD_FILE` MUST be reviewed for
    logging. Structured logger fields containing these values
    are forbidden.
32. **Bootstrap is idempotent.** Running the installer twice
    with identical inputs MUST NOT overwrite a super admin's
    credentials without the explicit `--force-reset-superadmin`
    flag, itself gated by `ALLOW_SUPERADMIN_RESET=true` in
    production.
33. **2PA is enforced server-side.** The client is informed that
    an action requires two-person authorisation but never
    enforces it alone. Servers validate the 2PA token freshly
    on apply.
34. **Impersonation always double-audits.** Every action
    performed during impersonation emits audit chain entries
    tagging BOTH the acting admin AND the effective user.
    Single-principal audits during impersonation are a
    data-integrity bug.
35. **Email enumeration is never permitted.** Signup, password
    reset, and OAuth flows MUST return neutral responses that
    do not reveal whether an email is already registered.
36. **Every new FR with UX impact must be documented.** PRs
    that add or modify FRs MUST also update the documentation
    site; CI flags undocumented FRs.
37. **Env vars, Helm values, and feature flags are
    auto-documented.** Developers annotate inline; CI
    regenerates the reference docs; drift fails the build.
    Never hand-edit the generated references.
38. **Multi-language parity is enforced, not hoped.** Canonical
    English content can lead translation by at most 7 days.
    Beyond that, CI blocks merges touching affected sections.
39. **Every secret resolves via SecretProvider.** Code MUST NOT
    call `os.getenv` / `os.Getenv` directly for names matching
    secret patterns (`*_SECRET`, `*_PASSWORD`, `*_API_KEY`,
    `*_TOKEN`) outside `SecretProvider` implementation files.
    A CI static-analysis check enforces this.
40. **Vault token value never appears in logs.** Structured log
    fields carrying the token, child tokens, AppRole SecretIDs,
    Kubernetes SA tokens, or OAuth client secrets are
    forbidden. Review + CI checks enforce.
41. **Vault failure does not bypass authentication.**
    Critical-path operations (login verification, OAuth
    callback) fail explicitly when Vault is unreachable and
    cache is cold. Hardcoded-credential fallbacks are never
    permitted.
42. **OAuth env-var bootstrap is idempotent.** Reinstall
    preserves manual UI changes unless `FORCE_UPDATE=true` is
    set. Force overwrite emits a critical audit chain entry.
43. **OAuth client secrets live in Vault, never in the
    database.** The database stores only the Vault path
    reference. Rotation happens in Vault via KV v2 versioning.
44. **Rotation responses never return the new secret.** Admin
    submits a secret for rotation; the API response confirms
    rotation but does not echo back any secret value.
45. **Every user-facing backend capability has a user-facing
    UI.** If a backend endpoint is user-accessible, a UI
    surface MUST exist for it — either a dedicated page or
    integration into an existing workbench. Admin-only UIs are
    not a substitute for user self-service.
46. **Self-service endpoints are scoped to `current_user`.**
    Endpoints under `/api/v1/me/*` accept no `user_id`
    parameter and always operate on the authenticated
    principal's own data. Cross-user access attempts return
    403 without information leakage.
47. **Workspace-scoped resources clearly distinguish from
    platform-scoped.** When a resource type can be both
    workspace-owned and platform-owned (connectors, quotas,
    policies, visibility grants), the UI MUST visually
    distinguish scope and the backend MUST enforce it on every
    operation. Cross-scope leakage is a security bug.
48. **Platform state is user-visible.** Maintenance mode,
    incidents, and degraded performance are never invisible
    errors from the user's perspective. The shell always shows
    explanatory context via `<PlatformStatusBanner>`.
49. **Public status page is operationally independent.** The
    status page MUST remain reachable during a full platform
    outage. Its deployment topology MUST NOT share a single
    point of failure with the main platform.
50. **Mock LLM provider for creator previews.** Context profile
    previews, contract previews, and any test-time execution
    that could otherwise cost money or produce side effects
    MUST default to the mock LLM provider. Real-LLM preview is
    an explicit opt-in with a clear cost indicator.

## Core Principles

These decisions are locked. Do not deviate without explicit human
approval.

### I. Modular Monolith for the Python Control Plane

The Python control plane is ONE codebase deployed as MULTIPLE runtime
profiles (api, scheduler, worker, projection-indexer, trust-certifier,
context-engineering, agentops-testing, ws-hub). All bounded contexts
live in the same repo. They communicate in-process via service
interfaces and via Kafka events where decoupling is needed. No bounded
context directly accesses another's database tables.

### II. Go Reasoning Engine as a Separate Satellite Service

The reasoning engine (`services/reasoning-engine/`) is a separate Go
binary communicating via gRPC. It handles:

- Reasoning budget tracking (sub-millisecond via Redis)
- Self-correction convergence detection (tight numerical loops)
- Tree-of-thought branch management (concurrent goroutines)
- Chain-of-thought trace coordination

The Python monolith has thin coordination layers (`reasoning/` and
`self_correction/` bounded contexts) that handle API exposure, policy
resolution, event consumption, and query interfaces. They delegate all
hot-path execution to the Go reasoning engine via gRPC.

### III. Dedicated Data Stores from Day 1

Every data store is chosen for its workload characteristics:

- **PostgreSQL**: ACID relational truth. Never use it for vector
  search, full-text marketplace search, OLAP analytics, or caching.
- **Qdrant**: All vector operations. Never store vectors in PostgreSQL.
- **Neo4j**: All graph traversals. Never use recursive CTEs in
  PostgreSQL for graph queries (except in local mode fallback).
- **ClickHouse**: All time-series analytics and aggregations. Never
  compute rollups in PostgreSQL.
- **Redis**: All caching and hot state. Never use application-level
  in-memory caches for shared state.
- **OpenSearch**: All full-text search and marketplace discovery. Never
  use PostgreSQL FTS for user-facing search.
- **Kafka**: All async event coordination. Never use database polling
  for event-driven patterns.

### IV. No Cross-Boundary Database Access

Bounded context A MUST NOT query bounded context B's tables directly.
Inter-context communication happens through:

1. Well-defined internal service interfaces (Python function calls
   within the monolith)
2. Kafka events (for decoupled async communication)
3. Explicit query APIs (read-only projections)

### V. Append-Only Execution Journal

The workflow execution journal is append-only. Current execution state
is computed by projecting journal events. Never mutate journal entries.
Never delete journal entries.

### VI. Policy Is Machine-Enforced

Markdown files (TOOLS.md, SOUL.md) are descriptive documentation. They
never constitute the enforcement model. All enforcement happens through
structured policies, the tool gateway, memory write gate, and approval
systems.

### VII. Simulation Isolation from Production

Simulation workloads MUST run in a separate Kubernetes namespace
(`platform-simulation`) with network policies preventing access to
production namespaces. Simulation artifacts are tagged and stored in
separate buckets. No simulation code path can trigger real external
actions.

### VIII. Agent Identity Uses FQN as Primary Addressing

Every agent has a Fully Qualified Name: `{namespace}:{local_name}`
(e.g., `finance-ops:kyc-verifier`). The FQN is the primary scheme for
discovery, policy attachment, certification binding, and visibility
configuration. Namespaces are unique across the platform. Within a
namespace, local names are unique. Each FQN may have multiple running
instances, each with a UUID.

### IX. Zero-Trust Default Visibility for Agents

By default, a new agent sees zero agents and zero tools. Visibility
MUST be explicitly granted through the agent's visibility
configuration (FQN patterns — exact match or regex). Workspace-level
visibility grants can override per-agent defaults. This is a security
posture, not a convenience feature.

### X. Goal ID (GID) Is a First-Class Correlation Dimension

Goal-oriented workspaces use a Goal ID (GID) to track all activity
related to a shared objective. The GID is a first-class field in the
`CorrelationContext` alongside workspace_id, conversation_id,
interaction_id, execution_id, and fleet_id. The workspace serves as a
super-context — a persistent, searchable, real-time shared scratchpad.

### XI. Secrets Are Never in the LLM Context Window

Secrets (API keys, database credentials, tokens) are injected by the
runtime framework directly into tool executions, bypassing the LLM's
context window entirely. Tool output sanitization strips any secret
patterns before returning results to the LLM context. Any design that
passes secrets through the LLM is a security violation.

### XII. Task Plans Are Persisted as Auditable Artifacts

Every agent execution MUST persist its task plan — the structured plan
the agent created before execution begins. Task plans are stored as
`TaskPlanRecord` in PostgreSQL (metadata) and object storage (full
payload). This supports Layer 4 (explainability) of the seven-layer
trust framework.

### XIII. Attention Pattern for Out-of-Band Agent-Initiated Urgency

Agents can signal urgent need for human input or peer assistance via
the Attention pattern — a dedicated out-of-band channel
(`interaction.attention` Kafka topic) that does not interrupt regular
execution flow. Users receive attention signals via a dedicated
WebSocket channel distinct from operational alerts.

### XIV. A2A Protocol for External Agent Interoperability

The platform implements the A2A (Agent-to-Agent) open protocol for
interoperability with external agents. A2A is for external
agent-to-agent communication only; internal communication continues to
use Kafka events and gRPC. All A2A interactions go through
authentication, RBAC, policy enforcement, and output sanitization.

### XV. MCP for External Tool Interoperability

The platform supports the Model Context Protocol (MCP) for plug-and-
play tool interoperability. All MCP tool invocations go through the
tool gateway with the same policy validation, visibility checks, and
output sanitization as native tools.

### XVI. Generic S3 Storage, MinIO Optional

Object storage access MUST use the generic S3 protocol via
boto3/aws-sdk-go-v2 with provider-agnostic configuration
(`S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`,
`S3_BUCKET_PREFIX`). Any S3-compatible provider (Hetzner, AWS, R2,
Wasabi) works. MinIO is a dev/self-hosted option only — never a hard
dependency. Application code MUST NOT reference MinIO directly.
MinIO appears only in optional Helm charts and docker-compose.dev.

## Architecture Decisions (Audit Pass — UPD-023 through UPD-045)

> AD-1 through AD-13 are embedded in Core Principles I–XVI above.
> AD-14 through AD-16 are formalized by Principle XIV, XV, XVI.
> The audit pass adds AD-17 through AD-23 below.

- **AD-17: Tombstone-based RTBF proof.** Right-to-be-forgotten
  produces immutable tombstone records with a cryptographic hash.
  Tombstones are themselves audit records — they never contain the
  deleted data.
- **AD-18: Hash-chain audit integrity.** Audit log entries link to
  their predecessor via hash. Chain integrity is verifiable.
  Export is signed for regulatory submission.
- **AD-19: Provider-agnostic model routing.** All LLM calls go
  through the model router. Provider SDKs are never imported from
  business logic.
- **AD-20: Per-execution cost attribution.** Cost is a first-class
  dimension alongside correlation IDs. Every execution step
  records model/compute/storage/overhead to ClickHouse
  synchronously at commit.
- **AD-21: Region as a first-class dimension.** Every workspace
  has a region. Cross-region transfers require explicit
  configuration; enforcement is at query time, not at install
  time.
- **AD-22: Structured JSON logs only.** All platform services emit
  JSON to stdout with a canonical field set. Promtail parses and
  redacts before shipping to Loki. Unstructured logging is a
  constitution violation.
- **AD-23: Loki for logs; Jaeger for traces; Prometheus for
  metrics.** Three separate backends bound together by Grafana and
  linked by shared label conventions (`trace_id`, `service`,
  `correlation_id`). No single-backend consolidation is planned.

## New Bounded Contexts (Audit Pass — UPD-023 through UPD-045)

The audit pass introduces 7 new bounded contexts from v1.2.0
(UPD-023 through UPD-035). v1.3.0 (UPD-036 through UPD-045)
adds no new bounded contexts — those features extend existing
ones (`auth/`, `accounts/`, `connectors/security.py`) and add
new frontend surfaces (`/admin/*`, `/signup`, `/notifications`,
`/workspaces/{id}`, `/settings/*`, `status.musematic.ai`,
creator workbench pages). All Python BCs live under
`apps/control-plane/src/platform/` and follow the standard
bounded context structure (`models.py`, `schemas.py`,
`service.py`, `repository.py`, `router.py`, `events.py`,
`exceptions.py`).

| Bounded Context | Owning Feature | Scope |
|---|---|---|
| `privacy_compliance/` | UPD-023 | DSR, RTBF cascade, DLP, PIA, residency |
| `security_compliance/` | UPD-024 | SBOM, vuln, pentest, rotation, JIT, audit chain, compliance evidence |
| `cost_governance/` | UPD-027 | Attribution, chargeback, budgets, forecasting |
| `multi_region_ops/` | UPD-025 | Region config, replication monitoring, failover, maintenance mode |
| `model_catalog/` | UPD-026 | Approved models, model cards, fallback policies, provider credentials |
| `localization/` | UPD-030 | Locale files, i18n workflow, user locale preferences |
| `incident_response/` | UPD-031 | Incidents, runbooks, post-mortems |

The existing `privacy/` baseline differential-privacy context is
absorbed into `privacy_compliance/`. The existing `notifications/`
and `audit/` contexts are EXTENDED (not replaced) by UPD-028 and
UPD-024 respectively.

## Observability Extension (UPD-034 and UPD-035)

Feature 047 established Prometheus + Jaeger + Grafana. The audit
pass extends this with:

- **Loki** — structured log aggregation; uses S3 for chunk storage
  (`platform-loki-chunks` bucket); hot retention 14 days; labels
  are low-cardinality only (rule 22)
- **Promtail** — Loki's collector; parses JSON logs and applies
  redaction patterns; best-effort, MUST NOT crash nodes
- **14 new Grafana dashboards** — one per new bounded context plus
  platform-wide composites; all shipped as ConfigMaps in the
  unified `deploy/helm/observability/` umbrella chart
- **Unified observability Helm bundle** (UPD-035) — single-command
  install of the complete observability stack

## Tech Stack — Authoritative Reference

### Python Control Plane

| Component | Technology | Version |
|---|---|---|
| Runtime | Python | 3.12+ |
| Web framework | FastAPI | 0.115+ |
| Validation | Pydantic | v2.x |
| ORM | SQLAlchemy | 2.x (async only) |
| Migrations | Alembic | 1.13+ |
| Kafka client | aiokafka | 0.11+ |
| Redis client | redis-py | 5.x (async) |
| Qdrant client | qdrant-client | 1.12+ |
| Neo4j client | neo4j-python-driver | 5.x (async) |
| ClickHouse client | clickhouse-connect | 0.8+ |
| OpenSearch client | opensearch-py | 2.x (async) |
| Object storage | boto3 / aioboto3 | latest |
| HTTP client | httpx | 0.27+ (async) |
| gRPC client | grpcio + grpcio-tools | 1.65+ |
| Task scheduling | APScheduler | 3.x |
| Password hashing | argon2-cffi | 23+ (Argon2id) |
| JWT | PyJWT | 2.x (RS256) |
| TOTP | pyotp | 2.x |
| OpenTelemetry | opentelemetry-sdk | 1.27+ |
| Testing | pytest + pytest-asyncio | 8.x |
| Linting | ruff | 0.7+ |
| Type checking | mypy | 1.11+ (strict) |

### Go Satellite Services

| Component | Technology | Version |
|---|---|---|
| Runtime | Go | 1.22+ |
| gRPC | google.golang.org/grpc | 1.67+ |
| Protobuf | google.golang.org/protobuf | 1.34+ |
| Kubernetes client | client-go | 0.31+ |
| Redis client | go-redis/v9 | 9.x |
| PostgreSQL client | pgx/v5 | 5.x |
| Kafka client | confluent-kafka-go/v2 | 2.x |
| Object storage | aws-sdk-go-v2 | 2.x |
| OpenTelemetry | go.opentelemetry.io/otel | 1.29+ |
| Logging | log/slog | stdlib |
| Testing | testing + testify | stdlib + 1.9 |
| Linting | golangci-lint | 1.61+ |

### Frontend

| Component | Technology | Version |
|---|---|---|
| Framework | Next.js | 14+ (App Router) |
| Language | TypeScript | 5.x (strict) |
| UI library | React | 18+ |
| Component system | shadcn/ui | latest |
| Styling | Tailwind CSS | 3.4+ |
| Server state | TanStack Query | v5 |
| Client state | Zustand | 5.x |
| Forms | React Hook Form + Zod | 7.x + 3.x |
| Charts | Recharts | 2.x |
| Graph viz | @xyflow/react | 12+ |
| Code editor | Monaco Editor | 0.50+ |
| Markdown | react-markdown + remark-gfm | 9.x |
| Icons | Lucide React | latest |
| Dates | date-fns | 4.x |
| Package manager | pnpm | 9+ |

### Data Stores

| Store | Technology | Purpose | Port |
|---|---|---|---|
| Relational | PostgreSQL 16+ | System-of-record | 5432 |
| Vector search | Qdrant | Semantic memory | 6333/6334 |
| Graph | Neo4j 5.x | Knowledge graph | 7687/7474 |
| Analytics | ClickHouse | OLAP, cost intel | 8123/9000 |
| Cache/hot state | Redis 7+ Cluster | Sessions, budgets | 6379 |
| Full-text search | OpenSearch 2.x | Marketplace | 9200 |
| Event backbone | Apache Kafka | Durable streaming | 9092 |
| Object storage | S3-compatible | Artifacts, traces | 9000 |

### Infrastructure

| Component | Technology |
|---|---|
| Container orchestration | Kubernetes 1.28+ |
| Helm | Helm 3.x |
| PostgreSQL operator | CloudNativePG |
| Kafka operator | Strimzi |
| CI/CD | GitHub Actions |
| Container registry | ghcr.io |
| Observability | OTEL + Prometheus + Grafana + Jaeger |

## Repository Structure

```
apps/
  control-plane/
    src/platform/
      main.py
      api/ auth/ accounts/ workspaces/ connectors/ registry/
      marketplace/ interactions/ workflows/ execution/ fleets/
      policies/ trust/ promptops/ memory/ analytics/ evaluation/
      audit/ search/ notifications/ hooks/ workbenches/
      context_engineering/ reasoning/ self_correction/
      resource_optimization/ agent_composition/
      scientific_discovery/ privacy/ marketplace_intelligence/
      fleet_learning/ simulation/ agentops/ testing/
      communication/ a2a_gateway/
      common/
        config.py database.py dependencies.py exceptions.py
        pagination.py correlation.py auth_middleware.py
        events/ models/ clients/
    migrations/versions/
    entrypoints/
    tests/unit/ tests/integration/ tests/e2e/
  ui/nextjs-app/
  ops-cli/
services/
  runtime-controller/ reasoning-engine/ sandbox-manager/
  hostops-broker/ simulation-controller/
sdk/python/ sdk/go/
templates/
proto/
deploy/helm/
docs/
.github/workflows/
```

## Coding Conventions — Python

- All code is async. Use `async def` for all service, repository, and
  route handler methods.
- Never use `time.sleep()`. Use `asyncio.sleep()`.
- Never use synchronous database operations. Always `AsyncSession`.
- Never use global mutable state. Use dependency injection.
- All function signatures MUST have type annotations.
- All public functions MUST have docstrings.
- Maximum line length: 120 characters (ruff enforced).
- Import order: stdlib → third-party → local (ruff enforced).

### Bounded Context Structure

```
context_name/
  __init__.py
  models.py       # SQLAlchemy models (only this context's tables)
  schemas.py      # Pydantic request/response schemas
  service.py      # Business logic (async service class)
  repository.py   # Database access (async, SQLAlchemy queries only)
  router.py       # FastAPI router (thin — delegates to service)
  events.py       # Event definitions and publishers
  exceptions.py   # Context-specific exceptions
  dependencies.py # Context-specific FastAPI dependencies
  projections.py  # Read-model projections (if applicable)
```

### Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Files | snake_case | `context_engineering.py` |
| Classes | PascalCase | `ContextAssemblyRecord` |
| Functions | snake_case | `assemble_context()` |
| Constants | UPPER_SNAKE | `MAX_CONTEXT_TOKENS` |
| SQLAlchemy models | PascalCase, singular | `AgentRevision` |
| Pydantic schemas | PascalCase + suffix | `AgentRevisionCreate` |
| FastAPI routers | snake_case variable | `router = APIRouter(...)` |
| Kafka topics | dot.separated | `runtime.reasoning` |
| Kafka event types | dot.separated | `reasoning.budget.exceeded` |
| Alembic migrations | hash + description | `a1b2_add_table` |

### Error Handling

All domain errors inherit from `PlatformError(code, message, details)`.
Subtypes: `NotFoundError` → 404, `AuthorizationError` → 403,
`ValidationError` → 422, `PolicyViolationError` → 403,
`BudgetExceededError` → 429, `ConvergenceFailedError` → 500.

### Database Patterns

- Repository pattern: every bounded context owns its queries.
- Service layer: business logic, never raw SQL.
- Router: thin, delegates everything to service.
- Canonical event envelope (`EventEnvelope` Pydantic model) for all
  Kafka events with correlation context and trace context.

## Coding Conventions — Go

- Standard Go project layout: `cmd/`, `internal/`, `api/`, `pkg/`.
- All exported functions have doc comments.
- Errors are values. Use `fmt.Errorf("...: %w", err)` for wrapping.
- `context.Context` is the first parameter of every I/O function.
- Use `slog` for structured JSON logging.
- Use table-driven tests with `testify/assert`.
- Use `golangci-lint` with `govet`, `staticcheck`, `errcheck`, `gosec`.

## Coding Conventions — Frontend

- Function components only. No class components.
- Use `shadcn/ui` for ALL UI primitives. Never install alternative
  component libraries (no MUI, no Ant Design, no Chakra).
- No custom CSS files. Tailwind utility classes only (except
  `globals.css` for design tokens).
- `TanStack Query` for all server state. Never `useEffect` + `useState`
  for data fetching.
- `Zustand` for client-only state.
- `React Hook Form` + `Zod` for all forms.
- `date-fns` for all date operations. Never `moment.js`.

## Kafka Topics Registry

| Topic | Key | Producers | Consumers |
|---|---|---|---|
| `interaction.events` | interaction_id | interactions | workflow, monitor |
| `workflow.runtime` | execution_id | runtime controller | execution, analytics |
| `runtime.lifecycle` | runtime_id | runtime controller | execution, monitor |
| `runtime.reasoning` | execution_id | Go reasoning engine | reasoning coord |
| `runtime.selfcorrection` | execution_id | Go reasoning engine | self-correction coord |
| `sandbox.events` | sandbox_id | sandbox manager | execution, monitor |
| `workspace.goal` | workspace_id | interactions | agents, fleet orch |
| `connector.ingress` | workspace_id | connector workers | interactions |
| `connector.delivery` | workspace_id | execution engine | connector workers |
| `monitor.alerts` | — | all services | notifications, operator |
| `trust.events` | — | trust service | marketplace, registry |
| `evaluation.events` | — | evaluation engine | analytics, agentops |
| `context.quality` | execution_id | context eng service | analytics, drift |
| `fleet.health` | fleet_id | fleet observers | fleet learning |
| `agentops.behavioral` | agent_id | agentops service | analytics |
| `simulation.events` | simulation_id | simulation controller | simulation coord |
| `testing.results` | — | testing engine | evaluation, agentops |
| `communication.broadcast` | fleet_id | communication service | fleet members |
| `interaction.attention` | target_id | any agent | notifications, WS |
| `governance.verdict.issued` | — | judge agents | enforcer agents, audit |
| `governance.enforcement.executed` | — | enforcer agents | audit, operator |
| `privacy.dsr.received` | dsr_id | privacy_compliance | audit, notifications |
| `privacy.dsr.completed` | dsr_id | privacy_compliance | audit, notifications, admin |
| `privacy.deletion.cascaded` | dsr_id | privacy_compliance | audit |
| `privacy.dlp.event` | workspace_id | trust (DLP) | privacy_compliance, security_compliance, audit |
| `privacy.pia.approved` | pia_id | privacy_compliance | trust, registry |
| `security.sbom.published` | artifact_id | security_compliance | registry, audit |
| `security.scan.completed` | scan_id | security_compliance | release pipeline, audit |
| `security.pentest.finding.raised` | finding_id | security_compliance | trust, notifications |
| `security.secret.rotated` | credential_id | security_compliance | all credential consumers |
| `security.jit.issued` | grant_id | security_compliance | audit |
| `security.jit.revoked` | grant_id | security_compliance | audit |
| `security.audit.chain.verified` | — | security_compliance | compliance dashboard |
| `cost.execution.attributed` | execution_id | cost_governance | analytics, cost dashboard |
| `cost.budget.threshold.reached` | budget_id | cost_governance | notifications |
| `cost.budget.exceeded` | budget_id | cost_governance | notifications, execution (block) |
| `cost.anomaly.detected` | workspace_id | cost_governance | notifications, operator |
| `cost.forecast.updated` | workspace_id | cost_governance | cost dashboard |
| `region.replication.lag` | region_id | multi_region_ops | operator, incidents |
| `region.failover.initiated` | region_id | multi_region_ops | notifications, audit |
| `region.failover.completed` | region_id | multi_region_ops | notifications, audit |
| `maintenance.mode.enabled` | — | multi_region_ops | all services (drain) |
| `maintenance.mode.disabled` | — | multi_region_ops | all services (resume) |
| `model.catalog.updated` | model_id | model_catalog | registry, workflow |
| `model.card.published` | model_id | model_catalog | trust, registry |
| `model.fallback.triggered` | execution_id | model_catalog | analytics, cost_governance |
| `model.deprecated` | model_id | model_catalog | notifications, registry |
| `incident.triggered` | incident_id | incident_response | PagerDuty/OpsGenie/VictorOps |
| `incident.resolved` | incident_id | incident_response | post-mortem service |
| `content.moderation.event` | workspace_id | trust (moderator) | privacy_compliance, audit |

## REST Endpoint Prefixes (Audit Pass — UPD-023 through UPD-045)

| Prefix | Owner | Purpose |
|---|---|---|
| `/api/v1/privacy/dsr/*` | privacy_compliance | Data subject requests |
| `/api/v1/privacy/residency/*` | privacy_compliance | Region configuration |
| `/api/v1/privacy/dlp/*` | privacy_compliance | DLP rules and events |
| `/api/v1/privacy/pia/*` | privacy_compliance | Privacy impact assessments |
| `/api/v1/privacy/consent/*` | privacy_compliance | Consent records |
| `/api/v1/security/sbom/*` | security_compliance | SBOM retrieval |
| `/api/v1/security/scans/*` | security_compliance | Vulnerability scan results |
| `/api/v1/security/pentests/*` | security_compliance | Pen test tracking |
| `/api/v1/security/rotations/*` | security_compliance | Secret rotation schedules |
| `/api/v1/security/jit/*` | security_compliance | JIT credential management |
| `/api/v1/security/audit-chain/*` | security_compliance | Hash chain verification + export |
| `/api/v1/security/compliance/*` | security_compliance | Compliance evidence + controls |
| `/api/v1/costs/*` | cost_governance | Attribution, budgets, forecasts |
| `/api/v1/regions/*` | multi_region_ops | Region config, replication, failover |
| `/api/v1/maintenance/*` | multi_region_ops | Maintenance mode schedule |
| `/api/v1/model-catalog/*` | model_catalog | Approved models, model cards |
| `/api/v1/notifications/channels/*` | notifications | Channel configuration |
| `/api/v1/notifications/webhooks/*` | notifications | Outbound webhook registration |
| `/api/v1/openapi.json` | (FastAPI) | OpenAPI 3.1 specification |
| `/api/docs`, `/api/redoc` | (FastAPI) | Swagger UI / Redoc |
| `/api/v1/debug-logging/*` | (admin) | Time-bounded debug logging sessions |
| `/api/v1/incidents/*` | incident_response | Incidents and post-mortems |
| `/api/v1/runbooks/*` | incident_response | Runbook library |
| `/api/v1/tags/*` | common tagging | Generic tag CRUD across entities |
| `/api/v1/labels/*` | common tagging | Generic label CRUD |
| `/api/v1/saved-views/*` | common tagging | Saved filter combinations |
| `/api/v1/me/preferences` | localization | User preferences (theme, language, timezone) |
| `/api/v1/locales/*` | localization | Locale files |

## Integration Constraints (Audit Pass)

### Privacy compliance MUST NOT break existing features

- Cascade deletion (UPD-023) MUST NOT delete data owned by users
  who have not made a DSR request.
- DLP (UPD-023) is feature-flagged — default disabled until each
  workspace explicitly enables.
- Residency enforcement MUST NOT break cross-workspace discovery
  unless configured.

### Security compliance MUST NOT falsely block releases

- Vulnerability scan thresholds are tunable; critical CVEs in dev
  dependencies MUST NOT block platform releases.
- Hash-chain writes are asynchronous — synchronous hashing in
  every audit write would degrade performance.
- Secret rotation uses dual-credential windows; old and new
  credentials both valid during rotation.

### Cost governance MUST NOT produce stale data

- Attribution is written synchronously at execution commit, not
  in a batch job.
- Budget checks are cached but invalidated on every attribution
  write.
- Anomaly detection runs as an async job, not per request.

### Model catalog MUST NOT break existing agents

- Agents already using specific models are grandfathered via
  migration.
- Unapproved models during grace period show warning, not block.
- Fallback policies default to retry-only for safety.

### Multi-region MUST NOT add latency in single-region

- Region checks are fast-path when only one region is configured.
- Replication monitoring runs in the secondary region, not the
  primary.

### i18n MUST NOT regress accessibility

- Screen reader tests include all supported languages.
- RTL support is planned but not v1 — rollout carefully.

### Logs MUST NOT break services (UPD-034)

- Log emission is fire-and-forget; Loki unreachability MUST NOT
  cause application failures.
- Promtail is best-effort; pod failure MUST NOT crash the node.
- Redaction patterns are additive.
- Dashboard queries default to a bounded time range (1h).

### Observability MUST NOT cost more than it observes

- Log volume per service is watched; sustained >1 MB/sec triggers
  review.
- Label cardinality is capped (no `workspace_id`, `user_id`,
  `goal_id` as labels).
- Hot retention 14 days; older data lives in cold S3 archive at
  ~1/10 the cost.

## Feature Flag Inventory (Audit Pass)

| Flag | Default | Controlled By | Purpose |
|---|---|---|---|
| `FEATURE_PRIVACY_DSR_ENABLED` | `false` | superadmin | DSR API endpoints |
| `FEATURE_DLP_ENABLED` | `false` | workspace admin | Per-workspace DLP |
| `FEATURE_RESIDENCY_ENFORCEMENT` | `false` | superadmin | Cross-region transfer blocks |
| `FEATURE_CONTENT_MODERATION` | `false` | workspace admin | Per-workspace moderation |
| `FEATURE_COST_HARD_CAPS` | `false` | workspace admin | Hard-cap blocking |
| `FEATURE_API_RATE_LIMITING` | `true` | superadmin | Per-principal rate limiting |
| `FEATURE_APPROVED_MODEL_CATALOG_ENFORCEMENT` | `false` → `true` | superadmin | Grace period default false |
| `FEATURE_MAINTENANCE_MODE` | `false` | superadmin | Runtime maintenance mode |
| `FEATURE_MULTI_REGION` | `false` | superadmin | Secondary region replication |
| `FEATURE_I18N` | `true` | (always on) | UI i18n |
| `FEATURE_AUDIT_CHAIN_VERIFICATION` | `true` | (always on) | Hash chain writes |
| `FEATURE_STRUCTURED_LOGGING` | `true` | (always on) | JSON log emission |
| `FEATURE_LOKI_ENABLED` | `true` | superadmin | Loki log ingestion |
| `FEATURE_PROMTAIL_REDACTION` | `true` | superadmin | Promtail secret redaction |

## gRPC Service Registry

| Service | Proto file | Namespace | Port |
|---|---|---|---|
| RuntimeControlService | `runtime_controller.proto` | platform-execution | 50051 |
| ReasoningEngineService | `reasoning_engine.proto` | platform-execution | 50052 |
| SandboxService | `sandbox_manager.proto` | platform-execution | 50053 |
| HostOpsService | `hostops_broker.proto` | platform-execution | 50054 |
| SimulationControlService | `simulation_controller.proto` | platform-simulation | 50055 |

## Kubernetes Namespaces

| Namespace | Contents |
|---|---|
| `platform-edge` | Ingress, API gateway, WebSocket gateway |
| `platform-control` | Control-plane pods (all 8 profiles), BFFs |
| `platform-execution` | Runtime controller, reasoning engine, sandbox, HostOps, connectors |
| `platform-simulation` | Simulation controller, simulation pods (network-isolated) |
| `platform-data` | PostgreSQL, Qdrant, Neo4j, ClickHouse, Redis, OpenSearch, Kafka, MinIO |
| `platform-observability` | OTEL collector, Prometheus, Grafana, Jaeger |

## Local Mode Fallbacks

| Production Store | Local Fallback |
|---|---|
| PostgreSQL | SQLite |
| Qdrant | In-memory Qdrant (single-node) |
| Neo4j | SQLite recursive CTEs |
| ClickHouse | SQLite aggregate queries |
| Redis | In-process dict or embedded Redis |
| OpenSearch | SQLite FTS5 |
| Kafka | In-process asyncio queue |
| S3-compatible | Local filesystem |
| Go reasoning engine | Local subprocess or in-process mock |

## Quality Gates

### PR Merge Requirements

- ruff lint passes (Python)
- mypy --strict passes (Python)
- pytest passes with >=95% line coverage (Python)
- golangci-lint passes (Go)
- go test -race passes with >=95% coverage (Go)
- ESLint passes (Frontend)
- TypeScript compilation passes (Frontend)
- helm lint passes for all modified charts
- Alembic migration chain integrity verified
- No secrets in code (gitleaks)
- Proto files compile (buf lint + buf generate)

### Agent Deployment Gates (AgentOps)

- Policy conformance check passes
- Evaluation suite passes (configurable threshold)
- Certification is active (not expired/revoked)
- No behavioral regression detected (statistical significance)
- Trust tier qualification met

### Release Gates

- All PR merge requirements pass
- Integration tests pass
- E2E scenario tests pass (on kind, same Helm charts as production)
- Helm chart validation passes (kubeconform)
- Docker images build and scan clean
- SBOM generated

## Critical Reminders for AI Agents

1. Never bypass the tool gateway.
2. Never mutate the execution journal.
3. Never access another bounded context's tables.
4. Never store vectors in PostgreSQL. Use Qdrant.
5. Never compute analytics in PostgreSQL. Use ClickHouse.
6. Never use PostgreSQL FTS for user-facing search. Use OpenSearch.
7. Never cache in application memory for shared state. Use Redis.
8. Never allow simulation to reach production.
9. Never deploy an agent without passing all AgentOps gates.
10. Never let a self-correction loop run unbounded.
11. All async, all the time.
12. Correlation IDs everywhere.
13. Provenance on everything.
14. Budget tracking is real-time (Go + Redis, not Python batch).
15. Secrets never touch the LLM. Resolved by Runtime Controller,
    injected via env vars to tool code.
16. Agent visibility is zero-trust by default.
17. Use FQN for agent addressing.
18. Goal IDs (GID) are mandatory for workspace goals.
19. Persist task plans, not just reasoning traces.
20. Judge and Enforcer are distinct from Observer.
21. A2A is for external interoperability only. Internal agent
    coordination stays on Kafka + gRPC.
22. MCP tools go through the tool gateway. Same policy, visibility,
    sanitization as native tools.
23. Evaluate trajectories, not just outputs. TrajectoryScorer assesses
    the full action path.
24. Zero-trust visibility is a feature flag. Default OFF for existing
    deployments, ON for new deployments. Gradual rollout.
25. No MinIO in application code. All object storage access uses
    generic S3 config (`S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, etc.).
    MinIO is only in optional Helm chart and docker-compose.dev.
26. E2E tests run on kind, not docker-compose. The E2E environment
    uses the same Helm charts as production — no test-only bypass
    paths. Dev-only seeding/chaos endpoints live under
    `/api/v1/_e2e/*` gated by `FEATURE_E2E_MODE` and return 404 in
    production.
27. **Do not recreate existing functionality.** If in doubt, check
    the previous 22 features (original 52 + UPD-001 through
    UPD-022) first.
28. **Extend the existing testing bounded context.** UPD-021
    provides E2E kind infrastructure and UPD-022 provides user
    journey tests. New journey tests go alongside existing
    journeys — not in a parallel tree.
29. **Cascade deletion is destructive.** Test exhaustively on
    staging. Tombstones MUST always include the cryptographic
    proof.
30. **Audit chain writes MUST be durable.** Never drop an audit
    event under backpressure. Use Kafka durability guarantees.
31. **Cost data is cumulative.** Never modify past attributions.
    Corrections happen via credit entries.
32. **Model catalog governance is political.** Deprecation and
    blocking have organizational impact — always provide migration
    grace periods.
33. **Region failover is risky.** Test quarterly. Failback is
    harder than failover.
34. **i18n translations are a shared asset.** Treat locale files
    like code — versioned, reviewed, tested.
35. **Logs are not a substitute for traces.** Use traces for
    request flow, logs for context details. Don't log every step
    of a request — that's what spans are for.
36. **Dashboard sprawl is real.** 14 new dashboards in this pass
    is deliberate and bounded to new bounded contexts. Adding more
    requires justification and a new bounded context.
37. **Every LLM call routes through `model_router`.** Never import
    provider SDKs (openai, anthropic, google-generativeai, etc.)
    from business logic. The router enforces catalog + fallback.
38. **Every cost-incurring step calls `attribution_service`.**
    Budget enforcement happens at the tool gateway; attribution
    records happen at commit.
39. **Correlation IDs are context-managed, never passed
    manually.** Use ContextVars (Python) / `context.Context` (Go);
    middleware sets them at ingress.
40. **Loki labels MUST be low-cardinality.** `workspace_id`,
    `user_id`, `goal_id` go in the JSON payload, not as labels.
41. **WCAG AA violations fail the build.** Accessibility is
    enforced by axe-core in headless browser automation, not by
    review.

## Document References

| Document | Path |
|---|---|
| System Architecture | `docs/system-architecture.md` |
| Software Architecture | `docs/software-architecture.md` |
| Functional Requirements | `docs/functional-requirements.md` |
| Technical Requirements | `docs/technical-requirements.md` |
| Infra Backlog | `docs/backlog-infra.md` |
| Backend Backlog | `docs/backlog-backend.md` |
| Frontend Backlog | `docs/backlog-frontend.md` |

## Governance

- This constitution supersedes all other project documentation when
  there is a conflict.
- Amendments require: (1) written proposal, (2) justification of
  impact, (3) migration plan for existing code, (4) explicit human
  approval.
- All PRs and code reviews MUST verify compliance with the Core
  Principles listed above.
- Complexity beyond what the constitution prescribes MUST be justified
  in the PR description.
- The plan template's "Constitution Check" section validates feature
  plans against these principles before implementation begins.
- Version follows semantic versioning: MAJOR for principle removal or
  redefinition, MINOR for new principle or material expansion, PATCH
  for clarifications and wording fixes.

**Version**: 1.3.0 | **Ratified**: 2026-04-09 | **Last Amended**: 2026-04-23
