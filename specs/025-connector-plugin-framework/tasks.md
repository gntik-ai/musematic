# Tasks: Connector Plugin Framework

**Input**: Design documents from `specs/025-connector-plugin-framework/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/connectors-api.md ✓, quickstart.md ✓

**Organization**: Tasks grouped by user story for independent implementation and testing. 8 phases (1 setup + 1 foundational + 6 user stories + 1 polish).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1–US6)
- Paths under `apps/control-plane/`

---

## Phase 1: Setup

**Purpose**: Package scaffold, migration, dependency additions, seed script

- [X] T001 Create `apps/control-plane/src/platform/connectors/` package with stub `__init__.py`
- [X] T002 [P] Create `apps/control-plane/src/platform/connectors/implementations/` subpackage with stub `__init__.py`
- [X] T003 [P] Add `aioimaplib>=1.0`, `aiosmtplib>=3.0` to `apps/control-plane/pyproject.toml` dependencies
- [X] T004 Create Alembic migration `apps/control-plane/migrations/versions/010_connectors.py` — 6 tables: `connector_types`, `connector_instances`, `connector_credential_refs`, `connector_routes`, `outbound_deliveries`, `dead_letter_entries` with all indexes and constraints per data-model.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core cross-cutting infrastructure that every user story depends on — plugin protocol, enums, exceptions, base repository, Kafka events skeleton, credential security skeleton

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Create `apps/control-plane/src/platform/connectors/models.py` — 6 SQLAlchemy models (`ConnectorType`, `ConnectorInstance`, `ConnectorCredentialRef`, `ConnectorRoute`, `OutboundDelivery`, `DeadLetterEntry`) + enums (`ConnectorTypeSlug`, `ConnectorInstanceStatus`, `ConnectorHealthStatus`, `DeliveryStatus`, `DeadLetterResolution`) per data-model.md
- [X] T006 [P] Create `apps/control-plane/src/platform/connectors/plugin.py` — `BaseConnector` Protocol with `validate_config`, `normalize_inbound`, `deliver_outbound`, `health_check`; `InboundMessage`, `DeliveryRequest`, `HealthCheckResult` dataclasses per data-model.md
- [X] T007 [P] Create `apps/control-plane/src/platform/connectors/exceptions.py` — `ConnectorError`, `ConnectorNotFoundError`, `ConnectorTypeNotFoundError`, `ConnectorTypeDeprecatedError`, `ConnectorConfigError`, `ConnectorDisabledError`, `ConnectorNameConflictError`, `CredentialUnavailableError`, `WebhookSignatureError`, `DeliveryError`, `DeliveryPermanentError`, `DeadLetterNotFoundError`, `DeadLetterAlreadyResolvedError`
- [X] T008 Create `apps/control-plane/src/platform/connectors/repository.py` — `ConnectorsRepository` with SQLAlchemy CRUD stubs for all 6 models; workspace isolation enforced on all queries
- [X] T009 [P] Create `apps/control-plane/src/platform/connectors/events.py` — `ConnectorIngressPayload`, `ConnectorDeliveryRequestPayload`, `ConnectorDeliverySucceededPayload`, `ConnectorDeliveryFailedPayload`, `ConnectorDeadLetteredPayload` + `publish_*` helpers using canonical `EventEnvelope` on `connector.ingress` and `connector.delivery` topics
- [X] T010 [P] Create `apps/control-plane/src/platform/connectors/implementations/registry.py` — `CONNECTOR_TYPE_REGISTRY: dict[str, type[BaseConnector]]` populated at import time; `get_connector(type_slug) → BaseConnector` helper
- [X] T011 [P] Create `apps/control-plane/src/platform/connectors/seed.py` — insert 4 built-in `ConnectorType` rows (slack, telegram, webhook, email) with config JSON schemas; idempotent (upsert on slug)
- [X] T012 [P] Create `apps/control-plane/src/platform/connectors/dependencies.py` — `get_connectors_service()` FastAPI DI factory

**Checkpoint**: Foundation complete — all 6 models, protocol, exceptions, repository skeleton, events, registry

---

## Phase 3: User Story 1 — Connector Registration and Configuration (Priority: P1) 🎯 MVP

**Goal**: Operators can create, configure, update, enable/disable, delete connector instances within a workspace. Config is validated against the connector type's schema. Credentials stored as vault references only. Workspace isolation enforced.

**Independent Test**: Create a Slack connector with valid config → verify 201. Create with missing required field → verify 400. Update config → verify 200. Disable → verify status=disabled. Delete → verify 404 on subsequent GET. Access from different workspace → verify 404.

- [X] T013 [US1] Implement `ConnectorsRepository` methods in `apps/control-plane/src/platform/connectors/repository.py`: `get_connector_type()`, `list_connector_types()`, `create_connector_instance()`, `get_connector_instance()`, `list_connector_instances()`, `update_connector_instance()`, `soft_delete_connector_instance()`, `upsert_credential_refs()`
- [X] T014 [P] [US1] Create `apps/control-plane/src/platform/connectors/schemas.py` — `ConnectorTypeResponse`, `ConnectorInstanceCreate` (with `{"$ref": key}` sentinel validation), `ConnectorInstanceUpdate`, `ConnectorInstanceResponse` (credential values masked); `HealthCheckResponse` per data-model.md
- [X] T015 [US1] Implement `ConnectorsService` in `apps/control-plane/src/platform/connectors/service.py` — `list_connector_types()`, `get_connector_type()`, `create_connector_instance()` (validate config against type schema via registry, store credential refs in separate table, config JSONB preserves `{"$ref": key}` sentinels), `get_connector_instance()`, `list_connector_instances()`, `update_connector_instance()` (re-validate + invalidate route cache), `delete_connector_instance()`, `run_health_check()` (resolve credentials from vault, call `connector.health_check()`, persist result)
- [X] T016 [US1] Add connector types and instance management endpoints to `apps/control-plane/src/platform/connectors/router.py`: `GET /api/v1/connectors/types`, `GET /api/v1/connectors/types/{slug}`, `POST /api/v1/workspaces/{ws_id}/connectors`, `GET /api/v1/workspaces/{ws_id}/connectors`, `GET /api/v1/workspaces/{ws_id}/connectors/{id}`, `PUT /api/v1/workspaces/{ws_id}/connectors/{id}`, `DELETE /api/v1/workspaces/{ws_id}/connectors/{id}`, `POST /api/v1/workspaces/{ws_id}/connectors/{id}/health-check`
- [X] T017 [US1] Implement `SlackConnector` in `apps/control-plane/src/platform/connectors/implementations/slack.py` — `validate_config()` (required: team_id, bot_token ref, signing_secret ref), `health_check()` (httpx POST to Slack auth.test API with Bearer token); register in `implementations/registry.py`
- [X] T018 [P] [US1] Implement `TelegramConnector` in `apps/control-plane/src/platform/connectors/implementations/telegram.py` — `validate_config()` (required: bot_token ref), `health_check()` (httpx GET Telegram getMe); register in registry
- [X] T019 [P] [US1] Implement `WebhookConnector` in `apps/control-plane/src/platform/connectors/implementations/webhook.py` — `validate_config()` (required: signing_secret ref), `health_check()` (httpx HEAD to destination URL if configured); register in registry
- [X] T020 [P] [US1] Implement `EmailConnector` skeleton in `apps/control-plane/src/platform/connectors/implementations/email.py` — `validate_config()` (required: imap_host, imap_port, smtp_host, smtp_port, email_address, imap_password ref, smtp_password ref), `health_check()` (aioimaplib NOOP); register in registry
- [X] T021 [US1] Write integration tests `apps/control-plane/tests/integration/test_conn_instance_lifecycle.py` — connector instance CRUD, config validation pass/fail, enable/disable, health check, workspace isolation (cross-workspace 404)

**Checkpoint**: Connector types, instances, credentials, and health checks fully functional. Workspace isolation verified.

---

## Phase 4: User Story 2 — Inbound Message Routing (Priority: P1)

**Goal**: Inbound messages from Slack/Telegram/Webhook are verified (signature), normalized to `InboundMessage`, routed via priority-ordered rules, and published to `connector.ingress`. Unmatched messages are logged. Disabled connectors reject inbound.

**Independent Test**: Configure Slack connector with route `#support* → support-ops:triage-agent`. POST simulated Slack event → verify `connector.ingress` receives normalized `ConnectorIngressPayload` with correct route target. POST for unmatched channel → verify logged as unrouted. POST with invalid signature → verify 401. POST to disabled connector → verify 400.

