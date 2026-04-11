# Research: Connector Plugin Framework

**Branch**: `025-connector-plugin-framework` | **Date**: 2026-04-11 | **Phase**: 0

## Decision Log

### Decision 1 — Plugin Contract Implementation
- **Decision**: Python `Protocol` class (`BaseConnector`) with four abstract methods: `validate_config()`, `normalize_inbound()`, `deliver_outbound()`, `health_check()`. Each built-in connector type is a concrete class implementing the protocol.
- **Rationale**: `Protocol` is structural typing — new connector types require no base class registration, just method implementation. Consistent with the Python 3.12+ type-safe approach mandated by the constitution (mypy --strict). The four methods map directly to the four lifecycle stages required by all six user stories.
- **Alternatives considered**: Abstract base class (`ABC`) — rejected because `Protocol` allows third-party implementations without inheriting from a platform class, enabling future extensibility without a hard dependency. Registry pattern with entry points — rejected as over-engineering for a single codebase.

### Decision 2 — Connector Type Registry
- **Decision**: A `CONNECTOR_TYPE_REGISTRY` dict mapping type slug (`slack`, `telegram`, `webhook`, `email`) to the concrete `BaseConnector` class. Populated at module import time in `connectors/registry.py`. `ConnectorType` table in PostgreSQL stores metadata (slug, display name, config schema, deprecated flag) but the actual logic lives in the registry dict.
- **Rationale**: Runtime dispatch via registry dict avoids dynamic class loading and reflection. Config schema stored in PostgreSQL as JSONB validates `ConnectorInstance.config` at creation/update time. Deprecated types still have registry entries (for existing instances to function) but are marked in the DB so no new instances can be created.
- **Alternatives considered**: Full database-driven dispatch — rejected because connector implementations contain business logic that belongs in code, not DB records. Enum-only approach without a DB table — rejected because we need to store per-type config schemas and deprecation state.

### Decision 3 — PostgreSQL Schema (6 Tables)
- **Decision**: Six tables in Alembic migration `010_connectors`:
  1. `connector_types` — registry metadata, config JSON schema, deprecated flag
  2. `connector_instances` — workspace-scoped, FK to connector_type, config JSONB, enabled, health status
  3. `connector_credential_refs` — vault path references only (never plaintext), FK to connector_instance, credential key name
  4. `connector_routes` — workspace-scoped routing rules, FK to connector_instance, conditions JSONB, target agent FQN, priority, enabled
  5. `outbound_deliveries` — delivery queue with retry state (attempt_count, next_retry_at, status), content JSONB, error_history JSONB array
  6. `dead_letter_entries` — permanently failed deliveries, FK to outbound_delivery, resolution_status (pending/redelivered/discarded)
- **Rationale**: Separate tables for each entity enables clean workspace isolation queries and independent indexing. Normalizing credential refs away from config JSONB makes it impossible to accidentally serialize a secret value into the config column.
- **Alternatives considered**: Embedding credential refs inside config JSONB — rejected because it creates a path where credential data co-mingles with non-sensitive config, violating §XI. Single delivery+DLQ table with a flag — rejected because DLQ entries have a distinct lifecycle (inspect/redeliver/discard) and query patterns that warrant their own table.

### Decision 4 — Inbound Message Flow
- **Decision**: Connector worker processes inbound webhooks (Slack, Telegram, generic webhook) in-process within the FastAPI `api` profile. Upon receiving a valid inbound request, the connector normalizes it to `InboundMessage` and publishes to the `connector.ingress` Kafka topic. Email inbound uses APScheduler in the `worker` profile, polling at a configurable interval (default 60s).
- **Rationale**: Webhook connectors are driven by HTTP push — they naturally live in the FastAPI router. The `connector.ingress` topic decouples reception from routing (interactions BC feature 024 consumes it). Email polling is a background task, not an HTTP handler, so it belongs in the `worker` profile alongside outbound delivery processing.
- **Alternatives considered**: Separate `inbound-worker` profile for all types — rejected as unnecessary overhead for HTTP-push connectors that already run in the API profile. IMAP IDLE push for email — rejected per spec assumption (polling is simpler, avoids long-lived TCP connections).

### Decision 5 — Outbound Delivery Worker
- **Decision**: Outbound delivery runs in the `worker` runtime profile. The worker consumes from `connector.delivery` Kafka topic, creates an `OutboundDelivery` record, attempts delivery via the connector's `deliver_outbound()` method, and updates retry state on failure. Exponential backoff intervals (1s, 4s, 16s, base 4) are stored as `next_retry_at` timestamps in the DB. A separate APScheduler job in the worker profile scans `outbound_deliveries` for past-due retries.
- **Rationale**: Kafka-driven consumption decouples delivery from the API profile. Storing `next_retry_at` as a DB column enables crash-safe retry scheduling — if the worker restarts mid-retry cycle, pending retries are picked up on restart. APScheduler retry scanner avoids complex Kafka delay-topic mechanics.
- **Alternatives considered**: In-process asyncio retry with sleep — rejected because pod restarts would lose pending retries. Kafka delay topics — rejected as over-engineering; the DB-backed retry scanner is simpler and meets SC-003 requirements.

