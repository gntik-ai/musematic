# Implementation Plan: Connector Plugin Framework

**Branch**: `025-connector-plugin-framework` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/025-connector-plugin-framework/spec.md`

## Summary

Build the `connectors/` bounded context within `apps/control-plane/src/platform/`. This covers the `BaseConnector` plugin protocol with four lifecycle methods (validate_config, normalize_inbound, deliver_outbound, health_check), four built-in connector implementations (Slack, Telegram, Webhook, Email), workspace-scoped connector instance management, configurable routing rules with priority-based glob matching and Redis caching, per-workspace credential isolation via vault references (§XI), exponential backoff retry (base 4: 1s/4s/16s) with dead-letter queue, webhook signature verification (HMAC-SHA256) before payload parsing, and Kafka integration on two topics (`connector.ingress`, `connector.delivery`). Storage: PostgreSQL (6 tables). A separate connector worker runtime profile handles outbound delivery consumption and email polling via APScheduler.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+ (two topics), redis-py 5.x async (route caching), aioimaplib 1.0+ (email inbound), aiosmtplib 3.0+ (email outbound), httpx 0.27+ (Slack/Telegram/webhook HTTP calls), APScheduler 3.x (email poll + retry scanner), aioboto3 latest (DLQ archival to MinIO)
**Storage**: PostgreSQL (6 tables: connector_types, connector_instances, connector_credential_refs, connector_routes, outbound_deliveries, dead_letter_entries) + Redis (route cache, DLQ depth counter) + MinIO (discarded DLQ archival)
**Testing**: pytest 8.x + pytest-asyncio
**Target Platform**: Linux server, Kubernetes `platform-control` namespace (`api` profile for inbound HTTP + management endpoints; `worker` profile for outbound delivery consumer + email polling)
**Performance Goals**: Inbound normalization + routing ≤ 500ms (SC-001); outbound delivery initiation ≤ 300ms (SC-002); retry backoff 100% adherent (SC-003); 500 inbound messages/min/workspace (SC-008)
**Constraints**: Test coverage ≥ 95%; all async; ruff + mypy --strict; credentials NEVER in logs/events/responses (§XI); workspace isolation on all operations; credential rotation takes effect on next operation (no cache)
**Scale/Scope**: 6 user stories, 20 FRs, 10 SCs, ~28 REST endpoints + 2 internal interfaces, 6 PostgreSQL tables, 2 Kafka topics, 6 event types

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Python 3.12+ | PASS | §2.1 mandated |
| FastAPI 0.115+ | PASS | §2.1 mandated |
| Pydantic v2 for all schemas | PASS | §2.1 mandated |
| SQLAlchemy 2.x async only | PASS | §2.1 mandated — 6 PostgreSQL tables |
| All code async | PASS | Coding conventions: "All code is async"; aioimaplib/aiosmtplib for email |
| Bounded context structure | PASS | models, schemas, service, repository, router, events, exceptions, dependencies, plugin, retry, security, seed |
| No cross-boundary DB access | PASS | §IV — routing targets stored as FQN strings; no FK to registry tables |
| Canonical EventEnvelope | PASS | All events on 2 topics use EventEnvelope from feature 013 |
| CorrelationContext everywhere | PASS | Events carry workspace_id + connector_instance_id in CorrelationContext |
| Repository pattern | PASS | `ConnectorsRepository` (SQLAlchemy) in repository.py |
| Kafka for async events (not DB polling) | PASS | §III — 2 topics, 6 event types; retry scanner uses DB but emits Kafka events |
| Alembic for PostgreSQL schema changes | PASS | migration 010_connectors for all 6 tables |
| ClickHouse for OLAP/time-series | N/A | No OLAP analytics in this bounded context |
| No PostgreSQL for rollups | N/A | No rollups |
| Qdrant for vector search | N/A | No vector operations |
| Redis for caching | PASS | §2.4 — route cache per workspace/connector instance (TTL 60s) |
| OpenSearch | N/A | No full-text search |
| No PostgreSQL FTS | N/A | No FTS use case |
| Neo4j for graph traversal | N/A | Routing rules are simple priority-ordered list, not graph traversal |
| ruff 0.7+ | PASS | §2.1 mandated |
| mypy 1.11+ strict | PASS | §2.1 mandated |
| pytest + pytest-asyncio 8.x | PASS | §2.1 mandated |
| Secrets not in LLM context | PASS | §XI — credentials stored as vault refs, injected at call time, never in logs/events/responses |
| Zero-trust visibility | PASS | §IX — workspace-scoped access control on all operations (FR-012) |
| Goal ID as first-class correlation | N/A | No goal-oriented workflow in this bounded context |
| Modular monolith (no HTTP between contexts) | PASS | §I — 2 internal interfaces are in-process function calls |
| Attention pattern (out-of-band) | N/A | No agent urgency signals in this bounded context |
| APScheduler for background tasks | PASS | §2.1 — email polling (60s) + retry scanner (30s) in worker profile |

**All 25 applicable constitution gates PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/025-connector-plugin-framework/
├── plan.md                           # This file
├── spec.md                           # Feature specification
├── research.md                       # Phase 0 decisions (12 decisions)
├── data-model.md                     # Phase 1 — SQLAlchemy models, Pydantic schemas, service signatures
├── quickstart.md                     # Phase 1 — run/test guide
├── contracts/
│   └── connectors-api.md             # REST API contracts (~28 endpoints + 2 internal interfaces)
└── tasks.md                          # Phase 2 — generated by /speckit.tasks
```

