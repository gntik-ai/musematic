# Phase 1 Data Model: API Governance and Developer Experience

**Feature**: 073-api-governance-dx
**Date**: 2026-04-23

## Overview

Three new Postgres tables (all created in migration 057), four new
Redis key prefixes, one new Kafka topic, and one in-process registry
for deprecation markers. No new bounded context — all tables live
under `apps/control-plane/src/platform/common/` and are owned by the
two new modules (`common/rate_limiter/`, `common/debug_logging/`).

---

## 1. PostgreSQL

### 1.1 `api_subscription_tiers`

Static catalogue of rate-limit budgets. Seeded at migration time.

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | UUID (PK) | `DEFAULT gen_random_uuid()` | Surrogate PK |
| `name` | VARCHAR(32) | `NOT NULL UNIQUE` | Tier name (`anonymous`, `default`, `pro`, `enterprise`) |
| `requests_per_minute` | INTEGER | `NOT NULL CHECK (> 0)` | Per-minute budget |
| `requests_per_hour` | INTEGER | `NOT NULL CHECK (> 0)` | Per-hour budget |
| `requests_per_day` | INTEGER | `NOT NULL CHECK (> 0)` | Per-day budget |
| `description` | TEXT | `NOT NULL` | Short human-readable description |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` | Audit |
| `updated_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` | Audit |

**Indexes**: `UNIQUE(name)` (implicit).

**Seed rows** (per research.md D-007):

```
('anonymous',  60,    1000,    10000)
('default',    300,   10000,   100000)
('pro',        1000,  50000,   500000)
('enterprise', 5000,  500000,  10000000)
```

**Relationships**: Referenced by `api_rate_limits.subscription_tier_id`.

---

### 1.2 `api_rate_limits`

Per-principal rate-limit configuration. Overrides the per-tier
defaults when populated (optional; absent → tier defaults apply
directly from `api_subscription_tiers`).

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | UUID (PK) | `DEFAULT gen_random_uuid()` | Surrogate PK |
| `principal_type` | VARCHAR(32) | `NOT NULL CHECK (IN ('user', 'service_account', 'external_a2a'))` | Principal kind |
| `principal_id` | UUID | `NOT NULL` | FK-loose reference to the principal's bounded context |
| `subscription_tier_id` | UUID | `NOT NULL REFERENCES api_subscription_tiers(id)` | Tier binding (pre-resolved to save a join) |
| `requests_per_minute_override` | INTEGER | `NULL` | Optional per-principal override of RPM |
| `requests_per_hour_override` | INTEGER | `NULL` | Optional per-principal override of RPH |
| `requests_per_day_override` | INTEGER | `NULL` | Optional per-principal override of RPD |
| `created_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` | Audit |
| `updated_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` | Audit |

**Indexes**:
- `UNIQUE (principal_type, principal_id)` — each principal has at most
  one row.
- `ix_api_rate_limits_tier` on `(subscription_tier_id)` — for tier
  change enumeration.

**Business rules**:
- A principal without a row here is treated as belonging to the
  `default` tier (rule D-006). This is resolved at request time by the
  rate-limit middleware.
- Override columns, when non-null, shadow the tier defaults; `NULL`
  falls through to the tier.
- No FK to the principal's table (`users.id`, service accounts,
  external A2A peers) because the principal lives across multiple
  bounded contexts and constitution principle IV forbids cross-BC
  FKs. Cleanup on principal deletion happens via cascade-deletion
  (per privacy rule 15) by the DSR/RTBF tooling that knows which
  principal type applies.

---

### 1.3 `debug_logging_sessions`

Audit + lifecycle record for a time-bounded debug-logging session.

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | UUID (PK) | `DEFAULT gen_random_uuid()` | Session ID |
| `target_type` | VARCHAR(32) | `NOT NULL CHECK (IN ('user', 'workspace'))` | Scope kind |
| `target_id` | UUID | `NOT NULL` | Scope's ID |
| `requested_by` | UUID | `NOT NULL REFERENCES users(id)` | Support engineer |
| `justification` | TEXT | `NOT NULL CHECK (length(justification) >= 10)` | Written reason |
| `started_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` | Open time |
| `expires_at` | TIMESTAMPTZ | `NOT NULL CHECK (expires_at <= started_at + INTERVAL '4 hours')` | Hard max 4 h per FR-025 |
| `terminated_at` | TIMESTAMPTZ | `NULL` | Set when session ends early (RTBF cascade, manual close) |
| `termination_reason` | VARCHAR(64) | `NULL` | `expired`, `rtbf_cascade`, `manual_close` |
| `capture_count` | INTEGER | `NOT NULL DEFAULT 0` | Running count (monotonically increasing) |
| `correlation_id` | UUID | `NOT NULL` | Correlation ID of the opening request |

**Indexes**:
- `ix_debug_sessions_target` on `(target_type, target_id, expires_at)`
  — hot lookup for "is there an active session for this target?"
  during request capture; filtered `WHERE terminated_at IS NULL AND
  now() < expires_at`.
- `ix_debug_sessions_requested_by` on `(requested_by, started_at)` —
  admin dashboards.
- `ix_debug_sessions_expires_at` on `(expires_at)` — purge job.

**Business rules**:
- `expires_at` MUST be ≤ `started_at + 4 hours` (check constraint);
  the application layer ALSO enforces this to give a user-friendly
  error before hitting the DB constraint.
- Extending a session past its original `expires_at` is not allowed
  (FR-025); administrators open a fresh session instead.
- On termination (any reason), `terminated_at` is set and captures for
  this session stop being written by the capture middleware.

---

### 1.4 `debug_logging_captures`

PII-redacted request/response pairs captured during an active session.

| Column | Type | Constraints | Purpose |
|---|---|---|---|
| `id` | UUID (PK) | `DEFAULT gen_random_uuid()` | Capture ID |
| `session_id` | UUID | `NOT NULL REFERENCES debug_logging_sessions(id) ON DELETE CASCADE` | Parent session |
| `captured_at` | TIMESTAMPTZ | `NOT NULL DEFAULT now()` | Capture time |
| `method` | VARCHAR(10) | `NOT NULL` | HTTP method |
| `path` | TEXT | `NOT NULL` | Normalised path (query string redacted) |
| `request_headers` | JSONB | `NOT NULL` | Allowlisted headers (per redaction rule D-009) |
| `request_body` | TEXT | `NULL` | Redacted body, truncated to 8 KiB |
| `response_status` | INTEGER | `NOT NULL` | HTTP status |
| `response_headers` | JSONB | `NOT NULL` | Allowlisted response headers |
| `response_body` | TEXT | `NULL` | Redacted body, truncated to 8 KiB |
| `duration_ms` | INTEGER | `NOT NULL CHECK (>= 0)` | Request duration |
| `correlation_id` | UUID | `NOT NULL` | Request's correlation ID |

**Indexes**:
- `ix_debug_captures_session` on `(session_id, captured_at)` — order
  captures within a session chronologically.
- `ix_debug_captures_captured_at` on `(captured_at)` — purge job.

**Business rules**:
- Bodies are truncated to 8 KiB and the final 32 characters of the
  original body's sha-256 digest are appended with `…[truncated=<sha256-32>]`
  so support engineers can detect truncation.
- `ON DELETE CASCADE` on `session_id` makes RTBF cascades clean
  (sessions erased → captures erased atomically).

---

### 1.5 Migration 057 shape

```python
# apps/control-plane/migrations/versions/057_api_governance.py
"""api governance: rate limits + debug logging

Revision ID: 057
Revises: 056
Create Date: 2026-04-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "057"
down_revision = "056"

def upgrade() -> None:
    op.create_table(
        "api_subscription_tiers", ...
    )
    op.create_table(
        "api_rate_limits", ...
    )
    op.create_table(
        "debug_logging_sessions", ...
    )
    op.create_table(
        "debug_logging_captures", ...
    )
    # Seed the four default tiers
    op.bulk_insert(...)

def downgrade() -> None:
    op.drop_table("debug_logging_captures")
    op.drop_table("debug_logging_sessions")
    op.drop_table("api_rate_limits")
    op.drop_table("api_subscription_tiers")
```

---

## 2. Redis

### 2.1 Key schema

| Key pattern | Purpose | TTL |
|---|---|---|
| `ratelimit:principal:{principal_type}:{principal_id}:min` | Per-principal minute counter | 60 s |
| `ratelimit:principal:{principal_type}:{principal_id}:hour` | Per-principal hour counter | 3600 s |
| `ratelimit:principal:{principal_type}:{principal_id}:day` | Per-principal day counter | 86400 s |
| `ratelimit:anon:{source_ip}:min` | Per-IP minute counter | 60 s |
| `ratelimit:anon:{source_ip}:hour` | Per-IP hour counter | 3600 s |
| `ratelimit:anon:{source_ip}:day` | Per-IP day counter | 86400 s |
| `ratelimit:tier:{tier_id}` | Cached tier budget (`{"rpm":…,"rph":…,"rpd":…}`) | 300 s |
| `ratelimit:principal_tier:{principal_type}:{principal_id}` | Cached tier binding for a principal | 60 s |
| `debug_session:active:{target_type}:{target_id}` | Cached "active session?" answer (session_id or `""`) | 30 s |

### 2.2 Lua script: `rate_limit_multi_window.lua`

```lua
-- KEYS: [1]=min_key, [2]=hour_key, [3]=day_key
-- ARGV: [1]=rpm_limit, [2]=rph_limit, [3]=rpd_limit
--       [4]=min_ttl, [5]=hour_ttl, [6]=day_ttl
-- Returns: [allowed (0|1), remaining_min, remaining_hour, remaining_day, retry_after_ms]

local function check_bucket(key, limit, ttl)
  local current = tonumber(redis.call("GET", key) or "0")
  if current >= limit then
    local ttl_ms = redis.call("PTTL", key)
    return { 0, 0, ttl_ms }
  end
  redis.call("INCR", key)
  -- Set TTL only on first increment (current was 0)
  if current == 0 then
    redis.call("EXPIRE", key, ttl)
  end
  return { 1, limit - current - 1, 0 }
end

local min_result = check_bucket(KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[4]))
local hour_result = check_bucket(KEYS[2], tonumber(ARGV[2]), tonumber(ARGV[5]))
local day_result = check_bucket(KEYS[3], tonumber(ARGV[3]), tonumber(ARGV[6]))

-- Overall allow = all three buckets allowed
local allowed = min_result[1] * hour_result[1] * day_result[1]

-- Retry-after is the max of whichever buckets denied
local retry_after_ms = math.max(min_result[3], hour_result[3], day_result[3])

return { allowed, min_result[2], hour_result[2], day_result[2], retry_after_ms }
```

Loaded at startup by `AsyncRedisClient.initialize()` (extend the
script list in `common/clients/redis.py:112-118`). SHA cached in
`_lua_scripts`.

---

## 3. Kafka

### 3.1 New topic: `debug_logging.events`

| Partition key | Event type | Payload |
|---|---|---|
| `session_id` | `debug_logging.session.created` | `{session_id, requested_by, target_type, target_id, justification, started_at, expires_at, correlation_id}` |
| `session_id` | `debug_logging.session.expired` | `{session_id, duration_ms, capture_count, termination_reason}` |
| `session_id` | `debug_logging.capture.written` | `{session_id, capture_id, captured_at, method, path, response_status, duration_ms, correlation_id}` (no bodies — PII-sensitive) |

Events MUST NOT carry redacted bodies; event payloads are lightweight
audit pointers to the Postgres capture row.

Registered in a new `common/debug_logging/events.py` module with the
same `publish_*_event` shape established in
`auth/events.py:publish_auth_event`.

---

## 4. In-process: Deprecation Marker Registry

A module-level dict keyed by route ID:

```python
# common/api_versioning/registry.py

@dataclass(frozen=True)
class DeprecationMarker:
    sunset: datetime        # RFC-9110 HTTP-date serialisable
    successor_path: str | None

_markers: dict[str, DeprecationMarker] = {}

def mark_deprecated(route_id: str, *, sunset: datetime, successor: str | None = None) -> None:
    _markers[route_id] = DeprecationMarker(sunset=sunset, successor_path=successor)

def get_marker(route_id: str) -> DeprecationMarker | None:
    return _markers.get(route_id)
```

Populated at import time via a decorator
`@deprecated_route(sunset="2026-10-01", successor="/api/v2/…")` that
wraps the FastAPI route handler, sets `route.deprecated = True` on the
underlying `APIRoute` (so FastAPI's OpenAPI generator emits
`deprecated: true`), and calls `mark_deprecated(route.unique_id, …)`.

The `ApiVersioningMiddleware` looks up the marker on egress via the
route ID stored in `request.scope["route"]`.

---

## 5. Scope boundaries

- **No new bounded context.** All models live under `common/rate_limiter/`
  and `common/debug_logging/`; principle IV compliance is upheld
  because these are **infrastructure shared modules**, explicitly
  scoped to cross-cutting concerns that cross all bounded contexts.
- **No new UI surface** (per FR and constitution rule 45 partial note).
  Admin surface ships backend-only; UPD-036 will consume it.
- **No new environment variables** on the control plane. CI publishing
  tokens (`PYPI_TOKEN`, `NPM_TOKEN`, `CRATES_IO_TOKEN`,
  `GITHUB_TOKEN`) live in GitHub Actions secrets, consumed only by
  `sdks.yml`.