### Decision 6 — Credential Isolation
- **Decision**: `ConnectorCredentialRef` stores only `vault_path` (string) and `credential_key` (logical name like `bot_token`). At delivery/health-check time, the connector worker calls `vault_client.get_secret(vault_path)` to retrieve the actual value. The value is injected directly into the HTTP request and never assigned to a variable that enters any logging context. The `ConnectorInstance.config` JSONB replaces credential values with a sentinel `{"$ref": "<credential_key>"}` before storage.
- **Rationale**: Per §XI, secrets are never in the LLM context and never in logs. The sentinel pattern prevents accidental plaintext storage. Vault resolution at call time supports credential rotation (SC-010) without connector restart.
- **Alternatives considered**: Encrypting credentials in the DB — rejected because the vault already handles encryption-at-rest; double-encryption adds key management complexity. Caching resolved credentials in Redis — rejected because credential rotation must take effect on the next operation (FR-020), and a cache would delay this.

### Decision 7 — Webhook Signature Verification
- **Decision**: Webhook signature verification happens in a FastAPI dependency (`verify_webhook_signature`) called before the route handler body. The dependency reads the raw request bytes (before Pydantic parsing), computes HMAC-SHA256 over them with the connector instance's signing secret, and compares to the signature header. Verification failure raises `WebhookSignatureError` (HTTP 401) before any payload processing occurs.
- **Rationale**: Verifying on raw bytes (before parsing) is standard practice and prevents signature bypass via JSON normalization differences. Failing before payload processing satisfies FR-007 ("rejected before any processing occurs"). The dependency approach is idiomatic FastAPI.
- **Alternatives considered**: Middleware-level verification — rejected because middleware cannot easily look up the per-connector signing secret (needs connector instance ID from the URL path). Post-parse verification — rejected as it allows JSON parsing of untrusted input.

### Decision 8 — Routing Rule Evaluation
- **Decision**: Routing rules are evaluated in-process at message receipt time. Rules are loaded from PostgreSQL per connector instance and cached in Redis (`connector:routes:{workspace_id}:{connector_instance_id}`, TTL 60s). Rule matching applies `channel_pattern` (glob) and `sender_pattern` (glob) conditions. Rules are sorted by `priority` (ASC, lower = higher priority), then `created_at` (ASC) as tiebreaker. First match wins.
- **Rationale**: In-process evaluation is faster than a separate routing service. Redis caching avoids a DB round-trip per message. Redis cache key includes workspace_id for isolation. TTL-based invalidation is acceptable for routing rules (changes take effect within 60s); immediate invalidation on rule update is also implemented by deleting the cache key.
- **Alternatives considered**: Database query per inbound message — rejected (too slow for SC-001: 500ms normalization + routing budget). Separate routing microservice — rejected (constitution §I: modular monolith).

### Decision 9 — Dead-Letter Queue Design
- **Decision**: `DeadLetterEntry` is a separate PostgreSQL table with `resolution_status` enum (pending, redelivered, discarded). Manual redeliver creates a new `OutboundDelivery` record (does not mutate the DLQ entry). Discard sets `resolution_status = discarded` and archives to MinIO object storage for audit. A workspace-level Redis counter tracks DLQ depth; an alert is triggered when it exceeds the configurable threshold.
- **Rationale**: Separate table enables DLQ-specific query patterns (list pending entries by workspace, filter by connector). Creating a new delivery record on redeliver follows the append-only principle and preserves the original failure history. MinIO archival of discarded entries satisfies audit requirements.
- **Alternatives considered**: Kafka dead-letter topic — rejected because operators need to inspect, redeliver, and discard entries via the management API; a Kafka topic does not support this interaction pattern. In-memory DLQ — rejected because DLQ entries must survive restarts (spec assumption).

### Decision 10 — Email Connector Implementation
- **Decision**: Email inbound uses `aioimaplib` for async IMAP polling. Email outbound uses `aiosmtplib` for async SMTP. The email connector's APScheduler job runs in the `worker` profile, polling every 60s (configurable per instance). Each polled email is normalized to `InboundMessage` and published to `connector.ingress`.
- **Rationale**: `aioimaplib` and `aiosmtplib` are the async-native IMAP/SMTP libraries compatible with the Python 3.12+ async-everywhere constraint. Polling in the `worker` profile (not API) keeps the API profile stateless.
- **Alternatives considered**: IMAP IDLE — rejected per spec assumption (complexity vs. benefit). Synchronous IMAP in a thread pool — rejected (violates async-everywhere convention). SES/SendGrid for outbound — rejected as a simplification; spec says standard email delivery (SMTP).

### Decision 11 — Kafka Topics
- **Decision**: Two topics:
  - `connector.ingress` — keyed by `connector_instance_id`; consumed by interactions BC (feature 024) to create interactions from inbound messages
  - `connector.delivery` — keyed by `connector_instance_id`; produced by execution BC, consumed by connector worker profile
- **Rationale**: Keying by `connector_instance_id` ensures ordered processing per connector. Two-topic separation matches the spec (FR-014, FR-015) and follows constitution §III event topology.
- **Alternatives considered**: Single topic with type field — rejected because inbound and outbound have entirely different consumers and retention requirements.

### Decision 12 — Alembic Migration Sequence
- **Decision**: `010_connectors` migration creates all 6 tables. Depends on migration `009_interactions_conversations` (feature 024) for workspace FK. No FK dependency on interactions tables — connectors and interactions are independent bounded contexts that coordinate via Kafka.
- **Rationale**: Migration 010 follows the sequential numbering pattern. No cross-BC FK is needed because routing targets (agent FQN) are stored as strings, not FKs to registry tables.
- **Alternatives considered**: FK from `connector_routes.target_agent_fqn` to `registry_agent_profiles.fqn` — rejected because it would create a cross-boundary DB dependency violating §IV.
