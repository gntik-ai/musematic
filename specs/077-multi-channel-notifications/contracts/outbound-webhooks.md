# Outbound Webhooks Contract

**Feature**: 077-multi-channel-notifications
**Modules**:
- `apps/control-plane/src/platform/notifications/routers/webhooks_router.py`
- `apps/control-plane/src/platform/notifications/deliverers/webhook_deliverer.py` (modified)
- `apps/control-plane/src/platform/notifications/workers/webhook_retry_worker.py` (new)
- `apps/control-plane/src/platform/notifications/canonical.py` (new)

This contract documents both the workspace-admin REST surface and the delivery worker.

## REST endpoints

Under `/api/v1/notifications/webhooks/*` (already reserved in constitution § REST Endpoint Prefixes):

| Method + path | Purpose | Role |
|---|---|---|
| `POST /api/v1/notifications/webhooks` | Register a new outbound webhook for a workspace; returns the new HMAC secret ONCE in the response (subsequent calls show only the vault path, never the secret). | `workspace_admin` for the target workspace |
| `GET /api/v1/notifications/webhooks?workspace_id=` | List webhooks (active + inactive). | `workspace_admin`, `auditor`, `superadmin` |
| `GET /api/v1/notifications/webhooks/{id}` | Get one webhook (no secret material). | same |
| `PATCH /api/v1/notifications/webhooks/{id}` | Update name, URL (with re-residency-check), event_types, retry_policy, active flag. | `workspace_admin` |
| `POST /api/v1/notifications/webhooks/{id}/rotate-secret` | Rotate HMAC secret. Response confirms rotation but never echoes back the new secret value (rule 44). The new secret is fetched separately via the secret-retrieval flow scoped to the rotating actor. | `workspace_admin` |
| `DELETE /api/v1/notifications/webhooks/{id}` | Soft-delete (sets active=false; row retained for audit) or hard-delete (operator-only with 2PA). | `workspace_admin` (soft) / `superadmin` + 2PA (hard) |
| `POST /api/v1/notifications/webhooks/{id}/test` | Synthesize a test event and dispatch through the full pipeline (HMAC, retries, DLQ); returns the delivery row id for inspection. | `workspace_admin` |

## Per-user webhook channels (different surface)

Self-service user webhooks live under `/api/v1/me/notifications/channels/*` (rule 46 — `current_user`-scoped, no `user_id` parameter):

| Method + path | Purpose |
|---|---|
| `GET /api/v1/me/notifications/channels` | List own channels. |
| `POST /api/v1/me/notifications/channels` | Add channel (any of the 6 types). Triggers verification flow. |
| `PATCH /api/v1/me/notifications/channels/{id}` | Update label, quiet hours, alert-type filter, severity floor, enabled. |
| `POST /api/v1/me/notifications/channels/{id}/verify` | Submit verification token / code. |
| `POST /api/v1/me/notifications/channels/{id}/resend-verification` | Resend verification challenge. Rate-limited. |
| `DELETE /api/v1/me/notifications/channels/{id}` | Remove channel. |

Cross-user access denied (403) without information leakage (rule 46).

## Webhook delivery — the dispatch loop

```
Event → outbound_webhooks subscribed to event_type
     → ChannelRouter.route_workspace_event(envelope)
     → for each webhook:
          DLP scan_outbound (rule 34)
          residency check (rule 18)
          construct canonical payload (JCS)
          construct idempotency_key = uuid_v5(webhook.id, event.id)
          INSERT webhook_deliveries (status='pending', attempts=0)
          → webhook_deliverer.send(...)
          → on 2xx → status='delivered'
          → on retriable failure → status='failed', next_attempt_at=schedule[0]
          → on permanent 4xx → status='dead_letter', failure_reason='4xx_permanent'
```

## Retry worker

`webhook_retry_worker.py` runs every 30s (APScheduler):

```python
async def run_retry_scan() -> int:
    now = datetime.now(UTC)
    rows = await repo.list_due_deliveries(now=now, limit=200)
    for row in rows:
        if not await redis.acquire_lease(row.id, ttl=60):
            continue                                  # another worker has it
        try:
            await dispatch_with_retry(row)
        finally:
            await redis.release_lease(row.id)
    return len(rows)
```

