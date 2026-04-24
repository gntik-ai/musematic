# Tasks: API Governance and Developer Experience

**Input**: Design documents from `/specs/073-api-governance-dx/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Required (CI coverage gate is ≥ 95% per the repo's existing `.github/workflows/ci.yml`); each user story has an associated test phase grounded in contract test IDs.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label [US1]–[US5]

---

## Phase 1: Setup

**Purpose**: Scaffold empty module directories, lint config, and placeholder files so all downstream phases can proceed in parallel.

- [X] T001 Create the new `common/` sub-package directories: `apps/control-plane/src/platform/common/middleware/`, `apps/control-plane/src/platform/common/rate_limiter/`, `apps/control-plane/src/platform/common/debug_logging/`, `apps/control-plane/src/platform/common/api_versioning/`, and `apps/control-plane/src/platform/common/lua/` (the latter may already exist — confirm). Add an empty `__init__.py` to each.
- [X] T002 [P] Add the Spectral ruleset `.spectral.yaml` at the repo root extending `spectral:oas` with the four custom rules from `contracts/openapi-endpoints.md` (every operation tagged, non-anonymous operations declare `security`, `/api/v1/admin/*` paths carry the `admin` tag, deprecated operations mention sunset date in description).
- [X] T003 [P] Create placeholder `ci/schema_diff.py` script at repo root (executable) that accepts `<previous_openapi.json> <current_openapi.json>` and exits non-zero on breaking changes. Implementation deferred to T036; this task creates the file with a clear `NotImplementedError` stub so the workflow can reference it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration, Lua script, settings extensions, and exempt-path updates that every user story depends on.

**⚠️ CRITICAL**: No user story (Phase 3–7) can begin until Phase 2 is complete.

- [X] T004 Write Alembic migration `apps/control-plane/migrations/versions/057_api_governance.py` creating all four tables (`api_subscription_tiers`, `api_rate_limits`, `debug_logging_sessions`, `debug_logging_captures`) per `data-model.md` §1.1–1.4. Include the seed rows for the four default tiers (`anonymous`, `default`, `pro`, `enterprise`) with the budgets from `research.md` D-007. Include the 4-hour check constraint on `debug_logging_sessions.expires_at`.
- [X] T005 [P] Create `apps/control-plane/src/platform/common/lua/rate_limit_multi_window.lua` with the atomic three-bucket script from `data-model.md` §2.2.
- [X] T006 [P] Extend `apps/control-plane/src/platform/common/clients/redis.py` `initialize()` method (around line 112–118) to preload `rate_limit_multi_window.lua` alongside the existing four scripts; add a public `check_multi_window_rate_limit(...)` helper on `AsyncRedisClient` that wraps the `EVALSHA` call.
- [X] T007 [P] Extend `apps/control-plane/src/platform/common/config.py` with a new `ApiGovernanceSettings` Pydantic model (fields per `contracts/rate-limit-middleware.md` Settings table: `rate_limiting_enabled`, `rate_limiting_fail_open`, `tier_cache_ttl_seconds`, `principal_cache_ttl_seconds`, `anonymous_tier_name`, `default_tier_name`) and attach it to `PlatformSettings.api_governance`. Every field carries `Field(description=...)` so constitution rule 37 (auto-documented config) is honoured.
- [X] T008 [P] Update `EXEMPT_PATHS` in `apps/control-plane/src/platform/common/auth_middleware.py` (currently at lines 11–24) with the set from `contracts/openapi-endpoints.md` — add `/api/openapi.json`, `/api/docs`, `/api/redoc` and keep legacy paths (`/openapi.json`, `/docs`, `/redoc`) for one release cycle.
- [X] T009 Extend `AuthMiddleware` in the same file to set `request.state.user["principal_type"]` to one of `user` / `service_account` / `external_a2a` based on the existing resolution path. For JWT-authenticated users → `user`; for `resolve_api_key_identity` → `service_account`; for A2A-exempt paths where an external cert is present → `external_a2a`. If ambiguous, default to `user`.

**Checkpoint**: Foundation complete — all 5 user stories can now begin in parallel.

---

## Phase 3: User Story 1 — OpenAPI Discovery (Priority: P1) 🎯 MVP

**Goal**: Publish a canonical, lintable OpenAPI 3.1 document at `/api/openapi.json` with Swagger UI and Redoc renderings.

**Independent Test**: `curl http://localhost:8000/api/openapi.json | spectral lint --fail-on=error -` returns zero errors; `/api/docs` and `/api/redoc` load as interactive renderers.

### Tests for User Story 1

- [X] T010 [P] [US1] Unit test `apps/control-plane/tests/unit/common/test_openapi_config.py` asserting `create_app().openapi()["info"]` has `title`, `version`, `contact`; every path has at least one tag; every non-exempt operation has a non-empty `security` array; paths under `/api/v1/admin/` carry the `admin` tag.
- [X] T011 [P] [US1] Unit test `apps/control-plane/tests/unit/common/test_openapi_paths.py` asserting `create_app().openapi_url == "/api/openapi.json"`, `docs_url == "/api/docs"`, `redoc_url == "/api/redoc"`.

### Implementation for User Story 1

- [X] T012 [US1] Modify `apps/control-plane/src/platform/main.py` `create_app()` (line 712) to pass `openapi_url="/api/openapi.json"`, `docs_url="/api/docs"`, `redoc_url="/api/redoc"`, and `title`, `version`, `contact` per `contracts/openapi-endpoints.md`.
- [X] T013 [US1] Walk existing admin routers (search for `/admin/` in router prefixes) and add the `admin` tag to each via `APIRouter(prefix="/api/v1/admin/...", tags=["admin", "<bc>"])`. Update each file found in the grep; list of expected files includes any `admin_router.py` or admin sub-routers. Leave a tombstone comment if no admin routers exist yet.
- [X] T014 [US1] Add a new CI job `openapi-lint` to `.github/workflows/ci.yml` per `contracts/openapi-endpoints.md` CI-gate section: generates the OpenAPI doc via a Python one-liner and runs `stoplightio/spectral-action@v0.8.1` against it with the `.spectral.yaml` ruleset.

**Checkpoint**: US1 complete. Externally-visible: OpenAPI discoverable + lint-gated in CI.

---

## Phase 4: User Story 2 — SDK Generation + Publishing (Priority: P1)

**Goal**: On every tagged release, generate SDKs for Python, Go, TypeScript, Rust from the published OpenAPI doc and publish them atomically to their registries.

**Independent Test**: `gh workflow run sdks.yml -f release_tag=<test-tag>` runs to green; all four SDKs exist as job artefacts; publish jobs run or report failure atomically per FR-009.

### Tests for User Story 2

- [X] T015 [P] [US2] Write `ci/tests/test_schema_diff.py` covering: identical documents → no change flagged; field type change → breaking change flagged unless `BREAKING:` in release notes; path removed → breaking change; new optional field → non-breaking.

### Implementation for User Story 2

- [X] T016 [US2] Implement the schema-diff logic in `ci/schema_diff.py` (replaces the T003 stub). Compare two OpenAPI JSON documents; print breaking changes (removed paths, added-required fields, type changes); exit 1 when breaking changes are detected without a `BREAKING:` marker in the release body (passed via `GH_RELEASE_BODY` env).
- [X] T017 [US2] Create `.github/workflows/sdks.yml` with the exact job layout from `contracts/sdk-generation-ci.md`: `fetch-openapi`, `guard-schema-skew`, `generate` (4-way matrix), `publish` (4-way matrix). Pin generator versions (`openapi-python-client==0.21.*`, `oapi-codegen@v2.4.0`, `openapi-typescript@7`, `@openapitools/openapi-generator-cli@2.13`).
- [X] T018 [US2] Document the four publish-token secrets (`PYPI_TOKEN`, `NPM_TOKEN`, `CRATES_IO_TOKEN`, `GITHUB_TOKEN`) in `docs/administration/integrations-and-credentials.md` per constitution rule 37. Note that `GITHUB_TOKEN` is auto-provisioned; the other three are operator-provisioned one-time.

**Checkpoint**: US2 complete. On `release: published` events, SDKs publish atomically to PyPI / GitHub release assets / npm / crates.io.

---

## Phase 5: User Story 3 — Per-Principal Rate Limiting (Priority: P2)

**Goal**: Enforce per-principal rate limits across three temporal buckets with `X-RateLimit-*` headers and HTTP 429 + `Retry-After` on exhaustion.

**Independent Test**: Drive 305 requests against a default-tier user in one minute; assert the 301st returns 429 with a `Retry-After` header; wait 60 s and confirm the next request succeeds.

### Tests for User Story 3

- [X] T019 [P] [US3] Unit tests T1–T9 in `apps/control-plane/tests/unit/common/test_rate_limit_middleware.py` per `contracts/rate-limit-middleware.md`: below-budget, minute exhaustion, hour exhaustion, isolation between principals, tier change, anonymous tier, fail-closed, fail-open, exempt paths.
- [X] T020 [P] [US3] Integration test `apps/control-plane/tests/integration/common/test_rate_limit_e2e.py` per `contracts/rate-limit-middleware.md` integration-test contract: 320 sequential default-tier requests, two-principal isolation under concurrency, Redis bounce behaviour.

### Implementation for User Story 3

- [X] T021 [P] [US3] Create SQLAlchemy models `SubscriptionTier` and `RateLimitConfig` in `apps/control-plane/src/platform/common/rate_limiter/models.py` matching `data-model.md` §1.1–1.2.
- [X] T022 [P] [US3] Create Pydantic schemas in `apps/control-plane/src/platform/common/rate_limiter/schemas.py` for the admin tier-assignment API (request/response shapes).
- [X] T023 [P] [US3] Create `apps/control-plane/src/platform/common/rate_limiter/repository.py` with async query methods: `get_tier_by_name`, `get_rate_limit_config`, `upsert_rate_limit_config`.
- [X] T024 [US3] Implement `RateLimiterService` in `apps/control-plane/src/platform/common/rate_limiter/service.py`: tier resolution (with Redis-cached principal→tier mapping, 60 s TTL), effective budget computation (override > tier default), Redis EVALSHA invocation per `contracts/rate-limit-middleware.md` algorithm. Depends on T005, T006, T021, T023.
- [X] T025 [US3] Implement `RateLimitMiddleware` in `apps/control-plane/src/platform/common/middleware/rate_limit_middleware.py` delegating to `RateLimiterService`; emit `X-RateLimit-*` and `Retry-After` headers; respect `FEATURE_API_RATE_LIMITING_FAIL_OPEN` for the incident override; emit Prometheus metrics (`rate_limit_decisions_total`, `rate_limit_enforcement_duration_seconds`, `rate_limit_redis_errors_total`, `rate_limit_fail_open_activations_total`).
- [X] T026 [US3] Register `RateLimitMiddleware` in `apps/control-plane/src/platform/main.py` `create_app()` AFTER `AuthMiddleware` (line 808) and BEFORE any later middleware. Exact addition order: `app.add_middleware(RateLimitMiddleware)` after `app.add_middleware(AuthMiddleware)` and before the versioning middleware (T031).

**Checkpoint**: US3 complete. Every authenticated request carries `X-RateLimit-*` headers; exhaustion returns 429.

---

## Phase 6: User Story 4 — API Versioning & Deprecation (Priority: P2)

**Goal**: Deprecated routes emit `Deprecation`, `Sunset`, and `Link: …; rel="successor-version"` headers. After the sunset date, the route returns HTTP 410.

**Independent Test**: Register a stub route with a sunset-in-the-future marker; assert response has `Deprecation: true` + `Sunset` header. Monkey-patch `datetime.now` past the sunset; assert 410 Gone.

### Tests for User Story 4

- [X] T027 [P] [US4] Unit tests V1–V7 in `apps/control-plane/tests/unit/common/test_api_versioning_middleware.py` per `contracts/versioning-middleware.md`: non-deprecated route, deprecated before sunset, deprecated with successor, post-sunset 410, boundary at exact sunset time, OpenAPI reflection.
- [X] T028 [P] [US4] Integration test `apps/control-plane/tests/integration/common/test_versioning_e2e.py` covering end-to-end header emission and 410 short-circuit via a temporary stub route.

### Implementation for User Story 4

- [X] T029 [P] [US4] Create `apps/control-plane/src/platform/common/api_versioning/registry.py` with the `DeprecationMarker` dataclass, the module-level `_markers` dict, and `mark_deprecated` / `get_marker` functions per `data-model.md` §4.
- [X] T030 [P] [US4] Create the `@deprecated_route(sunset=..., successor=...)` decorator in `apps/control-plane/src/platform/common/api_versioning/decorator.py` matching `contracts/versioning-middleware.md`. The decorator attaches a `__deprecated_marker__` attribute to the endpoint function and mutates the docstring with the sunset + successor note.
- [X] T031 [US4] Implement `ApiVersioningMiddleware` in `apps/control-plane/src/platform/common/middleware/api_versioning_middleware.py` per contract: inbound 410 short-circuit on past sunset; outbound `Deprecation` + `Sunset` + `Link` header emission.
- [X] T032 [US4] In `apps/control-plane/src/platform/main.py` `create_app()`, immediately after `app.include_router(api_router)` add a loop that iterates `app.routes` and for each `APIRoute` with a `__deprecated_marker__` attribute on its endpoint: copies the marker into the registry keyed by `route.unique_id` and sets `route.deprecated = True`. Register `ApiVersioningMiddleware` as the outermost custom middleware.

**Checkpoint**: US4 complete. Deprecation lifecycle works end-to-end; OpenAPI doc shows `deprecated: true` on affected operations.

---

## Phase 7: User Story 5 — Time-Bounded Debug Logging (Priority: P3)

**Goal**: Support engineers open audited, time-bounded debug sessions (≤ 4 h) that capture PII-redacted request/response pairs for a user or workspace.

**Independent Test**: Open a 30-minute session for a user via `POST /api/v1/admin/debug-logging/sessions`; make a few requests as that user; fetch captures via GET; confirm redaction. Close the session; confirm no further captures.

### Tests for User Story 5

- [X] T033 [P] [US5] Unit tests D1–D6 in `apps/control-plane/tests/unit/common/test_debug_logging_redaction.py` per `contracts/debug-logging-api.md` §D: header allowlist, body field denylist, JWT regex, email regex, query-param stripping, body truncation with sha256 suffix.
- [X] T034 [P] [US5] Integration tests E1–E6 in `apps/control-plane/tests/integration/common/test_debug_logging_e2e.py` per `contracts/debug-logging-api.md` §E: single-user session capture, workspace-scoped capture, session expiry, manual termination, RTBF cascade, Kafka event emission.

### Implementation for User Story 5

- [X] T035 [P] [US5] Create SQLAlchemy models `DebugLoggingSession` and `DebugLoggingCapture` in `apps/control-plane/src/platform/common/debug_logging/models.py` per `data-model.md` §1.3–1.4.
- [X] T036 [P] [US5] Create Pydantic schemas in `apps/control-plane/src/platform/common/debug_logging/schemas.py` for the 6 admin endpoints (create session, list, get, delete, list captures, patch-disallowed) per `contracts/debug-logging-api.md` §A.
- [X] T037 [P] [US5] Create `apps/control-plane/src/platform/common/debug_logging/repository.py` with async methods: `create_session`, `get_session`, `find_active_session_for_target`, `list_sessions`, `terminate_session`, `append_capture`, `list_captures`, `purge_old_captures`.
- [X] T038 [P] [US5] Create `apps/control-plane/src/platform/common/debug_logging/redaction.py` implementing `redact_headers`, `redact_body`, `redact_path` per `contracts/debug-logging-api.md` §C.
- [X] T039 [P] [US5] Create `apps/control-plane/src/platform/common/debug_logging/events.py` following the `auth/events.py:publish_auth_event` pattern: three event types (`debug_logging.session.created`, `debug_logging.session.expired`, `debug_logging.capture.written`), published to a new `debug_logging.events` Kafka topic. Register event schemas via the platform's `event_registry.register` mechanism.
- [X] T040 [US5] Implement `DebugLoggingService` in `apps/control-plane/src/platform/common/debug_logging/service.py`: `open_session` (enforces 4-h cap + 10-char justification min + 409 on active conflicting session), `terminate_session`, `record_capture`, cache population of `debug_session:active:{target_type}:{target_id}` in Redis with 30 s TTL. Depends on T035, T037, T039.
- [X] T041 [US5] Implement `DebugCaptureMiddleware` (ASGI) in `apps/control-plane/src/platform/common/debug_logging/capture.py` per `contracts/debug-logging-api.md` §B: resolve candidate targets (user + workspace), check active-session cache, capture + redact + persist + emit event; non-blocking Kafka publish.
- [X] T042 [US5] Create admin router at `apps/control-plane/src/platform/common/debug_logging/router.py` with the 6 endpoints under `/api/v1/admin/debug-logging/sessions(/{id}(/captures))` per contract. Every method depends on `require_admin` or `require_superadmin`. Tag the router with `admin` + `debug-logging` for OpenAPI filtering.
- [X] T043 [US5] Register the admin router + `DebugCaptureMiddleware` in `apps/control-plane/src/platform/main.py` `create_app()`. Middleware installation order (from T026 + T032): Correlation → Auth → RateLimit → **DebugCapture** → ApiVersioning → routes.
- [X] T044 [US5] Add an APScheduler job `purge_debug_captures` in `apps/control-plane/src/platform/common/debug_logging/service.py` (registered at lifespan startup in `main.py`) running daily at 02:00 UTC, deleting captures older than the platform's audit-retention window whose parent session is terminated.

**Checkpoint**: US5 complete. Support engineers can open, observe, and close debug sessions; captures stay redacted and audited.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Regression protection, documentation alignment, and quickstart validation.

- [X] T045 Write regression test `apps/control-plane/tests/unit/common/test_middleware_order.py` that introspects `create_app().user_middleware` and asserts the exact order: Correlation → Auth → RateLimit → DebugCapture → ApiVersioning. This mitigates the Complexity Item #6 from `plan.md` (middleware-order regression risk).
- [X] T046 [P] Update the feature-catalogue skeleton `docs/features/073-api-governance-dx.md` (auto-generated by `docs/initial-site` branch — may not yet exist on this branch): replace the seven `TODO(andrea)` placeholders with grounded content now that the feature ships. If the file does not yet exist on this branch, create it with the curated content directly.
- [X] T047 [P] Update `docs/administration/integrations-and-credentials.md` with the PyPI/npm/crates.io/GitHub secret inventory from T018 (cross-reference the SDK generation workflow).
- [X] T048 Run the five quickstart walkthroughs (Q1–Q5 in `quickstart.md`) against a local `make dev-up` cluster and fix any divergence from documented behaviour before marking the feature complete.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS all user stories**.
- **US1 (Phase 3)**: Depends on Phase 2.
- **US2 (Phase 4)**: Depends on Phase 2. Requires US1 (OpenAPI publication) to have a document to generate SDKs from — but the SDK workflow reads from `https://api.musematic.ai/api/openapi.json` only at release time, so US2 implementation can proceed in parallel with US1 (the workflow simply won't green until US1 is deployed).
- **US3 (Phase 5)**: Depends on Phase 2. Independent of US1/US2/US4/US5.
- **US4 (Phase 6)**: Depends on Phase 2. Independent of US1/US2/US3/US5.
- **US5 (Phase 7)**: Depends on Phase 2. Independent of US1/US2/US3/US4.
- **Polish (Phase 8)**: Depends on US1–US5 complete.

### Within Phase 2

- T004 (migration) can run in parallel with T005–T009.
- T005–T008 all `[P]` (different files).
- T009 modifies `auth_middleware.py` — runs after T008 (same file) but can proceed immediately after.

### Within each user story

- Models (T021 US3, T029 US4, T035 US5) can all run `[P]`.
- Schemas / repositories can run `[P]` in each user story's phase.
- Services depend on models + repositories.
- Middleware / router registration depends on the service being implemented.
- Main.py edits (T026, T032, T043) are serialised because they touch the same file.

### Parallel execution opportunities

```bash
# Phase 1 (setup) — 3 parallel:
Task: "Scaffold common/ directories (T001)"
Task: "Add .spectral.yaml (T002)"
Task: "Stub ci/schema_diff.py (T003)"

# Phase 2 (foundational) — 4 parallel once T004 starts:
Task: "Alembic migration 057 (T004)"
Task: "rate_limit_multi_window.lua (T005)"
Task: "Redis client preload (T006)"
Task: "ApiGovernanceSettings (T007)"
Task: "EXEMPT_PATHS (T008)"
# T009 depends on T008 completing first.

# After Phase 2, all five user story phases can kick off in parallel
# across team members:
Developer A → US1 (Phase 3, 5 tasks)
Developer B → US2 (Phase 4, 4 tasks)
Developer C → US3 (Phase 5, 8 tasks) — most complex
Developer D → US4 (Phase 6, 6 tasks)
Developer E → US5 (Phase 7, 12 tasks) — most tasks

# Within US3 (Phase 5), 3 parallel after T007:
Task: "SQLAlchemy models (T021)"
Task: "Pydantic schemas (T022)"
Task: "Repository (T023)"
# T024 service depends on all three.
# T025 middleware depends on T024.
# T026 main.py registration depends on T025.
```

---

## Implementation Strategy

### MVP scope (US1 only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T009)
3. Complete Phase 3: US1 (T010–T014)
4. **STOP and VALIDATE**: `spectral lint /api/openapi.json` passes; Swagger UI and Redoc render; CI gate green. Feature delivers standalone value (developers can discover the API).

### Incremental delivery

1. MVP (US1) ships → marketplace of external integrators unlocked.
2. **+ US2 (SDK gen)** → integrators adopt the platform's ecosystems in four languages.
3. **+ US3 (rate limiting)** → platform capacity protected from misbehaving principals.
4. **+ US4 (deprecation)** → API lifecycle announce-and-sunset hygiene.
5. **+ US5 (debug logging)** → support ops has a compliant investigation tool.
6. Polish (T045–T048) lands with the last user story.

### Parallel team strategy (5 developers)

- **Developer A** (US1 P1): T010–T014. Smallest phase; can then pick up Polish tasks.
- **Developer B** (US2 P1): T015–T018. Mostly CI surface; independent of Python code changes.
- **Developer C** (US3 P2): T019–T026. Most architecturally load-bearing; owns the hot-path Redis call.
- **Developer D** (US4 P2): T027–T032. Small surface but touches main.py (coordinate with C).
- **Developer E** (US5 P3): T033–T044. Most tasks (12); largest module tree (six new files in `common/debug_logging/`).

Developers C, D, E all mutate `main.py` — serialise main.py edits on a single branch or use a shared "middleware-registration" commit.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in the same phase.
- [Story] label maps each task to its user story for traceability.
- Tests are part of each user story's phase (not a separate polish phase), matching the plan's constitution-driven 95 % coverage gate.
- Every constitution v1.3.0 rule cited in the plan has a corresponding task: rule 29 → T013, rule 30 → T042, rule 9 → T039, rule 23 → T038, rule 37 → T007.
- `main.py` is edited by T012, T026, T032, T043. Conflicts are unavoidable; resolve by having one developer own the final integration commit for `main.py`.
- The feature introduces exactly one Alembic migration (057); the migration chain continues linearly from `056_proximity_graph_workspace.py`.
