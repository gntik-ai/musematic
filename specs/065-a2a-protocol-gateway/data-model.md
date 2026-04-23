# Data Model: A2A Protocol Gateway

**Feature**: 065-a2a-protocol-gateway | **Date**: 2026-04-19

## New Tables (Migration 052)

### a2a_tasks

Tracks every inbound or outbound A2A task from submission to terminal state.

```sql
CREATE TABLE a2a_tasks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id           VARCHAR(128) NOT NULL UNIQUE,  -- external A2A task identifier
    direction         a2a_direction NOT NULL,          -- 'inbound' | 'outbound'
    a2a_state         a2a_task_state NOT NULL DEFAULT 'submitted',
    agent_fqn         VARCHAR(512) NOT NULL,           -- targeted platform agent (inbound) or external agent (outbound)
    principal_id      UUID,                            -- authenticated external principal (inbound) or calling agent_id (outbound)
    workspace_id      UUID REFERENCES workspaces(id) ON DELETE SET NULL,
    interaction_id    UUID REFERENCES interactions(id) ON DELETE SET NULL,
    conversation_id   UUID,                            -- backing conversation id
    external_endpoint_id UUID REFERENCES a2a_external_endpoints(id) ON DELETE SET NULL,
    protocol_version  VARCHAR(16) NOT NULL,
    submitted_message JSONB NOT NULL,                  -- initial A2A Message payload
    result_payload    JSONB,                           -- final result when terminal
    error_code        VARCHAR(128),                    -- A2A error code on failure
    error_message     TEXT,                            -- sanitized error message
    last_event_id     VARCHAR(128),                    -- SSE last-event-id for reconnection
    idle_timeout_at   TIMESTAMPTZ,                     -- auto-cancel deadline (input_required state)
    cancellation_requested_at TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_a2a_tasks_state ON a2a_tasks(a2a_state);
CREATE INDEX ix_a2a_tasks_workspace ON a2a_tasks(workspace_id);
CREATE INDEX ix_a2a_tasks_principal ON a2a_tasks(principal_id);
CREATE INDEX ix_a2a_tasks_interaction ON a2a_tasks(interaction_id);
```

### a2a_external_endpoints

Operator-registered external A2A endpoints that platform agents are allowed to call.

```sql
CREATE TABLE a2a_external_endpoints (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id      UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    name              VARCHAR(255) NOT NULL,
    endpoint_url      VARCHAR(2048) NOT NULL,          -- HTTPS required (enforced at service layer)
    agent_card_url    VARCHAR(2048) NOT NULL,           -- URL to fetch Agent Card
    auth_config       JSONB NOT NULL,                  -- auth scheme config (no secrets — references vault)
    card_ttl_seconds  INTEGER NOT NULL DEFAULT 3600,
    cached_agent_card JSONB,                           -- durable fallback for Redis miss
    card_cached_at    TIMESTAMPTZ,
    card_is_stale     BOOLEAN NOT NULL DEFAULT FALSE,
    declared_version  VARCHAR(64),                     -- version from last-fetched Agent Card
    status            VARCHAR(32) NOT NULL DEFAULT 'active',  -- active | suspended | deleted
    created_by        UUID NOT NULL,                   -- operator user_id
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, endpoint_url)
);

CREATE INDEX ix_a2a_endpoints_workspace ON a2a_external_endpoints(workspace_id);
CREATE INDEX ix_a2a_endpoints_status ON a2a_external_endpoints(status);
```

### a2a_audit_records

Audit trail for all A2A interactions — both success and failure, inbound and outbound.

```sql
CREATE TABLE a2a_audit_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID REFERENCES a2a_tasks(id) ON DELETE SET NULL,
    direction       a2a_direction NOT NULL,
    principal_id    UUID,
    agent_fqn       VARCHAR(512) NOT NULL,
    action          VARCHAR(64) NOT NULL,    -- task_submitted | task_completed | task_failed |
                                             -- task_cancelled | outbound_call | outbound_denied |
                                             -- auth_failed | authz_failed | rate_limited | sanitized
    result          VARCHAR(32) NOT NULL,    -- success | denied | error
    policy_decision JSONB,                  -- GateResult if applicable
    workspace_id    UUID,
    error_code      VARCHAR(128),
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_a2a_audit_task ON a2a_audit_records(task_id);
CREATE INDEX ix_a2a_audit_occurred_at ON a2a_audit_records(occurred_at);
CREATE INDEX ix_a2a_audit_workspace ON a2a_audit_records(workspace_id);
```

