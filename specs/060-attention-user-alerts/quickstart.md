# Quickstart & Test Scenarios: Attention Pattern and Configurable User Alerts (Feature 060)

---

## Prerequisites

1. Platform running with all services (control-plane, ws_hub, Kafka, PostgreSQL, Redis).
2. Migration 047 applied: `alembic upgrade head`.
3. Two test users: `user_a@test.com` (online), `user_b@test.com` (offline).
4. One test agent with FQN `test-ns:attention-agent` and credentials to publish to `interaction.attention`.
5. WebSocket client connected as `user_a`.

---

## S1 — Attention request reaches online user within 2 seconds

**Setup**: `user_a` connected via WebSocket.  
**Action**: Publish an `AttentionRequestedPayload` to `interaction.attention` with `target_identity=user_a_id`, `urgency=high`, `context_summary="Needs approval"`, `source_agent_fqn="test-ns:attention-agent"`.  
**Verify**:
- `user_a`'s WebSocket receives a message on the `alerts` channel within 2 seconds.
- Message contains `alert_type="attention_request"`, `urgency="high"`, `title` non-empty, `read=false`.
- `GET /api/v1/me/alerts` returns the alert.
- `GET /api/v1/me/alerts/unread-count` returns `{"count": 1}`.

---

## S2 — Attention request persisted for offline user

**Setup**: `user_b` is offline (no WebSocket session).  
**Action**: Publish attention request targeting `user_b_id`.  
**Verify**:
- No WebSocket delivery attempt occurs.
- `user_alerts` DB record created with `read=false` for `user_b_id`.
- `user_b` logs in, connects WebSocket — `GET /api/v1/me/alerts?read=unread` returns the alert.
- WebSocket receives `notifications.alert_created` push on `alerts` channel on connect.

---

## S3 — Multiple sessions receive alert simultaneously

**Setup**: `user_a` has two active WebSocket sessions (browser tab + mobile).  
**Action**: Publish attention request targeting `user_a_id`.  
**Verify**:
- Both sessions receive the alert on the `alerts` channel within 2 seconds.
- Only one `user_alerts` DB record is created (not one per session).

---

## S4 — User configures preferences — unsubscribed transition generates no alert

**Setup**: `user_a` has default settings (`working_to_pending`, `any_to_complete`, `any_to_failed`).  
**Action**: `PUT /api/v1/me/alert-settings` with `state_transitions=["any_to_failed"]`.  
**Action 2**: Trigger `interaction.state_changed` with `from_state=running, to_state=completed` for an interaction in `user_a`'s workspace.  
**Verify**:
- No new `user_alerts` record created for `user_a` (completed is not in their subscription).  
**Action 3**: Trigger `from_state=running, to_state=failed`.  
**Verify**: Alert created and delivered to `user_a`.

---

## S5 — any_to_failed matches any from_state

**Setup**: `user_a` settings: `state_transitions=["any_to_failed"]`.  
**Action**: Trigger `from_state=paused, to_state=failed`.  
**Verify**: Alert generated (any_to_failed matches paused→failed).

---

## S6 — working_to_pending transition pattern matching

**Setup**: `user_a` settings: `state_transitions=["working_to_pending"]`.  
**Action**: Trigger `from_state=running, to_state=waiting`.  
**Verify**: Alert generated (working maps to running, pending maps to waiting).  
**Action 2**: Trigger `from_state=ready, to_state=waiting`.  
**Verify**: No alert (ready_to_waiting does not match working_to_pending).

---

## S7 — Default settings applied when no record exists

**Setup**: Delete `user_a`'s alert settings record.  
**Action**: Trigger `from_state=running, to_state=completed`.  
**Verify**: Alert generated (default `any_to_complete` matches).  
**Action 2**: `GET /api/v1/me/alert-settings` returns default settings (not persisted).

---

## S8 — webhook delivery method validated

**Action**: `PUT /api/v1/me/alert-settings` with `delivery_method="webhook"`, no `webhook_url`.  
**Verify**: Response 422 with message `"webhook_url is required when delivery_method is webhook"`.