`dispatch_with_retry` implements:
- If `attempts >= len(retry_policy.backoff_seconds)` OR `now - created_at > retry_policy.total_window_seconds`: dead-letter.
- Else: increment `attempts`, do HTTP attempt, evaluate response, set `next_attempt_at` to next backoff or terminal status.

## HMAC signing

```python
def build_signature_headers(
    *, webhook_id: UUID, payload: bytes, secret: bytes
) -> dict[str, str]:
    timestamp = str(int(time.time()))
    signed = f"{timestamp}.".encode() + payload
    digest = hmac.new(secret, signed, hashlib.sha256).hexdigest()
    return {
        "X-Musematic-Signature": f"sha256={digest}",
        "X-Musematic-Timestamp": timestamp,
        "X-Musematic-Idempotency-Key": str(idempotency_key),
        "Content-Type": "application/json",
        "User-Agent": f"musematic-webhook/{platform_version}",
    }
```

The same canonicalization is used consistently between sign-time and audit-time so receivers can verify and the audit chain entry is reproducible.

## Receiver verification (publishable contract)

Receivers verify by:

```python
def verify(headers, body, secret, *, replay_window=300):
    sig = headers["X-Musematic-Signature"].removeprefix("sha256=")
    ts = int(headers["X-Musematic-Timestamp"])
    if abs(time.time() - ts) > replay_window:
        raise ValueError("stale signature")
    expected = hmac.new(secret, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("bad signature")
```

This snippet ships in the platform documentation site (UPD-039) as the canonical receiver-side example.

## Failure classification

| HTTP outcome | Classification | Action |
|---|---|---|
| 2xx | success | status='delivered' |
| 3xx | redirect (max 3 hops, then permanent fail) | retry once with the new URL; if loop, dead-letter `failure_reason=redirect_loop` |
| 400, 401, 403, 410 | permanent client error | dead-letter `failure_reason=4xx_permanent` |
| 404 | permanent client error (URL not found) | dead-letter `failure_reason=4xx_permanent` |
| 408 | request timeout (transient) | retry per schedule |
| 429 | rate limit | honour `Retry-After` header if present, else schedule |
| 4xx (other) | permanent client error | dead-letter |
| 5xx | server error (transient) | retry per schedule |
| connection refused / DNS fail / TLS error | transient | retry per schedule |
| timeout (HTTP-level, default 10s) | transient | retry per schedule |

## Unit-test contract

- **OWH1** — POST creates webhook with vault-stored secret; response carries the secret exactly once and never again.
- **OWH2** — HTTP URL rejected at registration when `allow_http_webhooks=false`.
- **OWH3** — URL whose region violates residency rejected at registration.
- **OWH4** — successful delivery: HMAC signature verifiable with the registered secret; idempotency key is `uuid_v5(webhook.id, event.id)`.
- **OWH5** — same event delivered twice (forced by setting `next_attempt_at` past): both deliveries carry the same idempotency key.
- **OWH6** — receiver returns 503 then 503 then 200: 3 attempts; final status `delivered`; idempotency key stable.
- **OWH7** — receiver returns 400: 1 attempt; final status `dead_letter`, `failure_reason=4xx_permanent`.
- **OWH8** — receiver returns 429 with `Retry-After: 30`: next_attempt_at honours the header.
- **OWH9** — DLP `block` verdict: status `dead_letter`, `failure_reason=dlp_blocked`; no HTTP request made.
- **OWH10** — webhook deactivated mid-retry: pending row dead-letters with `failure_reason=webhook_inactive`.
- **OWH11** — secret rotation: rotate endpoint succeeds; rotate response does NOT contain new secret; subsequent delivery signs with the new secret.
- **OWH12** — retry-window exceeded: row dead-letters with `failure_reason=retry_window_exhausted` even if attempts < max_retries.
- **OWH13** — Redis lease prevents two workers dispatching the same row.
- **OWH14** — receiver-side verification snippet (shipped in docs) accepts a real platform delivery and rejects a tampered one.
