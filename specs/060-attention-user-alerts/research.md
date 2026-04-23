# Research: Attention Pattern and Configurable User Alerts (Feature 060)

**Phase 0 output** | Feature directory: `specs/060-attention-user-alerts/`

---

## Decision 1 — interaction.state_changed event must be added

**Decision**: Add a generic `interaction.state_changed` event type to `interactions/events.py` and call it from `interaction_service.py` on every state transition.

**Rationale**: The existing specific events (`interaction.started`, `interaction.completed`, `interaction.failed`, `interaction.canceled`) do not include a `running → waiting` transition event, which maps to the default `working_to_pending` subscription pattern. A single `interaction.state_changed` event with `from_state` and `to_state` fields is the correct pattern — the notifications consumer filters by state pair, not by event type name. This is additive (does not change existing consumers of the specific events).

**Source**: `interactions/events.py` lines 15–26 (existing event types); `interactions/state_machine.py` lines 6–20 (triggers and states).

**Files to modify**: `apps/control-plane/src/platform/interactions/events.py`, `apps/control-plane/src/platform/interactions/interaction_service.py`.

---

## Decision 2 — context_summary must be added to AttentionRequestedPayload

**Decision**: Add `context_summary: str | None = None` to `AttentionRequestedPayload` in `interactions/events.py`. Update `publish_attention_requested()` callers to populate it.

**Rationale**: `AttentionRequest.context_summary` exists on the DB model (lines 348–381 of `interactions/models.py`) but is NOT in the Kafka payload. The notifications consumer cannot access the interactions bounded context's database tables (Principle IV). Adding `context_summary` to the payload is the only cross-boundary-safe way to populate the alert's `body` field. This is backward compatible (optional field with None default).

**Alternatives considered**: Fetch from DB via an internal service interface — rejected because it adds synchronous cross-service coupling in a hot-path Kafka consumer.

---

## Decision 3 — notifications.alerts Kafka topic for in-app WebSocket delivery

**Decision**: Introduce a new `notifications.alerts` Kafka topic (key = `user_id`) for in-app alert delivery. The notifications service publishes to this topic when delivery_method is `in_app`; the ws_hub fanout adds a consumer for it and routes messages to the existing `alerts` channel by `user_id`.

**Rationale**: The ws_hub currently pushes raw `interaction.attention` events to all subscribed clients through the attention channel (see `ws_hub/fanout.py` line 278). The notifications service needs to push *processed* alerts (preference-filtered, persisted, enriched with urgency/type/body) to clients. Using a separate topic avoids:
- Duplicate delivery (ws_hub raw + notifications processed)
- Cross-boundary method calls from notifications service into ws_hub's ConnectionRegistry

The existing fanout pattern already handles dynamic topic subscription by `resource_id` (user_id).

**Alternatives considered**: Call `ConnectionRegistry.get_by_user_id()` directly from notifications service — rejected as cross-boundary access.

**Files to modify**: `apps/control-plane/src/platform/ws_hub/fanout.py`, `apps/control-plane/src/platform/ws_hub/channels.py` (add `ALERTS` channel type if not present).

---

## Decision 4 — Migration 047 for the three new tables

**Decision**: Create Alembic migration `047_notifications_alerts.py` with `down_revision = "046_workspace_goal_lifecycle_and_decision"`. Adds tables `user_alert_settings`, `user_alerts`, `alert_delivery_outcomes` and enums `deliverymethod`, `deliveryoutcome`.

**Source**: Migration list — highest is `046_workspace_goal_lifecycle_and_decision.py`. Pattern from `010_connectors.py` and `045_oauth_providers_and_links.py`.

---

## Decision 5 — Webhook retry follows connectors/retry.py pattern

**Decision**: Use `connectors.retry.compute_next_retry_at(attempt_count)` (4^(n-1) second backoff) and an APScheduler scanner job registered in `main.py`. Store retry state in `alert_delivery_outcomes.next_retry_at`.