---

## S9 — Email delivery

**Setup**: `user_a` settings: `delivery_method=email`. Platform SMTP configured.  
**Action**: Trigger qualifying state transition.  
**Verify**:
- `user_alerts` record created.
- `alert_delivery_outcomes` record created with `delivery_method=email`.
- Email arrives at `user_a`'s address within 60 seconds.
- `alert_delivery_outcomes.outcome` updated to `success`, `delivered_at` set.

---

## S10 — Webhook delivery success

**Setup**: `user_a` settings: `delivery_method=webhook`, `webhook_url=http://test-endpoint/hook`.  
**Action**: Trigger qualifying event.  
**Verify**:
- POST received at `http://test-endpoint/hook` within 5 seconds.
- Payload contains `id`, `alert_type`, `title`, `urgency`.
- `alert_delivery_outcomes.outcome="success"`.
- No credentials in payload (verify `webhook_url` itself is not echoed).

---

## S11 — Webhook delivery retry on failure

**Setup**: Test endpoint configured to return 503 for first 2 calls, then 200.  
**Action**: Trigger qualifying event.  
**Verify**:
- First attempt fails, `attempt_count=1`, `next_retry_at` set (4^0=1s from now).
- Retry scanner picks it up, second attempt fails, `attempt_count=2`, `next_retry_at` set (4^1=4s).
- Third attempt succeeds, `outcome=success`.

---

## S12 — Webhook fallback when URL missing

**Setup**: `user_a` settings: `delivery_method=webhook`, `webhook_url=null` (edge case — URL deleted post-save).  
**Action**: Trigger qualifying event.  
**Verify**:
- Alert persisted with `alert_type` as expected.
- Delivery falls back to `in_app` (WebSocket push).
- `alert_delivery_outcomes.outcome=fallback`, `error_detail` contains reason.

---

## S13 — Mark alert as read propagates across sessions

**Setup**: `user_a` has 2 active WebSocket sessions, 3 unread alerts.  
**Action**: `PATCH /api/v1/me/alerts/{alert_id}/read` from session 1.  
**Verify**:
- `user_alerts.read=true` for the alert.
- Both WebSocket sessions receive `notifications.alert_read` push with `unread_count=2`.
- `GET /api/v1/me/alerts/unread-count` returns `{"count": 2}`.

---

## S14 — Rate limiting prevents flood

**Setup**: A misbehaving agent is configured to spam attention requests at 60 req/min (above threshold).  
**Action**: Publish 100 attention requests from `test-ns:flood-agent` targeting `user_a` within 1 minute.  
**Verify**:
- At most `settings.notifications.rate_limit_per_source_per_minute` alerts created for `user_a` from that source.
- Excess events discarded; incident log entry created per dropped event.

---

## S15 — Retention GC removes old alerts

**Setup**: Insert `user_alerts` records with `created_at` older than `alert_retention_days`.  
**Action**: Trigger retention GC job (either wait for daily schedule or call directly).  
**Verify**:
- Old records deleted from `user_alerts` (cascades to `alert_delivery_outcomes`).
- `GET /api/v1/me/alerts` no longer returns deleted alerts.
- If `user_b` was offline and alert expired, next login does not deliver expired alert.

---

## S16 — Authorization isolation

**Action**: Authenticated as `user_a`, call `GET /api/v1/me/alerts/{alert_id}` where `alert_id` belongs to `user_b`.  
**Verify**: Response 403 (not 404, not data leak).

---

## S17 — Unknown transition pattern ignored

**Setup**: `user_a` settings: `state_transitions=["nonexistent_pattern", "any_to_failed"]`.  
**Action**: Trigger `from_state=running, to_state=failed`.  
**Verify**: Alert generated (any_to_failed matches; unknown pattern is ignored).

---

## S18 — Unknown urgency defaults to medium

**Action**: Publish attention request with `urgency="super_critical"` (not in enum).  
**Verify**:
- Alert created with `urgency="medium"`.
- Warning logged.
- Alert still delivered.
