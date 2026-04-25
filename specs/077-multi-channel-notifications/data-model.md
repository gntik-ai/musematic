# Data Model: Multi-Channel Notifications

**Feature**: 077-multi-channel-notifications
**Phase**: 1 — Design
**Migration**: `058_multi_channel_notifications.py`

This document captures the persistence shape (Postgres tables, Redis keys, Vault paths, Kafka topics) without prescribing exact column types — those are pinned in the Alembic migration during implementation. The shape MUST stay backwards-compatible with the existing `notifications/` BC.

---

## PostgreSQL — schema additions

### 1. `notification_channel_configs` (NEW)

Per-user destination row. One row per (user, channel type, target).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Default `gen_random_uuid()`. |
| `user_id` | UUID FK → `users.id` ON DELETE CASCADE | A user's channel configs are deleted with the user (and the privacy-cascade in feature 076 reinforces this). |
| `channel_type` | `deliverymethod` enum | One of `in_app`, `email`, `webhook`, `slack`, `teams`, `sms` (existing enum extended). |
| `target` | TEXT | Email address, phone number (E.164), webhook URL, Slack webhook URL, Teams connector URL. NEVER stores a credential. |
| `display_name` | TEXT NULL | Optional label the user gives the channel ("My personal email", "Oncall phone"). |
| `signing_secret_ref` | VARCHAR(256) NULL | Vault path for the user's webhook HMAC secret. NULL for non-webhook channels and for chat/SMS targets that authenticate via the URL itself. |
| `enabled` | BOOLEAN NOT NULL DEFAULT TRUE | Self-service disable without delete. |
| `verified_at` | TIMESTAMPTZ NULL | Set once the verification flow completes. NULL = `pending_verification`. |
| `verification_token_hash` | VARCHAR(128) NULL | SHA-256 hash of the verification challenge token. Cleared on verify. |
| `verification_expires_at` | TIMESTAMPTZ NULL | Channel auto-archives if verification is not completed before this. |
| `quiet_hours` | JSONB NULL | `{"start": "22:00", "end": "08:00", "timezone": "Europe/Madrid"}`. NULL = no quiet hours. |
| `alert_type_filter` | JSONB NULL | List of allowed alert types, e.g. `["execution.failed","governance.verdict.issued"]`. NULL = all alert types pass. |
| `severity_floor` | VARCHAR(16) NULL | Minimum severity (`info`, `warn`, `high`, `critical`). NULL = no floor. SMS rows default to `critical`. |
| `extra` | JSONB NULL | Channel-specific extension blob (e.g., Slack channel display name, SMS sender ID). |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

**Constraints**:
- `UNIQUE(user_id, channel_type, target)` — a user cannot register the same target twice for the same channel.
- Index on `(user_id, enabled)` for the channel-router's hot read path.
- Partial index on `(user_id, channel_type)` WHERE `enabled = TRUE AND verified_at IS NOT NULL`.

**State transitions** (computed, not enforced as a SQL state machine):
```
pending_verification ──[verify]──▶ active
pending_verification ──[expire]──▶ archived
active ──[disable]──▶ disabled
disabled ──[enable]──▶ active
* ──[delete]──▶ row removed
```

**Verification token**: 32-byte URL-safe random; SHA-256 stored at `verification_token_hash`. Email verification = the user clicks the link containing the raw token (24h TTL). Phone verification = the user submits a 6-digit code (10 min TTL). Slack/Teams verification = the user confirms receipt of a one-time test message (synthetic verify endpoint, 30 min TTL).

---

### 2. `outbound_webhooks` (NEW)