- [X] T022 [US2] Implement `ConnectorsRepository` methods: `create_route()`, `get_route()`, `list_routes()`, `update_route()`, `delete_route()`, `get_routes_for_instance()` (ordered by priority ASC, created_at ASC)
- [X] T023 [P] [US2] Add routing rule schemas to `apps/control-plane/src/platform/connectors/schemas.py` — `ConnectorRouteCreate` (with model_validator requiring at least one target), `ConnectorRouteUpdate`, `ConnectorRouteResponse`
- [X] T024 [US2] Create `apps/control-plane/src/platform/connectors/security.py` — `verify_webhook_signature` FastAPI dependency: reads raw request body, loads signing_secret from vault via `ConnectorCredentialRef.vault_path`, computes HMAC-SHA256, compares with `X-Hub-Signature-256` header; raises `WebhookSignatureError` (HTTP 401) on mismatch; never caches secret (supports rotation)
- [X] T025 [US2] Implement route matching in `ConnectorsService` in `apps/control-plane/src/platform/connectors/service.py` — `create/get/list/update/delete_route()`, `match_route()` (load from Redis cache key `connector:routes:{ws_id}:{instance_id}` TTL 60s; fallback to DB; first match by priority ASC + created_at ASC tiebreaker; invalidate cache on route CUD)
- [X] T026 [US2] Implement `process_inbound()` in `ConnectorsService` — for webhook type: call `verify_webhook_signature` dependency; normalize via `connector.normalize_inbound()`; call `match_route()`; if match: publish `ConnectorIngressPayload` to `connector.ingress` topic; if no match: log as unrouted; reject if connector disabled
- [X] T027 [US2] Implement `SlackConnector.normalize_inbound()` in `apps/control-plane/src/platform/connectors/implementations/slack.py` — map Slack `event_callback` payload fields to `InboundMessage` (sender_identity=event.user, channel=event.channel, content_text=event.text, timestamp from event.ts)
- [X] T028 [P] [US2] Implement `TelegramConnector.normalize_inbound()` in `apps/control-plane/src/platform/connectors/implementations/telegram.py` — map Telegram `Update` object to `InboundMessage`
- [X] T029 [P] [US2] Implement `WebhookConnector.normalize_inbound()` in `apps/control-plane/src/platform/connectors/implementations/webhook.py` — map raw POST body to `InboundMessage` (sender_identity from configurable header, channel from URL path)
- [X] T030 [US2] Add inbound webhook endpoints and route management endpoints to `apps/control-plane/src/platform/connectors/router.py` — `POST /api/v1/inbound/slack/{id}` (no JWT, Slack sig verification), `POST /api/v1/inbound/telegram/{id}` (no JWT, token in URL path), `POST /api/v1/inbound/webhook/{id}` (no JWT, HMAC sig verification), plus route CRUD: `POST/GET /workspaces/{ws_id}/connectors/{id}/routes`, `GET/PUT/DELETE /workspaces/{ws_id}/routes/{route_id}`
- [X] T031 [US2] Write unit tests `apps/control-plane/tests/unit/test_conn_routing.py` — route matching priority order, glob patterns (channel_pattern `#support*`), tiebreaker (created_at ASC), disabled route skipped, no match returns None
- [X] T032 [US2] Write unit tests `apps/control-plane/tests/unit/test_conn_webhook_security.py` — valid HMAC-SHA256 passes, wrong secret fails (401), missing header fails, timing-safe comparison
- [X] T033 [US2] Write integration tests `apps/control-plane/tests/integration/test_conn_inbound_routing.py` — full flow: POST → normalize → route match → Kafka publish; unrouted logging; disabled connector rejection; signature rejection

