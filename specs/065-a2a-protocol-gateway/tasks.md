# Tasks: A2A Protocol Gateway

**Input**: Design documents from `specs/065-a2a-protocol-gateway/`  
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅ | quickstart.md ✅

**Organization**: Tasks are grouped by user story and preserve current implementation progress. All tasks are new (no prior implementation).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared in-progress dependency)
- **[US#]**: Maps to a user story from `spec.md`
- Exact file paths are included in every task

---

## Phase 1: Setup

**Purpose**: Create the bounded context skeleton, Alembic migration, and shared exceptions.

- [x] T001 Create `apps/control-plane/src/platform/a2a_gateway/__init__.py` (empty module init)
- [x] T002 [P] Create `apps/control-plane/src/platform/a2a_gateway/exceptions.py` — define `A2AAuthenticationError`, `A2AAuthorizationError`, `A2APolicyDeniedError`, `A2AAgentNotFoundError`, `A2ARateLimitError`, `A2AProtocolVersionError`, `A2APayloadTooLargeError`, `A2AUnsupportedCapabilityError`, `A2AInvalidTaskStateError`, `A2AHttpsRequiredError`
- [x] T003 [P] Create `apps/control-plane/migrations/versions/052_a2a_gateway.py` — Alembic migration adding enums `a2a_task_state` and `a2a_direction`, then tables `a2a_tasks`, `a2a_external_endpoints`, and `a2a_audit_records` exactly as defined in `specs/065-a2a-protocol-gateway/data-model.md`

---

## Phase 2: Foundational

**Purpose**: Models, schemas, repository, events, and card generator — shared across all user stories.

**⚠️ CRITICAL**: All user story phases depend on this phase being complete.

- [x] T004 [P] Create `apps/control-plane/src/platform/a2a_gateway/models.py` — SQLAlchemy ORM models `A2ATask`, `A2AExternalEndpoint`, `A2AAuditRecord` and enums `A2ATaskState`, `A2ADirection` following the data-model spec; use `Base`, `UUIDMixin`, `TimestampMixin` mixins in that order
- [x] T005 [P] Create `apps/control-plane/src/platform/a2a_gateway/schemas.py` — Pydantic v2 request/response schemas: `A2ATaskSubmitRequest`, `A2ATaskResponse`, `A2ATaskStatusResponse`, `A2AFollowUpRequest`, `A2AExternalEndpointCreate`, `A2AExternalEndpointResponse`, `AgentCardResponse`, `A2ASSEEvent` — field names must match the REST API contract in `specs/065-a2a-protocol-gateway/contracts/rest-api.md`
- [x] T006 Create `apps/control-plane/src/platform/a2a_gateway/repository.py` — `A2AGatewayRepository` with async methods: `create_task`, `get_task_by_task_id`, `update_task_state`, `create_external_endpoint`, `get_external_endpoint`, `list_external_endpoints`, `update_external_endpoint_cache`, `delete_external_endpoint`, `create_audit_record`, `list_tasks_idle_expired` (for the timeout scanner); uses `AsyncSession` pattern matching `interactions/repository.py`
- [x] T007 [P] Create `apps/control-plane/src/platform/a2a_gateway/events.py` — `A2AEventPublisher` wrapping the existing `EventProducer`; publish `EventEnvelope`-wrapped events to topic `a2a.events` for event types: `a2a.task.submitted`, `a2a.task.state_changed`, `a2a.task.completed`, `a2a.task.failed`, `a2a.task.cancelled`, `a2a.outbound.attempted`, `a2a.outbound.denied`; follow the `EventEnvelope` format from `apps/control-plane/src/platform/common/events/envelope.py`
- [x] T008 [P] Create `apps/control-plane/src/platform/a2a_gateway/card_generator.py` — `AgentCardGenerator` with method `generate_platform_card(session) -> dict` that queries active, public `AgentProfile` + `AgentRevision` records (via registry internal service interface), maps `fqn → name`, `purpose → description`, `manifest_snapshot → capabilities/skills/auth_schemes/endpoint_url`, excludes archived/revoked/incomplete agents, and returns a valid A2A Agent Card JSON dict

**Checkpoint**: Foundation is in place. Server-mode and client-mode implementation can start.

---

## Phase 3: User Story 1 — External Client Discovers and Invokes a Platform Agent (Priority: P1)

**Goal**: External clients can discover the platform via `GET /.well-known/agent.json`, authenticate, submit tasks, and track lifecycle (S1–S5, S8).

**Independent Test**: Fetch `GET /.well-known/agent.json`, authenticate with a Bearer token, POST to `/api/v1/a2a/tasks` targeting a real platform agent FQN, poll `GET /api/v1/a2a/tasks/{task_id}` until terminal state. Verify correct state transitions, A2A response format, audit record creation, and Kafka event emission.

- [x] T009 [US1] Create `apps/control-plane/src/platform/a2a_gateway/server_service.py` — `A2AServerService` with methods: `submit_task(request, principal_id, workspace_id, session)` (auth check via `AuthService.validate_token`, authz check via `ToolGatewayService.validate_tool_invocation`, rate-limit check via `AsyncRedisClient.check_rate_limit`, create `A2ATask` + backing `Interaction` via `InteractionsRepository.create_interaction`, emit `a2a.task.submitted`); `get_task_status(task_id, principal_id, session)` returning `A2ATaskStatusResponse`; `get_platform_agent_card(session)` returning the card JSON via `AgentCardGenerator`; `cancel_task(task_id, principal_id, session)` transitioning to `cancellation_pending`
- [x] T010 [US1] Create `apps/control-plane/src/platform/a2a_gateway/router.py` — FastAPI `APIRouter` with endpoints:  
  `GET /.well-known/agent.json` (anonymous, calls `server_service.get_platform_agent_card`);  
  `POST /api/v1/a2a/tasks` (authenticated, calls `server_service.submit_task`);  
  `GET /api/v1/a2a/tasks/{task_id}` (authenticated, calls `server_service.get_task_status`);  
  `DELETE /api/v1/a2a/tasks/{task_id}` (authenticated, calls `server_service.cancel_task`);  
  each endpoint maps exceptions from `exceptions.py` to correct HTTP status codes and A2A error body format per the REST API contract
- [x] T011 [US1] Modify `apps/control-plane/src/platform/main.py` — import `a2a_gateway_router` from `a2a_gateway.router`; add `app.include_router(a2a_gateway_router)` following the existing `include_router` pattern (lines 908–934); the `/.well-known/agent.json` route does NOT carry the `/api/v1/a2a` prefix, so it must be mounted at root or with an explicit path; the task endpoints use prefix `/api/v1/a2a`
- [x] T012 [P] [US1] Add unit tests for server-mode task submission and status in `apps/control-plane/tests/unit/a2a_gateway/test_server_service.py` — cover: valid submission creates task + interaction, auth failure raises A2AAuthenticationError, authz failure raises A2AAuthorizationError, rate-limit exceeded raises A2ARateLimitError, unknown agent FQN raises A2AAgentNotFoundError, task status polling returns correct state
- [x] T013 [P] [US1] Add integration tests in `apps/control-plane/tests/integration/a2a_gateway/test_server_mode.py` — cover scenarios S1, S4, S5, S6, S7, S8 from `specs/065-a2a-protocol-gateway/quickstart.md`

**Checkpoint**: Server-mode discovery + task submission is reachable and tested. Client mode starts next.

---

## Phase 4: User Story 2 — Platform Agent Invokes an External A2A Agent (Priority: P1)

**Goal**: Platform agents can call registered external A2A endpoints via a policy-checked internal service (S15, S16, S17, S24).

**Independent Test**: Register an external endpoint pointing to a mock A2A server. Call `A2AGatewayClientService.invoke_external_agent(...)` from a platform agent context. Verify: policy check passes, outbound task submitted, result returned to caller, audit record written, `a2a.outbound.attempted` event emitted. Test deny path: configure deny-all policy, verify `A2APolicyDeniedError` raised and `a2a.outbound.denied` emitted.

- [x] T014 [US2] Create `apps/control-plane/src/platform/a2a_gateway/external_registry.py` — `ExternalAgentCardRegistry` with methods: `get_card(endpoint_id, session)` (check Redis `cache:a2a_card:{hash}` first, fall back to DB `cached_agent_card`, return with `is_stale` flag); `fetch_and_cache(endpoint, session)` (httpx GET to `agent_card_url`, validate response is valid Agent Card JSON, update Redis + DB, handle fetch failure → set stale flag + schedule retry); cache key = `cache:a2a_card:{sha256(endpoint_url)[:16]}`; use `AsyncRedisClient` patterns from `apps/control-plane/src/platform/policies/service.py` (`_redis_set_json`/`_redis_get_json`)
- [x] T015 [US2] Create `apps/control-plane/src/platform/a2a_gateway/client_service.py` — `A2AGatewayClientService` with method `invoke_external_agent(calling_agent_id, calling_agent_fqn, external_endpoint_id, message, workspace_id, execution_id, session)`: fetch endpoint record, policy check via `ToolGatewayService.validate_tool_invocation(tool_fqn=f"a2a:{endpoint_id}")`, fetch Agent Card via `ExternalAgentCardRegistry`, validate supported capabilities/auth, submit A2A task via httpx POST to external endpoint URL, poll/await result, sanitize result via `OutputSanitizer.sanitize()`, write audit record, emit Kafka events; raises `A2APolicyDeniedError` on deny, `A2AUnsupportedCapabilityError` on incompatible Agent Card
- [x] T016 [US2] Add endpoints to `apps/control-plane/src/platform/a2a_gateway/router.py` —  
  `GET /api/v1/a2a/external-endpoints` (operator-only, calls repository list);  
  `POST /api/v1/a2a/external-endpoints` (operator-only, validates HTTPS, calls repository create);  
  `DELETE /api/v1/a2a/external-endpoints/{endpoint_id}` (operator-only, soft-delete via repository update)
- [x] T017 [P] [US2] Add unit tests in `apps/control-plane/tests/unit/a2a_gateway/test_client_service.py` — cover: outbound call happy path, policy deny raises A2APolicyDeniedError, HTTPS enforcement raises A2AHttpsRequiredError, unsupported capability raises A2AUnsupportedCapabilityError, output sanitization applied to result, dual-write audit to A2AAuditRecord + PolicyBlockedActionRecord on deny
- [x] T018 [P] [US2] Add integration tests in `apps/control-plane/tests/integration/a2a_gateway/test_client_mode.py` — cover scenarios S15, S16, S17, S24 from quickstart.md; use an httpx mock server as the external A2A endpoint

**Checkpoint**: Client mode is fully exercised. Policy enforcement story (US3) cross-cuts both modes.

---

## Phase 5: User Story 3 — All A2A Interactions Enforced by Policy (Priority: P1)

**Goal**: Comprehensive policy, sanitization, and audit coverage for both directions (S6, S7, S9, S16, S18).

**Independent Test**: Configure deny-all outbound policy; verify outbound is denied with audit. Submit unauthenticated inbound task; verify 401. Submit task with synthetic secret-bearing agent response; verify secret is redacted before external client sees it. Submit over-rate-limit requests; verify 429 logged.

- [x] T019 [P] [US3] Add output sanitization to `apps/control-plane/src/platform/a2a_gateway/server_service.py` — in the path where a platform agent's result is returned to the external client, call `OutputSanitizer.sanitize(result_text, agent_id=..., agent_fqn=..., tool_fqn="a2a:inbound", execution_id=..., workspace_id=..., session=...)` before writing `result_payload` to `A2ATask`; log `redaction_count` to the audit record; test with `apps/control-plane/tests/unit/a2a_gateway/test_server_service.py` scenario for sanitization (S18)
- [x] T020 [P] [US3] Extend `apps/control-plane/src/platform/a2a_gateway/repository.py` — add `create_policy_blocked_record(PolicyBlockedActionRecord, session)` that dual-writes to the `policies` domain's `PolicyBlockedActionRecord` table for all A2A denials (auth failure, authz failure, outbound policy block, rate-limit breach); this ensures policy dashboards show A2A denials without requiring policy domain changes
- [x] T021 [P] [US3] Add integration tests in `apps/control-plane/tests/integration/a2a_gateway/test_policy_enforcement.py` — cover scenarios S6, S7, S9 (inbound auth/authz/rate-limit), S16 (outbound policy deny), S18 (output sanitization), S23 (protocol version mismatch) from quickstart.md

**Checkpoint**: Policy enforcement is comprehensive and auditable.

---

## Phase 6: User Story 4 — SSE Streaming and Multi-Turn Conversations (Priority: P2)

**Goal**: External clients receive real-time lifecycle events via SSE; multi-turn input-required flow works end-to-end (S10, S11, S12, S13, S14).

**Independent Test**: Submit a task, subscribe to `GET /api/v1/a2a/tasks/{task_id}/stream`. Verify events emitted for each state transition; stream closes on terminal state. Simulate `input_required` state transition; verify SSE event emitted; submit follow-up via `POST /api/v1/a2a/tasks/{task_id}/messages`; verify task resumes. Disconnect and reconnect with `Last-Event-ID`; verify no missed transitions.

- [x] T022 [US4] Create `apps/control-plane/src/platform/a2a_gateway/streaming.py` — `A2ASSEStream` class with: `event_generator(task_id, last_event_id, session_factory)` async generator that polls `A2ATask` state from the repository (or listens to an in-process asyncio Queue updated by state-change events), yields `id: {event_id}\nevent: a2a_task_event\ndata: {json}\n\n` formatted strings, terminates on terminal state; `last_event_id` support: if provided, skip events before the requested ID; use `asyncio.sleep` between polls (configurable interval, default 500ms)
- [x] T023 [US4] Add `submit_follow_up(task_id, message, principal_id, session)` to `apps/control-plane/src/platform/a2a_gateway/server_service.py` — validates task is in `input_required` state, creates a new `Interaction` in the backing conversation via `InteractionsRepository.create_interaction`, transitions `A2ATask.a2a_state` to `working`, emits `a2a.task.state_changed`, returns updated task status
- [x] T024 [US4] Add streaming and multi-turn endpoints to `apps/control-plane/src/platform/a2a_gateway/router.py` —  
  `GET /api/v1/a2a/tasks/{task_id}/stream` returns `StreamingResponse(stream.event_generator(...), media_type="text/event-stream")`, accepts optional `?token=` query param for SSE clients that cannot set Authorization headers;  
  `POST /api/v1/a2a/tasks/{task_id}/messages` calls `server_service.submit_follow_up`
- [x] T025 [P] [US4] Add unit tests for SSE and multi-turn in `apps/control-plane/tests/unit/a2a_gateway/test_streaming.py` and `test_server_service.py` — cover: stream yields correct events in order, terminal event closes stream, Last-Event-ID resumes from correct position, follow-up accepted in input_required state, follow-up rejected in non-input_required state
- [x] T026 [P] [US4] Add integration tests in `apps/control-plane/tests/integration/a2a_gateway/test_streaming.py` — cover scenarios S10, S11, S12, S13, S14 from quickstart.md

**Checkpoint**: SSE streaming and multi-turn are fully exercised.

---

## Phase 7: User Story 5 — External Agent Card Registry with Caching (Priority: P3)

**Goal**: External Agent Cards are cached in Redis with TTL, stale fallback on refresh failure, and version-aware invalidation (S19, S20, S21).

**Independent Test**: Register an external endpoint. Invoke twice within TTL — verify cache hit on second call. Override TTL to 5 seconds, wait, invoke again — verify fresh fetch. Force `agent_card_url` to return 503 — verify stale fallback with `card_is_stale: true`.

- [x] T027 [P] [US5] Extend `apps/control-plane/src/platform/a2a_gateway/external_registry.py` — add `refresh_if_expired(endpoint, session)` that checks `card_cached_at + card_ttl_seconds` against now, calls `fetch_and_cache` if expired; add `invalidate_if_version_changed(endpoint, new_card, session)` that compares `declared_version` with newly-fetched card version and replaces cache + DB entry if changed; add staleness flag logic: on fetch failure, set `card_is_stale=True` in DB + `cache:a2a_card_stale:{hash}` in Redis (TTL = 2× card_ttl_seconds), schedule retry via APScheduler or background task
- [x] T028 [P] [US5] Add unit tests for caching in `apps/control-plane/tests/unit/a2a_gateway/test_external_registry.py` — cover: cache hit returns cached card without fetch, cache miss triggers fetch and caches result, TTL expiry triggers refresh, version change invalidates cache, fetch failure sets stale flag and returns cached card, Redis miss falls back to DB `cached_agent_card`
- [x] T029 [P] [US5] Add integration tests in `apps/control-plane/tests/integration/a2a_gateway/test_external_registry.py` — cover scenarios S19, S20, S21 from quickstart.md

**Checkpoint**: External Agent Card caching is hardened and tested.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Idle timeout scanner, validation, regression safety, and final scenario closure.

- [x] T030 [P] Add `idle_timeout_scanner` APScheduler job in `apps/control-plane/src/platform/a2a_gateway/server_service.py` (or a dedicated `scanner.py`) — runs every 5 minutes, queries `a2a_tasks` for rows in `input_required` state where `idle_timeout_at < NOW()`, transitions each to `cancelled`, writes audit record, emits `a2a.task.cancelled` Kafka event; register the job in the application lifespan in `apps/control-plane/src/platform/main.py`
- [x] T031 [P] Add `PlatformSettings` additions to `apps/control-plane/src/platform/common/config.py` — add: `A2A_PROTOCOL_VERSION: str = "1.0"`, `A2A_MAX_PAYLOAD_BYTES: int = 10_485_760` (10 MB), `A2A_TASK_IDLE_TIMEOUT_MINUTES: int = 30`, `A2A_DEFAULT_CARD_TTL_SECONDS: int = 3600`, `A2A_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE: int = 60`; following the existing `PlatformSettings` Pydantic settings pattern in `config.py`
- [x] T032 [P] Run Python validation — `pytest apps/control-plane/tests/unit/a2a_gateway/ apps/control-plane/tests/integration/a2a_gateway/`, `ruff check apps/control-plane/src/platform/a2a_gateway/`, `mypy --strict apps/control-plane/src/platform/a2a_gateway/` — fix any failures
- [x] T033 Run end-to-end acceptance scenarios S1–S25 from `specs/065-a2a-protocol-gateway/quickstart.md` against a locally-running control-plane instance with a mock external A2A server; close any remaining regressions
- [x] T034 [P] Verify existing internal coordination tests are unaffected — run `pytest apps/control-plane/tests/` excluding a2a_gateway tests; confirm SC-014 (100% of pre-existing tests pass)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1**: immediate
- **Phase 2**: depends on Phase 1 (skeleton must exist)
- **Phase 3 (US1)**: depends on Phase 2 (models, repo, card generator, events)
- **Phase 4 (US2)**: depends on Phase 2; independent of Phase 3 (different service file)
- **Phase 5 (US3)**: depends on Phase 3 + Phase 4 (cross-cutting over both directions)
- **Phase 6 (US4)**: depends on Phase 3 (streaming over server mode task lifecycle)
- **Phase 7 (US5)**: depends on Phase 4 (caching is part of client mode card lookup)
- **Phase 8**: after all desired stories are implemented

### Parallel Opportunities

```text
T002 ∥ T003                       (exceptions + migration, different files)
T004 ∥ T005 ∥ T007 ∥ T008        (models, schemas, events, card_generator — all different files)
T012 ∥ T013                       (US1 unit + integration tests)
T017 ∥ T018                       (US2 unit + integration tests)
T019 ∥ T020 ∥ T021                (US3 sanitization, dual-write, integration tests)
T025 ∥ T026                       (US4 unit + integration tests)
T027 ∥ T028 ∥ T029                (US5 caching ext, unit tests, integration tests)
T030 ∥ T031 ∥ T032 ∥ T034        (polish tasks, all different files)
```

### Suggested MVP for the next implementation pass

1. T001–T003 (setup + migration)
2. T004–T008 (foundational models, schemas, repo, events, card generator)
3. T009–T011 (server-mode service + router + main.py mount)
4. T012–T013 (US1 tests)
5. T033 (S1–S5 acceptance scenarios)

This delivers a working server-mode gateway (Agent Card discovery + task submission + lifecycle tracking) that external clients can exercise against a real platform instance.