Workspace-level webhook subscriptions used by external integrations.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Default `gen_random_uuid()`. |
| `workspace_id` | UUID FK → `workspaces.id` ON DELETE CASCADE | A workspace's outbound webhooks are deleted with the workspace. |
| `name` | VARCHAR(120) NOT NULL | Human label. |
| `url` | TEXT NOT NULL | HTTPS URL (HTTP rejected unless `FEATURE_ALLOW_HTTP_WEBHOOKS=true`). |
| `event_types` | JSONB NOT NULL | Array of subscribed event types: `["execution.failed","governance.verdict.issued",...]`. Empty = nothing. |
| `signing_secret_ref` | VARCHAR(256) NOT NULL | Vault path for the per-webhook HMAC secret. |
| `active` | BOOLEAN NOT NULL DEFAULT TRUE | Workspace admin can pause without delete. |
| `retry_policy` | JSONB NOT NULL DEFAULT `{"max_retries":3,"backoff_seconds":[60,300,1800],"total_window_seconds":86400}` | Per-webhook retry tunables; bounded by `notifications.retry_window_max_seconds` setting. |
| `region_pinned_to` | VARCHAR(64) NULL | Optional residency pin — when set, deliveries only fire from this region; cross-region attempts dead-letter. |
| `last_rotated_at` | TIMESTAMPTZ NULL | Last HMAC secret rotation. |
| `created_by` | UUID FK → `users.id` | For audit. |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

**Constraints**:
- Index on `(workspace_id, active)`.
- Index on `(workspace_id)` for listing.

---

### 3. `webhook_deliveries` (NEW)

One row per (webhook, event) delivery sequence. Retries reuse the same row, incrementing `attempts` and timestamps.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Default `gen_random_uuid()`. |
| `webhook_id` | UUID FK → `outbound_webhooks.id` ON DELETE CASCADE | |
| `idempotency_key` | UUID NOT NULL | Deterministic `uuid_v5(namespace=webhook.id, name=event.id)`. Stable across retries. |
| `event_id` | UUID NOT NULL | Source event ID (from `EventEnvelope.event_id`). |
| `event_type` | VARCHAR(96) NOT NULL | For filtering and dashboards. |
| `payload` | JSONB NOT NULL | Canonicalised body (JCS, sorted keys, no whitespace). The signed bytes. |
| `status` | VARCHAR(16) NOT NULL | `pending`, `delivering`, `delivered`, `failed`, `dead_letter`. |
| `failure_reason` | VARCHAR(64) NULL | `5xx`, `4xx_permanent`, `timeout`, `connection_refused`, `dlp_blocked`, `residency_violation`, `webhook_inactive`, `cost_cap_exceeded`, `retry_window_exhausted`. |
| `attempts` | INTEGER NOT NULL DEFAULT 0 | Number of HTTP attempts made. |
| `last_attempt_at` | TIMESTAMPTZ NULL | |
| `last_response_status` | INTEGER NULL | HTTP status from the most recent attempt. |
| `next_attempt_at` | TIMESTAMPTZ NULL | When to retry (NULL when terminal: `delivered` or `dead_letter`). |
| `dead_lettered_at` | TIMESTAMPTZ NULL | Set when `status = 'dead_letter'`. |
| `replayed_from` | UUID FK → `webhook_deliveries.id` NULL | When set, this delivery is a manual replay of a dead-letter entry. |
| `replayed_by` | UUID FK → `users.id` NULL | Operator who triggered replay. |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

**Constraints**:
- `UNIQUE(webhook_id, idempotency_key)` — one row per (webhook, event) sequence; replays create a new row that links back via `replayed_from`.
- Index on `(status, next_attempt_at)` for the retry-worker scan.
- Index on `(webhook_id, status, dead_lettered_at)` for dead-letter listing.
- Partial index on `dead_lettered_at` WHERE `status = 'dead_letter'`.
- Partition by month on `created_at` may be added in a future migration if delivery volume warrants — out of scope for v1.

---

### 4. `DeliveryMethod` enum extension (additive)

`ALTER TYPE deliverymethod ADD VALUE IF NOT EXISTS 'slack';`
`ALTER TYPE deliverymethod ADD VALUE IF NOT EXISTS 'teams';`
`ALTER TYPE deliverymethod ADD VALUE IF NOT EXISTS 'sms';`

Existing values (`in_app`, `email`, `webhook`) preserved.

---

### 5. Tables NOT modified

- `user_alert_settings` — preserved as-is for backwards compat (rule 7). Read by the channel router as a fallback when the user has no `notification_channel_configs` rows AND `FEATURE_MULTI_CHANNEL_NOTIFICATIONS=false`.
- `user_alerts` — preserved as-is.
- `alert_delivery_outcomes` — preserved as-is for in-app, email, and per-user webhook deliveries. Workspace outbound webhook deliveries persist instead in `webhook_deliveries` (richer at-least-once shape).