**Checkpoint**: Inbound message normalization, routing, and Kafka publish fully functional for all HTTP-push types.

---

## Phase 5: User Story 3 — Outbound Message Delivery (Priority: P1)

**Goal**: Delivery requests are enqueued, the connector worker delivers them with exponential backoff retry (1s/4s/16s), and permanently failed messages move to the dead-letter queue. Worker consumes `connector.delivery` Kafka topic.

**Independent Test**: POST delivery request → verify `OutboundDelivery` created, `connector.delivery` published. Simulate transient failure → verify retry at +1s. Simulate 3 failures → verify `DeadLetterEntry` created. Verify `OutboundDelivery.error_history` has all 3 attempt records.

- [X] T034 [US3] Create `apps/control-plane/src/platform/connectors/retry.py` — `compute_next_retry_at(attempt_count: int) → datetime` (base 4: 1s/4s/16s); `RetryScanner` APScheduler job scanning `outbound_deliveries` WHERE status=failed AND next_retry_at <= now() LIMIT 100, re-enqueuing via `execute_delivery()`
- [X] T035 [US3] Implement `ConnectorsRepository` delivery methods — `create_outbound_delivery()`, `get_outbound_delivery()`, `list_outbound_deliveries()`, `update_delivery_status()`, `append_error_history()`, `get_pending_retries()`, `create_dead_letter_entry()`, `increment_connector_metrics()` (atomic UPDATE on connector_instances counters)
- [X] T036 [P] [US3] Add delivery and DLQ schemas to `apps/control-plane/src/platform/connectors/schemas.py` — `OutboundDeliveryCreate`, `OutboundDeliveryResponse`, `DeadLetterEntryResponse`, `DeadLetterRedeliverRequest`, `DeadLetterDiscardRequest`
- [X] T037 [US3] Implement `create_delivery()` and `execute_delivery()` in `ConnectorsService` — `create_delivery()` persists record + publishes `ConnectorDeliveryRequestPayload` to `connector.delivery`; `execute_delivery()` resolves credentials from vault (never cached), calls `connector.deliver_outbound()`, on success: status=delivered + emit succeeded event; on transient failure: increment attempt_count + compute next_retry_at + emit failed event; on permanent failure or attempt_count >= max_attempts: create `DeadLetterEntry` + emit dead-lettered event
- [X] T038 [US3] Implement `SlackConnector.deliver_outbound()` in `apps/control-plane/src/platform/connectors/implementations/slack.py` — httpx POST to `chat.postMessage` API with Bearer bot_token; map content_structured to Slack blocks if present; raise `DeliveryError` on 5xx, `DeliveryPermanentError` on 4xx (e.g., channel_not_found)
- [X] T039 [P] [US3] Implement `TelegramConnector.deliver_outbound()` in `apps/control-plane/src/platform/connectors/implementations/telegram.py` — httpx POST to Bot API `sendMessage`; Markdown formatting for outbound
- [X] T040 [P] [US3] Implement `WebhookConnector.deliver_outbound()` in `apps/control-plane/src/platform/connectors/implementations/webhook.py` — httpx POST to destination URL with raw JSON body; configurable timeout
- [X] T041 [P] [US3] Implement `EmailConnector.deliver_outbound()` in `apps/control-plane/src/platform/connectors/implementations/email.py` — aiosmtplib SMTP send; MIME encoding for HTML/plain text; from_address from connector config
- [X] T042 [US3] Add delivery management endpoints to `apps/control-plane/src/platform/connectors/router.py` — `POST /api/v1/workspaces/{ws_id}/deliveries`, `GET /api/v1/workspaces/{ws_id}/deliveries`, `GET /api/v1/workspaces/{ws_id}/deliveries/{id}`
- [X] T043 [US3] Write unit tests `apps/control-plane/tests/unit/test_conn_retry.py` — `compute_next_retry_at`: attempt 1→1s, 2→4s, 3→16s; max_attempts exhaustion triggers DLQ transition; error_history accumulation
- [X] T044 [US3] Write integration tests `apps/control-plane/tests/integration/test_conn_outbound_delivery.py` — full delivery lifecycle: create → worker execute → success; transient failure → retry scheduling; 3 failures → DLQ creation; error_history correctness