### Source Code

```text
apps/control-plane/
├── src/platform/
│   └── connectors/
│       ├── __init__.py
│       ├── models.py                                # SQLAlchemy: 6 models + enums
│       ├── schemas.py                               # Pydantic: all request/response schemas
│       ├── service.py                               # ConnectorsService — all business logic
│       ├── repository.py                            # ConnectorsRepository — SQLAlchemy CRUD
│       ├── router.py                                # FastAPI router: /api/v1/workspaces/*/connectors/* + /inbound/*
│       ├── events.py                                # Event payload types + publish_* helpers for 2 topics
│       ├── exceptions.py                            # ConnectorError, WebhookSignatureError, DeliveryError, etc.
│       ├── dependencies.py                          # get_connectors_service DI factory
│       ├── plugin.py                                # BaseConnector Protocol, InboundMessage, DeliveryRequest, HealthCheckResult
│       ├── retry.py                                 # compute_next_retry_at(), retry scanner (APScheduler job)
│       ├── security.py                              # verify_webhook_signature FastAPI dependency
│       ├── seed.py                                  # Seed script: insert 4 built-in connector types
│       └── implementations/
│           ├── __init__.py
│           ├── registry.py                          # CONNECTOR_TYPE_REGISTRY dict
│           ├── slack.py                             # SlackConnector implementing BaseConnector
│           ├── telegram.py                          # TelegramConnector implementing BaseConnector
│           ├── webhook.py                           # WebhookConnector implementing BaseConnector
│           └── email.py                             # EmailConnector implementing BaseConnector (aioimaplib + aiosmtplib)
├── migrations/
│   └── versions/
│       └── 010_connectors.py                        # Alembic: 6 tables + indexes
└── tests/
    ├── unit/
    │   ├── test_conn_plugin_protocol.py             # BaseConnector Protocol, validate_config per type
    │   ├── test_conn_normalization.py               # normalize_inbound for all 4 types → same InboundMessage format
    │   ├── test_conn_routing.py                     # Route matching: priority order, glob patterns, tiebreaker
    │   ├── test_conn_retry.py                       # compute_next_retry_at: 1s/4s/16s; max_attempts; DLQ transition
    │   └── test_conn_webhook_security.py            # HMAC-SHA256 verification, invalid sig rejection
    └── integration/
        ├── test_conn_instance_lifecycle.py          # CRUD + enable/disable + health check + workspace isolation
        ├── test_conn_inbound_routing.py             # Inbound → normalize → route match → connector.ingress publish
        ├── test_conn_outbound_delivery.py           # Delivery → worker execute → success/failure/retry/DLQ
        ├── test_conn_credential_isolation.py        # Vault refs only in DB; values never in API responses/logs
        └── test_conn_dead_letter.py                 # DLQ list + redeliver + discard + MinIO archive
```

## Implementation Phases

### Phase 1 — Setup & Package Structure
- Create `src/platform/connectors/` package and `implementations/` subpackage with all module stubs
- Alembic migration `010_connectors.py`: 6 tables + indexes
  - `connector_types`, `connector_instances` (workspace FK, soft-delete), `connector_credential_refs` (workspace FK, no plaintext), `connector_routes` (workspace FK, priority index, target check constraint), `outbound_deliveries` (retry index on status + next_retry_at), `dead_letter_entries`