---

## Redis — key patterns

| Key | Type | TTL | Purpose |
|---|---|---|---|
| `notifications:webhook_lease:{delivery_id}` | string (worker host) | 60s | Prevents two retry workers from picking up the same delivery row simultaneously. Acquired with `SET NX EX 60` on dispatch; released on terminal status. |
| `notifications:webhook_dlq_depth:{workspace_id}` | counter | none | Maintained by trigger or by aggregation worker; observed by `deadletter_threshold_worker` for the operator alert (FR-026). |
| `notifications:channel_verify:{token_hash}` | string (channel_id) | matches verification window | Lookup index for verification challenges so the verification handler can resolve a token without scanning the table. |
| `notifications:sms_cost:{workspace_id}:{yyyy-mm}` | counter | 35d | Per-month per-workspace SMS cost accumulator for cost-cap enforcement. |

---

## Vault — secret paths

| Path | Contains | Rotation |
|---|---|---|
| `secret/data/notifications/webhook-secrets/{webhook_id}` | `{"hmac_secret": "<32-byte-base64>"}` | Manual (admin-triggered); KV v2 versioning preserves history; rotation does not echo back the value (rule 44). |
| `secret/data/notifications/user-webhook-secrets/{config_id}` | `{"hmac_secret": "<32-byte-base64>"}` | Manual (user-triggered for personal webhooks); same rotation pattern. |
| `secret/data/notifications/sms-providers/{deployment}` | Provider-specific (Twilio: `{"account_sid":"...","auth_token":"..."}`) | Manual; rotation by superadmin. |
| `secret/data/notifications/email-smtp/{deployment}` | Existing — unchanged. | Existing rotation. |

All paths resolve via `common.secrets.secret_provider` (rule 39). DB stores only the path strings.

---

## Kafka — events emitted

| Topic | Event type | Producer | Consumers |
|---|---|---|---|
| `monitor.alerts` (existing) | `notifications.channel.config.changed` | `notifications/service.py` | analytics (delivery health), audit (forward to chain) |
| `monitor.alerts` (existing) | `notifications.webhook.registered` / `.deactivated` / `.rotated` | `notifications/service.py` | analytics, audit |
| `monitor.alerts` (existing) | `notifications.delivery.attempted` | `channel_router` | analytics |
| `monitor.alerts` (existing) | `notifications.delivery.dead_lettered` | `webhook_retry_worker` | analytics, audit |
| `monitor.alerts` (existing) | `notifications.dlq.depth.threshold_reached` | `deadletter_threshold_worker` | operator (already on `monitor.alerts`) |

**No new Kafka topics.** All emissions reuse the existing `monitor.alerts` topic (the constitution lists this topic as already serving the notifications BC), keeping the topic registry clean.

---

## Configuration — `PlatformSettings.notifications` extensions

New fields (under existing `NotificationsSettings`):

| Field | Type | Default | Purpose |
|---|---|---|---|
| `multi_channel_enabled` | bool | False | Master flag (`FEATURE_MULTI_CHANNEL_NOTIFICATIONS`). |
| `webhook_default_backoff_seconds` | list[int] | `[60, 300, 1800]` | Default retry schedule. |
| `webhook_max_retry_window_seconds` | int | 86400 | Hard upper bound (24h, rule 17). |
| `webhook_replay_window_seconds` | int | 300 | Receiver-side timestamp tolerance. |
| `channels_per_user_max` | int | 6 | Per-user channel cap. |
| `webhooks_per_workspace_max` | int | 50 | Per-workspace webhook cap. |
| `dead_letter_retention_days` | int | 30 | DLQ row retention. |
| `dead_letter_warning_threshold` | int | 100 | Per-workspace DLQ depth that triggers operator alert. |
| `sms_default_severity_floor` | str | `critical` | Default SMS severity floor. |
| `sms_provider` | str | `twilio` | Provider key for adapter selection. |
| `sms_workspace_monthly_cost_cap_eur` | float | 50.0 | Per-workspace SMS cost cap. |
| `allow_http_webhooks` | bool | False | Dev-only escape hatch (`FEATURE_ALLOW_HTTP_WEBHOOKS`). Refuses to enable when `ENV=production`. |
| `quiet_hours_default_severity_bypass` | str | `critical` | Severity at or above which alerts bypass quiet hours. |