**Checkpoint**: Outbound delivery with retry and dead-letter creation fully functional. Worker Kafka consumer wired.

---

## Phase 6: User Story 4 — Credential Isolation and Security (Priority: P1)

**Goal**: All credential handling enforces §XI — vault references only in DB, actual values injected at call time only, never in API responses/logs/events. Credential rotation takes effect on next operation without restart.

**Independent Test**: Create connector with credential refs → GET instance → verify config shows `{"$ref": "key"}` only, no vault_path in response. Execute delivery → inspect logs → verify no credential pattern. Access credentials from different workspace → verify 404. Rotate credential → execute next delivery → verify new credential used.

- [X] T045 [US4] Audit `ConnectorsService.execute_delivery()` in `apps/control-plane/src/platform/connectors/service.py` — verify vault resolution happens only inside `deliver_outbound()` call scope; resolved secret value never assigned to any variable named in log format strings; add `# SECURITY: credential value is local-only, not logged` comment at resolution site
- [X] T046 [P] [US4] Audit `ConnectorsService.run_health_check()` — same pattern: credential resolved from vault inside `health_check()` call; verify `HealthCheckResult.error` field never contains credential substrings; add log scrubbing guard
- [X] T047 [US4] Ensure `ConnectorInstanceResponse` serializer in `apps/control-plane/src/platform/connectors/schemas.py` excludes `vault_path` from all response models; add Pydantic `field_serializer` to mask any accidentally included credential fields
- [X] T048 [US4] Verify `ConnectorCredentialRef` is never included in any Kafka event payload — audit `apps/control-plane/src/platform/connectors/events.py` event payload classes for any credential fields
- [X] T049 [US4] Write integration tests `apps/control-plane/tests/integration/test_conn_credential_isolation.py` — GET instance response has no plaintext credentials; delivery execution log has no credential patterns (log capture); cross-workspace credential access returns 404; credential rotation (update vault mock → next delivery uses new value)

