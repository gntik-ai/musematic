<!--
  Sync Impact Report
  ==================
  Version change: 1.0.0 → 1.1.0
  Bump rationale: MINOR — new Principle XVI, new Brownfield Rules
    section, 3 new critical reminders, 2 new Kafka topics.
  Modified principles:
    - None renamed or removed
    - XVI added: Generic S3 Storage, MinIO Optional
  Added sections:
    - Brownfield Rules (8 rules for update-pass governance)
  Removed sections: None
  Enhanced items:
    - Reminder 15: added "Resolved by Runtime Controller" context
    - Reminder 21: added "Internal coordination stays on Kafka + gRPC"
    - Reminder 22: added "Same policy, visibility, sanitization"
    - Reminder 23: added "TrajectoryScorer" context
  New reminders: 24 (zero-trust feature flag), 25 (no MinIO in app
    code), 26 (E2E on kind)
  New Kafka topics: governance.verdict.issued,
    governance.enforcement.executed
  Templates requiring updates:
    - .specify/templates/plan-template.md ✅ compatible
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

**Version**: 1.1.0 | **Ratified**: 2026-04-09 | **Last Amended**: 2026-04-18