---

## Entity relationships

```
users 1───∞ notification_channel_configs
workspaces 1───∞ outbound_webhooks 1───∞ webhook_deliveries
users 1───∞ user_alert_settings (existing, preserved)
users 1───∞ user_alerts 1───1 alert_delivery_outcomes (existing, preserved)

workspaces.data_residency_configs (feature 076) ───┐
                                                    ├──▶ used by channel_router for residency check
notification_channel_configs.target (URL) ─────────┘
outbound_webhooks.url ─────────────────────────────┘
```

---

## Validation rules (enforced at service layer)

- `channel_type='sms'` ⇒ `target` matches E.164 phone format; `severity_floor` defaults to `critical` and may not drop below `high`.
- `channel_type='webhook'` ⇒ `target` is a valid URL; HTTPS unless `allow_http_webhooks=true`; URL passes residency check at registration.
- `channel_type='slack'` or `'teams'` ⇒ `target` matches the provider's expected incoming-webhook format; first dispatch is a verification test message.
- `channel_type='email'` ⇒ `target` is a valid RFC 5322 email; verification link is sent at registration.
- `quiet_hours.timezone` ⇒ valid IANA zone (resolvable by `zoneinfo`).
- `alert_type_filter` ⇒ entries match the platform's known alert-type registry (the registry is in `notifications.events`).
- `outbound_webhooks.event_types` ⇒ entries match the platform's `EventEnvelope` event-type registry; unknown types rejected.

---

## Backwards compatibility checklist

- Existing `user_alert_settings.delivery_method` still operates as the per-user routing source when `multi_channel_enabled=false`.
- When `multi_channel_enabled=true` AND a user has no `notification_channel_configs` rows, the legacy `user_alert_settings.delivery_method` is consulted as a single-channel fallback.
- When a user has at least one `notification_channel_configs` row, the legacy `user_alert_settings.delivery_method` is ignored for that user (the per-channel rows take over).
- Existing `email` and `webhook` deliverers are reused unchanged for legacy single-channel paths and as the underlying transport for the new channel router.
- Existing tests in `tests/control-plane/unit/notifications/` remain green without modification (the new code paths are additive).

---

## Audit chain integration (rule 9, 32)

Every channel-config CRUD and outbound-webhook CRUD operation calls `audit_chain_service.append(payload)` with a payload of the form:

```json
{
  "event": "notifications.channel.config.changed",
  "actor": "<user_id>",
  "subject": "<channel_config_id or webhook_id>",
  "scope": {"workspace_id": "...", "user_id": "..."},
  "diff": {"before": {...}, "after": {...}},
  "occurred_at": "<iso8601>"
}
```

Audit calls are fire-and-forget (per critical reminder #30 — Kafka guarantees durability) but use the existing audit chain infrastructure rather than emitting a parallel chain.

---

## DLP integration (rule 34)

Before any outbound delivery (US1 channels and US2 webhooks alike), the channel router calls:

```python
verdict = await dlp_service.scan_outbound(
    payload=canonical_payload,
    workspace_id=workspace_id,
    channel_type=channel_type,
)
if verdict.action == "block":
    raise DlpBlockedError(...)
elif verdict.action == "redact":
    canonical_payload = verdict.redacted_payload
# verdict.action == "allow" — proceed
```

For workspace outbound webhooks, the DLP `scan_outbound` is called with the workspace's DLP configuration. For per-user channels, it's called with the workspace context if available, else with platform-default rules.

---

## Residency integration (rule 18)

At webhook registration:

```python
region_resolved = residency_service.resolve_region_for_url(url)
allowed = residency_service.check_egress(workspace_id, region_resolved)
if not allowed:
    raise ResidencyViolationError(...)
```

At runtime delivery (in case configuration drift):

```python
if not residency_service.check_egress(workspace_id, region_resolved):
    delivery.status = "dead_letter"
    delivery.failure_reason = "residency_violation"
```