**Rationale**: Connectors already implement this exact pattern (`connectors/retry.py`, `main.py` lines 2449–2504). Reusing it is consistent with Brownfield Rule 4 (use existing patterns). The `DeliveryOutcome` enum values (`success`, `failed`, `timed_out`, `fallback`) map directly to FR-011 and FR-012 requirements.

**Source**: `apps/control-plane/src/platform/connectors/retry.py` (exponential backoff), `main.py` APScheduler setup pattern.

---

## Decision 6 — Email delivery via aiosmtplib with platform SMTP settings

**Decision**: The notifications service delivers emails using `aiosmtplib` directly with SMTP settings from `PlatformSettings` (same settings used by accounts for transactional email). No dependency on the connectors bounded context.

**Rationale**: The connectors framework is designed for user-configurable external connector instances, not platform-internal transactional email. Accounts (feature 016) already uses platform SMTP settings for verification/reset emails — the notifications service follows the same pattern. This avoids cross-boundary service calls and Kafka round-trips for email delivery.

**Source**: `apps/control-plane/src/platform/connectors/implementations/email.py` (aiosmtplib pattern).

---

## Decision 7 — Rate limiting via Redis sliding window (existing pattern)

**Decision**: Use `AsyncRedisClient.check_rate_limit("notifications", f"{source_fqn}:{user_id}", limit, 60_000)` to enforce per-source-per-user rate limits. Key pattern: `ratelimit:notifications:{source_fqn}:{user_id}`.

**Source**: `apps/control-plane/src/platform/common/clients/redis.py` lines 248–266 (`check_rate_limit`), `lua/rate_limit_check.lua` (sorted-set sliding window). Pattern confirmed in `auth/dependencies_oauth.py` lines 44–61.

---

## Decision 8 — Transition name pattern mapping

**Decision**: The `user_alert_settings.state_transitions` JSONB stores patterns like `working_to_pending`, `any_to_complete`, `any_to_failed`. The notifications service maps these to actual state enum values via a fixed alias table:

```python
_STATE_ALIASES: dict[str, str] = {
    "working": "running",
    "pending": "waiting",
    "complete": "completed",
    "failed": "failed",
    "canceled": "canceled",
    "ready": "ready",
    "paused": "paused",
}
```

A `matches_transition_pattern(pattern, from_state, to_state)` function handles `any_to_X` wildcards and exact `A_to_B` matches.

**Source**: `interactions/state_machine.py` (actual state names), user input DDL (pattern naming convention).

---

## Decision 9 — Retention GC via APScheduler daily job

**Decision**: Add an APScheduler daily job `notifications-retention-gc` in `main.py` that deletes `user_alerts` records older than `settings.notifications.alert_retention_days` (default 90). Cascades to `alert_delivery_outcomes`.

**Rationale**: APScheduler is the established pattern for periodic maintenance (connectors retry scanner, context engineering drift scanner). A daily interval is sufficient for retention GC.

---

## Key File Locations

| Asset | Path |
|---|---|
| AttentionRequest model | `apps/control-plane/src/platform/interactions/models.py` lines 348–381 |
| AttentionRequestedPayload | `apps/control-plane/src/platform/interactions/events.py` lines 99–106 |
| publish_attention_requested | `apps/control-plane/src/platform/interactions/events.py` lines 285–297 |
| ws_hub attention fanout | `apps/control-plane/src/platform/ws_hub/fanout.py` lines 278–280 |
| ConnectionRegistry | `apps/control-plane/src/platform/ws_hub/connection.py` lines 27–54 |
| Rate limit check | `apps/control-plane/src/platform/common/clients/redis.py` lines 248–266 |
| EventEnvelope + make_envelope | `apps/control-plane/src/platform/common/events/envelope.py` lines 11–65 |
| compute_next_retry_at | `apps/control-plane/src/platform/connectors/retry.py` |
| APScheduler main.py setup | `apps/control-plane/src/platform/main.py` lines 2449–2504 |
| Interaction state machine | `apps/control-plane/src/platform/interactions/state_machine.py` |
| Migration 046 (down_revision ref) | `apps/control-plane/migrations/versions/046_workspace_goal_lifecycle_and_decision.py` |