## New Enums (Migration 052)

```sql
CREATE TYPE a2a_task_state AS ENUM (
    'submitted',
    'working',
    'input_required',
    'completed',
    'failed',
    'cancelled',
    'cancellation_pending'
);

CREATE TYPE a2a_direction AS ENUM (
    'inbound',
    'outbound'
);
```

## SQLAlchemy Models

### `a2a_gateway/models.py`

```python
class A2ATaskState(StrEnum):
    submitted = "submitted"
    working = "working"
    input_required = "input_required"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    cancellation_pending = "cancellation_pending"

class A2ADirection(StrEnum):
    inbound = "inbound"
    outbound = "outbound"

class A2ATask(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "a2a_tasks"

    task_id: Mapped[str]           # VARCHAR(128), UNIQUE
    direction: Mapped[A2ADirection]
    a2a_state: Mapped[A2ATaskState]
    agent_fqn: Mapped[str]
    principal_id: Mapped[UUID | None]
    workspace_id: Mapped[UUID | None]
    interaction_id: Mapped[UUID | None]
    conversation_id: Mapped[UUID | None]
    external_endpoint_id: Mapped[UUID | None]
    protocol_version: Mapped[str]
    submitted_message: Mapped[dict]          # JSONB
    result_payload: Mapped[dict | None]      # JSONB
    error_code: Mapped[str | None]
    error_message: Mapped[str | None]
    last_event_id: Mapped[str | None]
    idle_timeout_at: Mapped[datetime | None]
    cancellation_requested_at: Mapped[datetime | None]

class A2AExternalEndpoint(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "a2a_external_endpoints"

    workspace_id: Mapped[UUID | None]
    name: Mapped[str]
    endpoint_url: Mapped[str]
    agent_card_url: Mapped[str]
    auth_config: Mapped[dict]                # JSONB
    card_ttl_seconds: Mapped[int]
    cached_agent_card: Mapped[dict | None]   # JSONB
    card_cached_at: Mapped[datetime | None]
    card_is_stale: Mapped[bool]
    declared_version: Mapped[str | None]
    status: Mapped[str]
    created_by: Mapped[UUID]

class A2AAuditRecord(Base, UUIDMixin):
    __tablename__ = "a2a_audit_records"

    task_id: Mapped[UUID | None]
    direction: Mapped[A2ADirection]
    principal_id: Mapped[UUID | None]
    agent_fqn: Mapped[str]
    action: Mapped[str]
    result: Mapped[str]
    policy_decision: Mapped[dict | None]     # JSONB
    workspace_id: Mapped[UUID | None]
    error_code: Mapped[str | None]
    occurred_at: Mapped[datetime]
```

## Go Structures (N/A)

The A2A gateway is Python-only. No Go satellite service changes are required.

## Redis Keys

| Key pattern | Purpose | TTL |
|---|---|---|
| `cache:a2a_card:{sha256(url)[:16]}` | External Agent Card hot cache | `card_ttl_seconds` (default 3600s) |
| `cache:a2a_card_stale:{hash}` | Staleness flag when refresh fails | 7200s (2× TTL) |
| `ratelimit:a2a:{principal_id}` | Per-principal A2A rate limiting | Sliding window, no explicit TTL |

## Kafka Events

**Topic**: `a2a.events`

| Event type | Trigger |
|---|---|
| `a2a.task.submitted` | Inbound task accepted |
| `a2a.task.state_changed` | Any state transition |
| `a2a.task.completed` | Task reached completed state |
| `a2a.task.failed` | Task reached failed state |
| `a2a.task.cancelled` | Task reached cancelled state |
| `a2a.outbound.attempted` | Outbound call initiated (post-policy-allow) |
| `a2a.outbound.denied` | Outbound call blocked by policy |

## Existing Infrastructure Used

| Component | Usage |
|---|---|
| `registry/models.py` AgentProfile + AgentRevision | Agent Card auto-generation source |
| `interactions/` InteractionsRepository | Create Interaction records backing A2A tasks |
| `policies/gateway.py` ToolGatewayService | Inbound authz + outbound policy checks |
| `policies/sanitizer.py` OutputSanitizer | Sanitize A2A responses (both directions) |
| `auth/service.py` AuthService | Inbound token validation + revocation |
| `common/clients/redis.py` AsyncRedisClient | Card cache (set/get/TTL) + rate limiting |
| `common/events/` EventEnvelope + producer | Publish to `a2a.events` topic |