### Phase 2 — US1: Connector Registration and Configuration (P1)
- `models.py`: 6 SQLAlchemy models + enums (ConnectorTypeSlug, ConnectorInstanceStatus, ConnectorHealthStatus, DeliveryStatus, DeadLetterResolution)
- `plugin.py`: `BaseConnector` Protocol, `InboundMessage`, `DeliveryRequest`, `HealthCheckResult` dataclasses
- `exceptions.py`: `ConnectorError`, `ConnectorNotFoundError`, `ConnectorTypeNotFoundError`, `ConnectorTypeDeprecatedError`, `ConnectorConfigError`, `ConnectorDisabledError`, `ConnectorNameConflictError`, `CredentialUnavailableError`, `WebhookSignatureError`, `DeliveryError`, `DeliveryPermanentError`, `DeadLetterNotFoundError`, `DeadLetterAlreadyResolvedError`
- `schemas.py`: `ConnectorTypeResponse`, `ConnectorInstanceCreate/Update/Response`, `HealthCheckResponse`
- `repository.py`: `ConnectorsRepository` — CRUD for connector_types + connector_instances + credential_refs
- `service.py`: `list_connector_types()`, `get_connector_type()`, `create_connector_instance()` (validate config against type schema, store credential refs separately, config stores `{"$ref": key}` sentinel), `get/list/update/delete_connector_instance()`, `run_health_check()` (resolve credentials from vault, call `connector.health_check()`, update health status)
- `seed.py`: Insert 4 built-in connector types with config JSON schemas
- `router.py`: Endpoints — connector types (GET /types, GET /types/{slug}), connector instances (POST/GET/GET-list/PUT/DELETE, POST health-check)

### Phase 3 — US2: Inbound Message Routing (P1)
- `schemas.py`: `ConnectorRouteCreate/Update/Response`
- `repository.py`: `ConnectorRoute` CRUD + `get_routes_for_instance()`
- `security.py`: `verify_webhook_signature` FastAPI dependency (HMAC-SHA256 on raw bytes)
- `service.py`: `create/get/list/update/delete_route()`, `match_route()` (load from Redis cache TTL 60s; fallback to DB; return first matching rule by priority ASC + created_at ASC), `process_inbound()` (verify sig for webhook type, normalize via connector, match route, publish to `connector.ingress`)
- `events.py`: `ConnectorIngressPayload`, `publish_connector_ingress()` on `connector.ingress` topic
- `implementations/registry.py`: `CONNECTOR_TYPE_REGISTRY` dict; `get_connector(type_slug) → BaseConnector`
- `implementations/slack.py`: `SlackConnector` — `normalize_inbound()` from Slack event_callback payload, `validate_config()` (required: team_id, bot_token ref, signing_secret ref)
- `implementations/telegram.py`: `TelegramConnector` — `normalize_inbound()` from Telegram Update object
- `implementations/webhook.py`: `WebhookConnector` — `normalize_inbound()` from raw POST body
- `router.py`: Inbound endpoints (POST /inbound/slack/{id}, /inbound/telegram/{id}, /inbound/webhook/{id}) + route management endpoints (POST/GET routes per connector, GET/PUT/DELETE single route)

### Phase 4 — US3: Outbound Message Delivery + Retry (P1)
- `retry.py`: `compute_next_retry_at(attempt_count) → datetime`, `RetryScanner` APScheduler job (scan outbound_deliveries WHERE status=failed AND next_retry_at <= now() LIMIT 100)
- `schemas.py`: `OutboundDeliveryCreate/Response`
- `repository.py`: `OutboundDelivery` CRUD + `get_pending_retries()` + atomic status update
- `service.py`: `create_delivery()` (persist + publish to `connector.delivery`), `get/list_deliveries()`, `execute_delivery()` (resolve credentials from vault, call `connector.deliver_outbound()`, update attempt_count + error_history; on success: status=delivered; on transient failure: compute next_retry_at; on permanent failure or max_attempts exhausted: create DeadLetterEntry)
- `events.py`: `ConnectorDeliveryRequestPayload`, `ConnectorDeliverySucceededPayload`, `ConnectorDeliveryFailedPayload`, `ConnectorDeadLetteredPayload` + publish helpers
- `implementations/slack.py`: `deliver_outbound()` — httpx POST to Slack chat.postMessage API with Bearer token
- `implementations/telegram.py`: `deliver_outbound()` — httpx POST to Telegram Bot API sendMessage
- `implementations/webhook.py`: `deliver_outbound()` — httpx POST to destination URL
- `router.py`: Delivery endpoints (POST/GET/GET-list)

