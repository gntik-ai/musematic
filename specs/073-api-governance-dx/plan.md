# Implementation Plan: API Governance and Developer Experience

**Branch**: `056-ibor-integration-and` (spec authored on this branch; will be
moved to a dedicated `073-api-governance-dx` branch for implementation)
**Date**: 2026-04-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/073-api-governance-dx/spec.md`

## Summary

Publish a canonical OpenAPI 3.1 document at `/api/openapi.json` with Swagger
UI and Redoc renderings; generate and publish official SDKs for Python, Go,
TypeScript, and Rust on every tagged release; add per-principal rate
limiting across three temporal buckets (minute / hour / day) enforced
server-side via a single atomic Redis Lua script; ship response headers
(`X-RateLimit-*`, `Retry-After`) on every response; add deprecation
hygiene (`Deprecation`, `Sunset`, `Link: …; rel="successor-version"`
headers + HTTP 410 after sunset); introduce time-bounded audited debug
logging for support. No new bounded context; all changes extend existing
files and add common modules.

## Technical Context

**Language/Version**: Python 3.12+ (control plane); Go, TypeScript, Rust
only in generated SDK artefacts (no production Go/TS/Rust runtime added).
**Primary Dependencies** (Python):
- FastAPI 0.115+ (already present; extend `create_app` signature)
- Pydantic v2 (request/response schemas on new endpoints)
- aioredis / redis-py 5.x async (already present; reuse
  `AsyncRedisClient` from `common/clients/redis.py`)
- SQLAlchemy 2.x async (already present; new `api_rate_limits`,
  `debug_logging_sessions`, `debug_logging_captures` tables)
- aiokafka 0.11+ (already present; new `debug_logging.events` topic)
- APScheduler 3.x (already present; debug-capture purge job)
- structlog (already used via `common/logging.py`) for request/response
  capture
**Primary Dependencies** (CI-only, new tooling):
- `openapi-python-client` — Python SDK generator
- `oapi-codegen` (v2) — Go SDK generator
- `openapi-typescript` + `openapi-fetch` — TypeScript SDK
- `openapi-generator-cli` — Rust SDK (requires JRE in CI runner)
- `spectral` or `redocly lint` — OpenAPI linter CI gate
**Storage**:
- PostgreSQL — 3 new tables via Alembic migration `057_api_governance.py`
  (`api_rate_limits`, `debug_logging_sessions`, `debug_logging_captures`)
- Redis — 4 new key prefixes:
  `ratelimit:principal:{type}:{id}:{bucket}`,
  `ratelimit:anon:{ip}:{bucket}`, plus a new Lua script
  `rate_limit_multi_window.lua` loaded at startup alongside the existing
  four scripts
- Kafka — 1 new topic `debug_logging.events`
**Testing**:
- pytest + pytest-asyncio 8.x
- Contract tests for new middlewares (rate-limit, versioning, debug
  logging) under `apps/control-plane/tests/integration/common/`
- CI gate: `spectral lint --fail-on error` on `/api/openapi.json`
- CI gate: SDK-matrix build succeeds on schema-stable releases
**Target Platform**: Linux (Kubernetes, Docker, or local native); same
deployment matrix as the rest of the control plane.
**Project Type**: Platform middleware + CI pipeline extension. No new
bounded context; extends existing `apps/control-plane/src/platform/
common/` and `main.py`.
**Performance Goals** (from SC-010): ≥ 1,000 rate-limit enforcement
decisions / second per instance with ≤ 5 ms median latency overhead.
Redis `EVALSHA` round-trip on the hot path is budgeted at ≤ 2 ms p50.
**Constraints**:
- Rate-limit middleware MUST fail-closed if Redis is unreachable
  (spec Assumption; no unthrottled bypass).
- Debug-capture session expiry is a hard 4 h maximum (FR-025); enforced
  both in DB check constraint and in application logic.
- SDK generation CI job runs only on `release: published` events; it
  is atomic (all or none).
- OpenAPI document size expected > 1 MB on full platform; served gzip.
**Scale/Scope**:
- ~30 endpoints (2 middlewares × 2 directions + 1 Lua script + 1 debug
  API surface + 1 versioning decorator) to implement.
- ~3 new Postgres tables, 1 new Alembic migration, 1 new Kafka topic.
- 1 new CI workflow file (`.github/workflows/sdks.yml`) + extensions
  to `ci.yml` for OpenAPI lint gate.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*
Evaluated against `.specify/memory/constitution.md` at v1.3.0.

| Gate | Status | Notes |
|------|--------|-------|
| **Principle I** — Modular monolith | ✅ PASS | Extends `common/` and existing routers; no new bounded context. |
| **Principle III** — Dedicated data stores | ✅ PASS | Postgres for durable config, Redis for hot state, Kafka for events. Each store used per its charter. |
| **Principle IV** — No cross-boundary DB access | ✅ PASS | New tables owned by `common/` (shared infrastructure); `debug_logging_*` tables are read only by the debug-logging module itself. |
| **Principle VI** — Policy is machine-enforced | ✅ PASS | Rate-limit tier changes take effect on next request; no markdown docs drive enforcement. |
| **Principle XI** — Secrets never in LLM context | ✅ PASS | Feature has no LLM surface; PII redaction guarantees secrets never reach captured logs. |
| **Brownfield Rule 1** — Never rewrite | ✅ PASS | Purely additive to `main.py` and `common/`; no file wholesale replaced. |
| **Brownfield Rule 2** — Alembic migration | ✅ PASS | Migration 057 for new tables. |
| **Brownfield Rule 3** — Preserve existing tests | ✅ PASS | Adds tests; touches no existing ones. |
| **Brownfield Rule 4** — Use existing patterns | ✅ PASS | Reuses `AsyncRedisClient`, `publish_*_event`, `BaseHTTPMiddleware`, Alembic, APScheduler. |
| **Brownfield Rule 7** — Backward-compatible APIs | ✅ PASS | Headers are added; no fields removed; `/api/openapi.json` is net-new. |
| **Brownfield Rule 8** — Feature flags | ⚠️ N/A | `FEATURE_API_RATE_LIMITING` already exists in the constitution's feature-flag inventory (default `true`); this feature honours it as the on/off switch. |
| **Rule 9** — PII audit chain | ✅ PASS | Debug sessions emit audit records via Kafka on create / expire / capture per D-014. |
| **Rule 13** — i18n for user-facing strings | ⚠️ N/A | No UI strings introduced (API middleware only). |
| **Rule 17** — HMAC-signed outbound webhooks | ⚠️ N/A | No outbound webhooks introduced. |
| **Rule 20** — Structured JSON logs | ✅ PASS | All new modules use `structlog` from `common/logging.py`. |
| **Rule 21** — Correlation IDs via ContextVars | ✅ PASS | Existing `CorrelationMiddleware` runs outermost; rate-limit + versioning middlewares inherit `contextvars` state. |
| **Rule 22** — Loki low-cardinality labels | ✅ PASS | `principal_id`, `session_id` emitted in payload, not as labels. |
| **Rule 23** — Secrets never reach logs | ✅ PASS | Canonical redaction pattern set (D-009) scrubs auth headers, OAuth params, tokens, and PII before capture persistence. |
| **Rule 29** — Admin endpoints segregated | ✅ PASS | `/api/v1/admin/debug-logging/*` is admin-only; lives under the admin prefix, gets the `admin` tag (D-002), and the SDK generator filters the tag out of consumer artefacts. |
| **Rule 30** — Admin endpoints declare role gate | ✅ PASS | Every debug-logging admin route depends on `require_admin` or `require_superadmin`. |
| **Rule 36** — Every UX-impact FR documented | ✅ PASS | OpenAPI discoverability (US1) is itself the documentation surface; no orphan FRs. |
| **Rule 37** — Env vars / Helm values auto-documented | ⚠️ PASS | Feature introduces no new env vars on the control plane; CI introduces publishing tokens only (documented in `docs/administration/integrations-and-credentials.md`). |
| **Rule 39** — SecretProvider for secrets | ⚠️ N/A | No new runtime secrets. PyPI/npm/crates.io publishing tokens live in GitHub Actions secret store (SecretProvider is a runtime concept; CI secrets fall outside rule 39's `*_TOKEN` env-name scope because they never appear in control-plane code). |
| **Rule 45** — Every user-facing backend has a UI | ⚠️ PARTIAL | User-visible surfaces (OpenAPI, Swagger, Redoc) ARE the UI. Debug-logging admin endpoints will get their UI in UPD-036 (Administrator Workbench); this feature ships the backend, tagged for future admin-UI consumption. |

**No violations.** Complexity-tracking: see below.

## Project Structure

### Documentation (this feature)

```text
specs/073-api-governance-dx/
├── plan.md                       ✅ This file
├── spec.md                       ✅ Feature specification
├── research.md                   ✅ Phase 0 output (15 decisions)
├── data-model.md                 ✅ Phase 1 output
├── quickstart.md                 ✅ Phase 1 output
├── contracts/
│   ├── openapi-endpoints.md      ✅ OpenAPI publication + Swagger/Redoc routes
│   ├── rate-limit-middleware.md  ✅ RateLimitMiddleware contract
│   ├── versioning-middleware.md  ✅ ApiVersioningMiddleware contract
│   ├── debug-logging-api.md      ✅ Admin API surface for debug sessions
│   └── sdk-generation-ci.md      ✅ .github/workflows/sdks.yml contract
└── checklists/
    └── requirements.md           ✅ Spec validation (all pass)
```

### Source Code (extending `apps/control-plane/`)

```text
apps/control-plane/src/platform/
├── main.py                                       # MODIFY: pass openapi_url/docs_url/redoc_url in create_app; register new middlewares
├── common/
│   ├── auth_middleware.py                        # MODIFY: extend EXEMPT_PATHS with /api/{openapi.json,docs,redoc}; expose principal_type on request.state.user
│   ├── clients/redis.py                          # MODIFY: preload new Lua script
│   ├── lua/
│   │   └── rate_limit_multi_window.lua           # NEW: atomic 3-bucket check, EVALSHA-loaded at startup
│   ├── middleware/
│   │   ├── __init__.py                           # NEW
│   │   ├── rate_limit_middleware.py              # NEW: reads request.state.user, calls multi-window Lua, sets X-RateLimit-* headers, 429 on budget exhaustion
│   │   └── api_versioning_middleware.py          # NEW: reads per-route deprecation markers, sets Deprecation/Sunset/Link, short-circuits 410 after sunset
│   ├── rate_limiter/
│   │   ├── __init__.py                           # NEW
│   │   ├── service.py                            # NEW: RateLimiterService wrapping Redis Lua + Postgres tier lookup
│   │   ├── models.py                             # NEW: SQLAlchemy RateLimitConfig, SubscriptionTier
│   │   ├── schemas.py                            # NEW: Pydantic request/response for admin tier/assignment API
│   │   └── repository.py                         # NEW: async queries
│   ├── debug_logging/
│   │   ├── __init__.py                           # NEW
│   │   ├── service.py                            # NEW: DebugLoggingService — open/expire session, write capture, purge job
│   │   ├── models.py                             # NEW: DebugLoggingSession, DebugLoggingCapture
│   │   ├── schemas.py                            # NEW: Pydantic admin API surface
│   │   ├── redaction.py                          # NEW: canonical PII redaction (allowlist + denylist + regex)
│   │   ├── capture.py                            # NEW: ASGI middleware component that writes captures when a matching session is active
│   │   ├── events.py                             # NEW: publish_debug_logging_event on session.created/expired/capture.written
│   │   └── router.py                             # NEW: admin endpoints POST/PATCH/DELETE /api/v1/admin/debug-logging/sessions
│   └── api_versioning/
│       ├── __init__.py                           # NEW
│       ├── decorator.py                          # NEW: @deprecated_route(sunset=, successor=) to attach metadata to endpoints
│       └── registry.py                           # NEW: in-process registry of deprecation markers keyed by route ID
└── migrations/versions/
    └── 057_api_governance.py                     # NEW: 3 tables + seed for SubscriptionTier rows

.github/workflows/
├── ci.yml                                        # MODIFY: add "OpenAPI lint" job (spectral lint on /api/openapi.json)
└── sdks.yml                                      # NEW: matrix of 4 languages, triggered on release: published
```

### Key Architectural Boundaries

- **Rate-limit middleware is stateless**; all budget state lives in Redis
  (`ratelimit:*` keys). Postgres holds only the principal → tier mapping
  and the tier → budget mapping (both small, cacheable).
- **Debug logging writes are synchronous** to Postgres during request
  handling (capture table). The path is gated by "is there an active
  session covering this request's scope?" — lookup is a single indexed
  query against `debug_logging_sessions`, cached with 30s TTL.
- **Deprecation markers live in process memory**, populated at import
  time from decorators. Zero DB queries on the hot path.
- **OpenAPI document generation** runs at startup (FastAPI default) and
  is served from memory. Lint runs in CI against the generated
  document — no runtime lint overhead.

## Complexity Tracking

No constitution violations. Highest-risk areas:

1. **Rate-limit hot-path latency.** Every authenticated request now makes
   one extra Redis `EVALSHA` round-trip. Mitigation: the Lua script is
   constant-time, the Redis client reuses the existing connection pool,
   the script is pre-loaded and cached by SHA. Budget is ≤ 2 ms p50. If
   this becomes a bottleneck, a per-instance in-memory token-bucket
   cache can front the Lua call (fallback decision documented).
2. **Debug-capture write amplification.** Sessions are intended for
   targeted investigation, but a support engineer could open a session
   scoped to a workspace with heavy traffic. Mitigation: the session
   creator enters a justification (FR-024), the session is hard-capped
   at 4 h (FR-025), and the capture-table purge job runs daily. Future
   iteration may add per-session capture caps.
3. **SDK generator version skew.** The four generators advance at
   different rates; upstream changes can emit subtly different code
   shapes across releases. Mitigation: pin exact generator versions in
   `sdks.yml`; an "SDK regeneration is breaking" smoke test runs
   against the platform itself before publication.
4. **OpenAPI document instability breaks SDKs silently.** A route's
   schema change (e.g. field type change) can produce SDKs that compile
   but fail at runtime. Mitigation: FR-009's atomicity gate; the
   publish step compares the new OpenAPI document's route-count and
   schema-field hash against the previous release and requires an
   explicit release-note flag for breaking changes.
5. **Rate-limit fail-closed vs. availability trade-off.** The Redis
   outage path returns 503; operators may prefer degraded (rate-limit
   off) to outright denial. Mitigation: the middleware reads a
   `FEATURE_API_RATE_LIMITING_FAIL_OPEN` override flag (default
   `false`) that can be flipped during incidents to skip the Lua call
   and pass the request; the flag flip is audit-logged.
6. **Middleware-order regression.** Future PRs could add middleware
   between `RateLimitMiddleware` and `AuthMiddleware` inadvertently.
   Mitigation: a unit test in
   `apps/control-plane/tests/unit/common/test_middleware_order.py`
   inspects `app.user_middleware` post-factory and asserts the exact
   order; the test fails loudly on re-order.

## Phase 0: Research

**Status**: ✅ Complete — see [research.md](research.md).

15 decisions (D-001 through D-015) cover OpenAPI path selection, admin
endpoint segregation, Redis Lua algorithm, key naming, middleware
order, anonymous tier scope, tier catalogue, debug-capture storage,
PII redaction patterns, SDK tool choice, release atomicity,
versioning-middleware design, Alembic numbering, Kafka event shape,
and exempt-path updates.

## Phase 1: Design & Contracts

**Status**: ✅ Complete.

- [data-model.md](data-model.md) — entities and storage mapping:
  `SubscriptionTier`, `RateLimitConfig`, `DebugLoggingSession`,
  `DebugLoggingCapture`, `DeprecationMarker` (in-process), Redis key
  schema, migration 057 shape.
- [contracts/openapi-endpoints.md](contracts/openapi-endpoints.md) —
  `/api/openapi.json`, `/api/docs`, `/api/redoc` routing contract
  + admin-tag exclusion rules.
- [contracts/rate-limit-middleware.md](contracts/rate-limit-middleware.md)
  — request/response shape, headers set, Lua call semantics,
  fail-closed behaviour.
- [contracts/versioning-middleware.md](contracts/versioning-middleware.md)
  — deprecation decorator contract, header emission rules, 410-Gone
  short-circuit.
- [contracts/debug-logging-api.md](contracts/debug-logging-api.md) —
  admin endpoints for session lifecycle + capture readback.
- [contracts/sdk-generation-ci.md](contracts/sdk-generation-ci.md) —
  `.github/workflows/sdks.yml` job matrix + atomicity gates.
- [quickstart.md](quickstart.md) — five walkthroughs (Q1–Q5), one per
  user story.

## Phase 2: Tasks

**Status**: ⏳ Deferred to `/speckit.tasks`.