**Checkpoint**: Credential isolation verified end-to-end. §XI compliance documented in tests.

---

## Phase 7: User Story 5 — Multi-Channel Connector Types (Priority: P2)

**Goal**: All four built-in connector types produce the same normalized `InboundMessage` format despite different source payloads. All four types have complete `deliver_outbound()` and `health_check()` implementations.

**Independent Test**: For each type: create instance → health check passes → POST simulated inbound → verify normalized `InboundMessage` fields (sender_identity, channel, content_text, timestamp, original_payload) match expected schema. POST outbound delivery → verify channel-specific formatting (Slack blocks, Telegram Markdown, webhook raw, email MIME).

- [X] T050 [US5] Complete `EmailConnector.normalize_inbound()` in `apps/control-plane/src/platform/connectors/implementations/email.py` — aioimaplib IMAP FETCH; parse MIME email to extract sender (From header), channel (To/mailbox), content_text (text/plain part), timestamp (Date header); produce `InboundMessage` with same field structure as other types
- [X] T051 [US5] Implement email polling APScheduler job in `apps/control-plane/src/platform/connectors/implementations/email.py` — `EmailPollingJob`: for each enabled email connector instance in DB, open IMAP session with aioimaplib, SEARCH UNSEEN, fetch each unseen message, call `normalize_inbound()`, publish to `connector.ingress`, mark messages as SEEN; configurable poll interval per instance (default 60s)
- [X] T052 [US5] Write unit tests `apps/control-plane/tests/unit/test_conn_normalization.py` — for Slack, Telegram, webhook, email: given representative raw payload, assert `InboundMessage` has identical field names and types; assert `original_payload` contains the raw input; assert no extra fields injected
- [X] T053 [US5] Write unit tests `apps/control-plane/tests/unit/test_conn_plugin_protocol.py` — for each of the 4 connector implementations: assert `isinstance(connector, BaseConnector)` (runtime_checkable Protocol check); assert `validate_config()` raises `ConnectorConfigError` on missing required fields; assert `validate_config()` passes on minimal valid config

**Checkpoint**: All 4 connector types complete with normalization, delivery, health check. Normalization format consistency verified.

---