### Phase 5 — US4: Credential Isolation and Security (P1)
- `service.py`: Ensure `execute_delivery()` resolves credentials via vault at call time (never cached), credential values never passed to Pydantic serializers or log statements, `create_connector_instance()` stores only `{"$ref": key}` sentinels in config JSONB
- Integration test: `test_conn_credential_isolation.py` — assert vault path not in API response, assert log output contains no credential patterns
- `router.py`: Ensure `ConnectorInstanceResponse` serializer never includes `ConnectorCredentialRef.vault_path` values

### Phase 6 — US5: Multi-Channel Connector Types (P2)
- `implementations/slack.py`: Complete — `health_check()` (Slack auth.test API), Slack-specific rich text formatting for outbound
- `implementations/telegram.py`: Complete — `health_check()` (Telegram getMe API), Markdown formatting for outbound
- `implementations/webhook.py`: Complete — `health_check()` (HTTP HEAD to webhook URL), raw body for outbound
- `implementations/email.py`: `EmailConnector` — `normalize_inbound()` from MIME email via aioimaplib, `deliver_outbound()` via aiosmtplib SMTP, `health_check()` (IMAP NOOP), email polling APScheduler job (calls `normalize_inbound` for each new email, publishes to `connector.ingress`)
- Unit test: `test_conn_normalization.py` — assert all 4 connector types produce identical `InboundMessage` field names

### Phase 7 — US6: Monitoring and Dead-Letter Management (P3)
- `schemas.py`: `DeadLetterEntryResponse`, `DeadLetterRedeliverRequest`, `DeadLetterDiscardRequest`
- `repository.py`: `DeadLetterEntry` CRUD + `get_pending_entries()`, `increment_connector_metrics()` (atomic UPDATE on connector_instances delivery counters)
- `service.py`: `list/get_dead_letter_entries()`, `redeliver_dead_letter()` (create new OutboundDelivery; mark entry redelivered; publish to connector.delivery), `discard_dead_letter()` (archive to MinIO connector-dead-letters/{workspace_id}/{entry_id}.json; mark discarded), DLQ depth Redis counter update + workspace alert trigger
- `router.py`: DLQ endpoints (GET /dead-letter, GET /{id}, POST /{id}/redeliver, POST /{id}/discard)

### Phase 8 — Polish & Cross-Cutting Concerns
- Mount connectors router in `src/platform/api/__init__.py`
- Wire email polling APScheduler job + retry scanner into `worker_main.py`
- Wire connector worker Kafka consumer (`connector.delivery` group) into `worker_main.py`
- Full test coverage audit (≥ 95%)
- ruff + mypy --strict clean run

## Key Decisions (from research.md)

1. **Plugin Protocol**: Python `Protocol` class (structural typing) — no base class inheritance required; mypy --strict validates all 4 implementations at compile time
2. **6 PostgreSQL tables**: Separate tables per entity; credential refs isolated from config JSONB (impossible to accidentally store plaintext)
3. **Vault references**: `{"$ref": "key"}` sentinel in config JSONB; credentials resolved at delivery time only; rotation takes effect immediately (no caching)
4. **Webhook signature verification**: Raw-bytes HMAC-SHA256 in FastAPI dependency before Pydantic parsing; per-connector signing secret from vault
5. **Route caching**: Redis `connector:routes:{workspace_id}:{connector_instance_id}` TTL 60s; invalidated on route create/update/delete
6. **Retry mechanism**: Base 4 exponential backoff (1s/4s/16s); stored `next_retry_at` in DB — crash-safe; APScheduler retry scanner every 30s
7. **Dead-letter design**: Separate `dead_letter_entries` table; redeliver creates new `OutboundDelivery` (append-only); discard archives to MinIO for audit
8. **Email implementation**: `aioimaplib` (async IMAP) + `aiosmtplib` (async SMTP); polling in `worker` profile APScheduler (60s default)
9. **Inbound processing**: Webhook connectors handled in `api` profile (HTTP push); email polling in `worker` profile (periodic)
10. **Kafka topics**: `connector.ingress` keyed by `connector_instance_id` (consumed by interactions BC 024); `connector.delivery` keyed by `connector_instance_id` (consumed by connector worker)
11. **2 internal interfaces**: `get_connector_for_inbound()`, `resolve_inbound_route()` — in-process function calls
12. **Migration 010**: Sequential after 009_interactions_conversations; depends on workspaces FK from feature 018; no FK to registry tables (cross-BC isolation)