## Phase 8: User Story 6 — Monitoring and Dead-Letter Management (Priority: P3)

**Goal**: Operators can list dead-letter entries, manually redeliver (creates new delivery), or discard (archives to MinIO + marks discarded). Per-connector delivery metrics tracked atomically. DLQ depth Redis counter triggers workspace alert.

**Independent Test**: Send 10 deliveries → verify connector metrics (messages_sent=10). Force 2 into DLQ → verify `GET /dead-letter` shows 2 pending entries with full error_history. Redeliver one → verify new `OutboundDelivery` created + entry `resolution_status=redelivered`. Discard other → verify MinIO object created + entry `resolution_status=discarded`. List connectors → verify each shows accurate metrics.

- [X] T054 [US6] Implement `ConnectorsRepository` DLQ methods — `list_dead_letter_entries()` (filterable by workspace_id, connector_instance_id, resolution_status), `get_dead_letter_entry()`, `update_dead_letter_resolution()`, `archive_dead_letter_to_minio()` (aioboto3 PUT to `connector-dead-letters/{ws_id}/{entry_id}.json`)
- [X] T055 [US6] Implement DLQ service methods in `ConnectorsService` — `list_dead_letter_entries()`, `get_dead_letter_entry()`, `redeliver_dead_letter()` (create new `OutboundDelivery` + mark entry `redelivered` + publish to `connector.delivery`; reject if already resolved), `discard_dead_letter()` (archive payload to MinIO + set `archive_path` + mark `discarded`; reject if already resolved); update Redis DLQ depth counter on both operations
- [X] T056 [US6] Add DLQ endpoints to `apps/control-plane/src/platform/connectors/router.py` — `GET /api/v1/workspaces/{ws_id}/dead-letter`, `GET /api/v1/workspaces/{ws_id}/dead-letter/{entry_id}`, `POST /api/v1/workspaces/{ws_id}/dead-letter/{entry_id}/redeliver`, `POST /api/v1/workspaces/{ws_id}/dead-letter/{entry_id}/discard`
- [X] T057 [US6] Write integration tests `apps/control-plane/tests/integration/test_conn_dead_letter.py` — DLQ list + filter by resolution_status; redeliver creates new delivery + marks entry; discard archives to MinIO + marks entry; double-action on already-resolved entry returns 409; metrics counters accurate after operations

**Checkpoint**: Full dead-letter management operational. Operators can inspect, redeliver, and discard failed deliveries.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Wire worker profile, mount router, coverage audit, linting

- [X] T058 Mount connectors router in `apps/control-plane/src/platform/api/__init__.py`
- [X] T059 [P] Wire connector worker components into `apps/control-plane/entrypoints/worker_main.py` — Kafka consumer group for `connector.delivery` topic (calls `execute_delivery()`); `RetryScanner` APScheduler job (every 30s); `EmailPollingJob` APScheduler job (per-instance interval, default 60s)
- [X] T060 [P] Run `alembic upgrade head` to apply migration 010 and verify all 6 tables are created correctly
- [X] T061 [P] Run `python -m platform.connectors.seed` to verify 4 connector types are seeded correctly
- [X] T062 [P] Run full test suite `pytest tests/ --cov=src/platform/connectors --cov-report=term-missing` and verify coverage ≥ 95%
- [X] T063 [P] Run `ruff check apps/control-plane/src/platform/connectors/` and fix all linting issues
- [X] T064 [P] Run `mypy apps/control-plane/src/platform/connectors/ --strict` and fix all type errors
- [X] T065 [P] Execute quickstart.md Scenario 1 (Slack connector CRUD + health check) end-to-end

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phases 3–8 (User Stories)**: All depend on Phase 2 completion
  - US1 (Phase 3) → independent, must complete first (instances needed by all routing/delivery)
  - US2 (Phase 4) → depends on US1 (needs ConnectorInstance to exist)
  - US3 (Phase 5) → depends on US1 (needs ConnectorInstance); can overlap with US2
  - US4 (Phase 6) → depends on US3 (audits delivery execution paths)
  - US5 (Phase 7) → depends on US1/US2/US3 (completes all 4 connector implementations)
  - US6 (Phase 8) → depends on US3 (needs DeadLetterEntry from failed deliveries)
- **Phase 9 (Polish)**: Depends on all desired user stories complete

### User Story Dependencies

| User Story | Depends On | Can Parallelize With |
|------------|------------|----------------------|
| US1 — Registration (P1) | Foundational | — |
| US2 — Inbound Routing (P1) | US1 | US3 |
| US3 — Outbound Delivery (P1) | US1 | US2 |
| US4 — Credential Security (P1) | US3 | US5 |
| US5 — Multi-Channel Types (P2) | US1, US2, US3 | US4 |
| US6 — Monitoring + DLQ (P3) | US3 | — |

### Within Each User Story

- Repository → Service → Router (strict order)
- Connector implementations ([P]) → can parallelize across types
- Integration tests after implementation complete

### Parallel Opportunities

- **Phase 1**: T002, T003 parallel with T001
- **Phase 2**: T006, T007, T009, T010, T011, T012 all parallel with T005
- **Phase 3 (US1)**: T014 parallel with T013; T017, T018, T019, T020 all parallel after T015
- **Phase 4 (US2)**: T023 parallel with T022; T027, T028, T029 parallel after T026
- **Phase 5 (US3)**: T036 parallel with T035; T039, T040, T041 parallel with T038
- **Phase 7 (US5)**: T052, T053 parallel with T050, T051

---

## Parallel Example: Phase 2 (Foundational)

```bash
# After T005 (models.py) is started, these can all run in parallel:
Task: "T006 — plugin.py (BaseConnector Protocol)"
Task: "T007 — exceptions.py"
Task: "T009 — events.py"
Task: "T010 — implementations/registry.py"
Task: "T011 — seed.py"
Task: "T012 — dependencies.py"
```

## Parallel Example: Phase 3 (US1 Connector Implementations)

```bash
# After T015 (service.py create_connector_instance) completes:
Task: "T017 — SlackConnector validate_config + health_check"
Task: "T018 — TelegramConnector validate_config + health_check"
Task: "T019 — WebhookConnector validate_config + health_check"
Task: "T020 — EmailConnector validate_config + health_check"
```

---

## Implementation Strategy

### MVP First (P1 User Stories Only)

1. Complete **Phase 1** (Setup) + **Phase 2** (Foundational)
2. Complete **Phase 3** (US1 — Registration) → test connector CRUD independently
3. Complete **Phase 4** (US2 — Inbound Routing) → test inbound message flow
4. Complete **Phase 5** (US3 — Outbound Delivery) → test delivery + retry + DLQ creation
5. Complete **Phase 6** (US4 — Credential Security) → verify §XI compliance
6. **STOP AND VALIDATE**: All P1 stories functional. 4 of 6 stories deliverable.

### Full Delivery

7. Complete **Phase 7** (US5 — Multi-Channel) → all 4 connector types complete
8. Complete **Phase 8** (US6 — DLQ Management) → operator monitoring complete
9. Complete **Phase 9** (Polish) → coverage ≥ 95%, linting clean

### Parallel Team Strategy (3 developers post-Foundational)

- **Developer A**: US1 (Phase 3) → US4 (Phase 6)
- **Developer B**: US2 (Phase 4) → US6 (Phase 8)
- **Developer C**: US3 (Phase 5) → US5 (Phase 7)

---

## Summary

| Phase | User Story | Tasks | Priority |
|-------|------------|-------|----------|
| 1 | Setup | T001–T004 | — |
| 2 | Foundational | T005–T012 | — |
| 3 | US1: Registration | T013–T021 | P1 🎯 |
| 4 | US2: Inbound Routing | T022–T033 | P1 |
| 5 | US3: Outbound Delivery | T034–T044 | P1 |
| 6 | US4: Credential Security | T045–T049 | P1 |
| 7 | US5: Multi-Channel Types | T050–T053 | P2 |
| 8 | US6: DLQ Management | T054–T057 | P3 |
| 9 | Polish | T058–T065 | — |

**Total tasks**: 65
**P1 tasks (MVP)**: T001–T049 (49 tasks)
**Parallel opportunities**: 28 tasks marked [P]
